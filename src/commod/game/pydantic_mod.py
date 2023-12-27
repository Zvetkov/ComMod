import enum
import operator
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property, total_ordering
from pathlib import Path
from typing import Annotated, Any

from pathvalidate import sanitize_filename
from pydantic import BaseModel, DirectoryPath, Field, FilePath, StringConstraints, computed_field, field_validator, model_validator

from commod.game.data import SupportedGames
from commod.helpers.file_ops import SUPPORTED_IMG_TYPES, get_internal_file_path
from commod.helpers.parse_ops import parse_simple_relative_path, process_markdown, remove_substrings
from commod.localisation.service import KnownLangFlags, SupportedLanguages


@total_ordering
class Version(BaseModel):
    major: str = "0"
    minor: str = "0"
    patch: str = "0"
    identifier: str = ""

    @computed_field
    @property
    def is_numeric(self) -> bool:
        return all(part.isnumeric() for part in [self.major, self.minor, self.patch])

    class VersionPartCounts(enum.Enum):
        NO_VERSION = 0
        MAJOR_ONLY = 1
        SHORT_WITH_MINOR = 2
        FULL = 3
        FULL_WITH_ID = 4

    @classmethod
    def parse_from_str(cls, version_str: str) -> "Version":
        major = "0"
        minor = "0"
        patch = "0"
        identifier = ""

        identifier_index = version_str.find("-")
        has_minor_ver = "." in version_str

        if identifier_index != -1:
            identifier = version_str[identifier_index + 1:]
            numeric_version = version_str[:identifier_index]
        else:
            numeric_version = version_str

        if has_minor_ver:
            version_split = numeric_version.split(".")
            version_levels = len(version_split)
            if version_levels >= cls.VersionPartCounts.MAJOR_ONLY.value:
                major = version_split[0][:4]

            if version_levels >= cls.VersionPartCounts.SHORT_WITH_MINOR.value:
                minor = version_split[1][:4]

            if version_levels >= cls.VersionPartCounts.FULL.value:
                patch = version_split[2][:10]

            if version_levels >= cls.VersionPartCounts.FULL_WITH_ID.value:
                patch = "".join(version_split[2:])
        else:
            major = numeric_version
        return Version(major=major, minor=minor, patch=patch, identifier=identifier)


    def __str__(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.identifier:
            version += f"-{self.identifier}"
        return version

    def __repr__(self) -> str:
        return str(self)

    def _is_valid_operand(self, other: object) -> bool:
        return isinstance(other, Version)

    def __eq__(self, other: object) -> bool:
        if not self._is_valid_operand(other):
            return NotImplemented

        if self.is_numeric and other.is_numeric:
            return ((int(self.major), int(self.minor), int(self.patch))
                    ==
                    (int(other.major), int(other.minor), int(other.patch)))

        return ((self.major.lower(), self.minor.lower(), self.patch.lower())
                ==
                (self.major.lower(), self.minor.lower(), self.patch.lower()))

    def __lt__(self, other: "Version") -> bool:
        if not self._is_valid_operand(other):
            return NotImplemented

        if self.is_numeric and other.is_numeric:
            return ((int(self.major), int(self.minor), int(self.patch))
                    <
                    (int(other.major), int(other.minor), int(other.patch)))

        return ((self.major.lower(), self.minor.lower(), self.patch.lower())
                <
                (self.major.lower(), self.minor.lower(), self.patch.lower()))

class VersionConstrainStyle(enum.StrEnum):
    MIXED = enum.auto()
    RANGE = enum.auto()
    STRICT = enum.auto()

class Tags(enum.StrEnum):
    BUGFIX = enum.auto()
    GAMEPLAY = enum.auto()
    STORY = enum.auto()
    VISUAL = enum.auto()
    AUDIO = enum.auto()
    WEAPONS = enum.auto()
    VEHICLES = enum.auto()
    UI = enum.auto()
    BALANCE = enum.auto()
    HUMOR = enum.auto()
    UNCATEGORIZED = enum.auto()

    @classmethod
    def list_values(cls) -> list[str]:
        return [c.value for c in cls]

    @classmethod
    def list_names(cls) -> list[str]:
        return [c.name for c in cls]

class CompareOperator(enum.IntEnum):
    STRICT = 1
    MIXED = 2


@dataclass
class PatcherVersionRequirement:
    version_string: str

    @property
    def compare_operator(self) -> Callable:
        if self.version_string[:2] == ">=":
            return operator.ge
        if self.version_string[:2] == "<=":
            return operator.le
        if self.version_string[:1] == ">":
            return operator.gt
        if self.version_string[:1] == "<":
            return operator.lt
        if self.version_string[:1] == "=":
            return operator.eq
        # default "version" treated the same as ">=version":
        return operator.ge

    @property
    def version(self) -> str:
        return remove_substrings(self.version_string, (">", "<", "="))

class ModCompatConstrain(BaseModel):
    name: list[Annotated[str, StringConstraints(max_length=64)]]
    versions: list[str] | None = []
    optional_content: list[str] | None = []

    @field_validator("name", mode="before")
    @classmethod
    def convert_to_list(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [value]
        return value

    @computed_field
    @cached_property
    def constrain_style(self) -> VersionConstrainStyle:
        if self.versions:
            compare_ops: set[Callable] = set()
            for version_string in self.versions:
                version = version_string
                if version.startswith(">="):
                    compare_operation = operator.ge
                elif version.startswith("<="):
                    compare_operation = operator.le
                elif version.startswith(">"):
                    compare_operation = operator.gt
                elif version.startswith("<"):
                    compare_operation = operator.lt
                else:  # default "version" treated the same as "==version":
                    compare_operation = operator.eq

                for sign in (">", "<", "="):
                    version = version.replace(sign, "")
                compare_ops.add(compare_operation)

            list_ops = list(compare_ops)
            num_ops = len(list_ops)

            if num_ops == CompareOperator.STRICT and operator.eq in list_ops:
                return VersionConstrainStyle.STRICT

            if num_ops == CompareOperator.MIXED and operator.eq not in list_ops:
                first_op = list_ops[0]
                second_op = list_ops[1]

                range_format_1 = (
                    first_op in (operator.ge, operator.gt)
                    and
                    second_op in (operator.le, operator.lt))

                range_format_2 = (
                    first_op in (operator.lt, operator.lt)
                    and
                    second_op in (operator.ge, operator.gt))

                if range_format_1 or range_format_2:
                    return VersionConstrainStyle.RANGE

        return VersionConstrainStyle.MIXED


class PatcherOptions(BaseModel):
    gravity: Annotated[float, Field(ge=-100, le=-1)] | None = None
    skins_in_shop: Annotated[int, Field(ge=8, le=32)] | None = None
    blast_damage_friendly_fire: bool | None = None
    game_font: str | None = None

class ConfigOptions(BaseModel):
    first_level: str | None = Field(alias="firstLevel", default=None)
    dont_load_main_menu: str | None = Field(alias="DoNotLoadMainmenuLevel", default=None)
    weather_atmo_radius: str | None = Field(alias="weather_AtmoRadius", default=None)
    weather_config_file: str | None = Field(alias="weather_ConfigFile", default=None)

class InstallSettings(BaseModel):
    name: Annotated[str, StringConstraints(max_length=64)]
    description: Annotated[str, StringConstraints(max_length=1024)]

RESERVED_CONTENT_NAMES = ("base", "name", "display_name", "build", "version")
class OptionalContent(BaseModel):
    # required
    name: Annotated[str, StringConstraints(max_length=64)]
    display_name: Annotated[str, StringConstraints(max_length=64)]
    description: Annotated[str, StringConstraints(max_length=1024)]

    # have defaults
    default_option: str | None = None
    forced_option: bool = False
    install_settings: list[InstallSettings] = []
    patcher_options: PatcherOptions | None = None

    # file structure
    data_dirs: list[str] | list[DirectoryPath] = []

    @model_validator(mode="after")
    def default_is_valid(self) -> "OptionalContent":
        if self.install_settings:
            valid_option_names = [opt.name for opt in self.install_settings]
            valid_option_names.append("skip")
            if self.default_option and self.default_option not in valid_option_names:
                raise ValueError("Only 'skip' or names present in install settings are allowed")
        elif self.default_option and self.default_option not in ("skip", "install"):
            raise ValueError("Only 'skip' or 'install' is allowed for simple options")
        return self

    @field_validator("data_dirs", mode="after")
    @classmethod
    def parse_relative_paths(cls, value: list[str]) -> list[str]:
        return [parse_simple_relative_path(path) for path in value]

    @field_validator("name")
    @classmethod
    def name_is_not_reserved(cls, value: str) -> str:
        if value.lower() in RESERVED_CONTENT_NAMES:
            raise ValueError("Reserved name used for content name")
        return value

    @field_validator("install_settings")
    @classmethod
    def more_than_one_install_setting(cls, value: list[InstallSettings]) -> list[InstallSettings]:
        if value and len(value) == 1:
            raise ValueError("Multiple install settings need to exists for complex optional content")
        return value

    def model_post_init(self, __context: Any) -> None:
        if not self.data_dirs:
            self.data_dirs = [f"{self.name}/data"]

class Screenshot(BaseModel):
    img: str
    text: Annotated[str, StringConstraints(max_length=256)] = ""
    compare: str = ""

    screen_path: FilePath | None = None
    compare_path: FilePath | None = None

class Mod(BaseModel):
    # base directory where manifest is located
    mod_files_root: DirectoryPath
    # primary required
    name: Annotated[str, StringConstraints(max_length=64)]
    display_name: Annotated[str, StringConstraints(max_length=64)]
    description: Annotated[str, StringConstraints(max_length=2048)]
    authors: Annotated[str, StringConstraints(max_length=256)]
    version: Version
    build: Annotated[str, StringConstraints(min_length=6, max_length=7, strip_whitespace=True)]

    # primary with defaults
    installment: SupportedGames = SupportedGames.EXMACHINA
    language: Annotated[str, StringConstraints(max_length=2, to_lower=True)] = SupportedLanguages.RU.value
    patcher_version_requirement: str = ">=1.10"
    optional_content: list[OptionalContent] = []

    #compatibility
    prerequisites: list[ModCompatConstrain] = []
    incompatible: list[ModCompatConstrain] = []
    compatible_minor_versions: bool = False
    compatible_patch_versions: bool = False
    strict_requirements: bool = True
    safe_reinstall_options: bool = False


    # secondary
    release_date: Annotated[str, StringConstraints(max_length=32, strip_whitespace=True)] = ""
    url: Annotated[str, StringConstraints(max_length=128, strip_whitespace=True)] = ""
    trailer_url: Annotated[str, StringConstraints(max_length=128, strip_whitespace=True)] = ""
    tags: list[Tags] = [Tags.UNCATEGORIZED]
    logo: str = ""
    install_banner: str = ""
    screenshots: list[Screenshot] = []
    change_log: str = ""
    other_info: str = ""

    # patcher advanced functionality
    patcher_options: PatcherOptions | None = None
    config_options: ConfigOptions | None = None

    # child variants \ translations
    translations: list[str] = []
    translations_loaded: dict[str, "Mod"] = {}
    variants: list[str] = []
    variants_loaded: dict[str, "Mod"] = {}
    is_translation: bool = False
    is_variant: bool = False

    # mod files related
    no_base_content: bool = False
    data_dirs: list[str] | list[DirectoryPath] = []
    bin_dirs: list[str] | list[DirectoryPath] = []
    options_base_dir: str = ""

    @field_validator("version", mode="before")
    @classmethod
    def convert_to_version(cls, value: str) -> Version:
        return Version.parse_from_str(value)

    @field_validator("data_dirs", "bin_dirs", mode="after")
    @classmethod
    def parse_relative_paths(cls, value: list[str]) -> list[str]:
        return [parse_simple_relative_path(path) for path in value]

    @field_validator("options_base_dir", mode="after")
    @classmethod
    def parse_relative_path(cls, value: str) -> str:
        return parse_simple_relative_path(value)

    @computed_field
    @cached_property
    def id_str(self) -> str:
        return remove_substrings(
            sanitize_filename(
                self.name
                + str(self.version).replace(".", "")
                + self.build
                + f"{self.language}"
                + f"[{self.installment.replace('exmachina', 'em')}]"
                ), (" ", "_", "-"))

    @computed_field
    @property
    def vanilla_mod(self) -> bool:
        return not self.prerequisites

    @computed_field
    @property
    def developer_title(self) -> str:
        return "authors" if ", " in self.authors else "author"

    @computed_field
    @property
    def flag(self) -> str:
        if self.language in KnownLangFlags.list_values():
            return KnownLangFlags(self.language).value
        return KnownLangFlags.other.value

    @computed_field
    @cached_property
    def individual_require_status(self) -> list:
        # TODO: implement if actually required
        raise NotImplementedError

    @computed_field
    @cached_property
    def individual_incomp_status(self) -> list:
        # TODO: implement if actually required
        raise NotImplementedError

    def add_mod_translation(self, lang_alias: str, mod_tr: "Mod") -> None:
        if self.is_translation:
            raise ValueError("Translations can't have child translations")
        if self.is_variant:
            raise ValueError("Translations can't have child variants")
        if mod_tr.installment != self.installment:
            raise ValueError("Game installment mismatch, mod and translation should specify same game")
        if mod_tr.name != self.name:
            raise ValueError("Service name mismatch, service names for mod and translation should match")
        if mod_tr.version != self.version:
            raise ValueError("Version mismatch, version for mod and translation should match")
        if mod_tr.language == self.language:
            raise ValueError("Translation language is the same as the language of base mod")
        if sorted(mod_tr.tags) != sorted(self.tags):
            raise ValueError("Tags mismatch between mod and translation")
        self.translations_loaded[lang_alias] = mod_tr

    def add_mod_variant(self, variant_alias: str, mod_vr: "Mod") -> None:
        if self.is_variant:
            raise ValueError("Mod variants can't have child variants")
        if mod_vr.installment != self.installment:
            raise ValueError("Game installment mismatch, mod and it's variants should specify same game")
        if mod_vr.language != self.language:
            raise ValueError("Mod variant language is different from base mod")
        self.variants_loaded[variant_alias] = mod_vr

    @computed_field
    @property
    def change_log_path(self) -> Path | None:
        data_path = self.mod_files_root / self.change_log
        if data_path.exists() and data_path.suffix.lower() == ".md":
            return data_path
        return None

    @computed_field
    @cached_property
    def change_log_content(self) -> str:
        if self.change_log_path and self.change_log_path.exists():
            with open(self.change_log_path, encoding="utf-8") as fh:
                md = fh.read()
                return process_markdown(md)
        else:
            return ""

    @computed_field
    @property
    def other_info_path(self) -> Path | None:
        data_path = self.mod_files_root / self.change_log
        if data_path.exists() and data_path.suffix.lower() == ".md":
            return data_path
        return None

    @computed_field
    @cached_property
    def other_info_content(self) -> str:
        if self.other_info_path and self.other_info_path.exists():
            with open(self.other_info_path, encoding="utf-8") as fh:
                md = fh.read()
                return process_markdown(md)
        return ""

    @computed_field
    @property
    def logo_path(self) -> Path:
        if self.logo:
            data_path = self.mod_files_root / self.logo
            if data_path.exists() and data_path.suffix.lower() in SUPPORTED_IMG_TYPES:
                return data_path
        return get_internal_file_path("assets/no_logo.png")

    @computed_field
    @property
    def banner_path(self) -> Path | None:
        if self.install_banner:
            data_path = self.mod_files_root / self.install_banner
            if data_path.exists() and data_path.suffix.lower() in SUPPORTED_IMG_TYPES:
                return data_path
        return None

    @model_validator(mode="after")
    def load_file_paths(self) -> "Mod":
        for screen in self.screenshots:
            screen.screen_path = self.mod_files_root / screen.img
            if screen.compare:
                screen.compare_path = self.mod_files_root / screen.compare

        resolved_data_paths = [self.mod_files_root / one_dir for one_dir in self.data_dirs]
        for path in resolved_data_paths:
            if not path.is_dir():
                raise ValueError("Base data path doesn't exists", path)
        self.data_dirs = resolved_data_paths

        resolved_bin_paths = [self.mod_files_root / one_dir for one_dir in self.bin_dirs]
        for path in resolved_bin_paths:
            if not path.is_dir():
                raise ValueError("Base bin path doesn't exists", path)
        self.bin_dirs = resolved_bin_paths

        for item in self.optional_content:
            resolved_item_paths = [self.mod_files_root / self.options_base_dir / one_dir
                                   for one_dir in item.data_dirs]
            for path in resolved_item_paths:
                if not path.is_dir():
                    raise ValueError("Data path doesn't exists for optional content", path)
            item.data_dirs = resolved_item_paths

        return self


    def model_post_init(self, __context: Any) -> None:
        # higher order version part dictates compatibility
        if self.compatible_minor_versions:
            self.compatible_patch_versions = True

        if self.no_base_content:
            self.data_dirs.clear()
        # loading default or backwards compat fallbacks
        elif not self.data_dirs:
            if self.name == "community_patch":
                self.data_dirs = ["patch"]
            elif self.name == "community_remaster":
                self.data_dirs = ["patch", "remaster/data"]
            else:
                self.data_dirs = ["data"]

        if not self.bin_dirs and self.name in ("community_patch", "community_remaster"):
            self.bin_dirs = ["libs"]

        # self.load_mod_files()

@dataclass
class ModFamily:
    base: Mod
    translations: list[Mod]
    variations: list[Mod]
