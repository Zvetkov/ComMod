from __future__ import annotations

import logging
import operator
import os
import typing
from datetime import datetime
from enum import Enum
from functools import total_ordering
from pathlib import Path
from typing import Any, Awaitable, Optional
from zipfile import ZipInfo

from pathvalidate import sanitize_filename
from py7zr import py7zr

from console.color import bcolors, fconsole, remove_colors
from data import get_known_mod_display_name, is_known_lang
from file_ops import (copy_from_to, copy_from_to_async_fast,
                      get_internal_file_path, process_markdown, read_yaml)
from localisation import COMPATCH_GITHUB, DEM_DISCORD, WIKI_COMPATCH, tr

logger = logging.getLogger('dem')


class GameInstallments(Enum):
    ALL = 0
    EXMACHINA = 1
    M113 = 2
    ARCADE = 3
    UNKNOWN = 4


class Mod:
    '''Mod for HTA/EM, contains mod data, installation instructions
       and related functions'''
    def __init__(self, yaml_config: dict, distribution_dir: str) -> None:
        try:
            self.vanilla_mod = False
            self.name = \
                yaml_config.get("name")[:64].replace("/", "").replace("\\", "").replace(".", "").strip()

            installment = yaml_config.get("installment")
            if installment is None:
                self.installment = "exmachina"
            else:
                installment = installment.strip()
                match installment.lower():
                    case "exmachina" | "m113" | "arcade":
                        self.installment = installment.lower()
                    case _:
                        raise ValueError(f"Game installment id '{installment}' "
                                         "is not in the supported games list!")

            self.display_name = yaml_config.get("display_name")[:64].strip()
            self.description = yaml_config.get("description")[:2048].strip()
            self.language = yaml_config.get("language")
            self.authors = yaml_config.get("authors")[:256].strip()
            self.version = str(yaml_config.get("version"))[:64].strip()
            self.build = str(yaml_config.get("build"))[:7].strip()
            if self.language is None:
                self.language = "ru"

            self.id = sanitize_filename(
                self.name
                + str(Mod.Version(self.version)).replace(".", "")
                + self.build
                + f"{self.language}"
                + f"[{self.installment.replace('exmachina', 'em')}]"
                ).replace(" ", "").replace("_", "").replace("-", "")

            url = yaml_config.get("link")
            trailer_url = yaml_config.get("trailer_link")
            self.url = url[:128].strip() if url is not None else ""
            self.trailer_url = trailer_url[:128].strip() if trailer_url is not None else ""

            self.prerequisites = yaml_config.get("prerequisites")
            self.incompatible = yaml_config.get("incompatible")
            self.release_date = yaml_config.get("release_date")
            self.install_banner = yaml_config.get("install_banner")
            self.tags = yaml_config.get("tags")
            self.logo = yaml_config.get("logo")
            self.screenshots = yaml_config.get("screenshots")
            self.change_log = yaml_config.get("change_log")
            self.other_info = yaml_config.get("other_info")
            self.compatible_minor_versions = False
            self.compatible_patch_versions = False
            self.safe_reinstall_options = False

            compatible_minor_versions = yaml_config.get("compatible_minor_versions")
            if compatible_minor_versions is not None:
                if isinstance(compatible_minor_versions, bool):
                    self.compatible_minor_versions = compatible_minor_versions
                else:
                    compatible_minor_versions = str(compatible_minor_versions)

                    if compatible_minor_versions.lower() == "true":
                        self.compatible_minor_versions = True
                    elif compatible_minor_versions.lower() == "false":
                        pass
                    else:
                        raise ValueError("'compatible_minor_versions' should be boolean!")

            if self.compatible_minor_versions:
                self.compatible_patch_versions = True
                if yaml_config.get("compatible_patch_versions") is not None:
                    self.logger.debug(f"Warn for content '{self.name}': "
                                      "when compatible_minor_versions is True, "
                                      "compatible_patch_versions is automatically True. No need to specify.")
            else:
                compatible_patch_versions = yaml_config.get("compatible_patch_versions")
                if compatible_patch_versions is not None:
                    if isinstance(compatible_patch_versions, bool):
                        self.compatible_patch_versions = compatible_patch_versions
                    else:
                        compatible_patch_versions = str(compatible_patch_versions)

                        if compatible_patch_versions.lower() == "true":
                            self.compatible_patch_versions = True
                        elif compatible_patch_versions.lower() == "false":
                            pass
                        else:
                            raise ValueError("'compatible_patch_versions' should be boolean!")

            safe_reinstall_options = yaml_config.get("safe_reinstall_options")
            if safe_reinstall_options is not None:
                if isinstance(safe_reinstall_options, bool):
                    self.safe_reinstall_options = safe_reinstall_options
                else:
                    safe_reinstall_options = str(safe_reinstall_options)

                    if safe_reinstall_options.lower() == "true":
                        self.safe_reinstall_options = True
                    elif safe_reinstall_options.lower() == "false":
                        pass
                    else:
                        raise ValueError("'safe_reinstall_options' should be boolean!")

            self.individual_require_status = []
            self.individual_incomp_status = []
            self.requirements_style = "mixed"
            self.incompatibles_style = "mixed"

            translations = yaml_config.get("translations")
            self.translations = {}
            self.translations_loaded = {}
            if translations is not None:
                for translation in translations:
                    self.translations[translation] = is_known_lang(translation)

            if self.release_date is None:
                self.release_date = ""

            if self.tags is None:
                self.tags = [Mod.Tags.UNCATEGORIZED.name]
            else:
                # removing unknown values
                self.tags = list(set([tag.upper() for tag in self.tags]) & set(Mod.Tags.list_names()))

            if self.screenshots is None:
                self.screenshots = []
            elif isinstance(self.screenshots, list):
                for screenshot in self.screenshots:
                    if not isinstance(screenshot.get("img"), str):
                        next

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
            strict_requirements = yaml_config.get("strict_requirements")
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

            if not self.prerequisites:
                self.vanilla_mod = True

            if self.incompatible is None:
                self.incompatible = []
            elif isinstance(self.incompatible, list):
                for incomp in self.incompatible:
                    if isinstance(incomp.get("name"), str):
                        incomp["name"] = [incomp["name"]]
                    if isinstance(incomp.get("versions"), str):
                        incomp["versions"] = [incomp["versions"]]

            patcher_version_requirement = yaml_config.get("patcher_version_requirement")
            if patcher_version_requirement is None:
                self.patcher_version_requirement = [">=1.10"]
            elif not isinstance(patcher_version_requirement, list):
                self.patcher_version_requirement = [str(patcher_version_requirement)]
            else:
                self.patcher_version_requirement = [str(ver) for ver in patcher_version_requirement]

            self.patcher_options = yaml_config.get("patcher_options")
            self.config_options = yaml_config.get("config_options")

            self.distribution_dir = str(distribution_dir)
            self.options_dict = {}
            self.no_base_content = False

            no_base_content = yaml_config.get("no_base_content")
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

            self.optional_content = []

            optional_content = yaml_config.get("optional_content")
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

    def load_translations(self, load_gui_info: bool = False):
        self.translations_loaded[self.language] = self
        if load_gui_info:
            self.load_gui_info()
        if self.translations:
            for lang, _ in self.translations.items():
                lang_manifest_path = Path(self.distribution_dir, f"manifest_{lang}.yaml")
                if not lang_manifest_path.exists():
                    raise ValueError(f"Lang '{lang}' specified but manifest for it is missing! "
                                     f"(Mod: {self.name})")
                yaml_config = read_yaml(lang_manifest_path)
                config_validated = Mod.validate_install_config(yaml_config, lang_manifest_path)
                if config_validated:
                    mod_tr = Mod(yaml_config, self.distribution_dir)
                    if mod_tr.name != self.name:
                        raise ValueError("Service name mismatch in translation: "
                                         f"'{mod_tr.name}' name specified for translation, "
                                         f"but main mod name is '{self.name}'! "
                                         f"(Mod: {self.name}) (Translation: {mod_tr.language})")
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
                    if load_gui_info:
                        mod_tr.load_gui_info()

        for lang, mod in self.translations_loaded.items():
            mod.known_language = is_known_lang(lang)
            if mod.known_language:
                mod.lang_label = tr(lang)
            else:
                mod.lang_label = lang

    def load_gui_info(self):
        supported_img_extensions = [".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"]
        self.change_log_content = ""
        if self.change_log:
            changelog_path = Path(self.distribution_dir, self.change_log)
            if changelog_path.exists() and changelog_path.suffix.lower() == ".md":
                with open(changelog_path, "r", encoding="utf-8") as fh:
                    md = fh.read()
                    md = process_markdown(md)
                    self.change_log_content = md

        self.other_info_content = ""
        if self.other_info:
            other_info_path = Path(self.distribution_dir, self.other_info)
            if other_info_path.exists() and other_info_path.suffix.lower() == ".md":
                with open(other_info_path, "r", encoding="utf-8") as fh:
                    md = fh.read()
                    md = process_markdown(md)
                    self.other_info_content = md

        self.logo_path = get_internal_file_path("assets/no_logo.png")
        if isinstance(self.logo, str):
            logo_path = Path(self.distribution_dir, self.logo)
            if logo_path.exists() and logo_path.suffix.lower() in supported_img_extensions:
                self.logo_path = str(logo_path)

        self.banner_path = None
        if isinstance(self.install_banner, str):
            banner_path = Path(self.distribution_dir, self.install_banner)
            if banner_path.exists() and banner_path.suffix.lower() in supported_img_extensions:
                self.banner_path = str(banner_path)

        for screen in self.screenshots:
            screen_path = Path(self.distribution_dir, screen["img"])
            if screen_path.exists() and screen_path.suffix.lower() in supported_img_extensions:
                screen["path"] = str(screen_path)
            else:
                screen["path"] = ""
                logger.warning(f"Missing path for screenshot ({screen['img']}) "
                               f"in mod {self.name}-{self.language}")

            compare_path = Path(self.distribution_dir, screen["compare"])
            if compare_path.exists() and compare_path.suffix.lower() in supported_img_extensions:
                screen["compare_path"] = str(compare_path)
                if screen["text"]:
                    screen["text"] += "\n"
                screen["text"] = screen["text"] + f'({tr("click_screen_to_compare")})'
            else:
                screen["compare_path"] = ""

        # we ignore screens which do not exist
        self.screenshots = [screen for screen in self.screenshots if screen["path"]]

        if ", " in self.authors:
            self.developer_title = "authors"
        else:
            self.developer_title = "author"

    def load_commod_compatibility(self, commod_version):
        for translation in self.translations_loaded.values():
            translation.commod_compatible, translation.commod_compatible_err = \
                translation.compatible_with_mod_manager(commod_version)
            translation.commod_compatible_err = remove_colors(translation.commod_compatible_err)

    def load_game_compatibility(self, game_installment):
        for translation in self.translations_loaded.values():
            translation.installment_compatible = self.installment == game_installment

    def load_session_compatibility(self, installed_content, installed_descriptions):
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

    def install(self, game_data_path: str,
                install_settings: dict,
                existing_content: dict,
                existing_content_descriptions: dict,
                console: bool = False) -> tuple[bool, list]:
        '''Returns bool success status of install and errors list in case mod requirements are not met'''
        try:
            logger.info(f"Existing content at the start of install: {existing_content}")
            mod_files = []
            requirements_met, error_msgs = self.check_requirements(existing_content,
                                                                   existing_content_descriptions)
            if requirements_met:
                install_base = install_settings.get('base')
                if install_base is None:
                    raise KeyError(f"Installation config for base of mod '{self.name}' is broken")
                elif install_base == "skip":
                    logger.debug("No base content will be installed")
                else:
                    base_path = os.path.join(self.distribution_dir, "data")
                    if console:
                        if self.name == "community_remaster":
                            print("\n")  # separator
                        print(fconsole(tr("copying_base_files_please_wait"), bcolors.RED)
                              + "\n")
                    mod_files.append(base_path)

                for install_setting in install_settings:
                    if install_setting == "base":
                        continue
                    else:
                        wip_setting = self.options_dict[install_setting]
                        base_work_path = os.path.join(self.distribution_dir, wip_setting.name, "data")
                        installation_prompt_result = install_settings[install_setting]
                        if installation_prompt_result == "yes":
                            mod_files.append(base_work_path)
                        elif installation_prompt_result == "skip":
                            logger.debug(f"Skipping option {install_setting}")
                            continue
                        else:
                            custom_install_method = install_settings[install_setting]
                            custom_install_work_path = os.path.join(self.distribution_dir,
                                                                    wip_setting.name,
                                                                    custom_install_method,
                                                                    "data")
                            mod_files.append(base_work_path)
                            mod_files.append(custom_install_work_path)
                        if console and installation_prompt_result != "skip":
                            print(fconsole(tr("copying_options_please_wait"), bcolors.RED) + "\n")
                copy_from_to(mod_files, game_data_path, console)
                return True, []
            else:
                return False, error_msgs
        except Exception as ex:
            logger.error(ex)
            return False, []

    async def install_async(self, game_data_path: str,
                            install_settings: dict,
                            existing_content: dict,
                            callback_progbar: Awaitable,
                            callback_status: Awaitable):
        '''Uses fast async copy, returns bool success status of install'''
        try:
            logger.info(f"Existing content at the start of install: {existing_content}")
            mod_files = []
            install_base = install_settings.get('base')
            if install_base is None:
                raise KeyError(f"Installation config for base of mod '{self.name}' is broken")
            elif install_base == "skip":
                logger.debug("No base content will be installed")
            else:
                base_path = os.path.join(self.distribution_dir, "data")
                await callback_status(tr("copying_base_files_please_wait"))
                mod_files.append(base_path)
                start = datetime.now()
                await copy_from_to_async_fast(mod_files, game_data_path, callback_progbar)
                end = datetime.now()
                logger.debug(f"{(end - start).microseconds / 1000000} seconds took fast copy")
                mod_files.clear()

            for install_setting in install_settings:
                if install_setting == "base":
                    continue
                else:
                    wip_setting = self.options_dict[install_setting]
                    base_work_path = os.path.join(self.distribution_dir, wip_setting.name, "data")
                    installation_decision = install_settings[install_setting]
                    if installation_decision == "yes":
                        mod_files.append(base_work_path)
                    elif installation_decision == "skip":
                        logger.debug(f"Skipping option {install_setting}")
                        continue
                    else:
                        custom_install_method = install_settings[install_setting]
                        custom_install_work_path = os.path.join(self.distribution_dir,
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
            return True
        except Exception as ex:
            logger.error(ex)
            return False

    def check_requirement(self, prereq: dict, existing_content: dict,
                          existing_content_descriptions: dict,
                          is_compatch_env: bool) -> tuple[bool, str]:
        error_msg = []
        required_mod_name = None

        name_validated = True
        version_validated = True
        optional_content_validated = True

        for possible_prereq_mod in prereq['name']:
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
                compare_ops = set([])
                for version in prereq_versions:
                    if ">=" == version[:2]:
                        compare_operation = operator.ge
                    elif "<=" == version[:2]:
                        compare_operation = operator.le
                    elif ">" == version[:1]:
                        compare_operation = operator.gt
                    elif "<" == version[:1]:
                        compare_operation = operator.lt
                    else:  # default "version" treated the same as "==version":
                        compare_operation = operator.eq

                    for sign in (">", "<", "="):
                        version = version.replace(sign, '')

                    installed_version = existing_content[required_mod_name]["version"]
                    parsed_existing_ver = Mod.Version(installed_version)
                    parsed_required_ver = Mod.Version(version)

                    version_validated = compare_operation(parsed_existing_ver, parsed_required_ver)
                    compare_ops.add(compare_operation)
                    if compare_operation is operator.eq:
                        if parsed_required_ver.identifier:
                            if parsed_existing_ver.identifier != parsed_required_ver.identifier:
                                version_validated = False

                compare_ops = list(compare_ops)
                len_ops = len(compare_ops)
                if len_ops == 1 and operator.eq in compare_ops:
                    self.requirements_style = "strict"
                elif len_ops == 2 and operator.eq not in compare_ops:
                    if (compare_ops[0] in (operator.ge, operator.gt)
                       and compare_ops[1] in (operator.le, operator.lt)):
                        self.requirements_style = "range"
                    elif (compare_ops[0] in (operator.lt, operator.lt)
                          and compare_ops[1] in (operator.ge, operator.gt)):
                        self.requirements_style = "range"
                    else:
                        self.requirements_style = "mixed"
                else:
                    self.requirements_style = "mixed"

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
                        logger.info(f"   PASS: content requirement met: {option} "
                                    f"- of required mod: {name_label}")

        validated = name_validated and version_validated and optional_content_validated

        if not validated:
            if not name_validated:
                warning = f'\n{tr("required_mod_not_found")}:'
            else:
                warning = f'\n{tr("required_base")}:'

            if warning not in error_msg:
                error_msg.append(warning)

            if only_technical_name_available:
                name_label_tr = tr("technical_name")
            else:
                name_label_tr = tr("mod_name")
            error_msg.append(f'{name_label_tr.capitalize()}: '
                             f'{name_label}{version_label}{optional_content_label}')
            installed_description = existing_content_descriptions.get(required_mod_name)
            if installed_description is not None:
                installed_description = installed_description.strip("\n\n")
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
                           patcher_version: str | float = '') -> tuple[bool, list]:
        error_msg = []

        requirements_met = True
        is_compatch_env = ("community_remaster" not in existing_content.keys() and
                           "community_patch" in existing_content.keys())

        if patcher_version:
            if not self.compatible_with_mod_manager(patcher_version):
                requirements_met &= False
                error_msg.append(f"{tr('usupported_patcher_version')}: "
                                 f"{self.display_name} - {self.patcher_version_requirement}"
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

        if requirements_met:
            if self.strict_requirements:
                # we will handle more complex case in check_incompatibles
                if self.vanilla_mod:
                    fake_req = {"name_label": f"{tr('clean').capitalize()} " + tr(self.installment),
                                "mention_versions": False
                                }
                    if set(existing_content.keys()) - set([self.name]):
                        validated_vanilla_mod = False
                        mod_error = tr('cant_install_mod_for_vanilla')
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
                               existing_content_descriptions: dict) -> tuple[bool, bool, str]:
        '''Returns is_reinstallation: bool, can_be_installed: bool, warning_text: str'''
        previous_install = existing_content.get(self.name)
        comrem_on_compatch = False

        # comrem = existing_content.get("community_remaster")
        # compatch = existing_content.get("community_patch")
        # if comrem is not None:
        #     installing_on = "comrem"
        # elif compatch is not None:
        #     installing_on = "compatch"
        # else:
        #     installing_on = "clean"

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

        if self.build < previous_install["build"]:
            return True, False, tr("cant_reinstall_over_newer_build"), previous_install

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
            elif comrem_on_compatch:
                return True, True, tr("can_reinstall"), previous_install
            else:
                return True, False, tr("cant_reinstall_with_different_options"), previous_install

        elif self.build > previous_install["build"]:
            if not self.optional_content:
                # is reinstall, simple mod, unsafe reinstall
                return True, True, tr("can_reinstall"), previous_install

            if old_options == new_options:
                # is reinstall, complex mod, unsafe reinstall, forced options
                warning = tr("can_reinstall")
                if not self.safe_reinstall_options:
                    warning += "\n" + tr("to_increase_compat_options_are_limited")
                return True, True, warning, previous_install
            elif comrem_on_compatch:
                return True, True, tr("can_reinstall"), previous_install
            else:
                return True, False, tr("cant_reinstall_with_different_options"), previous_install

    def check_incompatible(self, incomp: dict, existing_content: dict,
                           existing_content_descriptions: dict) -> tuple[bool, list]:
        error_msg = []
        name_incompat = False
        version_incomp = False
        optional_content_incomp = False

        incomp_mod_name = None
        for possible_incomp_mod in incomp['name']:
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
                compare_ops = set([])
                for version in incomp_versions:
                    if ">=" == version[:2]:
                        compare_operation = operator.ge
                    elif "<=" == version[:2]:
                        compare_operation = operator.le
                    elif ">" == version[:1]:
                        compare_operation = operator.gt
                    elif "<" == version[:1]:
                        compare_operation = operator.lt
                    else:  # default "version" treated the same as "==version":
                        compare_operation = operator.eq

                    for sign in (">", "<", "="):
                        version = version.replace(sign, '')

                    parsed_existing_ver = Mod.Version(installed_version)
                    parsed_incompat_ver = Mod.Version(version)

                    version_incomp = compare_operation(parsed_existing_ver, parsed_incompat_ver)

                    compare_ops.add(compare_operation)
                    # while we ignore postfix for less/greater ops, we want to have an ability
                    # to make a specifix version with postfix incompatible
                    if compare_operation is operator.eq:
                        if parsed_incompat_ver.identifier:
                            if parsed_existing_ver.identifier != parsed_incompat_ver.identifier:
                                version_incomp = True

                compare_ops = list(compare_ops)
                len_ops = len(compare_ops)
                if len_ops == 1 and operator.eq in compare_ops:
                    self.incompatibles_style = "strict"
                elif len_ops == 2 and operator.eq not in compare_ops:
                    if (compare_ops[0] in (operator.ge, operator.gt)
                       and compare_ops[1] in (operator.le, operator.lt)):
                        self.incompatibles_style = "range"
                    elif (compare_ops[0] in (operator.lt, operator.lt)
                          and compare_ops[1] in (operator.ge, operator.gt)):
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

            if only_technical_name_available:
                name_label_tr = tr("technical_name")
            else:
                name_label_tr = tr("mod_name")

            if incompatible_with_game_copy:
                error_msg.append(f'\n{tr("found_incompatible")}:\n'
                                 f'{name_label_tr.capitalize()}: '
                                 f'{name_label}{version_label}{optional_content_label}')
                installed_description = existing_content_descriptions.get(incomp_mod_name)
                if installed_description is not None:
                    installed_description = installed_description.strip("\n\n")
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

        if compatible:
            if self.strict_requirements and self.prerequisites:
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

    def validate_install_config(install_config: Any, mod_config_path: str,
                                archive_file_list: Optional[list[ZipInfo] | py7zr.ArchiveFileList] = None,
                                root_path: Optional[str] = None) -> bool:
        logger.info("--- Validating install config struct ---")
        if root_path:
            logger.info(f"Path: {root_path}")
        else:
            logger.info(f"Path: {mod_config_path}")

        is_dict = isinstance(install_config, dict)
        if is_dict:
            # schema type 1: list of possible types, required(bool)
            # schema type 2: list of possible types, required(bool), value[min, max]
            schema_fieds_top = {
                "name": [[str], True],
                "display_name": [[str], True],
                "installment": [[str], False],
                "version": [[str, int, float], True],
                "build": [[str], True],
                "description": [[str], True],
                "authors": [[str], True],
                "language": [[str], False],  # defaults to ru

                "patcher_version_requirement": [[str, float, int, list[str | float | int]], True],
                "prerequisites": [[list], True],
                "incompatible": [[list], False],
                "compatible_patch_versions": [[bool, str], False],
                "compatible_minor_versions": [[bool, str], False],
                "safe_reinstall_options": [[bool, str], False],

                "release_date": [[str], False],
                "trailer_url": [[str], False],
                "translations": [[list[str]], False],
                "link": [[str], False],
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
            }

            schema_prereqs = {
                "name": [[str, list[str]], True],
                "versions": [[list[str | int | float]], False],
                "optional_content": [[list[str]], False]
            }
            schema_patcher_options = {
                "gravity": [[float], False, [-100.0, -1.0]],
                "skins_in_shop": [[int], False, [8, 32]],
                "blast_damage_friendly_fire": [[bool, str], False, None],
                "game_font": [[str], False]
            }
            schema_config_options = {
                "firstLevel": [[str], False],
                "DoNotLoadMainmenuLevel": [[str], False],
                "weather_AtmoRadius": [[str], False],
                "weather_ConfigFile": [[str], False]}
            schema_optional_content = {
                "name": [[str], True],
                "display_name": [[str], True],
                "description": [[str], True],

                "default_option": [[str], False],
                "forced_option": [[bool, str], False],
                "install_settings": [[list], False],
            }
            schema_install_settins = {
                "name": [[str], True],
                "description": [[str], True],
            }
            validated = Mod.validate_dict(install_config, schema_fieds_top)
            if validated:
                display_name = install_config.get("display_name")
                mod_name = install_config.get("name")
                mod_lang = install_config.get("language")
                logger.info(f"Validating mod '{display_name}' ({mod_name}, lang: {mod_lang})")
                logger.info("   PASS: Simple manifest validation result")
                patcher_options = install_config.get("patcher_options")
                config_options = install_config.get("config_options")
                optional_content = install_config.get("optional_content")
                prerequisites = install_config.get("prerequisites")
                incompatibles = install_config.get("incompatible")
                if patcher_options is not None:
                    validated &= Mod.validate_dict_constrained(patcher_options, schema_patcher_options)
                    logger.info(f"   {'PASS' if validated else 'FAIL'}: "
                                "patcher options dict validation result")
                    validated &= len(set(patcher_options.keys()) - set(schema_patcher_options.keys())) == 0
                    logger.info(f"   {'PASS' if validated else 'FAIL'}: "
                                "only supported patcher options validation result")

                if config_options is not None:
                    validated &= Mod.validate_dict_constrained(config_options, schema_config_options)
                    logger.info(f"   {'PASS' if validated else 'FAIL'}: "
                                "config options dict validation result")
                    validated &= len(set(config_options.keys()) - set(schema_config_options.keys())) == 0
                    logger.info(f"   {'PASS' if validated else 'FAIL'}: "
                                "only supported config options validation result")

                if prerequisites is not None:
                    has_forbidden_prerequisites = False
                    for prereq_entry in prerequisites:
                        validated &= Mod.validate_dict(prereq_entry, schema_prereqs)
                        if validated:
                            if isinstance(prereq_entry.get("name"), str):
                                prereq_entry_checked = [prereq_entry["name"]]
                            else:
                                prereq_entry_checked = prereq_entry["name"]
                            entry_optional_content = prereq_entry.get("optional_content")
                            has_forbidden_prerequisites |= ("community_patch" in prereq_entry_checked
                                                            and bool(entry_optional_content)
                                                            and entry_optional_content is not None)
                    if has_forbidden_prerequisites:
                        logger.error("   FAIL: prerequisites which include ComPatch "
                                     "can't specify optional content")
                    validated &= not has_forbidden_prerequisites
                    logger.info(f"   {'PASS' if validated else 'FAIL'}: prerequisites validation result")

                if incompatibles is not None:
                    has_forbidden_icompabilities = False
                    for incompatible_entry in incompatibles:
                        validated &= Mod.validate_dict(incompatible_entry, schema_prereqs)
                        if validated:
                            if isinstance(incompatible_entry.get("name"), str):
                                incompatible_entry_checked = [incompatible_entry["name"]]
                            else:
                                incompatible_entry_checked = incompatible_entry["name"]
                            has_forbidden_icompabilities |= bool(set(incompatible_entry_checked)
                                                                 & set(["community_patch"]))
                    if has_forbidden_icompabilities:
                        logger.error("   FAIL: incompatibles can't contain ComPatch, "
                                     "should just have ComRem prereq if mod is ComRem exclusive")
                    validated &= not has_forbidden_icompabilities
                    logger.info(f"   {'PASS' if validated else 'FAIL'}: "
                                "incompatible content validation result")

                if optional_content is not None:
                    validated &= Mod.validate_list(optional_content, schema_optional_content)
                    logger.info(f"   {'PASS' if validated else 'FAIL'}: optional content validation result")
                    if validated:
                        for option in optional_content:
                            if option.get("name") in ["base", "display_name", "build", "version"]:
                                validated = False
                                logger.error(f"   FAIL: optional content name '"
                                             f"{option.get('name')}' is one of the reserved service names, "
                                             f"can't load mod properly!")
                            install_settings = option.get("install_settings")
                            if install_settings is not None:
                                validated &= (len(install_settings) > 1)
                                logger.info(f"   {'PASS' if validated else 'FAIL'}: "
                                            "multiple install settings exists for complex optional content '"
                                            f"{option.get('name')}' validation result")
                                validated &= Mod.validate_list(install_settings, schema_install_settins)
                                logger.info(f"   {'PASS' if validated else 'FAIL'}: "
                                            f"install settings for content '{option.get('name')}' "
                                            "validation result")
                            patcher_options_additional = option.get('patcher_options')
                            if patcher_options_additional is not None:
                                validated &= Mod.validate_dict_constrained(patcher_options_additional,
                                                                           schema_patcher_options)
                                logger.info(f"   {'PASS' if validated else 'FAIL'}: "
                                            "patcher options for additional content "
                                            "validation result")

                if not validated:
                    logger.info("<! MOD MANIFEST FAILED VALIDATION, SKIPPING DATA CHECK !>")
                    return validated

                no_base_config = install_config.get("no_base_content")
                if no_base_config is None:
                    no_base_config = False

                if archive_file_list is not None:
                    if isinstance(archive_file_list, py7zr.ArchiveFileList):
                        archive_files = []
                        for file in archive_file_list:
                            if file.emptystream:
                                archive_files.append(f"{file.filename}/")
                            else:
                                archive_files.append(file.filename)
                    else:
                        archive_files = [file.filename for file in archive_file_list]
                    if mod_name == "community_remaster":
                        paths_to_check = [
                            mod_config_path.replace("remaster/manifest.yaml", "patch/"),
                            mod_config_path.replace("remaster/manifest.yaml", "libs/library.dll"),
                            mod_config_path.replace("remaster/manifest.yaml", "libs/library.pdb")]
                        validated_comrem = all(com_path in archive_files for com_path in paths_to_check)
                        validated &= validated_comrem
                        logger.info(f"   {'PASS' if validated_comrem else 'FAIL'}: "
                                    "Archived ComPatch files validation "
                                    "('patch' and 'libs' folders) result")

                    if not validated:
                        logger.info("<! COMPATCH FILES VALIDATION FAILED, SKIPPING FURTHER CHECKS !>")
                        return validated

                    if not no_base_config:
                        mod_data_path = mod_config_path.replace("manifest.yaml", "data/")
                        validated_data_dir = mod_data_path in archive_files
                        validated &= validated_data_dir
                        if not validated_data_dir:
                            logger.error("   FAIL: Archived base mod data folder validation fail, "
                                         f"expected path not found: {mod_data_path}")
                        else:
                            logger.info("   PASS: Archived base mod data folder validation result")

                    if not validated:
                        logger.info("<! BASE FILES VALIDATION FAILED, SKIPPING FURTHER CHECKS !>")
                        return validated

                    if optional_content is not None:
                        for option in optional_content:
                            validated &= mod_config_path.replace(
                                "manifest.yaml", f'{option.get("name")}/') in archive_files
                            if option.get("install_settings") is not None:
                                for setting in option.get("install_settings"):
                                    validated &= mod_config_path.replace(
                                        "manifest.yaml",
                                        f'{option.get("name")}/{setting.get("name")}/data/') in archive_files
                                    logger.info(f"   {'PASS' if validated else 'FAIL'}: "
                                                f"Archived optional content '{option.get('name')}' "
                                                f"install setting '{setting.get('name')}' "
                                                f"data folder validation result")
                            else:
                                validated &= mod_config_path.replace(
                                    "manifest.yaml", f'{option.get("name")}/data/') in archive_files
                            logger.info(f"   {'PASS' if validated else 'FAIL'}: "
                                        f"Archived optional content '{option.get('name')}' "
                                        "data folder validation result")
                else:
                    mod_root_dir = Path(mod_config_path).parent
                    if mod_name == "community_remaster":
                        comrem_root = mod_root_dir.parent
                        paths_to_check = [Path(comrem_root, "patch"),
                                          Path(comrem_root, "remaster"),
                                          Path(comrem_root, "remaster", "data"),
                                          Path(comrem_root, "remaster", "manifest.yaml"),
                                          Path(comrem_root, "libs", "library.dll"),
                                          Path(comrem_root, "libs", "library.pdb")]
                        validated_comrem = all(com_path.exists() for com_path in paths_to_check)
                        validated &= validated_comrem
                        logger.info(f"   {'PASS' if validated_comrem else 'FAIL'}: "
                                    "ComRem/Patch files validation "
                                    "('patch', 'remaster' and 'libs' folders) result")

                    if not no_base_config:
                        validated_data_dir = Path(mod_root_dir, "data").is_dir()
                        validated &= validated_data_dir
                        if not validated_data_dir:
                            logger.error('   FAIL: base mod data folder validation fail, '
                                         'expected path not exists: '
                                         f'{Path(mod_root_dir, "data")}')
                        else:
                            logger.info("   PASS: base mod data folder validation result")
                    if optional_content is not None:
                        for option in optional_content:
                            validated &= Path(mod_root_dir, option.get("name")).is_dir()
                            if option.get("install_settings") is not None:
                                for setting in option.get("install_settings"):
                                    validated &= Path(mod_root_dir,
                                                      option.get("name"),
                                                      setting.get("name"),
                                                      "data").is_dir()
                                    logger.info(f"   {'PASS' if validated else 'FAIL'}: "
                                                f"optional content '{option.get('name')}' "
                                                f"install setting '{setting.get('name')}' "
                                                f"data folder validation result")
                            else:
                                validated &= Path(mod_root_dir,
                                                  option.get("name"),
                                                  "data").is_dir()
                            logger.info(f"   {'PASS' if validated else 'FAIL'}: "
                                        f"optional content '{option.get('name')}' "
                                        "data folder validation result")

            logger.info("< MOD MANIFEST VALIDATED >" if validated else "<! MOD MANIFEST FAILED VALIDATION !>")
            return validated
        else:
            logger.error("   FAIL: broken config encountered, couldn't be read as dictionary")
            return False

    def compatible_with_mod_manager(self, patcher_version: str | float) -> bool:
        compatible = True

        patcher_version_parsed = Mod.Version(patcher_version)
        patcher_version_parsed.identifier = None
        error_msg = ""
        mod_manager_too_new = False

        for version in self.patcher_version_requirement:
            if ">=" == version[:2]:
                compare_operation = operator.ge
            elif "<=" == version[:2]:
                compare_operation = operator.le
            elif ">" == version[:1]:
                compare_operation = operator.gt
            elif "<" == version[:1]:
                compare_operation = operator.lt
            elif "=" == version[:1]:
                compare_operation = operator.eq
            else:  # default "version" treated the same as ">=version":
                compare_operation = operator.ge

            for sign in (">", "<", "="):
                version = version.replace(sign, '')

            parsed_required_ver = Mod.Version(version)
            parsed_required_ver.identifier = None

            if compare_operation is operator.eq and parsed_required_ver < patcher_version_parsed:
                mod_manager_too_new = True

            compatible &= compare_operation(patcher_version_parsed, parsed_required_ver)

        if not compatible:
            logger.warning(f"{self.display_name} manifest asks for an other mod manager version. "
                           f"Required: {self.patcher_version_requirement}, available: {patcher_version}")
            and_word = f" {tr('and')} "

            error_msg = (tr("usupported_patcher_version",
                            content_name=fconsole(self.display_name, bcolors.WARNING),
                            required_version=and_word.join(self.patcher_version_requirement),
                            current_version=patcher_version,
                            github_url=fconsole(COMPATCH_GITHUB, bcolors.HEADER)))

            if mod_manager_too_new and self.name == "community_remaster":
                error_msg += f"\n\n{tr('check_for_a_new_version')}\n\n"
                error_msg += tr("demteam_links",
                                discord_url=fconsole(DEM_DISCORD, bcolors.HEADER),
                                deuswiki_url=fconsole(WIKI_COMPATCH, bcolors.HEADER),
                                github_url=fconsole(COMPATCH_GITHUB, bcolors.HEADER)) + "\n"

        return compatible, error_msg.strip()

    @staticmethod
    def validate_dict(validating_dict: dict, scheme: dict) -> bool:
        '''Validates dictionary based on scheme in a format
           {name: [list of possible types, required(bool)]}.
           Supports generics for type checking in schemes'''
        # logger.debug(f"Validating dict with scheme {scheme.keys()}")
        if not isinstance(validating_dict, dict):
            logger.error(f"Validated part of scheme is not a dict: {validating_dict}")
            return False
        for field in scheme:
            types = scheme[field][0]
            required = scheme[field][1]
            value = validating_dict.get(field)
            if required and value is None:
                logger.error(f"key '{field}' is required but couldn't be found in manifest")
                return False
            elif required or (not required and value is not None):
                generics_present = any([hasattr(type_entry, "__origin__") for type_entry in types])
                if not generics_present:
                    valid_type = any([isinstance(value, type_entry) for type_entry in types])
                else:
                    valid_type = True
                    for type_entry in types:
                        if hasattr(type_entry, "__origin__"):
                            if isinstance(value, typing.get_origin(type_entry)):
                                if type(value) in [dict, list]:
                                    for value_internal in value:
                                        if not isinstance(value_internal, typing.get_args(type_entry)):
                                            valid_type = False
                                            break
                                else:
                                    valid_type = False
                                    break

                if not valid_type:
                    logger.error(f"key '{field}' has value {value} of invalid type '{type(value)}', "
                                 f"expected: {' or '.join(str(type_inst) for type_inst in types)}")
                    return False
        return True

    @staticmethod
    def get_unique_id_from_manifest(manifest):
        try:
            mod_id = []
            installment = manifest.get("installment")
            if installment is None:
                mod_id.append("exmachina")
            else:
                if installment.lower() not in ("exmachina", "m113", "arcade"):
                    return None
                mod_id.append(installment.lower())

            mod_id.append(manifest.get("name"))
            mod_id.append(str(Mod.Version(manifest.get("version"))))
            mod_id.append(manifest.get("build"))
            mod_id.append(manifest.get("language"))

            if any(part is None for part in mod_id):
                return None

            mod_id_full = "".join(mod_id)
            return mod_id_full
        except Exception as ex:
            logger.error("Error when calculating hash for mod manifest", ex)
            return None

    @staticmethod
    def validate_dict_constrained(validating_dict: dict, scheme: dict) -> bool:
        '''Validates dictionary based on scheme in a format
           {name: [list of possible types, required(bool), int or float value[min, max]]}.
           Doesn't support generics in schemes'''
        # logger.debug(f"Validating constrained dict with scheme {scheme.keys()}")
        for field in scheme:
            types = scheme[field][0]
            required = scheme[field][1]
            value = validating_dict.get(field)
            if (float in types) or (int in types):
                min_req = scheme[field][2][0]
                max_req = scheme[field][2][1]

            if required and value is None:
                logger.error(f"key '{field}' is required but couldn't be found in manifest")
                return False
            elif required or (not required and value is not None):
                valid_type = any([isinstance(value, type_entry) for type_entry in types])
                if not valid_type:
                    logger.error(f"key '{field}' is of invalid type '{type(field)}', expected '{types}'")
                    return False
                if float in types:
                    try:
                        value = float(value)
                    except ValueError:
                        logger.error(f"key '{field}' can't be converted to float as supported - "
                                     f"found value '{value}'")
                        return False
                if int in types:
                    try:
                        value = int(value)
                    except ValueError:
                        logger.error(f"key '{field}' can't be converted to int as supported - "
                                     f"found value '{value}'")
                        return False
                if ((float in types) or (int in types)) and (not (min_req <= value <= max_req)):
                    logger.error(f"key '{field}' is not in supported range '{min_req}-{max_req}'")
                    return False

        return True

    @staticmethod
    def validate_list(validating_list: list[dict], scheme: dict) -> bool:
        '''Runs validate_dict for multiple lists with the same scheme
           and returns total validation result for them'''
        # logger.debug(f"Validating list of length: '{len(validating_list)}'")
        to_validate = [element for element in validating_list if isinstance(element, dict)]
        result = all([Mod.validate_dict(element, scheme) for element in to_validate])
        # logger.debug(f"Result: {result}")
        return result

    def get_full_install_settings(self) -> dict:
        '''Returns settings that describe default installation of the mod'''
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
        '''Returns list of strings with localised description of the given mod installation config'''
        install_config = install_config_original.copy()

        descriptions = []

        base_part = install_config.pop("base")
        if base_part == 'yes':
            description = fconsole(f"{self.display_name}\n", bcolors.WARNING) + self.description
            descriptions.append(description)
        if len(install_config) > 0:
            ok_to_install = [entry for entry in install_config if install_config[entry] != 'skip']
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
        def list_values(cls):
            return list(map(lambda c: c.value, cls))

        @classmethod
        def list_names(cls):
            return list(map(lambda c: c.name, cls))

    @total_ordering
    class Version:
        def __init__(self, version_str: str) -> None:
            self.major = '0'
            self.minor = '0'
            self.patch = '0'
            self.identifier = ''

            identifier_index = version_str.find('-')
            has_minor_ver = "." in version_str

            if identifier_index != -1:
                self.identifier = version_str[identifier_index + 1:]
                numeric_version = version_str[:identifier_index]
            else:
                numeric_version = version_str

            if has_minor_ver:
                version_split = numeric_version.split('.')
                version_levels = len(version_split)
                if version_levels > 0:
                    self.major = version_split[0][:4]

                if version_levels > 1:
                    self.minor = version_split[1][:4]

                if version_levels > 2:
                    self.patch = version_split[2][:10]

                if version_levels > 3:
                    self.patch = ''.join(version_split[2:])
            else:
                self.major = numeric_version

            self.is_numeric = all([part.isnumeric() for part in [self.major, self.minor, self.patch]])

        def __str__(self) -> str:
            version = f"{self.major}.{self.minor}.{self.patch}"
            if self.identifier:
                version += f"-{self.identifier}"
            return version

        def __repr__(self) -> str:
            return str(self)

        def _is_valid_operand(self, other: typing.Any):
            return (isinstance(other, Mod.Version))

        def __eq__(self, other: Mod.Version) -> bool:
            if not self._is_valid_operand(other):
                return NotImplemented

            if self.is_numeric and other.is_numeric:
                return ((int(self.major), int(self.minor), int(self.patch))
                        ==
                        (int(other.major), int(other.minor), int(other.patch)))
            else:
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
            else:
                return ((self.major.lower(), self.minor.lower(), self.patch.lower())
                        <
                        (self.major.lower(), self.minor.lower(), self.patch.lower()))

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
            else:
                if isinstance(default_option, str):
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
