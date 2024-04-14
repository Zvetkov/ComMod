# ruff: noqa: N815
import enum
import operator
import os
import struct
import typing
from collections.abc import Callable
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Annotated, Any

from pydantic import (
    BaseModel,
    Field,
    FilePath,
    StringConstraints,
    computed_field,
    field_validator,
    model_validator,
)

from commod.game import data, hd_ui
from commod.helpers.file_ops import (
    RESOLUTION_OPTION_LIST_SIZE,
    get_config,
    get_internal_file_path,
    logger,
    patch_offsets,
    write_xml_to_file,
)
from commod.helpers.parse_ops import (
    get_child_from_xml_node,
    parse_simple_relative_path,
    remove_substrings,
    xml_to_objfy,
)
from commod.localisation.service import get_known_mod_display_name, tr


class PatcherOptions(BaseModel):
    gravity: Annotated[float, Field(ge=-100, le=-1)] | None = None
    skins_in_shop: Annotated[int, Field(ge=8, le=32)] | None = None
    sell_price_coeff: Annotated[float, Field(ge=0.0, le=1.0)] | None = None
    blast_damage_friendly_fire: bool | None = None
    game_font: str | None = None
    slow_brake: bool | None = None
    hq_reflections: bool | None = None
    draw_distance_limit: bool | None = None
    vanilla_fov: bool | None = None


class ConfigOptions(BaseModel):
    # Additional field names must follow actual game config names exactly
    firstLevel: str | None = None
    mainMenuLevelName: str | None = None
    DoNotLoadMainmenuLevel: str | None = None

    g_impostorThreshold: int | None = None

    ai_clash_coeff: float | None = None
    ai_enemies_ramming_damage_coeff: int | None = None
    ai_min_hit_velocity: int | None = None

    weather_AtmoRadius: float | None = None
    weather_ConfigFile: str | None = None

    mus_Volume:     Annotated[int, Field(ge=0, le=50)] | None = None
    snd_2dVolume:   Annotated[int, Field(ge=0, le=50)] | None = None
    snd_3dVolume:   Annotated[int, Field(ge=0, le=50)] | None = None


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

    def __add__(self, string: str) -> str:
        return str(self) + string

    def __radd__(self, string: str) -> str:
        return string + str(self)

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
        return Version(major=major, minor=minor, patch=patch,
                       identifier=identifier.strip().replace("\n", ""))


    def __str__(self) -> str:
        version = f"{self.major}.{self.minor}.{self.patch}"
        if self.identifier:
            version += f"-{self.identifier}"
        return version

    def __repr__(self) -> str:
        if self.patch != "0":
            version = f"{self.major}.{self.minor}.{self.patch}"
        else:
            version = f"{self.major}.{self.minor}"
        if self.identifier:
            version += f"-{self.identifier}"
        return version

    def _is_valid_operand(self, other: object) -> bool:
        return isinstance(other, Version)

    def __eq__(self, other: object) -> bool:
        if not self._is_valid_operand(other):
            return NotImplemented

        if self.is_numeric and other.is_numeric:
            return ((int(self.major), int(self.minor), int(self.patch), self.identifier.lower())
                    ==
                    (int(other.major), int(other.minor), int(other.patch), other.identifier.lower()))

        return ((self.major.lower(), self.minor.lower(), self.patch.lower(), self.identifier.lower())
                ==
                (other.major.lower(), other.minor.lower(), other.patch.lower(), self.identifier.lower()))

    def __lt__(self, other: object) -> bool:
        if not self._is_valid_operand(other):
            return NotImplemented

        if self.is_numeric and other.is_numeric:
            return ((int(self.major), int(self.minor), int(self.patch))
                    <
                    (int(other.major), int(other.minor), int(other.patch)))

        return ((self.major.lower(), self.minor.lower(), self.patch.lower())
                <
                (other.major.lower(), other.minor.lower(), other.patch.lower()))

    def __le__(self, other: object) -> bool:
        if not self._is_valid_operand(other):
            return NotImplemented

        if self.is_numeric and other.is_numeric:
            return ((int(self.major), int(self.minor), int(self.patch))
                    <=
                    (int(other.major), int(other.minor), int(other.patch)))

        return ((self.major.lower(), self.minor.lower(), self.patch.lower())
                <=
                (other.major.lower(), other.minor.lower(), other.patch.lower()))

    def __gt__(self, other: object) -> bool:
        if not self._is_valid_operand(other):
            return NotImplemented

        if self.is_numeric and other.is_numeric:
            return ((int(self.major), int(self.minor), int(self.patch))
                    >
                    (int(other.major), int(other.minor), int(other.patch)))

        return ((self.major.lower(), self.minor.lower(), self.patch.lower())
                >
                (other.major.lower(), other.minor.lower(), other.patch.lower()))

    def __ge__(self, other: object) -> bool:
        if not self._is_valid_operand(other):
            return NotImplemented

        if self.is_numeric and other.is_numeric:
            return ((int(self.major), int(self.minor), int(self.patch))
                    >=
                    (int(other.major), int(other.minor), int(other.patch)))

        return ((self.major.lower(), self.minor.lower(), self.patch.lower())
                >=
                (other.major.lower(), other.minor.lower(), other.patch.lower()))

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


@dataclass(frozen=True)
class VersionRequirement:
    version_string: str

    @computed_field
    @cached_property
    def compare_operator(self) -> Callable:
        if self.version_string.startswith(">="):
            return operator.ge
        if self.version_string.startswith("<="):
            return operator.le
        if self.version_string.startswith(">"):
            return operator.gt
        if self.version_string.startswith("<"):
            return operator.lt
        if self.version_string.startswith("="):
            return operator.eq
        # default "version" treated the same as "==version":
        return operator.eq

    @computed_field
    @cached_property
    def version(self) -> Version:
        return Version.parse_from_str(remove_substrings(self.version_string, (">", "<", "=")))


@dataclass(frozen=True)
class ManagerVersionRequirement:
    version_string: str

    @computed_field
    @cached_property
    def compare_operator(self) -> Callable:
        if self.version_string.startswith(">="):
            return operator.ge
        if self.version_string.startswith("<="):
            return operator.le
        if self.version_string.startswith(">"):
            return operator.gt
        if self.version_string.startswith("<"):
            return operator.lt
        if self.version_string.startswith("="):
            return operator.eq
        # default "version" treated the same as ">=version":
        return operator.ge

    @computed_field
    @cached_property
    def version(self) -> Version:
        return Version.parse_from_str(remove_substrings(self.version_string, (">", "<", "=")))


class CompareOperator(enum.IntEnum):
    STRICT = 1
    MIXED = 2


class ModCompatConstrain(BaseModel):
    name: list[Annotated[str, StringConstraints(max_length=64)]]
    versions: list[str] | list[VersionRequirement] | None = Field(default=[], repr=False)
    optional_content: list[str] | None = Field(default=[], repr=False)

    @field_validator("name", mode="before")
    @classmethod
    def convert_to_name_list(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [value]
        return value

    @field_validator("versions", mode="before")
    @classmethod
    def convert_to_version_list(cls, value: str | list[str]) -> list[str]:
        if value and not isinstance(value, list):
            return [value]
        return value

    @field_validator("versions", mode="before")
    @classmethod
    def convert_to_version_reqs(cls, value: list[str] | list[VersionRequirement]) -> list[VersionRequirement]:
        return [VersionRequirement(str(ver)) for ver in value]

    @computed_field
    @cached_property
    def constrain_style(self) -> VersionConstrainStyle:
        """Replacement for prerequisites_style param of mod.

        TODO: remove prerequisites_style from Mod calls
        """
        if self.versions:
            compare_ops: set[Callable] = {ver.compare_operator for ver in self.versions}
            ops_tuple = tuple(compare_ops)
            num_ops = len(ops_tuple)

            if num_ops == CompareOperator.STRICT and operator.eq in ops_tuple:
                return VersionConstrainStyle.STRICT

            if num_ops == CompareOperator.MIXED and operator.eq not in ops_tuple:
                first_op = ops_tuple[0]
                second_op = ops_tuple[1]

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


class Prerequisite(ModCompatConstrain):
    _name_label: str = ""
    _mention_versions: bool = False

    @computed_field
    @property
    def name_label(self) -> str:
        return self._name_label

    @computed_field
    @property
    # TODO: this is used in a very janky way, rethink if this is required and why
    def mention_versions(self) -> bool:
        return self._mention_versions

    def compute_current_status(self, existing_content: dict,
                       existing_content_descriptions: dict,
                       library_mods_info: dict[dict[str, str]] | None,
                       is_compatch_env: bool) -> tuple[bool, str]:
        """Return bool check success result and an error message string."""
        error_msg = []
        required_mod_name = None

        name_validated = True
        version_validated = True
        optional_content_validated = True

        for possible_prereq_mod in self.name:
            existing_mod = existing_content.get(possible_prereq_mod)
            if existing_mod is not None:
                required_mod_name = possible_prereq_mod

        if required_mod_name is None:
            name_validated = False

        # if trying to install compatch-only mod on comrem
        if (required_mod_name == "community_patch"
           and existing_content.get("community_remaster") is not None
           and self.name != "community_remaster"
           and "community_remaster" not in self.name):
            name_validated = False
            error_msg.append(f"{tr('compatch_mod_incompatible_with_comrem')}")

        or_word = f" {tr('or')} "
        and_word = f" {tr('and')} "
        only_technical_name_available = False

        name_label = []
        for service_name in self.name:
            known_name = get_known_mod_display_name(service_name, library_mods_info)
            if known_name is None:
                existing_mod = existing_content.get(service_name)
                if not name_label and existing_mod is not None and existing_mod.get("display_name"):
                    name_label.append(existing_mod["display_name"])
                else:
                    name_label.append(service_name)
                    only_technical_name_available = True
            else:
                name_label.append(known_name)

        name_label = or_word.join(name_label)
        version_label = ""
        optional_content_label = ""

        if self.versions:
            version_label = (f', {tr("of_version")}: '
                             f'{and_word.join([ver.version_string for ver in self.versions])}')
            if name_validated:
                for version_constrain in self.versions:

                    installed_version = str(existing_content[required_mod_name]["version"])
                    parsed_existing_ver = Version.parse_from_str(installed_version)
                    parsed_required_ver = version_constrain.version

                    version_validated = version_constrain.compare_operator(
                        parsed_existing_ver, parsed_required_ver)
                    if (version_constrain.compare_operator is operator.eq and
                        parsed_required_ver.identifier and
                        parsed_existing_ver.identifier != parsed_required_ver.identifier):
                                version_validated = False


        optional_content = self.optional_content
        if optional_content and optional_content is not None:
            optional_content_label = (f', {tr("including_options").lower()}: '
                                      f'{", ".join(self.optional_content)}')
            if name_validated and version_validated:
                for option in optional_content:
                    if existing_content[required_mod_name].get(option) in [None, "skip"]:
                        optional_content_validated = False
                        requirement_err = f"{tr('content_requirement_not_met')}:"
                        requirement_name = (f"  * '{option}' {tr('for_mod')} "
                                            f"{name_label}")

                        if requirement_err not in error_msg:
                            error_msg.append(requirement_err)

                        error_msg.append(requirement_name)

        validated = name_validated and version_validated and optional_content_validated

        if not validated:
            if not name_validated:
                warning = f'\n{tr("required_mod_not_found")}:'
            else:
                warning = f'\n{tr("required_base")}:'

            if warning not in error_msg:
                error_msg.append(warning)

            name_label_tr = tr("technical_name") if only_technical_name_available else tr("mod_name")
            error_msg.append(f"{name_label_tr.capitalize()}: "
                             f"{name_label}{version_label}{optional_content_label}")
            installed_description = existing_content_descriptions.get(required_mod_name)
            if installed_description is not None:
                installed_description = installed_description.strip(" \n")  # noqa: B005
                error_msg_entry = (f'\n{tr("version_available").capitalize()}:\n'
                                   f'{installed_description}')
                if error_msg_entry not in error_msg:
                    error_msg.append(error_msg_entry)

            # in case when we working with compatched game but mod requires comrem
            # it would be nice to tip a user that this is incompatibility in itself
            elif is_compatch_env and "community_remaster" in self.name:
                installed_description = existing_content_descriptions.get("community_patch")
                error_msg_entry = (f'\n{tr("version_available").capitalize()}:\n'
                                   f'{installed_description}')
                if error_msg_entry not in error_msg:
                    error_msg.append(error_msg_entry)
        # TODO: continue from here
        self._name_label = name_label
        self._mention_versions = True
        return validated, error_msg


class Incompatibility(ModCompatConstrain):
    _name_label: str = ""

    @computed_field
    @property
    def name_label(self) -> str:
        return self._name_label

    def compute_current_status(self, existing_content: dict,
                       existing_content_descriptions: dict,
                       library_mods_info: dict[dict[str, str]] | None) -> tuple[bool, list]:
        error_msg = []
        name_incompat = False
        version_incomp = False
        optional_content_incomp = False

        incomp_mod_name = None
        for possible_incomp_mod in self.name:
            existing_mod = existing_content.get(possible_incomp_mod)
            if existing_mod is not None:
                incomp_mod_name = possible_incomp_mod

        or_word = f" {tr('or')} "
        # and_word = f" {tr('and')} "
        only_technical_name_available = False

        name_label = []
        for service_name in self.name:
            existing_mod = existing_content.get(service_name)
            if existing_mod is not None and existing_mod.get("display_name") is not None:
                name_label.append(existing_mod["display_name"])
            else:
                known_name = get_known_mod_display_name(service_name, library_mods_info)
                if known_name is None:
                    name_label.append(service_name)
                    only_technical_name_available = True
                else:
                    name_label.append(known_name)

        name_label = or_word.join(name_label)
        version_label = ""
        optional_content_label = ""

        if incomp_mod_name is not None:
            # if incompatible mod is found we need to check if a tighter conformity check exists
            name_incompat = True

            if self.versions:
                installed_version = existing_content[incomp_mod_name]["version"]

                version_label = (f', {tr("of_version")}: '
                                 f'{or_word.join([ver.version_string for ver in self.versions])}')
                for version_constrain in self.versions:
                    parsed_existing_ver = Version.parse_from_str(installed_version)
                    parsed_incompat_ver = version_constrain.version

                    version_incomp = version_constrain.compare_operator(
                        parsed_existing_ver, parsed_incompat_ver)

                    # while we ignore postfix for less/greater ops, we want to have an ability
                    # to make a specifix version with postfix incompatible
                    if (version_constrain.compare_operator is operator.eq
                       and parsed_incompat_ver.identifier
                       and parsed_existing_ver.identifier != parsed_incompat_ver.identifier):
                        version_incomp = True
            else:
                version_incomp = True

            optional_content = self.optional_content

            if optional_content and optional_content is not None:

                optional_content_label = (f', {tr("with_options").lower()}: '
                                          f'{or_word.join(self.optional_content)}')

                for option in optional_content:
                    if existing_content[incomp_mod_name].get(option) not in [None, "skip"]:
                        optional_content_incomp = True
            else:
                optional_content_incomp = True

            incompatible_with_game_copy = name_incompat and version_incomp and optional_content_incomp

            name_label_tr = tr("technical_name") if only_technical_name_available else tr("mod_name")

            if incompatible_with_game_copy:
                error_msg.append(f'\n{tr("found_incompatible")}:\n'
                                 f'{name_label_tr.capitalize()}: '
                                 f'{name_label}{version_label}{optional_content_label}')
                installed_description = existing_content_descriptions.get(incomp_mod_name)
                if installed_description is not None:
                    installed_description = installed_description.strip(" \n")  # noqa: B005
                    error_msg.append(f'\n{tr("version_available").capitalize()}:\n'
                                     f'{installed_description}')
                else:
                    # TODO: check if this path even possible
                    raise NotImplementedError
            self._name_label = name_label
            return incompatible_with_game_copy, error_msg

        self._name_label = name_label
        return False, ""


class InstallSettings(BaseModel):
    name: Annotated[str, StringConstraints(max_length=64)]
    description: Annotated[str, StringConstraints(max_length=1024)] = Field(repr=False)

    @field_validator("description", mode="after")
    @classmethod
    def remove_lead_trail_newline_n_space(cls, value: str) -> str:
        return value.strip(" \n")

RESERVED_CONTENT_NAMES = {"base", "name", "display_name", "build", "version", "language", "installment"}


class OptionalContent(BaseModel):
    # required fields
    name: Annotated[str, StringConstraints(max_length=64)]
    display_name: Annotated[str, StringConstraints(max_length=64)]
    description: Annotated[str, StringConstraints(max_length=1024)] = Field(repr=False)

    # fields with defaults
    default_option: str | None = Field(default=None, repr=False)
    forced_option: bool = False
    install_settings: list[InstallSettings] = Field(default=[], repr=False)
    patcher_options: PatcherOptions | None = None

    # file structure
    data_dirs: list[str] = []

    @field_validator("name", "display_name", "description", mode="after")
    @classmethod
    def remove_newline_space(cls, value: str) -> str:
        return value.strip(" \n")

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

    def model_post_init(self, _unused_context: Any) -> None:  # noqa: ANN401
        if not self.data_dirs:
            self.data_dirs = [Path(self.name)]

class Screenshot(BaseModel):
    # TODO: add img extension checks previously existed in legacy Mod?
    img: str = Field(repr=False)
    text: Annotated[str, StringConstraints(max_length=256)] = ""
    compare: str = Field(default="", repr=False)

    _screen_path: FilePath | None = None
    _compare_path: FilePath | None = None

    @field_validator("text", mode="after")
    @classmethod
    def remove_lead_trail_newline_n_space(cls, value: str) -> str:
        return value.strip(" \n")

    @computed_field
    @property
    def screen_path(self) -> FilePath | None:
        return self._screen_path

    @computed_field
    @property
    def compare_path(self) -> FilePath | None:
        return self._compare_path


def patch_memory(target_exe: str) -> list[str]:
    """Apply two memory related binary exe fixes."""
    with open(target_exe, "rb+") as f:
        patch_offsets(f, data.minimal_mm_inserts, raw_strings=True)

        offsets_text = data.get_text_offsets("minimal")
        for offset in offsets_text:
            text_fin = offsets_text[offset][0]
            text_str = bytes(text_fin, "utf-8")
            allowed_len = offsets_text[offset][1]
            f.seek(offset)
            f.write(struct.pack(f"{allowed_len}s", text_str))

    return ["mm_inserts_patched"]


def patch_configurables(target_exe: str, exe_options: list[PatcherOptions] | None = None) -> None:
    """Apply binary exe fixes which support configuration."""
    with open(target_exe, "rb+") as f:
        # dict of values that mod configured to be patched
        configurable_values: dict[str, Any] = {}
        font_alias = ""

        for exe_options_config in exe_options:
            if exe_options_config.gravity is not None:
                configurable_values["gravity"] = exe_options_config.gravity

            if exe_options_config.skins_in_shop is not None:
                configurable_values["skins_in_shop_0"] = (exe_options_config.skins_in_shop,)
                configurable_values["skins_in_shop_1"] = (exe_options_config.skins_in_shop,)
                configurable_values["skins_in_shop_2"] = (exe_options_config.skins_in_shop,)

            if exe_options_config.blast_damage_friendly_fire is not None:
                configurable_values["blast_damage_friendly_fire"] = exe_options_config.blast_damage_friendly_fire

            if exe_options_config.game_font is not None:
                font_alias = exe_options_config.game_font

            if exe_options_config.draw_distance_limit is not None:
                limit_draw_dist = exe_options_config.draw_distance_limit

                if limit_draw_dist:
                    patch_offsets(f, data.offsets_draw_dist_vanilla, raw_strings=True)
                    patch_offsets(f, data.offset_draw_dist_numerics_vanilla)
                else:
                    patch_offsets(f, data.offsets_draw_dist, raw_strings=True)
                    patch_offsets(f, data.offset_draw_dist_numerics)

            if exe_options_config.hq_reflections is not None:
                hq_reflections = exe_options_config.hq_reflections

                if hq_reflections:
                    patch_offsets(f, data.offset_hq_reflections)
                else:
                    patch_offsets(f, data.offset_hq_reflections_vanilla)

            if exe_options_config.vanilla_fov is not None:
                vanilla_fov = exe_options_config.vanilla_fov

                if vanilla_fov:
                    patch_offsets(f, data.projection_matrix_vanilla, raw_strings=True)
                else:
                    patch_offsets(f, data.projection_matrix_fix, raw_strings=True)

            if exe_options_config.slow_brake is not None:
                slow_brake = exe_options_config.slow_brake

                if slow_brake:
                    patch_offsets(f, data.offsets_slow_brake)
                else:
                    patch_offsets(f, data.offsets_slow_brake_vanilla)

            if exe_options_config.sell_price_coeff is not None:
                new_coeff = exe_options_config.sell_price_coeff
                # changing value
                configurable_values["sell_price_coeff_new"] = new_coeff
                # changing pointer
                patch_offsets(f, data.sell_price_offsets)


        # mapping of offests to value/values needed for binary patch
        configured_offsets: dict[int, Any] = {}

        for offset_key, value in configurable_values.items():
            configured_offsets[data.configurable_offsets.get(offset_key)] = value

        if font_alias:
            hd_ui.scale_fonts(Path(target_exe).parent, data.OS_SCALE_FACTOR, font_alias)

        patch_offsets(f, configured_offsets)


def correct_damage_coeffs(root_dir: str, gravity: float) -> None:
    config = get_config(root_dir)
    if config.attrib.get("ai_clash_coeff") is not None:
        ai_clash_coeff = 0.001 / (gravity / -9.8)
        config.attrib["ai_clash_coeff"] = f"{ai_clash_coeff:.4f}"
        write_xml_to_file(config, os.path.join(root_dir, "data", "config.cfg"))


def patch_remaster_icon(f: typing.BinaryIO) -> None:
    f.seek(data.size_of_rsrc_offset)
    old_rsrc_size = int.from_bytes(f.read(4), byteorder="little")

    if old_rsrc_size == data.size_of_rsrc:
        # patching new icon
        icon_raw: bytes
        with open(get_internal_file_path("assets/icons/hta_comrem.ico"), "rb+") as ficon:
            ficon.seek(data.new_icon_header_ends)
            icon_raw = ficon.read()

        if icon_raw:
            size_of_icon = len(icon_raw)

            block_size_overflow = len(icon_raw) % 0x10
            padding_size = 0x10 - block_size_overflow

            # reading reloc struct to write in at the end of the rsrc latter on
            f.seek(data.offset_of_reloc_offset)
            reloc_offset = int.from_bytes(f.read(4), byteorder="little") - data.rva_offset
            f.seek(data.size_of_reloc_offset)
            reloc_size = int.from_bytes(f.read(4), byteorder="little")

            f.seek(reloc_offset)
            reloc = f.read(reloc_size)

            # writing icon
            f.seek(data.em_102_icon_offset)
            f.write(icon_raw)
            f.write(b"\x00" * padding_size)

            # writing icon group and saving address to write it to table below
            new_icon_group_address = f.tell()
            f.write(bytes.fromhex(data.new_icon_group_info))
            end_rscr_address = f.tell()
            f.write(b"\x00" * 8)  # padding for icon group

            current_size = f.tell() - data.offset_of_rsrc
            block_size_overflow = current_size % 0x1000

            # padding rsrc to 4Kb block size
            padding_size_rsrc = 0x1000 - block_size_overflow
            raw_size_of_rsrc = current_size + padding_size_rsrc
            f.write(b"\x00" * padding_size_rsrc)

            # now writing reloc struct and saving its address to write to table below
            new_reloc_address_raw = f.tell()
            new_reloc_address = new_reloc_address_raw + data.rva_offset

            # padding reloc to 4Kb block size
            block_size_overflow = len(reloc) % 0x1000
            padding_size = 0x1000 - block_size_overflow
            f.write(reloc)
            f.write(b"\x00" * padding_size)
            size_of_image = f.tell()

            # updating pointers in PE header for rsrc struct and reloc struct
            f.seek(data.size_of_rsrc_offset)
            # old_rsrc_size = int.from_bytes(f.read(4), byteorder='little')
            size_of_rscs = end_rscr_address - data.offset_of_rsrc
            f.write(size_of_rscs.to_bytes(4, byteorder="little"))
            f.seek(data.resource_dir_size)
            f.write(size_of_rscs.to_bytes(4, byteorder="little"))

            f.seek(data.raw_size_of_rsrc_offset)
            f.write(raw_size_of_rsrc.to_bytes(4, byteorder="little"))

            f.seek(data.offset_of_reloc_offset)
            f.write(new_reloc_address.to_bytes(4, byteorder="little"))

            # updating size of resource for icon and pointer to icon group resource
            f.seek(data.new_icon_size_offset)
            f.write(size_of_icon.to_bytes(4, byteorder="little"))

            f.seek(data.new_icon_group_offset)
            f.write((new_icon_group_address+data.rva_offset).to_bytes(4, byteorder="little"))

            f.seek(data.offset_of_reloc_raw)
            f.write(new_reloc_address_raw.to_bytes(4, byteorder="little"))

            f.seek(data.size_of_image)
            f.write((size_of_image+data.rva_offset).to_bytes(4, byteorder="little"))


def patch_game_exe(target_exe: str, version_choice: str, build_id: str,
                   monitor_res: tuple, exe_options: list[PatcherOptions] | None = None,
                   under_windows: bool = True) -> list[str]:
    """Apply binary exe fixes, makes related changes to config and global properties.

    Returns list with a localised description of applied changes
    """
    changes_description = []
    with open(target_exe, "rb+") as f:
        game_root_path = Path(target_exe).parent
        width, height = monitor_res

        if version_choice == "remaster":
            patch_offsets(f, data.offsets_comrem_relative, data.ENLARGE_UI_COEF)
            patch_offsets(f, data.offsets_comrem_absolute)

            hd_ui.toggle_16_9_UI_xmls(game_root_path, width, height, enable=True)
            hd_ui.toggle_16_9_glob_prop(game_root_path, enable=True)
            changes_description.append("widescreen_interface_patched")

        patch_offsets(f, data.binary_inserts, raw_strings=True)
        changes_description.append("binary_inserts_patched")
        changes_description.append("spawn_freezes_fix")
        changes_description.append("camera_patched")

        patch_offsets(f, data.minimal_mm_inserts, raw_strings=True)
        patch_offsets(f, data.additional_mm_inserts, raw_strings=True)
        changes_description.append("mm_inserts_patched")

        patch_offsets(f, data.offsets_exe_fixes)

        changes_description.append("numeric_fixes_patched")

        patch_offsets(f, data.offsets_draw_dist, raw_strings=True)
        patch_offsets(f, data.offset_draw_dist_numerics)
        changes_description.append("draw_distance_patched")

        if version_choice == "remaster":
            patch_remaster_icon(f)

            configured_font = ""
            for exe_options_config in exe_options:
                if exe_options_config.game_font is not None:
                    configured_font = exe_options_config.game_font

            if under_windows:
                font_alias = configured_font
                fonts_scaled = hd_ui.scale_fonts(game_root_path, data.OS_SCALE_FACTOR, font_alias)
                if fonts_scaled:
                    logger.info("fonts corrected")
                else:
                    logger.info("cant correct fonts")
            else:
                logger.warning("Font scaling is unsupported under OS other then Windows")

            width_list = []
            if width in data.PREFERED_RESOLUTIONS:
                width_list = data.PREFERED_RESOLUTIONS[width]
            else:
                width_possible = reversed(list(data.KNOWN_RESOLUTIONS))
                for width_candidate in width_possible:
                    if width_candidate <= width:
                        width_list.append(width_candidate)
                if len(width_list) >= RESOLUTION_OPTION_LIST_SIZE:
                    if width not in width_list:
                        width_list.insert(0, width)
                        data.KNOWN_RESOLUTIONS[width] = height
                    width_list = width_list[:5]
                    width_list.reverse()
                else:
                    width_list = data.DEFAULT_RESOLUTIONS

            for i in range(5):
                width_to_change = data.offsets_resolution_list[i][0]
                height_to_change = data.offsets_resolution_list[i][1]
                f.seek(width_to_change)
                f.write(struct.pack("i", width_list[i]))
                f.seek(height_to_change)
                f.write(struct.pack("i", data.KNOWN_RESOLUTIONS[width_list[i]]))
            logger.info("ui fixes patched")

        offsets_text = data.get_text_offsets(version_choice)
        for offset in offsets_text:
            text_fin = offsets_text[offset][0]
            if "ExMachina - " in offsets_text[offset][0]:
                text_fin += f" [{build_id}]"
            text_str = bytes(text_fin, "utf-8")
            allowed_len = offsets_text[offset][1]
            f.seek(offset)
            f.write(struct.pack(f"{allowed_len}s", text_str))

        configured_gravity = data.DEFAULT_COMREM_GRAVITY
        for exe_options_config in exe_options:
            if exe_options_config.gravity:
                configured_gravity = exe_options_config.gravity

        correct_damage_coeffs(game_root_path, configured_gravity)
        # increase_phys_step might not have an intended effect, need to verify
        # increase_phys_step(game_root_path)
        logger.info("damage coeff patched")

    patch_configurables(target_exe, exe_options)
    return changes_description


def rename_effects_bps(game_root_path: str) -> None:
    """Needed to ignore packed effects.bps.

    Without packed bps file game will use individual effects, which allows making edits to them
    """
    bps_path = os.path.join(game_root_path, "data", "models", "effects.bps")
    new_bps_path = os.path.join(game_root_path, "data", "models", "stock_effects.bps")
    if os.path.exists(bps_path):
        if os.path.exists(new_bps_path):
            os.remove(bps_path)
            logger.info(f"Deleted effects.bps in path '{bps_path}' as renamed backup already exists")
        else:
            os.rename(bps_path, new_bps_path)
            logger.info(f"Renamed effects.bps in path '{bps_path}'")
    elif not os.path.exists(new_bps_path):
        logger.warning(f"Can't find effects.bps not in normal path '{bps_path}', "
                       "nor in renamed form, probably was deleted by user")


def get_glob_props_path(root_dir: str) -> str:
    config = get_config(root_dir)
    if config.attrib.get("pathToGlobProps") is not None:
        glob_props_path = config.attrib.get("pathToGlobProps")
    # TODO: fix this idiocity
    return glob_props_path


def increase_phys_step(root_dir: str, enable: bool = True) -> None:
    glob_props_full_path = os.path.join(root_dir, get_glob_props_path(root_dir))
    glob_props = xml_to_objfy(glob_props_full_path)
    physics = get_child_from_xml_node(glob_props, "Physics")
    if physics is not None:
        if enable:
            physics.attrib["PhysicStepTime"] = "0.0166"
        else:
            physics.attrib["PhysicStepTime"] = "0.033"
    write_xml_to_file(glob_props, glob_props_full_path)


def patch_render_dll(target_dll: str) -> None:
    with open(target_dll, "rb+") as f:
        for offset in data.offsets_dll:
            f.seek(offset)
            if isinstance(data.offsets_dll[offset], str):  # hex address
                f.write(struct.pack("<Q", int(data.offsets_dll[offset], base=16))[:4])
            elif isinstance(data.offsets_dll[offset], float):
                f.write(struct.pack("f", data.offsets_dll[offset]))
            else:
                raise TypeError("Unsupported type given for dll binary patch!")
