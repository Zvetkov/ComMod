# ruff: noqa: SLF001

import logging
import operator
import os
from collections.abc import Awaitable
from datetime import datetime
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any

# from zipfile import ZipInfo
from pathvalidate import sanitize_filename

# from py7zr import py7zr
from pydantic import (
    BaseModel,
    DirectoryPath,
    Field,
    FilePath,
    StringConstraints,
    computed_field,
    field_validator,
    model_validator,
)

from commod.game.data import (
    COMPATCH_GITHUB,
    DEM_DISCORD,
    OWN_VERSION,
    WIKI_COMREM,
    SupportedGames,
)
from commod.game.mod_auxiliary import (
    RESERVED_CONTENT_NAMES,
    ConfigOptions,
    Incompatibility,
    ManagerVersionRequirement,
    OptionalContent,
    PatcherOptions,
    Prerequisite,
    Screenshot,
    Tags,
    Version,
)
from commod.helpers.errors import ModFileInstallationError
from commod.helpers.file_ops import (
    SUPPORTED_IMG_TYPES,
    copy_from_to_async_fast,
    get_internal_file_path,
    read_yaml,
)
from commod.helpers.parse_ops import parse_simple_relative_path, process_markdown, remove_substrings
from commod.localisation.service import KnownLangFlags, SupportedLanguages, is_known_lang, tr, tr_lang

logger = logging.getLogger("dem")
COMPATCH_REM = {"community_patch", "community_remaster"}

class Mod(BaseModel):
    # base directory where manifest is located
    manifest_root: DirectoryPath | Path
    # primary required
    name: Annotated[str, StringConstraints(max_length=64)]
    display_name: Annotated[str, StringConstraints(max_length=64)]
    description: Annotated[str, StringConstraints(max_length=2048)] = Field(repr=False)
    authors: Annotated[str, StringConstraints(max_length=256)] = Field(repr=False)
    version: Version = Field(repr=False)
    build: Annotated[str, StringConstraints(min_length=1, max_length=7,
                                            strip_whitespace=True)] = Field(repr=False)

    # primary with defaults
    installment: SupportedGames = SupportedGames.EXMACHINA
    language: Annotated[str, StringConstraints(min_length=2, max_length=3, to_lower=True)] = \
        SupportedLanguages.RU.value
    patcher_version_requirement: str | list[str] | list[ManagerVersionRequirement] = \
        Field(default=[">=1.10"], repr=False)
    optional_content: list[OptionalContent] = Field(default=[], repr=False)

    # compatibility
    prerequisites: list[Prerequisite] = Field(default=[], repr=False)
    incompatible: list[Incompatibility] = Field(default=[], repr=False)
    compatible_minor_versions: bool = Field(default=False, repr=False)
    compatible_patch_versions: bool = Field(default=False, repr=False)
    strict_requirements: bool = Field(default=True, repr=False)
    safe_reinstall_options: bool = Field(default=False, repr=False)


    # TODO: replace with computed fields, probably cached based on hashable insallation config,
    # ugly solution copied from previous Mod implementation for the time being
    compatible: bool = Field(default=False, repr=False)
    compatible_err: list[str] = Field(default=[], repr=False)

    prevalidated: bool = Field(default=False, repr=False)
    prevalidated_err: list[str] = Field(default=[], repr=False)

    is_reinstall: bool = Field(default=False, repr=False)
    can_be_reinstalled: bool = Field(default=False, repr=False)
    reinstall_warning: str | None = Field(default=None, repr=False)
    existing_version: str | None = Field(default=None, repr=False)

    installment_compatible: bool = Field(default=False, repr=False)

    can_install: bool = Field(default=False, repr=False)

    individual_require_status: list[tuple[Prerequisite, bool, list[str]]] = Field(default=[], repr=False)
    individual_incomp_status: list[tuple[Incompatibility, bool, list[str]]] = Field(default=[], repr=False)
    # end of ugly block

    # secondary
    release_date: Annotated[str, StringConstraints(max_length=32, strip_whitespace=True)] = \
        Field(default="", repr=False)
    url: Annotated[str, StringConstraints(max_length=128, strip_whitespace=True)] = \
        Field(default="", validation_alias="link", repr=False)
    trailer_url: Annotated[str, StringConstraints(max_length=128, strip_whitespace=True)] = \
        Field(default="", repr=False)
    tags: list[Tags] = Field(default=[Tags.UNCATEGORIZED], repr=False)
    logo: str = Field(default="", repr=False)
    install_banner: str = Field(default="", repr=False)
    screenshots: list[Screenshot] = Field(default=[], repr=False)
    _screen_option_names: dict[str, str] = {"base": ""}
    change_log: str = Field(default="", repr=False)
    other_info: str = Field(default="", repr=False)

    # patcher advanced functionality
    patcher_options: PatcherOptions | None = Field(default=None, repr=False)
    config_options: ConfigOptions | None = Field(default=None, repr=False)

    # child variants \ translations
    translations: list[str] = Field(default=[], repr=False)
    _translations_loaded: dict[str, "Mod"] = {}
    variants: list[str] = Field(default=[], repr=False)
    _variants_loaded: dict[str, "Mod"] = {}
    is_translation: bool = Field(default=False, repr=False)
    is_variant: bool = Field(default=False, repr=False)
    variant_alias: str = Field(default="", repr=False)
    _sister_variants: dict[str, "Mod"] = {}

    # mod files related
    no_base_content: bool = Field(default=False, repr=False)
    raw_data_dirs: list[str] = Field(default=[], validation_alias="data_dirs", repr=False)
    raw_bin_dirs: list[str] = Field(default=[], validation_alias="bin_dirs", repr=False)
    raw_options_base_dir: str = Field(default="", validation_alias="options_base_dir", repr=False)
    archive_file_list: Any | None = Field(default=None, repr=False) # list[ZipInfo] | py7zr.ArchiveFileList | None

    @field_validator("name", "description", mode="after")
    @classmethod
    def remove_newline_space(cls, value: str) -> str:
        return value.strip(" \n")

    @field_validator("version", mode="before")
    @classmethod
    def convert_to_version(cls, value: str) -> Version:
        return Version.parse_from_str(value)

    @field_validator("patcher_version_requirement", mode="before")
    @classmethod
    def convert_to_parsed_version(
            cls, value: str | list | ManagerVersionRequirement) -> ManagerVersionRequirement:
        if isinstance(value, str):
            return [ManagerVersionRequirement(value)]
        if isinstance(value, ManagerVersionRequirement):
            return [value]
        if isinstance(value, list):
            return [ManagerVersionRequirement(single_ver) for single_ver in value]
        return value

    @field_validator("raw_data_dirs", "raw_bin_dirs", mode="after")
    @classmethod
    def parse_relative_paths(cls, value: list[str]) -> list[str]:
        return [parse_simple_relative_path(path) for path in value]

    @field_validator("options_base_dir", mode="after")
    @classmethod
    def parse_relative_path(cls, value: str) -> str:
        return parse_simple_relative_path(value)

    @computed_field(repr=False)
    @property
    def sister_variants(self) -> dict[str, "Mod"]:
        return self._sister_variants

    @computed_field(repr=False)
    @cached_property
    def id_variant(self) -> str:
        return remove_substrings(
            sanitize_filename(
                self.name
                + str(self.version).replace(".", "")
                + self.build
                + f"[{self.installment.replace('exmachina', 'em')}]"
                ), (" ", "_", "-"))

    @computed_field(repr=False)
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

    @computed_field(repr=False)
    @property
    def vanilla_mod(self) -> bool:
        # legacy builds of comrem had compatch as prerequisite
        return not self.prerequisites or self.name in ("community_remaster", "community_patch")

    @computed_field(repr=True)
    @property
    def build_ver(self) -> str:
        return f"{self.version!r} [{self.build}]"

    @computed_field(repr=False)
    @property
    def developer_title(self) -> str:
        return "authors" if ", " in self.authors else "author"

    @computed_field(repr=False)
    @cached_property
    def flag(self) -> str:
        if self.known_language:
            return os.path.join(*KnownLangFlags[self.language].value.split("\\"))
        return os.path.join(*KnownLangFlags.other.value.split("\\"))


    @classmethod
    def is_mod_manager_too_new(cls, commod_version: str,
                             version_requirements: list[ManagerVersionRequirement]) -> bool:
        result = True
        for version_requirement in version_requirements:
            compare_operation = version_requirement.compare_operator
            version_current = Version.parse_from_str(commod_version)

            # TODO: check, for some reason previously op check was only valid if comp_op is operator.eq
            if (version_requirement.version < version_current
                and compare_operation in (operator.eq, operator.le, operator.lt)):
               continue
            result &= False
        return result

    @computed_field(repr=False)
    @cached_property
    def mod_manager_too_new(self) -> bool:
        return Mod.is_mod_manager_too_new(OWN_VERSION, self.patcher_version_requirement)

    @classmethod
    def is_commod_compatible(cls, commod_version: str,
                             version_requirements: list[ManagerVersionRequirement]) -> bool:
        compatible = True
        for version_requirement in version_requirements:
            compare_operation = version_requirement.compare_operator
            version_current = Version.parse_from_str(commod_version)

            compatible &= compare_operation(version_current, version_requirement.version)
        return compatible

    @computed_field(repr=False)
    @cached_property
    def commod_compatible(self) -> bool:
        return Mod.is_commod_compatible(OWN_VERSION, self.patcher_version_requirement)

    @classmethod
    def get_commod_compatible_err(
         cls, name: str, display_name: str, version_requirement: list[ManagerVersionRequirement],
         commod_compatible: bool, mod_manager_too_new: bool) -> str:
        if not commod_compatible:
            str_vers = [ver.version_string for ver in version_requirement]
            logger.warning(f"{display_name} manifest asks for another mod manager version. "
                           f"Required: {str_vers}, "
                           f"available: {OWN_VERSION}")
            and_word = f" {tr('and')} "

            error_msg = (tr("usupported_patcher_version",
                            content_name=display_name,
                            required_version=and_word.join(str_vers),
                            current_version=OWN_VERSION,
                            github_url=COMPATCH_GITHUB))

            # TODO: better to replace with showing error msg box when trying to load mod that is too new
            if mod_manager_too_new and name == "community_remaster":
                error_msg += f"\n\n{tr('check_for_a_new_version')}\n\n"
                error_msg += tr("demteam_links",
                                discord_url=DEM_DISCORD,
                                deuswiki_url=WIKI_COMREM,
                                github_url=COMPATCH_GITHUB) + "\n"
            return error_msg
        return ""

    @computed_field(repr=False)
    @property
    def commod_compatible_err(self) -> str:
        return Mod.get_commod_compatible_err(
            self.name, self.display_name, self.patcher_version_requirement,
            self.commod_compatible, self.mod_manager_too_new)

    # @computed_field
    # @cached_property
    # def individual_require_status(self) -> list:
    #     # TODO: implement if actually required
    #     raise NotImplementedError


    # @computed_field
    # @cached_property
    # def individual_incomp_status(self) -> list:
    #     # TODO: implement if actually required
    #     raise NotImplementedError

    @computed_field(repr=False)
    @property
    def translations_loaded(self) -> dict[str, "Mod"]:
        return self._translations_loaded

    @computed_field(repr=False)
    @property
    def variants_loaded(self) -> dict[str, "Mod"]:
        return self._variants_loaded

    def add_mod_translation(self, mod_tr: "Mod") -> None:
        if self.is_translation:
            raise ValueError("Translations can't have child translations")
        if mod_tr.installment != self.installment:
            raise ValueError("Game installment mismatch, mod and translation should specify same game: "
                             f"{mod_tr.installment=} != {self.installment=}")
        if mod_tr.name != self.name:
            raise ValueError("Service name mismatch, service names for mod and translation should match: "
                             f"{mod_tr.name=} != {self.name=}")
        if mod_tr.version != self.version:
            raise ValueError("Version mismatch, version for mod and translation should match: "
                             f"{mod_tr.version=} != {self.version=}")
        if mod_tr.build != self.build:
            raise ValueError("Build mismatch, build for mod and translation should match: "
                             f"{mod_tr.build=} != {self.build=}")
        if mod_tr.language == self.language:
            raise ValueError("Translation language is the same as the language of base mod: "
                             f"{mod_tr.language=} == {self.language=}")
        if ({str(ver.version) for ver in mod_tr.patcher_version_requirement}
            != {str(ver.version) for ver in self.patcher_version_requirement}):
            raise ValueError("Patcher version requirement mismatch, mod and it's translations "
                             "should specify same requirements: "
                             f"{self.patcher_version_requirement=} != {mod_tr.patcher_version_requirement=}")
        if sorted(mod_tr.tags) != sorted(self.tags):
            raise ValueError("Tags mismatch between mod and translation: "
                             f"{mod_tr.tags=} != {self.tags=}")
        mod_tr.is_translation = True
        self._translations_loaded[mod_tr.language] = mod_tr

    def add_mod_variant(self,  mod_vr: "Mod") -> None:
        if self.is_variant:
            raise ValueError("Mod variants can't have child variants")
        if self.is_translation:
            raise ValueError("Translations can't have child variants")
        if mod_vr.version != self.version:
            raise ValueError("Version mismatch, version for mod and variant should match: "
                             f"{mod_vr.version=} != {self.version=}")
        if mod_vr.build != self.build:
            raise ValueError("Build mismatch, build for mod and variant should match: "
                             f"{mod_vr.build=} != {self.build=}")
        if mod_vr.name == self.name or mod_vr.display_name == self.display_name:
            raise ValueError(
                "Mod variants can't have same name or display name as base mods: "
                f"{self.name=} == {mod_vr.name=} OR {self.display_name=} == {mod_vr.display_name=}")
        if mod_vr.installment != self.installment:
            raise ValueError("Game installment mismatch, mod and it's variants should specify same game: "
                             f"{self.installment=} != {mod_vr.installment=}")
        if ({str(ver.version) for ver in mod_vr.patcher_version_requirement}
            != {str(ver.version) for ver in self.patcher_version_requirement}):
            raise ValueError("Patcher version requirement mismatch, mod and it's variants "
                             "should specify same requirements: "
                             f"{self.patcher_version_requirement=} != {mod_vr.patcher_version_requirement=}")
        if mod_vr.language != self.language:
            raise ValueError("Mod variant language is different from base mod: "
                             f"{self.language=} != {mod_vr.language=}")
        self._variants_loaded[mod_vr.name] = mod_vr

    @computed_field(repr=False)
    @property
    def mod_files_root(self) -> DirectoryPath:
        # legacy compatch/comrem manifest was located inside "remaster" dir, not in mod root
        if (self.name in ("community_patch", "community_remaster")
            and not self.raw_data_dirs
            and self.manifest_root.stem == "remaster"):
                return self.manifest_root.parent
        return self.manifest_root

    @computed_field(repr=False)
    @property
    def options_base_dir(self) -> FilePath:
        if (self.name == "community_remaster" and not self.raw_options_base_dir):
            return "remaster"
        return self.raw_options_base_dir


    @computed_field(repr=False)
    @property
    def change_log_path(self) -> Path | None:
        data_path = self.manifest_root / self.change_log
        if data_path.exists() and data_path.suffix.lower() == ".md":
            return data_path
        return None

    @computed_field(repr=False)
    @property
    def change_log_content(self) -> str:
        try:
            if self.change_log_path and self.change_log_path.exists():
                with open(self.change_log_path, encoding="utf-8") as fh:
                    md = fh.read()
                    return process_markdown(md)
        except UnicodeDecodeError:
            logger.error(f"Wasn't able to decode content of {self.change_log_path}, need to be utf-8 text")
            return ""
        return ""

    @computed_field(repr=False)
    @property
    def other_info_path(self) -> Path | None:
        data_path = self.manifest_root / self.other_info
        if data_path.exists() and data_path.suffix.lower() == ".md":
            return data_path
        return None

    @computed_field(repr=False)
    @property
    def other_info_content(self) -> str:
        try:
            if self.other_info_path and self.other_info_path.exists():
                with open(self.other_info_path, encoding="utf-8") as fh:
                    md = fh.read()
                    return process_markdown(md)
        except UnicodeDecodeError:
            logger.error(f"Wasn't able to decode content of {self.other_info_path}, need to be utf-8 text")
            return ""
        return ""

    @computed_field(repr=False)
    @cached_property
    def known_language(self) -> bool:
        return is_known_lang(self.language)

    @computed_field(repr=False)
    @cached_property
    def lang_label(self) -> str:
        if self.known_language:
            return tr(self.language)
        return self.language

    @computed_field(repr=False)
    @cached_property
    def logo_path(self) -> Path:
        if self.logo:
            full_logo_path = self.manifest_root / self.logo
            if full_logo_path.exists() and full_logo_path.suffix.lower() in SUPPORTED_IMG_TYPES:
                return full_logo_path
        if self.name == "community_patch":
            return get_internal_file_path("assets/compatch_logo.png")
        return get_internal_file_path("assets/no_logo.png")

    @computed_field(repr=False)
    @cached_property
    def banner_path(self) -> Path | None:
        if self.install_banner:
            full_banner_path = self.manifest_root / self.install_banner
            if full_banner_path.exists() and full_banner_path.suffix.lower() in SUPPORTED_IMG_TYPES:
                return full_banner_path
        if self.name == "community_patch":
            return get_internal_file_path("assets/compatch_logo.png")
        return None

    @computed_field(repr=False)
    @cached_property
    def data_dirs(self) -> list[Path]:
        if self.no_base_content:
            return []
        if not self.raw_data_dirs:
            if self.name == "community_patch":
                return [Path("patch")]
            if self.name == "community_remaster":
                return [Path("patch"), Path("remaster/data")]
            return [Path("data")]

        return [Path(data_dir) for data_dir in self.raw_data_dirs]

    @computed_field(repr=False)
    @cached_property
    def bin_dirs(self) -> list[Path]:
        if not self.raw_bin_dirs and self.name in ("community_patch", "community_remaster"):
            return [Path("libs")]

        return [Path(bin_dir) for bin_dir in self.raw_bin_dirs]

    @computed_field(repr=False)
    @property
    def options_dict(self) -> dict[str, OptionalContent]:
        return {cont.name: cont for cont in self.optional_content}

    @computed_field(repr=False)
    @property
    def screen_option_names(self) -> dict[str, str]:
        return self._screen_option_names

    @model_validator(mode="after")
    def load_file_paths(self) -> "Mod":
        archive_files: list[str] = []
        if self.archive_file_list:
            archive_files = [file.filename.rstrip("/") for file in self.archive_file_list]

        for screen in self.screenshots:
            screen._screen_path = self.manifest_root / screen.img
            if screen.compare:
                screen._compare_path = self.manifest_root / screen.compare

            if archive_files:
                if str(screen._screen_path).replace("\\", "/") not in archive_files:
                    # screen doesn't exist in archive, probably can be ignored
                    logger.warning("Screen doesn't exist but specified in manifest: %s",
                                   screen._screen_path)
            else:
                if not screen.screen_path.exists():
                    # screen doesn't exist, probably can be ignored
                    screen.failed_validation = True
                    logger.warning("Screen doesn't exist but specified in manifest, ignoring: %s",
                                   screen._screen_path)
                if screen.compare_path is not None and not screen.compare_path.exists():
                    screen.failed_validation = True
                    logger.warning("Compare screen doesn't exist but specified in manifest, ignoring: %s",
                                   screen._compare_path)

        self.screenshots = [screen for screen in self.screenshots if not screen.failed_validation]

        screen_options = {screen.option_name for screen in self.screenshots}
        for screen_opt_name in screen_options:
            if screen_opt_name != "base":
                screen_opt_name_parts = screen_opt_name.split("/")
                screen_opt_obj = self.options_dict.get(screen_opt_name_parts[0])
                if screen_opt_obj is None:
                    raise AssertionError("Invalid 'option_name' specified for screen", screen_opt_name)
                if len(screen_opt_name_parts) == 1:
                    if screen_opt_obj.display_name:
                        display_name = screen_opt_obj.display_name
                    else:
                        display_name = screen_opt_obj.name
                    self._screen_option_names[screen_opt_name] = display_name
                elif len(screen_opt_name_parts) == 2:
                    install_sett_obj = screen_opt_obj.install_settings_dict.get(screen_opt_name_parts[1])
                    if install_sett_obj is None:
                        raise AssertionError("Invalid 'option_name' specified for screen", screen_opt_name)
                    if install_sett_obj.display_name:
                        display_name = (f"{install_sett_obj.display_name} "
                                        f"({screen_opt_obj.display_name or screen_opt_obj.name})")
                    else:
                        display_name = (f"{install_sett_obj.name} "
                                        f"({screen_opt_obj.display_name or screen_opt_obj.name})")
                    self._screen_option_names[screen_opt_name] = display_name
                else:
                    raise AssertionError("Invalid 'option_name' specified for screen", screen_opt_name)


        if self.no_base_content and self.raw_data_dirs:
            raise AssertionError("no_base_content mods can't specify data_dirs for root mod!")

        for data_path in self.data_dirs:
            resolved_data_path = self.mod_files_root / data_path

            if archive_files:
                data_arch_path = str(resolved_data_path).replace("\\", "/")
                if (data_arch_path not in archive_files and
                    not any(file_path.startswith(data_arch_path) for file_path in archive_files)):
                    # second partial match check for archives that don't list root directories
                    raise ValueError("Base data path wasn't found in archive", data_arch_path)
            elif not resolved_data_path.is_dir():
                raise ValueError("Base data path doesn't exists", resolved_data_path)

        for bin_path in self.bin_dirs:
            resolved_bin_path = self.mod_files_root / bin_path

            if archive_files:
                bin_arch_path = str(resolved_bin_path).replace("\\", "/")
                if (bin_arch_path not in archive_files and
                    not any(file_path.startswith(bin_arch_path) for file_path in archive_files)):
                    raise ValueError("Base bin path wasn't found in archive", bin_arch_path)
            elif not resolved_bin_path.is_dir():
                raise ValueError("Base bin path doesn't exists", resolved_bin_path)

        for item in self.optional_content:
            resolved_item_paths = [self.mod_files_root / self.options_base_dir / one_dir
                                   for one_dir in item.data_dirs]
            for resolved_opt_path in resolved_item_paths:
                if item.install_settings:
                    for custom_setting in item.install_settings:
                        for custom_data_dir in custom_setting.data_dirs:
                            path_to_check = resolved_opt_path / custom_data_dir
                            if archive_files:
                                path_to_check = str(resolved_opt_path).replace("\\", "/")
                                if (path_to_check not in archive_files and
                                    not any(file_path.startswith(path_to_check) for file_path in archive_files)):
                                    raise ValueError("Data path for optional content wasn't found in archive",
                                                     path_to_check)
                            elif not path_to_check.is_dir():
                                raise ValueError("Data path doesn't exists for optional content", path_to_check)
                else:
                    path_to_check = resolved_opt_path / "data"
                    if archive_files:
                        path_to_check = str(resolved_opt_path).replace("\\", "/")
                        if (path_to_check not in archive_files and
                            not any(file_path.startswith(path_to_check) for file_path in archive_files)):
                            raise ValueError("Data path for optional content wasn't found in archive",
                                             path_to_check)
                    elif not path_to_check.is_dir():
                        raise ValueError("Data path doesn't exists for optional content", path_to_check)
            item.data_dirs = resolved_item_paths
        return self

    @model_validator(mode="after")
    def load_variants(self) -> "Mod":
        if self.is_variant and self.variants:
            raise AssertionError("Mod variants can't have child variants")

        if self.is_translation and self.variants:
            raise AssertionError("Mod translations can't specify variants, do the oposite")

        if self.archive_file_list:
            archive_files = [file.filename.rstrip("/") for file in self.archive_file_list]
        else:
            archive_files = None

        for variant_alias in self.variants:
            manifest_name = f"manifest_{variant_alias}_{self.language}.yaml"
            variant_manifest_path = Path(self.manifest_root, f"manifest_{variant_alias}_{self.language}.yaml")

            if archive_files:
                if str(variant_manifest_path).replace("\\", "/") not in archive_files:
                    raise AssertionError(
                        f"Manifest for variant not present in the archive: {manifest_name}")
                return self

            if not variant_manifest_path.exists():
                raise ValueError(f"Variant '{variant_alias}' specified but manifest for it is missing! "
                                 f"(Mod: {self.name})")
            yaml_config = read_yaml(variant_manifest_path)
            if yaml_config is None:
                raise ValueError("Mod variant manifest is not a valid yaml file")

            yaml_config["build"] = self.build
            yaml_config["version"] = str(self.version)
            mod_vr = Mod(**yaml_config, is_variant=True, variant_alias=variant_alias,
                         manifest_root=self.manifest_root)
            self.add_mod_variant(mod_vr)

        if (self.name == "community_remaster"
           and not self.is_translation
           and not self.variants):
            self.prerequisites = []
            compatch_fallback = self.model_copy(update={
                "name": "community_patch",
                "display_name": "Community Patch",
                "description": tr_lang("compatch_description", self.language),
                "optional_content": [],
                "screenshots": [],
                "logo": "",
                "install_banner": "",
                "patcher_options": PatcherOptions(skins_in_shop=8, gravity=-19.62,
                                                  blast_damage_friendly_fire=False),
                "translations": [],
                "prerequisites": []
            })
            compatch_fallback._translations_loaded = {compatch_fallback.language: compatch_fallback}
            compatch_fallback._variants_loaded = {compatch_fallback.name: compatch_fallback}
            compatch_fallback.is_variant = True
            self.variants.append("patch")
            self.add_mod_variant(compatch_fallback)

        # for variant in self.variants_loaded.values():
        #     variant._sister_variants = {
        #         sis_var.name: sis_var
        #         for sis_var in self.variants_loaded.values()
        #         if sis_var.name != variant.name}
        return self

    @model_validator(mode="after")
    def load_translations(self) -> "Mod":
        if self.is_translation and self.translations:
            raise AssertionError("Translations can't have child translations")

        if self.archive_file_list:
            archive_files = [file.filename.rstrip("/") for file in self.archive_file_list]
        else:
            archive_files = None

        for translation_alias in self.translations:
            if self.is_variant:
                manifest_name = f"manifest_{self.variant_alias}_{translation_alias}.yaml"
            else:
                manifest_name = f"manifest_{translation_alias}.yaml"
            translation_manifest_path = Path(self.manifest_root, manifest_name)

            if archive_files:
                if str(translation_manifest_path).replace("\\", "/") not in archive_files:
                    raise AssertionError(
                        f"Manifest for translation not present in the archive: {manifest_name}")
                return self

            if not translation_manifest_path.exists():
                raise AssertionError(
                    f"Translation '{translation_alias}' specified but manifest for it is missing! "
                    f"(Mod: {self.name})")
            yaml_config = read_yaml(translation_manifest_path)
            if yaml_config is None:
                raise AssertionError("Mod translation manifest is not a valid yaml file")

            yaml_config["build"] = self.build
            yaml_config["version"] = str(self.version)
            mod_tr = Mod(**yaml_config, is_translation=True, is_variant=self.is_variant,
                         variant_alias=self.variant_alias, manifest_root=self.manifest_root)
            self.add_mod_translation(mod_tr)

        return self

    @model_validator(mode="after")
    def load_sister_variants(self) -> "Mod":
        if self.variants_loaded:
            all_known = []
            for var in self.variants_loaded.values():
                all_known.extend(var.translations_loaded.values())

            for mod in all_known:
                if not mod.sister_variants:
                    mod._sister_variants = {sis_mod.name: sis_mod for sis_mod in all_known
                                            if mod.version == sis_mod.version
                                            and mod.name != sis_mod.name
                                            and mod.language == sis_mod.language}

        return self

    def model_post_init(self, __context: Any) -> None:  # noqa: ANN401
        # higher order version part dictates compatibility
        if self.compatible_minor_versions:
            self.compatible_patch_versions = True

        self._translations_loaded[self.language] = self
        self._variants_loaded[self.name] = self

    # TODO: Here be dragons! Ugly legacy solution copied from previous implementation.
    # Replace, see comment
    def load_gui_info(self) -> None:
        raise DeprecationWarning

    def load_game_compatibility(self, game_installment: str) -> None:
        for translation in self._translations_loaded.values():
            translation.installment_compatible = self.installment == game_installment

    def load_session_compatibility(self, installed_content: dict, installed_descriptions: dict,
                                   library_mods_info: dict[dict[str, str]] | None) -> None:
        for translation in self._translations_loaded.values():

            translation.compatible, translation.compatible_err = \
                translation.check_requirements(
                    installed_content,
                    installed_descriptions,
                    library_mods_info)

            translation.compatible_err = "\n".join(translation.compatible_err).strip()

            translation.prevalidated, translation.prevalidated_err = \
                translation.check_incompatibles(
                    installed_content,
                    installed_descriptions,
                    library_mods_info)

            translation.prevalidated_err = "\n".join(translation.prevalidated_err).strip()

            (translation.is_reinstall, translation.can_be_reinstalled,
             translation.reinstall_warning, translation.existing_version) = \
                translation.check_reinstallability(
                    installed_content)

            translation.can_install = (translation.commod_compatible
                                       and translation.installment_compatible
                                       and translation.compatible
                                       and translation.prevalidated
                                       and translation.can_be_reinstalled)

    async def install_async(self, game_data_path: str,
                            install_settings: dict,
                            existing_content: dict,
                            callback_progbar: Awaitable,
                            callback_status: Awaitable) -> bool:
        """Use fast async copy, return bool success status of install."""
        try:
            logger.info(f"Existing content at the start of install: {existing_content}")
            mod_files = []
            install_base = install_settings.get("base")
            if install_base is None:
                raise KeyError(f"Installation config for base of mod '{self.name}' is broken")

            if install_base == "skip":
                logger.debug("No base content will be installed")
            else:
                bin_paths = [Path(self.mod_files_root, one_dir) for one_dir in self.bin_dirs]
                data_paths = [Path(self.mod_files_root, one_dir) for one_dir in self.data_dirs]
                await callback_status(tr("copying_base_files_please_wait"))
                mod_files.extend(data_paths)
                start = datetime.now()
                await copy_from_to_async_fast(mod_files, game_data_path, callback_progbar)
                await copy_from_to_async_fast(bin_paths, Path(game_data_path).parent, callback_progbar)
                end = datetime.now()
                logger.debug(f"{(end - start).microseconds / 1000000} seconds took fast copy")
                mod_files.clear()

            for install_setting in install_settings:
                if install_setting == "base":
                    continue

                wip_setting = self.options_dict[install_setting]
                installation_decision = install_settings[install_setting]

                if installation_decision == "yes":
                    for data_dir in wip_setting.data_dirs:
                        simple_option_path = Path(
                            data_dir,
                            "data")
                        mod_files.append(simple_option_path)
                elif installation_decision == "skip":
                    logger.debug(f"Skipping option {install_setting}")
                    continue
                else:
                    custom_install_method = install_settings[install_setting]
                    install_setting_obj = next(iter([sett for sett in wip_setting.install_settings
                                           if sett.name == custom_install_method]))
                    for data_dir in wip_setting.data_dirs:
                        for sett_data_dir in install_setting_obj.data_dirs:
                            complex_option_path = Path(
                                data_dir,
                                sett_data_dir)
                            mod_files.append(complex_option_path)
                if installation_decision != "skip":
                    await callback_status(tr("copying_options_please_wait"))

                start = datetime.now()
                await copy_from_to_async_fast(mod_files, game_data_path, callback_progbar)
                end = datetime.now()
                logger.debug(f"{(end - start).microseconds / 1000000} seconds took fast copy")

                mod_files.clear()
        except Exception as ex:
            logger.exception("Exception occured when installing mod!")
            raise ModFileInstallationError from ex
        else:
            return True

    def check_requirements(self, existing_content: dict, existing_content_descriptions: dict,
                           library_mods_info: dict[dict[str, str]] | None) -> tuple[bool, list[str]]:
        """Return bool for cumulative check success result and a list of error message string."""
        error_msgs = []

        requirements_met = True
        is_compatch_env = ("community_remaster" not in existing_content and
                           "community_patch" in existing_content)

        self.individual_require_status.clear()
        for prereq in self.prerequisites:
            if self.name == "community_remaster" and prereq.name[0] == "community_patch":
                continue

            validated, mod_error = prereq.compute_current_status(
                                        existing_content, existing_content_descriptions,
                                        library_mods_info,
                                        is_compatch_env)
            self.individual_require_status.append((prereq, validated, mod_error))
            if mod_error:
                error_msgs.extend(mod_error)
            requirements_met &= validated

        # we will handle more complex case in check_incompatibles
        if requirements_met and self.strict_requirements and self.vanilla_mod:
            fake_req = Prerequisite(name="clean_game")
            fake_req._name_label = f"{tr('clean').capitalize()} " + tr(self.installment)

            content_left = set(existing_content.keys())
            if self.name in COMPATCH_REM and COMPATCH_REM & content_left:
                return requirements_met, error_msgs

            if content_left - {self.name}:
                validated_vanilla_mod = False
                mod_error = tr("cant_install_mod_for_vanilla")
                error_msgs.append(mod_error)
            else:
                validated_vanilla_mod = True
                mod_error = ""
            self.individual_require_status.append(
                (fake_req, validated_vanilla_mod, [mod_error]))
            requirements_met &= validated_vanilla_mod

        # if error_msg:
            # error_msg.append(f'\n{tr("check_for_a_new_version")}')

        return requirements_met, error_msgs

    def check_reinstallability(self, existing_content: dict) -> tuple[bool, bool, str, str]:
        """Return tuple with result of the check.

        Return (is_reinstall: bool, can_be_reinstalled: bool,
        reinstall_warning: str, existing_version: str)
        """
        previous_install = existing_content.get(self.name)
        comrem_over_compatch = False
        variants_installed = []

        if self.sister_variants:
            variants_installed = [existing_content.get(srv_name) for srv_name in self.sister_variants
                                  if existing_content.get(srv_name) is not None]
            if variants_installed and self.name == "community_remaster":
                comrem_over_compatch = True
                previous_install = variants_installed[0]

        if self.name == "community_patch" and variants_installed: # previous_install is None and
            return True, False, tr("cant_install_patch_over_remaster"), variants_installed[0]

        if previous_install is None:
            if variants_installed:
                return True, False, tr("cant_reinstall_other_variant_on_top"), variants_installed[0]
            # not a reinstall, can be installed
            return False, True, "", None

        old_options = set(previous_install.keys()) - RESERVED_CONTENT_NAMES
        new_options = {opt.name for opt in self.optional_content}

        self_and_prereqs = {self.name}

        for prereq in self.prerequisites:
            self_and_prereqs = self_and_prereqs | set(prereq.name)

        if previous_install.get("language") != self.language:
            return True, False, tr("cant_reinstall_different_lang"), previous_install

        if self.name == "community_remaster":
            # compatch is the same mod as comrem, just with less options, so we allow install on top
            self_and_prereqs.add("community_patch")
            # TODO: make this available for other mods

        existing_other_mods = set(existing_content.keys()) - self_and_prereqs

        if existing_other_mods and self.strict_requirements:
            # is reinstall, can't be installed as other mods not from prerequisites were installed
            existing_mods_display_names = []
            for name in existing_other_mods:
                mod_name = existing_content[name].get("display_name")
                if mod_name is None:
                    mod_name = name
                existing_mods_display_names.append(mod_name)
            warning = (f'{tr("cant_reinstall_over_other_mods")}: '
                       + ", ".join(existing_mods_display_names) + ".")
            return True, False, warning, previous_install

        existing_version = Version.parse_from_str(previous_install["version"])
        this_version = self.version


        over_other_version_warning = tr("cant_reinstall_over_other_version")

        # special compat settings can make mod forward compatible
        # backwards compatibility is not supported
        if self.compatible_patch_versions:
            this_version_approximate = Version.parse_from_str(str(this_version))
            if existing_version > this_version_approximate:
                is_compatible_version = False
                over_other_version_warning = tr("cant_reinstall_over_newer_version")
            else:
                existing_version.patch = "0"
                this_version_approximate.patch = "0"

                if self.compatible_minor_versions:
                    existing_version.minor = "0"
                    this_version_approximate.minor = "0"

                is_compatible_version = existing_version == this_version_approximate
        else:
            is_compatible_version = existing_version == this_version

        if not is_compatible_version:
            return True, False, over_other_version_warning, previous_install

        if self.build == previous_install["build"]:
            if not self.optional_content and not comrem_over_compatch:
                # is reinstall, simple mod, safe reinstall
                return True, True, tr("can_reinstall"), previous_install

            if old_options == new_options:
                # is reinstall, complex mod, safe reinstall, forced options
                if not self.safe_reinstall_options:
                    warning = tr("to_increase_compat_options_are_limited")
                else:
                    warning = tr("can_reinstall")
                return True, True, warning, previous_install

            if comrem_over_compatch:
                return True, True, tr("can_reinstall"), previous_install

            return True, False, tr("cant_reinstall_with_different_options"), previous_install

        if self.build > previous_install["build"]:
            if not self.optional_content:
                # is reinstall, simple mod, unsafe reinstall
                return True, True, tr("can_reinstall"), previous_install

            if old_options == new_options:
                # is reinstall, complex mod, unsafe reinstall, forced options
                warning = tr("can_reinstall")
                if not self.safe_reinstall_options:
                    warning += "\n" + tr("to_increase_compat_options_are_limited")
                return True, True, warning, previous_install
            if comrem_over_compatch:
                return True, True, tr("can_reinstall"), previous_install

            return True, False, tr("cant_reinstall_with_different_options"), previous_install

        # self.build < previous_install["build"]
        return True, False, tr("cant_reinstall_over_newer_build"), previous_install

    def check_incompatibles(self, existing_content: dict,
                            existing_content_descriptions: dict,
                            library_mods_info: dict[dict[str, str]] | None) -> tuple[bool, list]:
        error_msg = []
        compatible = True

        self.individual_incomp_status.clear()

        for incomp in self.incompatible:
            incompatible_with_game_copy, mod_error = incomp.compute_current_status(
                existing_content, existing_content_descriptions, library_mods_info)
            self.individual_incomp_status.append((incomp, not incompatible_with_game_copy,
                                                 mod_error))
            if mod_error:
                error_msg.extend(mod_error)
            compatible &= (not incompatible_with_game_copy)

        # convoluted logic required to support inconsistent configs of legacy ComRem versions
        # which icluded ComPatch in prereqs while not really following that requirement
        if (compatible and self.strict_requirements
            and (self.prerequisites or self.name in COMPATCH_REM)):
            content_to_ignore = {self.name} | COMPATCH_REM
            for prereq in self.prerequisites:
                content_to_ignore = content_to_ignore | set(prereq.name)
            existing_other_mods = set(existing_content.keys()) - set(content_to_ignore)
            if existing_other_mods:
                existing_mods_display_names = []
                for name in existing_other_mods:
                    mod_name = existing_content[name].get("display_name")
                    if mod_name is None:
                        mod_name = name
                    existing_mods_display_names.append(mod_name)
                existing_string = ", ".join(existing_mods_display_names)
                error_msg.append(f'{tr("cant_install_strict_requirements")}: '
                                 + existing_string + ".")
                compatible = False
                fake_incomp = Incompatibility(name="other_mods")
                fake_incomp._name_label = existing_string

                self.individual_incomp_status.append(
                    (fake_incomp, False, [f'{tr("already_installed")}: {existing_string}']))
        return compatible, error_msg
