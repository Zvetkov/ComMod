# ruff: noqa
# type: ignore

from __future__ import annotations

import logging
import operator
import os
from collections.abc import Awaitable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from functools import total_ordering
from pathlib import Path
from typing import Any
from zipfile import ZipInfo

from pathvalidate import sanitize_filename
from py7zr import py7zr

from commod.game.data import (
    COMPATCH_GITHUB,
    DEM_DISCORD,
    WIKI_COMREM,
    SupportedGames,
)
from commod.helpers import validation
from commod.helpers.file_ops import copy_from_to_async_fast, get_internal_file_path, read_yaml
from commod.helpers.parse_ops import (
    parse_bool_from_dict,
    parse_simple_relative_path,
    parse_str_from_dict,
    process_markdown,
    remove_substrings,
)
from commod.localisation.service import SupportedLanguages, get_known_mod_display_name, is_known_lang, tr

logger = logging.getLogger("dem")


def validate_manifest_struct(install_config: Any) -> bool:  # noqa: ANN401
    logger.info("--- Validating install config struct ---")
    if not isinstance(install_config, dict):
        logger.error("\tFAIL: broken config encountered, can't be read as dictionary")
        return False

    # schema type 1: list of possible types, required(bool)
    # schema type 2: list of possible types, required(bool), value[min, max]
    schema_top_level: dict[str, list[Any]] = {
        # primary required
        "name": [[str], True],
        "display_name": [[str], True],
        "version": [[str, int, float], True],
        "build": [[str], True],
        "description": [[str], True],
        "authors": [[str], True],
        "patcher_version_requirement": [[str, float, int, list[str | float | int]], True],

        # primary with defaults
        "installment": [[str], False],
        "language": [[str], False],  # defaults to ru

        # compatibility
        "prerequisites": [[list], True],
        "incompatible": [[list], False],
        "compatible_patch_versions": [[bool, str], False],
        "compatible_minor_versions": [[bool, str], False],
        "safe_reinstall_options": [[bool, str], False],

        # child versions
        "translations": [[list[str]], False],
        "variants": [[list[str]], False],

        # secondary
        "release_date": [[str], False],
        "link": [[str], False],
        "trailer_url": [[str], False],
        "tags": [[list[str]], False],
        "logo": [[str], False],
        "install_banner": [[str], False],
        "screenshots": [[list], False],
        "change_log": [[str], False],
        "other_info": [[str], False],
        "patcher_options": [[dict], False],
        "config_options": [[dict], False],
        "optional_content": [[list], False],
        "strict_requirements": [[bool, str], False],
        "no_base_content": [[bool, str], False],
        "base_dirs": [[list[str]], False],
        "options_base_dir": [[str], False]
    }

    schema_prereqs = {
        "name": [[str, list[str]], True],
        "versions": [[list[str | int | float]], False],
        "optional_content": [[list[str]], False]
    }
    schema_patcher_options = {
        "gravity": [[float], False, (-100.0, -1.0)],
        "skins_in_shop": [[int], False, (8, 32)],
        "blast_damage_friendly_fire": [[bool, str], False, None],
        "game_font": [[str], False]
    }
    schema_config_options = {
        "firstLevel": [[str], False],
        "DoNotLoadMainmenuLevel": [[str], False],
        "weather_AtmoRadius": [[str], False],
        "weather_ConfigFile": [[str], False]}
    schema_optional_content: dict[str, list[Any]] = {
        "name": [[str], True],
        "display_name": [[str], True],
        "description": [[str], True],

        "default_option": [[str], False],
        "forced_option": [[bool, str], False],
        "install_settings": [[list], False],
    }
    schema_install_settings = {
        "name": [[str], True],
        "description": [[str], True],
    }
    validated = validation.validate_dict(install_config, schema_top_level)
    if not validated:
        logger.info("<! MOD MANIFEST STRUCTURE FAILED VALIDATION !>")
        return validated

    # TODO: minimize and wrap comrem specific checks as legacy logic,
    # add proper checks for new base_dirs functionality
    display_name = install_config.get("display_name")
    mod_name = install_config.get("name")
    mod_lang = install_config.get("language") or "ru"
    logger.info(f"Validating mod '{display_name}' ({mod_name}, lang: {mod_lang})")
    logger.info("\tPASS: Simple manifest validation result")

    patcher_options = install_config.get("patcher_options")
    if patcher_options is not None:
        validated &= validation.validate_dict_constrained(patcher_options, schema_patcher_options)
        logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
                    "patcher options dict validation result")
        validated &= len(set(patcher_options.keys()) - set(schema_patcher_options.keys())) == 0
        logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
                    "only supported patcher options validation result")

    config_options = install_config.get("config_options")
    if validated and config_options is not None:
        validated &= validation.validate_dict_constrained(config_options, schema_config_options)
        logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
                    "config options dict validation result")
        validated &= len(set(config_options.keys()) - set(schema_config_options.keys())) == 0
        logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
                    "only supported config options validation result")

    prerequisites = install_config.get("prerequisites")
    if validated and prerequisites is not None:
        for prereq_entry in prerequisites:
            validated &= validation.validate_dict(prereq_entry, schema_prereqs)
        logger.info(f"\t{'PASS' if validated else 'FAIL'}: prerequisites validation result")

    incompatibles = install_config.get("incompatible")
    if validated and incompatibles is not None:
        for incompatible_entry in incompatibles:
            validated &= validation.validate_dict(incompatible_entry, schema_prereqs)
        logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
                    "incompatible content validation result")

    optional_content = install_config.get("optional_content")
    if validated and optional_content is not None:
        validated &= validation.validate_list(optional_content, schema_optional_content)
        logger.info(f"\t{'PASS' if validated else 'FAIL'}: optional content validation result")
        if not validated:
            return None

        for option in optional_content:
            if option.get("name") in ["base", "display_name", "build", "version"]:
                validated = False
                logger.error(f"\tFAIL: optional content name '"
                             f"{option.get('name')}' is one of the reserved service names, "
                             f"can't load mod properly!")
            install_settings = option.get("install_settings")
            if validated and install_settings is not None:
                # not ideal place to validate data compliance, but separating this
                # requires another round of nested reading and checks which is equally ugly
                validated &= (len(install_settings) > 1)
                logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
                            "multiple install settings exists for complex optional content '"
                            f"{option.get('name')}' validation result")
                validated &= validation.validate_list(install_settings, schema_install_settings)
                logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
                            f"install settings for content '{option.get('name')}' "
                            "validation result")
            patcher_options_additional = option.get("patcher_options")
            if validated and patcher_options_additional is not None:
                validated &= validation.validate_dict_constrained(patcher_options_additional,
                                                           schema_patcher_options)
                logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
                            "patcher options for additional content "
                            "validation result")

    # if not validated:
        # logger.info("<! MOD MANIFEST FAILED VALIDATION, SKIPPING DATA CHECK !>")
        # return validated

    # validated &= Mod.validate_install_config_paths(install_config, archive_file_list)

    logger.info("< MOD MANIFEST STRUCTURE VALIDATED >" if validated
                else "<! MOD MANIFEST STRUCTURE FAILED VALIDATION !>")
    return validated

class Mod:
    """Mod for HTA/EM, created from valid manifest.

    Contains mod data, installation instructions and related functions.
    """

    def __init__(self, manifest: dict[str, Any], distribution_dir: str) -> None:
        try:
            # primary required
            self.name: str = sanitize_filename(manifest["name"])[:64].strip()
            self.display_name: str = manifest["display_name"][:64].strip()
            self.description: str = manifest["description"][:2048].strip()
            self.authors: str = manifest["authors"][:256].strip()
            self.version: str = str(manifest.get("version"))[:64].strip()
            self.build: str = str(manifest.get("build"))[:7].strip()

            # primary with defaults
            self.language: str = parse_str_from_dict(manifest, "language",
                                                     default=SupportedLanguages.RU.value).lower()
            self.installment: str = parse_str_from_dict(manifest, "installment",
                                                   default=SupportedGames.EXMACHINA.value).lower()
            # if installment in SupportedGames.list_values():
                # self.installment = installment
            # else:
                # raise ValueError("Game installment is not in the supported games list!", installment)

            # compatibility
            self.prerequisites = manifest.get("prerequisites")
            self.incompatible = manifest.get("incompatible")
            # TODO: clean this up
            # to simplify hadling of incomps and reqs
            # we always work with them as if they are list of choices
            if self.prerequisites is None:
                self.prerequisites = []
            elif isinstance(self.prerequisites, list):
                if not self.prerequisites:
                    self.strict_requirements = True
                for prereq in self.prerequisites:
                    if isinstance(prereq.get("name"), str):
                        prereq["name"] = [prereq["name"]]
                    if isinstance(prereq.get("versions"), str):
                        prereq["versions"] = [prereq["versions"]]

            if self.incompatible is None:
                self.incompatible = []
            elif isinstance(self.incompatible, list):
                for incomp in self.incompatible:
                    if isinstance(incomp.get("name"), str):
                        incomp["name"] = [incomp["name"]]
                    if isinstance(incomp.get("versions"), str):
                        incomp["versions"] = [incomp["versions"]]

            # TODO: can be calculated once on loading reqs and incomps
            self.prerequisites_style = "mixed"
            self.incompatibles_style = "mixed"

            self.compatible_minor_versions = parse_bool_from_dict(
                manifest, "compatible_minor_versions", default=False)

            if self.compatible_minor_versions:
                self.compatible_patch_versions = True
            else:
                self.compatible_patch_versions = parse_bool_from_dict(
                    manifest, "compatible_patch_versions", default=False)

            self.safe_reinstall_options = parse_bool_from_dict(
                    manifest, "safe_reinstall_options", default=False)

            # child versions
            ...

            # secondary
            release_date = manifest.get("release_date")
            url = manifest.get("link")
            trailer_url = manifest.get("trailer_link")
            self.release_date: str = release_date[:32] if release_date else ""
            self.url: str = url[:128].strip() if url else ""
            self.trailer_url: str = trailer_url[:128].strip() if trailer_url else ""

            tags = manifest.get("tags")
            if tags is None:
                self.tags = [Mod.Tags.UNCATEGORIZED.name]
            else:
                # removing unknown values
                self.tags = list({tag.upper() for tag in tags} & set(Mod.Tags.list_names()))


            self.logo = manifest.get("logo")
            self.install_banner = manifest.get("install_banner")
            self.screenshots = manifest.get("screenshots")
            self.change_log = manifest.get("change_log")
            self.other_info = manifest.get("other_info")

            # TODO: make this runtime computed properties?
            self.individual_require_status = []
            self.individual_incomp_status = []


            translations = manifest.get("translations")
            self.translations = {}
            self.translations_loaded = {}
            if translations is not None:
                for translation in translations:
                    self.translations[translation] = is_known_lang(translation)

            if self.screenshots is None:
                self.screenshots = []
            elif isinstance(self.screenshots, list):
                for screenshot in self.screenshots:
                    if not isinstance(screenshot.get("img"), str):
                        continue

                    screenshot["img"] = screenshot["img"].replace("..", "")

                    if isinstance(screenshot.get("text"), str):
                        screenshot["text"] = screenshot["text"].strip()
                    else:
                        screenshot["text"] = ""
                    if isinstance(screenshot.get("compare"), str):
                        pass
                    else:
                        screenshot["compare"] = ""

            if self.change_log is None:
                self.change_log = ""

            if self.other_info is None:
                self.other_info = ""

            self.strict_requirements = True
            strict_requirements = manifest.get("strict_requirements")
            if strict_requirements is not None:
                if isinstance(strict_requirements, bool):
                    self.strict_requirements = strict_requirements
                else:
                    strict_requirements = str(strict_requirements)

                    if strict_requirements.lower() == "true":
                        self.strict_requirements = True
                    elif strict_requirements.lower() == "false":
                        pass
                    else:
                        raise ValueError("'strict_requirements' should be boolean!")


            patcher_version_requirement = manifest.get("patcher_version_requirement")
            if patcher_version_requirement is None:
                self.patcher_requirement = [">=1.10"]
            elif not isinstance(patcher_version_requirement, list):
                self.patcher_requirement = [str(patcher_version_requirement)]
            else:
                self.patcher_requirement = [str(ver) for ver in patcher_version_requirement]

            self.patcher_options = manifest.get("patcher_options")
            self.config_options = manifest.get("config_options")

            self.mod_files_root = str(distribution_dir)
            self.options_dict = {}
            self.no_base_content = False

            no_base_content = manifest.get("no_base_content")
            if no_base_content is not None:
                if isinstance(no_base_content, bool):
                    self.no_base_content = no_base_content
                else:
                    no_base_content = str(no_base_content)

                    if no_base_content.lower() == "true":
                        self.no_base_content = True
                    elif no_base_content.lower() == "false":
                        pass
                    else:
                        raise ValueError("'no_base_content' should be boolean!")

            # TODO: fix horrible duplication for verification and loading the mod
            if self.no_base_content:
                self.data_dirs = []
            else:
                base_dirs = manifest.get("base_dirs")
                if base_dirs:
                    self.data_dirs = [parse_simple_relative_path(one_dir) for one_dir in base_dirs]
                elif self.name == "community_patch":
                    base_dirs = ["patch"]
                elif self.name == "community_remaster":
                    base_dirs = ["patch", "remaster/data"]
                else:
                    base_dirs = ["data"]

            # TODO: add verification, fix naming of libs_dirs param
            self.bin_dirs = []
            libs_dirs = manifest.get("libs_dirs")
            if libs_dirs is not None:
                self.bin_dirs = [parse_simple_relative_path(one_dir) for one_dir in libs_dirs]
            elif self.name in ("community_path", "community_remaster"):
                self.bin_dirs = ["libs"]

            self.options_base_dir = ""
            options_base_dir = manifest.get("options_base_dir")
            if options_base_dir is not None:
                self.options_base_dir = parse_simple_relative_path(options_base_dir)

            self.optional_content = []

            optional_content = manifest.get("optional_content")
            if optional_content and optional_content is not None:
                if isinstance(optional_content, list):
                    for option in optional_content:
                        option_loaded = Mod.OptionalContent(option, self)
                        self.optional_content.append(option_loaded)
                        self.options_dict[option_loaded.name] = option_loaded
                else:
                    raise ValueError(f"Broken manifest for optional part of content '{self.name}'! "
                                     "Bad structure for 'optional_content'.")

            if self.no_base_content and not self.optional_content:
                raise ValueError("'no_base_content' mod should include at least one option!")

        except Exception as ex:
            er_message = f"Broken manifest for content '{self.name}'! {ex}"
            # logger.error(ex)
            # logger.error(er_message)
            raise ValueError(er_message)

    @property
    def id_str(self) -> str:
        return remove_substrings(
            sanitize_filename(
                self.name
                + str(Mod.Version(self.version)).replace(".", "")
                + self.build
                + f"{self.language}"
                + f"[{self.installment.replace('exmachina', 'em')}]"
                ), (" ", "_", "-"))

    @property
    def vanilla_mod(self) -> bool:
        return not self.prerequisites

    def load_translations(self) -> None:
        self.translations_loaded[self.language] = self
        self.load_gui_info()
        if self.translations:
            for lang in self.translations:
                lang_manifest_path = Path(self.mod_files_root, f"manifest_{lang}.yaml")
                if not lang_manifest_path.exists():
                    raise ValueError(f"Lang '{lang}' specified but manifest for it is missing! "
                                     f"(Mod: {self.name})")
                yaml_config = read_yaml(lang_manifest_path)
                config_validated = validate_manifest_struct(yaml_config)
                if config_validated:
                    mod_tr = Mod(yaml_config, self.mod_files_root)
                    if mod_tr.name != self.name:
                        raise ValueError("Service name mismatch in translation: "
                                         f"'{mod_tr.name}' name specified for translation, "
                                         f"but main mod name is '{self.name}'! "
                                         f"(Mod: {self.name}) (Translation: {mod_tr.language})")
                    # TODO: is this an actually valid limitation? Might want to allow that
                    if mod_tr.version != self.version:
                        raise ValueError("Version mismatch: "
                                         f"'{mod_tr.version}' specified for translation, "
                                         f"but main mod version is '{self.version}'! "
                                         f"(Mod: {self.name}) (Translation: {mod_tr.language})")
                    if sorted(mod_tr.tags) != sorted(self.tags):
                        raise ValueError("Tags mismatch: "
                                         f"{mod_tr.tags} specified for translation, "
                                         f"but main mod tags are {self.tags}! "
                                         f"(Mod: {self.name}) (Translation: {mod_tr.language})")
                    if mod_tr.language != lang:
                        raise ValueError("Language mismatch for translation manifest name and info: "
                                         f"{mod_tr.language} in manifest, {lang} in manifest name! "
                                         f"(Mod: {self.name})")
                    if mod_tr.language == self.language:
                        raise ValueError("Language duplication for translation manifest: "
                                         f"{lang} in manifest, but {lang} is main lang already! "
                                         f"(Mod: {self.name})")
                    if mod_tr.installment != self.installment:
                        raise ValueError("Game mismatch for translation manifest and the main mod: "
                                         f"{mod_tr.installment} in translation, {self.installment} "
                                         f"in manifest name! (Mod: {self.name})")

                    self.translations_loaded[lang] = mod_tr
                    mod_tr.load_gui_info()

        for lang, mod in self.translations_loaded.items():
            mod.known_language = is_known_lang(lang)
            if mod.known_language:
                mod.lang_label = tr(lang)
            else:
                mod.lang_label = lang

    def load_gui_info(self) -> None:
        supported_img_extensions = [".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"]
        self.change_log_content = ""
        if self.change_log:
            changelog_path = Path(self.mod_files_root, self.change_log)
            if changelog_path.exists() and changelog_path.suffix.lower() == ".md":
                with open(changelog_path, encoding="utf-8") as fh:
                    md = fh.read()
                    md = process_markdown(md)
                    self.change_log_content = md

        self.other_info_content = ""
        if self.other_info:
            other_info_path = Path(self.mod_files_root, self.other_info)
            if other_info_path.exists() and other_info_path.suffix.lower() == ".md":
                with open(other_info_path, encoding="utf-8") as fh:
                    md = fh.read()
                    md = process_markdown(md)
                    self.other_info_content = md

        self.logo_path = get_internal_file_path("assets/no_logo.png")
        if isinstance(self.logo, str):
            logo_path = Path(self.mod_files_root, self.logo)
            if logo_path.exists() and logo_path.suffix.lower() in supported_img_extensions:
                self.logo_path = str(logo_path)

        self.banner_path = None
        if isinstance(self.install_banner, str):
            banner_path = Path(self.mod_files_root, self.install_banner)
            if banner_path.exists() and banner_path.suffix.lower() in supported_img_extensions:
                self.banner_path = str(banner_path)

        for screen in self.screenshots:
            screen_path = Path(self.mod_files_root, screen["img"])
            if screen_path.exists() and screen_path.suffix.lower() in supported_img_extensions:
                screen["path"] = str(screen_path)
            else:
                screen["path"] = ""
                logger.warning(f"Missing path for screenshot ({screen['img']}) "
                               f"in mod {self.name}-{self.language}")

            compare_path = Path(self.mod_files_root, screen["compare"])
            if compare_path.exists() and compare_path.suffix.lower() in supported_img_extensions:
                screen["compare_path"] = str(compare_path)
                if screen["text"]:
                    screen["text"] += "\n"
                screen["text"] = screen["text"] + f'({tr("click_screen_to_compare")})'
            else:
                screen["compare_path"] = ""

        # we ignore screens which do not exist
        # TODO: do we?
        self.screenshots = [screen for screen in self.screenshots if screen["path"]]

        if ", " in self.authors:
            self.developer_title = "authors"
        else:
            self.developer_title = "author"

    def load_commod_compatibility(self, commod_version) -> None:
        for translation in self.translations_loaded.values():
            translation.commod_compatible, translation.commod_compatible_err = \
                translation.compatible_with_mod_manager(commod_version)
            translation.commod_compatible_err = remove_colors(translation.commod_compatible_err)

    def load_game_compatibility(self, game_installment) -> None:
        for translation in self.translations_loaded.values():
            translation.installment_compatible = self.installment == game_installment

    def load_session_compatibility(self, installed_content, installed_descriptions) -> None:
        for translation in self.translations_loaded.values():

            translation.compatible, translation.compatible_err = \
                translation.check_requirements(
                    installed_content,
                    installed_descriptions)

            translation.compatible_err = "\n".join(translation.compatible_err).strip()

            translation.prevalidated, translation.prevalidated_err = \
                translation.check_incompatibles(
                    installed_content,
                    installed_descriptions)

            translation.prevalidated_err = "\n".join(translation.prevalidated_err).strip()

            (translation.is_reinstall, translation.can_be_reinstalled,
             translation.reinstall_warning, translation.existing_version) = \
                translation.check_reinstallability(
                    installed_content,
                    installed_descriptions)

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
                base_work_path = Path(self.mod_files_root, self.options_base_dir, wip_setting.name, "data")
                installation_decision = install_settings[install_setting]
                if installation_decision == "yes":
                    mod_files.append(base_work_path)
                elif installation_decision == "skip":
                    logger.debug(f"Skipping option {install_setting}")
                    continue
                else:
                    custom_install_method = install_settings[install_setting]
                    custom_install_work_path = os.path.join(
                        self.mod_files_root,
                        self.options_base_dir,
                        wip_setting.name,
                        custom_install_method,
                        "data")

                    mod_files.append(base_work_path)
                    mod_files.append(custom_install_work_path)
                if installation_decision != "skip":
                    await callback_status(tr("copying_options_please_wait"))

                start = datetime.now()
                await copy_from_to_async_fast(mod_files, game_data_path, callback_progbar)
                end = datetime.now()
                logger.debug(f"{(end - start).microseconds / 1000000} seconds took fast copy")

                mod_files.clear()
        except Exception as ex:
            logger.exception(exc_info=ex)
            return False
        else:
            return True

    def check_requirement(self, prereq: dict, existing_content: dict,
                          existing_content_descriptions: dict,
                          is_compatch_env: bool) -> tuple[bool, str]:
        """Return bool check success result and an error message string."""
        error_msg = []
        required_mod_name = None

        name_validated = True
        version_validated = True
        optional_content_validated = True

        for possible_prereq_mod in prereq["name"]:
            existing_mod = existing_content.get(possible_prereq_mod)
            if existing_mod is not None:
                required_mod_name = possible_prereq_mod

        if required_mod_name is None:
            name_validated = False

        # if trying to install compatch-only mod on comrem
        if (required_mod_name == "community_patch"
           and existing_content.get("community_remaster") is not None
           and self.name != "community_remaster"
           and "community_remaster" not in prereq["name"]):
            name_validated = False
            error_msg.append(f"{tr('compatch_mod_incompatible_with_comrem')}")

        or_word = f" {tr('or')} "
        and_word = f" {tr('and')} "
        only_technical_name_available = False

        name_label = []
        for service_name in prereq["name"]:
            existing_mod = existing_content.get(service_name)
            if existing_mod is not None:
                name_label.append(existing_mod["display_name"])
            else:
                known_name = get_known_mod_display_name(service_name)
                if known_name is None:
                    name_label.append(service_name)
                    only_technical_name_available = True
                else:
                    name_label.append(known_name)

        name_label = or_word.join(name_label)
        version_label = ""
        optional_content_label = ""

        prereq_versions = prereq.get("versions")
        if prereq_versions and prereq_versions is not None:
            version_label = (f', {tr("of_version")}: '
                             f'{and_word.join(prereq.get("versions"))}')
            if name_validated:
                compare_ops = set()
                for version_string in prereq_versions:
                    version = version_string
                    if version[:2] == ">=":
                        compare_operation = operator.ge
                    elif version[:2] == "<=":
                        compare_operation = operator.le
                    elif version[:1] == ">":
                        compare_operation = operator.gt
                    elif version[:1] == "<":
                        compare_operation = operator.lt
                    else:  # default "version" treated the same as "==version":
                        compare_operation = operator.eq

                    for sign in (">", "<", "="):
                        version = version.replace(sign, "")

                    installed_version = existing_content[required_mod_name]["version"]
                    parsed_existing_ver = Mod.Version(installed_version)
                    parsed_required_ver = Mod.Version(version)

                    version_validated = compare_operation(parsed_existing_ver, parsed_required_ver)
                    compare_ops.add(compare_operation)
                    if (compare_operation is operator.eq and
                        parsed_required_ver.identifier and
                        parsed_existing_ver.identifier != parsed_required_ver.identifier):
                                version_validated = False

                compare_ops = list(compare_ops)
                len_ops = len(compare_ops)
                if len_ops == 1 and operator.eq in compare_ops:
                    self.prerequisites_style = "strict"
                elif len_ops == 2 and operator.eq not in compare_ops:
                    if ((compare_ops[0] in (operator.ge, operator.gt)
                       and compare_ops[1] in (operator.le, operator.lt)) or
                        (compare_ops[0] in (operator.lt, operator.lt)
                          and compare_ops[1] in (operator.ge, operator.gt))):
                        self.prerequisites_style = "range"
                    else:
                        self.prerequisites_style = "mixed"
                else:
                    self.prerequisites_style = "mixed"

        optional_content = prereq.get("optional_content")
        if optional_content and optional_content is not None:
            optional_content_label = (f', {tr("including_options").lower()}: '
                                      f'{", ".join(prereq["optional_content"])}')
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
                    else:
                        logger.info(f"\tPASS: content requirement met: {option} "
                                    f"- of required mod: {name_label}")

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
                installed_description = installed_description.strip("\n\n")  # noqa: B005
                error_msg_entry = (f'\n{tr("version_available").capitalize()}:\n'
                                   f'{remove_colors(installed_description)}')
                if error_msg_entry not in error_msg:
                    error_msg.append(error_msg_entry)

            else:
                # in case when we working with compatched game but mod requires comrem
                # it would be nice to tip a user that this is incompatibility in itself
                if is_compatch_env and "community_remaster" in prereq["name"]:
                    installed_description = existing_content_descriptions.get("community_patch")
                    error_msg_entry = (f'\n{tr("version_available").capitalize()}:\n'
                                       f'{remove_colors(installed_description)}')
                    if error_msg_entry not in error_msg:
                        error_msg.append(error_msg_entry)
        prereq["name_label"] = name_label
        prereq["mention_versions"] = True
        return validated, error_msg

    def check_requirements(self, existing_content: dict, existing_content_descriptions: dict,
                           patcher_version: str | float = "") -> tuple[bool, list[str]]:
        """Return bool for cumulative check success result and a list of error message string."""
        error_msg = []

        requirements_met = True
        is_compatch_env = ("community_remaster" not in existing_content and
                           "community_patch" in existing_content)

        if patcher_version and not self.compatible_with_mod_manager(patcher_version):
            requirements_met &= False
            error_msg.append(f"{tr('usupported_patcher_version')}: "
                             f"{self.display_name} - {self.patcher_requirement}"
                             f" > {patcher_version}")

        self.individual_require_status.clear()
        for prereq in self.prerequisites:
            if self.name == "community_remaster" and prereq["name"][0] == "community_patch":
                continue

            validated, mod_error = self.check_requirement(prereq,
                                                          existing_content, existing_content_descriptions,
                                                          is_compatch_env)
            self.individual_require_status.append((prereq, validated, mod_error))
            if mod_error:
                error_msg.extend(mod_error)
            requirements_met &= validated

        # we will handle more complex case in check_incompatibles
        if requirements_met and self.strict_requirements and self.vanilla_mod:
            fake_req = {"name_label": f"{tr('clean').capitalize()} " + tr(self.installment),
                        "mention_versions": False
                        }
            if set(existing_content.keys()) - set([self.name]):
                validated_vanilla_mod = False
                mod_error = tr("cant_install_mod_for_vanilla")
                error_msg.append(mod_error)
            else:
                validated_vanilla_mod = True
                mod_error = ""
            self.individual_require_status.append(
                (fake_req, validated_vanilla_mod, [mod_error]))
            requirements_met &= validated_vanilla_mod

        # if error_msg:
            # error_msg.append(f'\n{tr("check_for_a_new_version")}')

        return requirements_met, error_msg

    def check_reinstallability(self, existing_content: dict,
                               existing_content_descriptions: dict) -> tuple[bool, bool, str, str]:
        """Return is_reinstallation: bool, can_be_installed: bool, warning_text: str."""
        previous_install = existing_content.get(self.name)
        comrem_on_compatch = False

        if self.name == "community_remaster":
            compatch_preivous = existing_content.get("community_patch")
            if previous_install is None:
                previous_install = compatch_preivous
                comrem_on_compatch = True

        if previous_install is None:
            # no reinstall, can be installed
            return False, True, "", None

        old_options = set(previous_install.keys()) - set(["base", "version", "display_name",
                                                          "build", "language", "installment"])
        new_options = set([opt.name for opt in self.optional_content])

        self_and_prereqs = [self.name, "community_patch"]
        for prereq in self.prerequisites:
            self_and_prereqs.extend(prereq["name"])

        if previous_install.get("language") != self.language:
            return True, False, tr("cant_reinstall_different_lang"), previous_install

        existing_other_mods = set(existing_content.keys()) - set(self_and_prereqs)
        if existing_other_mods:
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

        existing_version = Mod.Version(previous_install["version"])
        this_version = Mod.Version(self.version)

        over_other_version_warning = tr("cant_reinstall_over_other_version")

        # special compat settings can make mod forward compatible
        # backwards compatibility is not supported
        if self.compatible_patch_versions:
            if existing_version > this_version:
                is_compatible_version = False
                over_other_version_warning = tr("cant_reinstall_over_newer_version")
            else:
                existing_version.patch = 0
                this_version.patch = 0

                if self.compatible_minor_versions:
                    existing_version.minor = 0
                    this_version.minor = 0

                is_compatible_version = existing_version == this_version
        else:
            is_compatible_version = existing_version == this_version

        if not is_compatible_version:
            return True, False, over_other_version_warning, previous_install

        if self.build == previous_install["build"]:
            if not self.optional_content and not comrem_on_compatch:
                # is reinstall, simple mod, safe reinstall
                return True, True, tr("can_reinstall"), previous_install

            if old_options == new_options:
                # is reinstall, complex mod, safe reinstall, forced options
                if not self.safe_reinstall_options:
                    warning = tr("to_increase_compat_options_are_limited")
                else:
                    warning = tr("can_reinstall")
                return True, True, warning, previous_install

            if comrem_on_compatch:
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
            if comrem_on_compatch:
                return True, True, tr("can_reinstall"), previous_install

            return True, False, tr("cant_reinstall_with_different_options"), previous_install

        # self.build < previous_install["build"]
        return True, False, tr("cant_reinstall_over_newer_build"), previous_install

    def check_incompatible(self, incomp: dict, existing_content: dict,
                           existing_content_descriptions: dict) -> tuple[bool, list]:
        error_msg = []
        name_incompat = False
        version_incomp = False
        optional_content_incomp = False

        incomp_mod_name = None
        for possible_incomp_mod in incomp["name"]:
            existing_mod = existing_content.get(possible_incomp_mod)
            if existing_mod is not None:
                incomp_mod_name = possible_incomp_mod

        or_word = f" {tr('or')} "
        # and_word = f" {tr('and')} "
        only_technical_name_available = False

        name_label = []
        for service_name in incomp["name"]:
            existing_mod = existing_content.get(service_name)
            if existing_mod is not None:
                name_label.append(existing_mod["display_name"])
            else:
                known_name = get_known_mod_display_name(service_name)
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

            incomp_versions = incomp.get("versions")
            if incomp_versions and incomp_versions is not None:
                installed_version = existing_content[incomp_mod_name]["version"]

                version_label = (f', {tr("of_version")}: '
                                 f'{or_word.join(incomp.get("versions"))}')
                compare_ops = set()
                for version_string in incomp_versions:
                    version = version_string
                    if version[:2] == ">=":
                        compare_operation = operator.ge
                    elif version[:2] == "<=":
                        compare_operation = operator.le
                    elif version[:1] == ">":
                        compare_operation = operator.gt
                    elif version[:1] == "<":
                        compare_operation = operator.lt
                    else:  # default "version" treated the same as "==version":
                        compare_operation = operator.eq

                    for sign in (">", "<", "="):
                        version = version.replace(sign, "")

                    parsed_existing_ver = Mod.Version(installed_version)
                    parsed_incompat_ver = Mod.Version(version)

                    version_incomp = compare_operation(parsed_existing_ver, parsed_incompat_ver)

                    compare_ops.add(compare_operation)
                    # while we ignore postfix for less/greater ops, we want to have an ability
                    # to make a specifix version with postfix incompatible
                    if (compare_operation is operator.eq
                       and parsed_incompat_ver.identifier
                       and parsed_existing_ver.identifier != parsed_incompat_ver.identifier):
                        version_incomp = True

                compare_ops = list(compare_ops)
                len_ops = len(compare_ops)
                if len_ops == 1 and operator.eq in compare_ops:
                    self.incompatibles_style = "strict"
                elif len_ops == 2 and operator.eq not in compare_ops:
                    if ((compare_ops[0] in (operator.ge, operator.gt)
                         and compare_ops[1] in (operator.le, operator.lt))
                        or (compare_ops[0] in (operator.lt, operator.lt)
                            and compare_ops[1] in (operator.ge, operator.gt))):
                        self.incompatibles_style = "range"
                    else:
                        self.incompatibles_style = "mixed"
                else:
                    self.incompatibles_style = "mixed"

            else:
                version_incomp = True

            optional_content = incomp.get("optional_content")

            if optional_content and optional_content is not None:

                optional_content_label = (f', {tr("including_options").lower()}: '
                                          f'{or_word.join(incomp.get("optional_content"))}')

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
                    installed_description = installed_description.strip("\n\n")  # noqa: B005
                    error_msg.append(f'\n{tr("version_available").capitalize()}:\n'
                                     f'{remove_colors(installed_description)}')
                else:
                    # TODO: check if this path even possible
                    raise NotImplementedError
            incomp["name_label"] = name_label
            return incompatible_with_game_copy, error_msg

        incomp["name_label"] = name_label
        return False, ""

    def check_incompatibles(self, existing_content: dict,
                            existing_content_descriptions: dict) -> tuple[bool, list]:
        error_msg = []
        compatible = True

        self.individual_incomp_status.clear()

        for incomp in self.incompatible:
            incompatible_with_game_copy, mod_error = self.check_incompatible(
                incomp, existing_content, existing_content_descriptions)
            self.individual_incomp_status.append((incomp, not incompatible_with_game_copy,
                                                 mod_error))
            if mod_error:
                error_msg.extend(mod_error)
            compatible &= (not incompatible_with_game_copy)

        if compatible and self.strict_requirements and self.prerequisites:
            self_and_prereqs = [self.name, "community_patch"]
            for prereq in self.prerequisites:
                self_and_prereqs.extend(prereq["name"])
            existing_other_mods = set(existing_content.keys()) - set(self_and_prereqs)
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
                fake_incomp = {"name_label": existing_string,
                               "mention_versions": False}
                self.individual_incomp_status.append(
                    (fake_incomp, False, [f'{tr("already_installed")}: {existing_string}']))
        return compatible, error_msg

    def load_legacy_path_defaults(self) -> None:
        """Needed to support older mods that existed before the configurable mod file structure.

        Early mods, including ComPatch/ComRem
        do not specify base dirs in manifest so to contain special case handling
        and to make them installable with ComMod 2.1+ we need this fallback
        """
        if self.no_base_content:
            self.data_dirs = []
        elif not self.data_dirs:
            if self.name == "community_patch":
                self.data_dirs = ["patch"]
            elif self.name == "community_remaster":
                self.data_dirs = ["patch", "remaster/data"]
            else:
                self.data_dirs = ["data"]

        if not self.bin_dirs and self.name in ("community_remaster", "community_patch"):
            self.bin_dirs = ["libs"]

        if self.optional_content:
            if not self.options_base_dir and self.name == "community_remaster":
                self.options_base_dir = "remaster"
            else:
                # TODO: move these defaults to __init__
                self.options_base_dir = ""

    def validate_mod_paths(
            self, mod_config_path: str,
            archive_file_list: list[ZipInfo] | py7zr.ArchiveFileList | None = None):
        # TODO: move to __init__ after loading legacy path fallbacks
        # self.base_data_dirs = [parse_simple_relative_path(dir) for dir in self.base_data_dirs]
        # self.bin_dirs = [parse_simple_relative_path(dir) for dir in self.bin_dirs]
        # self.options_base_dir = parse_simple_relative_path(self.options_base_dir)

        # if archive_file_list is not None:
        #     if isinstance(archive_file_list, py7zr.ArchiveFileList):
        #         archive_files = []
        #         for file in archive_file_list:
        #             if file.emptystream:
        #                 archive_files.append(f"{file.filename}/")
        #             else:
        #                 archive_files.append(file.filename)
        #     elif isinstance(archive_file_list, list[ZipInfo]):
        #         archive_files = [file.filename for file in archive_file_list]
        #     else:
        #         raise NotImplemented("Wrong archive type passed to validator")

        #     if not self.no_base_content:
        #         mod_base_paths = []
        #         if self.base_data_dirs:
        #             # TODO: check that using Path instead of str is not breaking checks here
        #             mod_base_paths = [Path(mod_config_path).parent / dir for dir in self.base_data_dirs]
        #         else:
        #             mod_base_paths.append(Path(mod_config_path).parent / "data")

        #         if self.bin_dirs:
        #             mod_base_paths.extend(Path(mod_config_path).parent / dir for dir in self.bin_dirs)

        #         data_dir_validated = all(base_path in archive_files for base_path in mod_base_paths)
        #         validated &= data_dir_validated
        #         if data_dir_validated:
        #             logger.info("\tPASS: Archived base mod data folder validation result")
        #         else:
        #             logger.error("\tFAIL: Archived base mod data folder validation fail, "
        #                          f"expected path not found: {mod_base_paths}")

        #     if not validated:
        #         logger.info("<! BASE FILES VALIDATION FAILED, SKIPPING FURTHER CHECKS !>")
        #         return validated

        #     # TODO: replaced None check with empty check, is this OK?
        #     if self.optional_content:
        #         for option in self.optional_content:
        #             validated &= mod_config_path.replace(
        #                 "manifest.yaml", f'{self.options_base_dir}{option.get("name")}/') in archive_files
        #             if option.get("install_settings") is not None:
        #                 for setting in option.get("install_settings"):
        #                     validated &= mod_config_path.replace(
        #                         "manifest.yaml",
        #                         f'{option.get("name")}/{setting.get("name")}/data/') in archive_files
        #                     logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
        #                                 f"Archived optional content '{option.get('name')}' "
        #                                 f"install setting '{setting.get('name')}' "
        #                                 f"data folder validation result")
        #             else:
        #                 validated &= mod_config_path.replace(
        #                     "manifest.yaml", f'{option.get("name")}/data/') in archive_files
        #             logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
        #                         f"Archived optional content '{option.get('name')}' "
        #                         "data folder validation result")
        # else:

        validated = True

        mod_root_dir = Path(mod_config_path).parent
        if not self.no_base_content:
            mod_base_paths = []
            if self.data_dirs:
                mod_base_paths = [Path(mod_root_dir) / base_dir for base_dir in self.data_dirs]

            if self.bin_dirs:
                mod_base_paths.extend(Path(mod_root_dir) / bin_dir for bin_dir in self.bin_dirs)

            # TODO: is checking for is_dir enough? How it works for non existing but valid paths?
            data_dir_validated = all(base_path.is_dir() for base_path in mod_base_paths)

            validated &= data_dir_validated
            if not data_dir_validated:
                logger.error('\tFAIL: base mod data folders validation fail, '
                             'expected path not exists: '
                             f'{Path(mod_root_dir, "data")}')
            else:
                logger.info("\tPASS: base mod data folders validation result")

        if self.optional_content:
            for option in self.optional_content:
                validated &= Path(mod_root_dir, self.options_base_dir, option.get("name")).is_dir()
                if option.get("install_settings") is not None:
                    for setting in option.get("install_settings"):
                        validated &= Path(mod_root_dir,
                                          self.options_base_dir,
                                          option.get("name"),
                                          setting.get("name"),
                                          "data").is_dir()
                        logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
                                    f"optional content '{option.get('name')}' "
                                    f"install setting '{setting.get('name')}' "
                                    f"data folder validation result")
                else:
                    validated &= Path(mod_root_dir,
                                      self.options_base_dir,
                                      option.get("name"),
                                      "data").is_dir()
                logger.info(f"\t{'PASS' if validated else 'FAIL'}: "
                            f"optional content '{option.get('name')}' "
                            "data folder validation result")
        logger.info("< MOD FILES VALIDATED >" if validated
                        else "<! MOD FILES FAILED VALIDATION !>")
        return validated

    def compatible_with_mod_manager(self, patcher_version: str | float) -> tuple(bool, str):
        compatible = True

        patcher_version_parsed = Mod.Version(str(patcher_version))
        patcher_version_parsed.identifier = None
        error_msg = ""
        mod_manager_too_new = False

        for version_string in self.patcher_requirement:
            version = version_string
            if version[:2] == ">=":
                compare_operation = operator.ge
            elif version[:2] == "<=":
                compare_operation = operator.le
            elif version[:1] == ">":
                compare_operation = operator.gt
            elif version[:1] == "<":
                compare_operation = operator.lt
            elif version[:1] == "=":
                compare_operation = operator.eq
            else:  # default "version" treated the same as ">=version":
                compare_operation = operator.ge

            for sign in (">", "<", "="):
                version = version.replace(sign, "")

            parsed_required_ver = Mod.Version(version)
            parsed_required_ver.identifier = None

            if compare_operation is operator.eq and parsed_required_ver < patcher_version_parsed:
                mod_manager_too_new = True

            compatible &= compare_operation(patcher_version_parsed, parsed_required_ver)

        if not compatible:
            logger.warning(f"{self.display_name} manifest asks for an other mod manager version. "
                           f"Required: {self.patcher_requirement}, available: {patcher_version}")
            and_word = f" {tr('and')} "

            error_msg = (tr("usupported_patcher_version",
                            content_name=fconsole(self.display_name, bcolors.WARNING),
                            required_version=and_word.join(self.patcher_requirement),
                            current_version=patcher_version,
                            github_url=fconsole(COMPATCH_GITHUB, bcolors.HEADER)))

            if mod_manager_too_new and self.name == "community_remaster":
                error_msg += f"\n\n{tr('check_for_a_new_version')}\n\n"
                error_msg += tr("demteam_links",
                                discord_url=fconsole(DEM_DISCORD, bcolors.HEADER),
                                deuswiki_url=fconsole(WIKI_COMREM, bcolors.HEADER),
                                github_url=fconsole(COMPATCH_GITHUB, bcolors.HEADER)) + "\n"

        return compatible, error_msg.strip()

    def get_full_install_settings(self) -> dict:
        """Return settings that describe default installation of the mod."""
        install_settings = {}
        install_settings["base"] = "yes"
        if self.optional_content:
            for option in self.optional_content:
                if option.default_option is not None:
                    install_settings[option.name] = option.default_option
                else:
                    install_settings[option.name] = "yes"
        return install_settings

    def get_install_description(self, install_config_original: dict) -> list[str]:
        """Return list of strings with localised description of the given mod installation config."""
        install_config = install_config_original.copy()

        descriptions = []

        base_part = install_config.pop("base")
        if base_part == "yes":
            description = fconsole(f"{self.display_name}\n", bcolors.WARNING) + self.description
            descriptions.append(description)
        if len(install_config) > 0:
            ok_to_install = [entry for entry in install_config if install_config[entry] != "skip"]
            if len(ok_to_install) > 0:
                descriptions.append(f"{tr('including_options')}:")
        for mod_part in install_config:
            setting_obj = self.options_dict.get(mod_part)
            if install_config[mod_part] == "yes":
                description = (fconsole(f"* {setting_obj.display_name}\n", bcolors.OKBLUE)
                               + setting_obj.description)
                descriptions.append(description)
            elif install_config[mod_part] != "skip":
                description = (fconsole(f"* {setting_obj.display_name}\n", bcolors.OKBLUE)
                               + setting_obj.description)
                if setting_obj.install_settings is not None:
                    for setting in setting_obj.install_settings:
                        if setting.get("name") == install_config[mod_part]:
                            install_description = setting.get("description")
                            description += (f"\t** {tr('install_setting_title')}: "
                                            f"{install_description}")
                descriptions.append(description)
        return descriptions

    class Tags(Enum):
        BUGFIX = 0
        GAMEPLAY = 1
        STORY = 2
        VISUAL = 3
        AUDIO = 4
        WEAPONS = 5
        VEHICLES = 6
        UI = 7
        BALANCE = 8
        HUMOR = 9
        UNCATEGORIZED = 10

        @classmethod
        def list_values(cls) -> list[int]:
            return [c.value for c in cls]

        @classmethod
        def list_names(cls) -> list[str]:
            return [c.name for c in cls]

    @dataclass
    class Screenshot:
        img: str
        text: str | None = None
        compare: str | None = None

        @property
        def text(self) -> str | None:
            return self.compare if isinstance(self._compare, str) else None

        @text.setter
        def text(self, value) -> None:
            if isinstance(value, str):
                self.text = value

        @property
        def compare(self) -> str | None:
            return self.compare if isinstance(self._compare, str) else None


    class OptionalContent:
        def __init__(self, description: dict, parent: Mod) -> None:
            self.name = str(description.get("name"))[:64].replace("/", "").replace("\\", "").replace(".", "")
            self.display_name = description.get("display_name")[:64]
            self.description = description.get("description")[:512].strip()

            self.install_settings = description.get("install_settings")
            self.default_option = None
            self.forced_option = False
            default_option = description.get("default_option")

            if self.install_settings is not None:
                for custom_setting in self.install_settings:
                    custom_setting["name"] = custom_setting["name"][:64].strip()
                    custom_setting["description"] = custom_setting["description"][:128].strip()
                if default_option in [opt["name"] for opt in self.install_settings]:
                    self.default_option = default_option
                elif isinstance(default_option, str):
                    if default_option.lower() == "skip":
                        self.default_option = "skip"
                elif default_option is None:
                    pass  # default behavior if default option is not specified
                else:
                    er_message = (f"Incorrect default option '{default_option}' "
                                  f"for '{self.name}' in content manifest! "
                                  f"Only 'skip' or names present in install settings are allowed")
                    logger.error(er_message)
                    raise KeyError(er_message)
            # TODO: what if not str?
            elif isinstance(default_option, str):
                    if default_option.lower() == "skip":
                        self.default_option = "skip"
                    elif default_option.lower() == "install":
                        pass  # same as default
                    else:
                        er_message = (f"Incorrect default option '{default_option}' "
                                      f"for '{self.name}' in content manifest. "
                                      f"Only 'skip' or 'install' is allowed for simple options!")

            forced_option = description.get("forced_option")
            if forced_option is not None:
                if isinstance(forced_option, bool):
                    self.forced_option = forced_option
                else:
                    forced_option = str(forced_option)

                    if forced_option.lower() == "true":
                        self.forced_option = True
                    elif forced_option.lower() == "false":
                        pass  # default
                    else:
                        raise ValueError("'forced_option' should be boolean!")

            if self.default_option is not None and self.forced_option:
                er_message = (f"Mod option {self.name} specifies both default_option and forced_option flags!"
                              " Should only have one or another.")
                logger.error(er_message)
                raise KeyError(er_message)

            patcher_options = description.get("patcher_options")
            if patcher_options is not None:
                for option in patcher_options:
                    # optional content can overwrite base mode options
                    parent.patcher_options[option] = patcher_options[option]

    @total_ordering
    class Version:
        class VersionPartCounts(Enum):
            NO_VERSION = 0
            MAJOR_ONLY = 1
            SHORT_WITH_MINOR = 2
            FULL = 3
            FULL_WITH_ID = 4

        def __init__(self, version_str: str) -> None:
            self.major = "0"
            self.minor = "0"
            self.patch = "0"
            self.identifier = ""

            identifier_index = version_str.find("-")
            has_minor_ver = "." in version_str

            if identifier_index != -1:
                self.identifier = version_str[identifier_index + 1:]
                numeric_version = version_str[:identifier_index]
            else:
                numeric_version = version_str

            if has_minor_ver:
                version_split = numeric_version.split(".")
                version_levels = len(version_split)
                if version_levels >= self.VersionPartCounts.MAJOR_ONLY.value:
                    self.major = version_split[0][:4]

                if version_levels >= self.VersionPartCounts.SHORT_WITH_MINOR.value:
                    self.minor = version_split[1][:4]

                if version_levels >= self.VersionPartCounts.FULL.value:
                    self.patch = version_split[2][:10]

                if version_levels >= self.VersionPartCounts.FULL_WITH_ID.value:
                    self.patch = "".join(version_split[2:])
            else:
                self.major = numeric_version

            self.is_numeric = all(part.isnumeric() for part in [self.major, self.minor, self.patch])

        def __str__(self) -> str:
            version = f"{self.major}.{self.minor}.{self.patch}"
            if self.identifier:
                version += f"-{self.identifier}"
            return version

        def __repr__(self) -> str:
            return str(self)

        def _is_valid_operand(self, other: object) -> bool:
            return isinstance(other, Mod.Version)

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

        def __lt__(self, other: Mod.Version) -> bool:
            if not self._is_valid_operand(other):
                return NotImplemented

            if self.is_numeric and other.is_numeric:
                return ((int(self.major), int(self.minor), int(self.patch))
                        <
                        (int(other.major), int(other.minor), int(other.patch)))

            return ((self.major.lower(), self.minor.lower(), self.patch.lower())
                    <
                    (self.major.lower(), self.minor.lower(), self.patch.lower()))
