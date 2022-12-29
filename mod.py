from __future__ import annotations
from functools import total_ordering

import logging
from math import isclose
import operator
import os
from pathlib import Path
import typing

from console_color import bcolors, format_text, remove_colors
from data import loc_string
from file_ops import copy_from_to

logger = logging.getLogger('dem')


class Mod:
    '''Mod for HTA/EM, contains mod data, installation instructions
       and related functions'''
    def __init__(self, yaml_config: dict, distribution_dir: str) -> None:
        self.logger = logging.getLogger('dem')
        try:
            self.name = str(yaml_config.get("name"))[:64]
            self.display_name = str(yaml_config.get("display_name"))[:64]
            self.description = str(yaml_config.get("description"))[:2048]
            self.authors = str(yaml_config.get("authors"))[:128]
            self.version = str(yaml_config.get("version"))[:64]
            self.build = str(yaml_config.get("build"))[:7]
            self.url = str(yaml_config.get("link"))[:256]
            self.prerequisites = yaml_config.get("prerequisites")
            self.incompatible = yaml_config.get("incompatible")

            # to simplify hadling of incomps and reqs
            # we always work with them as if they are list of choices
            if self.prerequisites is None:
                self.prerequisites = []
            elif isinstance(self.prerequisites, list):
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

            patcher_version_requirement = yaml_config.get("patcher_version_requirement")
            if patcher_version_requirement is None:
                self.patcher_version_requirement = "1.10"
            else:
                self.patcher_version_requirement = str(patcher_version_requirement)
            self.patcher_options = yaml_config.get("patcher_options")
            self.distibution_dir = distribution_dir
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
                        raise ValueError(f"Broken manifest for content '{self.name}'!")

            self.optional_content = None

            optional_content = yaml_config.get("optional_content")
            if optional_content and optional_content is not None:
                self.optional_content = []
                if isinstance(optional_content, list):
                    for option in optional_content:
                        option_loaded = Mod.OptionalContent(option, self)
                        self.optional_content.append(option_loaded)
                        self.options_dict[option_loaded.name] = option_loaded
                else:
                    raise ValueError(f"Broken manifest for optional part of content '{self.name}'!")

        except Exception as ex:
            er_message = f"Broken manifest for content '{self.name}'!"
            self.logger.error(ex)
            self.logger.error(er_message)
            raise ValueError(er_message)

    def install(self, game_data_path: str,
                install_settings: dict,
                existing_content: dict,
                existing_content_descriptions: dict,
                console: bool = False) -> tuple[bool, list]:
        '''Returns bool success status of install and errors list in case mod requirements are not met'''
        try:
            mod_files = []
            requirements_met, error_msgs = self.check_requirements(existing_content,
                                                                   existing_content_descriptions)
            if requirements_met:
                for install_setting in install_settings:
                    if install_setting == "base":
                        install_base = install_settings.get('base')
                        if install_base is None:
                            raise KeyError(f"Installation config for base of mod '{self.name}' is broken")
                        if self.optional_content is not None:
                            for option in self.optional_content:
                                option_config = install_settings.get(option.name)
                                if option_config is None:
                                    raise KeyError(f"Installation config for option '{option.name}'"
                                                   f" of mod '{self.name}' is broken")
                        base_path = os.path.join(self.distibution_dir, "data")
                        if console:
                            if self.name == "community_remaster":
                                print("\n")  # separator
                            print(format_text(loc_string("copying_base_files_please_wait"), bcolors.RED))
                        mod_files.append(base_path)
                    else:
                        wip_setting = self.options_dict[install_setting]
                        base_work_path = os.path.join(self.distibution_dir, wip_setting.name, "data")
                        installation_prompt_result = install_settings[install_setting]
                        if installation_prompt_result == "yes":
                            mod_files.append(base_work_path)
                        elif installation_prompt_result == "skip":
                            pass
                        else:
                            custom_install_method = install_settings[install_setting]
                            custom_install_work_path = os.path.join(self.distibution_dir,
                                                                    wip_setting.name,
                                                                    custom_install_method)

                            mod_files.append(base_work_path)
                            mod_files.append(custom_install_work_path)
                        if console and installation_prompt_result != "skip":
                            print(format_text(loc_string("copying_options_please_wait"), bcolors.RED))
                copy_from_to(mod_files, game_data_path, console)
                return True, []
            else:
                return False, error_msgs
        except Exception as ex:
            self.logger.error(ex)
            return False, []

    def check_requirements(self, existing_content: dict, existing_content_descriptions: dict,
                           patcher_version: str | float = '') -> tuple[bool, list]:
        error_msg = []
        requirements_met = True
        compatch_env = ("community_remaster" not in existing_content.keys() and
                        "community_patch" in existing_content.keys())

        if patcher_version:
            if not self.compatible_with_mod_manager(patcher_version):
                version_validated = False
                error_msg.append(f"{loc_string('usupported_patcher_version')}: "
                                 f"{self.display_name} - {self.patcher_version_requirement}"
                                 f" > {patcher_version}")

        for prereq in self.prerequisites:
            required_mod_name = None

            name_validated = True
            version_validated = True
            optional_content_validated = True

            for possible_prereq_mod in prereq['name']:
                if existing_content.get(possible_prereq_mod):
                    required_mod_name = possible_prereq_mod

            if required_mod_name is None:
                name_validated = False

            # if trying to install compatch-only mod on comrem
            if (required_mod_name == "community_patch"
               and existing_content.get("community_remaster") is not None
               and self.name != "community_remaster"):
                name_validated = False
                error_msg.append(f"{loc_string('compatch_mod_incompatible_with_comrem')}: "
                                 f"{self.display_name}")

            # if not name_validated:
            #     name_label = or_word.join(prereq["name"])

            #     if prereq.get("optional_content") is not None:
            #         if prereq.get("optional_content"):
            #             optional_content_label = (f', {loc_string("including_options").lower()}: '
            #                                       f'{or_word.join(prereq.get("optional_content"))}')

                # error_msg.append(f'\n{loc_string("for_mod").capitalize()} "{self.display_name}" '
                #                  f'{loc_string("required_mod_not_found").lower()}:\n'
                #                  f'{loc_string("technical_name").capitalize()}: {name_label}{version_label}'
                #                  f'{optional_content_label}')

            or_word = f" {loc_string('or')} "
            and_word = f" {loc_string('and')} "

            name_label = or_word.join(prereq["name"])
            version_label = ""
            optional_content_label = ""

            prereq_versions = prereq.get("versions")
            if prereq_versions and prereq_versions is not None:
                version_label = (f', {loc_string("of_version")}: '
                                 f'{and_word.join(prereq.get("versions"))}')
                if name_validated:
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

                        version_validated = compare_operation(parsed_required_ver, parsed_existing_ver)

                        if compare_operation is operator.eq:
                            if parsed_required_ver.identifier:
                                if parsed_existing_ver.identifier != parsed_required_ver.identifier:
                                    version_validated = False


                    # supported_version = installed_version in versions

                    # if not supported_version:
                    #     self.logger.warning(f"{loc_string('version_needed')}: {str(versions)} - "
                    #                         f"{loc_string('version_available')}: {installed_version}")
                    #     error_msg.extend([f"{loc_string('version_requirement_not_met')}: {required_mod_name}",
                    #                       (f"{loc_string('version_needed')}: {str(versions)} - "
                    #                        f"{loc_string('version_available')}: {installed_version}\n")])
                    #     error_msg.append(f'{loc_string("version_available").capitalize()}:\n'
                    #                      f'{remove_colors(existing_content_descriptions[required_mod_name])}')
                    # version_validated = (installed_version in versions) and version_validated

            optional_content_label = ""

            optional_content = prereq.get("optional_content")
            if optional_content and optional_content is not None:
                optional_content_label = (f', {loc_string("including_options").lower()}: '
                                          f'{", ".join(prereq["optional_content"])}')
                if name_validated and version_validated:
                    for option in optional_content:
                        if existing_content[required_mod_name].get(option) in [None, "skip"]:
                            optional_content_validated = False
                            requirement_err = f"{loc_string('content_requirement_not_met')}:"
                            requirement_name = (f"  * '{option}' {loc_string('for_mod')} "
                                                f"'{required_mod_name}'")

                            if requirement_err not in error_msg:
                                error_msg.append(requirement_err)

                            error_msg.append(requirement_name)

                            # existng_descript = remove_colors(existing_content_descriptions[required_mod_name])
                            # error_msg.append(f'{loc_string("version_available").capitalize()}:\n'
                                            #  f'{existng_descript}')
                        else:
                            self.logger.info(f"content validated: {option} - "
                                             f"for mod: {required_mod_name}")

            validated = name_validated and version_validated and optional_content_validated

            if not validated:
                if not name_validated:
                    warning = loc_string("required_mod_not_found")
                else:
                    warning = f'\n{loc_string("required_base")}'

                error_msg.append(f'{warning} {loc_string("for_mod")} '
                                 f'"{self.display_name}":\n{loc_string("technical_name").capitalize()}: '
                                 f'{name_label}{version_label}{optional_content_label}')
                installed_description = existing_content_descriptions.get(required_mod_name)
                if installed_description is not None:
                    installed_description = installed_description.strip("\n\n")
                    error_msg.append(f'\n{loc_string("version_available").capitalize()}:\n'
                                     f'{remove_colors(installed_description)}')
                else:
                    # in case when we working with compatched game but mod requires comrem
                    # it would be nice to tip a user that this is incompatibility in itself 
                    if compatch_env and "community_remaster" in prereq["name"]:
                        installed_description = existing_content_descriptions.get("community_patch")
                        error_msg.append(f'\n{loc_string("version_available").capitalize()}:\n'
                                         f'{remove_colors(installed_description)}')

            requirements_met &= validated

        if error_msg:
            error_msg.append(f'\n{loc_string("check_for_a_new_version")}')
            # if self.url is not None:
            #     error_msg.append(f"\n{loc_string('mod_url')} {self.url}")

        return requirements_met, error_msg

    def check_incompatibles(self, existing_content: dict,
                            existing_content_descriptions: dict) -> tuple[bool, list]:
        error_msg = []
        compatible = True

        for incomp in self.incompatible:
            name_incompat = False
            version_incomp = False
            optional_content_incomp = False

            incomp_mod_name = None
            for possible_incomp_mod in incomp['name']:
                if existing_content.get(possible_incomp_mod):
                    incomp_mod_name = possible_incomp_mod

            if incomp_mod_name is not None:
                # if incompatible mod is found we need to check if a tighter conformity check exists
                name_incompat = True
                or_word = f" {loc_string('or')} "
                and_word = f" {loc_string('and')} "

                name_label = or_word.join(incomp["name"])

                version_label = ""

                incomp_versions = incomp.get("versions")
                if incomp_versions and incomp_versions is not None:
                    installed_version = existing_content[incomp_mod_name]["version"]

                    version_label = (f', {loc_string("of_version")}: '
                                     f'{or_word.join(incomp.get("versions"))}')
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

                        version_incomp = compare_operation(parsed_incompat_ver, parsed_existing_ver)

                        # while we ignore postfix for less/greater ops, we want to have an ability
                        # to make a specifix version with postfix incompatible
                        if compare_operation is operator.eq:
                            if parsed_incompat_ver.identifier:
                                if parsed_existing_ver.identifier != parsed_incompat_ver.identifier:
                                    version_incomp = True
                else:
                    version_incomp = True

                optional_content_label = ""
                optional_content = incomp.get("optional_content")

                if optional_content and optional_content is not None:

                    optional_content_label = (f', {loc_string("including_options").lower()}: '
                                              f'{or_word.join(incomp.get("optional_content"))}')

                    for option in optional_content:
                        if existing_content[incomp_mod_name].get(option) not in [None, "skip"]:
                            optional_content_incomp = True
                else:
                    optional_content_incomp = True

                incompatible_with_game_copy = name_incompat and version_incomp and optional_content_incomp

                if incompatible_with_game_copy:
                    error_msg.append(f'\n{loc_string("found_incompatible")} {loc_string("for_mod")} '
                                     f'"{self.display_name}":\n{loc_string("technical_name").capitalize()}: '
                                     f'{name_label}{version_label}{optional_content_label}')
                    installed_description = existing_content_descriptions.get(incomp_mod_name)
                    if installed_description is not None:
                        installed_description = installed_description.strip("\n\n")
                        error_msg.append(f'\n{loc_string("version_available").capitalize()}:\n'
                                         f'{remove_colors(installed_description)}')
                    else:
                        b = 1

                compatible &= (not incompatible_with_game_copy)

        if error_msg:
            error_msg.append(f'\n{loc_string("check_for_a_new_version")}')
            # if self.url is not None:
            #     error_msg.append(f"\n{loc_string('mod_url')} {self.url}")
        return compatible, error_msg

    def validate_install_config(install_config: typing.Any, mod_config_path: str,
                                skip_data_validation: bool = False) -> bool:
        mod_path = Path(mod_config_path).parent.parent
        is_dict = isinstance(install_config, dict)
        if is_dict:
            # schema type 1: list of possible types, required(bool)
            # schema type 2: list of possible types, required(bool), value[min, max]
            schema_fieds_top = {
                "name": [[str], True],
                "display_name": [[str], True],
                "version": [[str, int, float], True],
                "build": [[str], True],
                "description": [[str], True],
                "authors": [[str], True],
                "prerequisites": [[list], True],
                "incompatible": [[list], False],
                "patcher_version_requirement": [[str], True],

                "release_date": [[str], False],
                "language": [[str], False],
                "link": [[str], False],
                "patcher_options": [[dict], False],
                "optional_content": [[list], False],
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
            }
            schema_optional_content = {
                "name": [[str], True],
                "display_name": [[str], True],
                "description": [[str], True],

                "default_option": [[str], False],
                "install_settings": [[list], False],
            }
            schema_install_settins = {
                "name": [[str], True],
                "description": [[str], True],
            }
            validated = Mod.validate_dict(install_config, schema_fieds_top)
            if validated:
                display_name = install_config.get("display_name")
                logger.info("***")
                logger.info(f"Initial mod '{display_name}' validation result: True")
                patcher_options = install_config.get("patcher_options")
                optional_content = install_config.get("optional_content")
                prerequisites = install_config.get("prerequisites")
                incompatibles = install_config.get("incompatible")
                if patcher_options is not None:
                    validated &= Mod.validate_dict_constrained(patcher_options, schema_patcher_options)
                    logger.info(f"Patcher options for mod '{display_name}' validation result: {validated}")

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
                        logger.error("Prerequisites which include ComPatch can't specify optional content")
                    validated &= not has_forbidden_prerequisites
                    logger.info(f"Prerequisites for mod '{display_name}' validation result: {validated}")

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
                        logger.error("Incompatibles can't contain ComPatch, should just have ComRem prereq")
                    validated &= not has_forbidden_icompabilities
                    logger.info(f"Incompatible content for mod '{display_name}' "
                                f"validation result: {validated}")

                if optional_content is not None:
                    validated &= Mod.validate_list(optional_content, schema_optional_content)
                    logger.info(f"Optional content for mod '{display_name}' validation result: {validated}")
                    if validated:
                        for option in optional_content:
                            install_settings = option.get("install_settings")
                            if install_settings is not None:
                                validated = (len(install_settings) > 1) or validated
                                logger.info(f"More than one install setting if they exist check for content '"
                                            f"{option.get('name')}' of mod '{display_name}' "
                                            f"validation result: {validated}")
                                validated &= Mod.validate_list(install_settings, schema_install_settins)
                                logger.info(f"Install settings for content '{option.get('name')}' "
                                            f"of mod '{display_name}' validation result: {validated}")
                            patcher_options_additional = option.get('patcher_options')
                            if patcher_options_additional is not None:
                                validated &= Mod.validate_dict_constrained(patcher_options_additional,
                                                                           schema_patcher_options)
                                logger.info(f"Patcher options for additional content of the mod "
                                            f"'{display_name}' validation result: {validated}")

                if not skip_data_validation:
                    # community remaster is a mod, but it has a special folder name, we handle it here
                    if install_config.get("name") == "community_remaster":
                        mod_identifier = "remaster"
                    else:
                        mod_identifier = install_config.get("name")

                    if not install_config.get("no_base_content"):
                        validated &= os.path.isdir(os.path.join(mod_path, mod_identifier, "data"))
                        logger.info(f"Mod '{display_name}' data folder validation result: {validated}")
                    if optional_content is not None:
                        for option in optional_content:
                            validated &= os.path.isdir(os.path.join(mod_path,
                                                                    mod_identifier,
                                                                    option.get("name")))
                            if option.get("install_settings") is not None:
                                for setting in option.get("install_settings"):
                                    validated &= os.path.isdir(os.path.join(mod_path,
                                                                            mod_identifier,
                                                                            option.get("name"),
                                                                            setting.get("name")))
                                    logger.info(f"Mod '{display_name}' optional content "
                                                f"'{option.get('name')}' setting '{setting.get('name')}' "
                                                f"folder validation result: {validated}")
                            logger.info(f"Mod '{display_name}' optional content '{option.get('name')}' "
                                        f"data folder validation result: {validated}")

            return validated
        else:
            logger.error("Broken config encountered, couldn't be read as dictionary")
            return False

    def compatible_with_mod_manager(self, patcher_version: str | float) -> bool:
        if (isclose(float(self.patcher_version_requirement), float(patcher_version)) or
           (float(patcher_version) > float(self.patcher_version_requirement))):
            return True
        else:
            return False

    @staticmethod
    def validate_dict(validating_dict: dict, scheme: dict) -> bool:
        '''Validates dictionary based on scheme in a format
           {name: [list of possible types, required(bool)]}.
           Supports generics for type checking in schemes'''
        logger.debug(f"Validating dict with scheme {scheme.keys()}")
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
    def validate_dict_constrained(validating_dict: dict, scheme: dict) -> bool:
        '''Validates dictionary based on scheme in a format
           {name: [list of possible types, required(bool), int or float value[min, max]]}.
           Doesn't support generics in schemes'''
        logger.debug(f"Validating constrained dict with scheme {scheme.keys()}")
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
                if ((float in types) or (int in types)) and (not(min_req <= value <= max_req)):
                    logger.error(f"key '{field}' is not in supported range '{min_req}-{max_req}'")
                    return False
        return True

    @staticmethod
    def validate_list(validating_list: list[dict], scheme: dict) -> bool:
        '''Runs validate_dict for multiple lists with the same scheme
           and returns total validation result for them'''
        logger.debug(f"Validating list of length: '{len(validating_list)}'")
        to_validate = [element for element in validating_list if isinstance(element, dict)]
        result = all([Mod.validate_dict(element, scheme) for element in to_validate])
        logger.debug(f"Result: {result}")
        return result

    def get_full_install_settings(self) -> dict:
        '''Returns settings that describe default installation of the mod'''
        install_settings = {}
        install_settings["base"] = "yes"
        if self.optional_content is not None:
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
            description = format_text(f"{self.display_name}\n", bcolors.WARNING) + self.description
            descriptions.append(description)
        if len(install_config) > 0:
            ok_to_install = [entry for entry in install_config if install_config[entry] != 'skip']
            if len(ok_to_install) > 0:
                descriptions.append(f"{loc_string('including_options')}:")
        for mod_part in install_config:
            setting_obj = self.options_dict.get(mod_part)
            if install_config[mod_part] == "yes":
                description = (format_text(f"* {setting_obj.display_name}\n", bcolors.OKBLUE)
                               + setting_obj.description)
                descriptions.append(description)
            elif install_config[mod_part] != "skip":
                description = (format_text(f"* {setting_obj.display_name}\n", bcolors.OKBLUE)
                               + setting_obj.description)
                if setting_obj.install_settings is not None:
                    for setting in setting_obj.install_settings:
                        if setting.get("name") == install_config[mod_part]:
                            install_description = setting.get("description")
                            description += (f"\t** {loc_string('install_setting_title')}: "
                                            f"{install_description}")
                descriptions.append(description)
        return descriptions

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
                        >
                        (int(other.major), int(other.minor), int(other.patch)))
            else:
                return ((self.major.lower(), self.minor.lower(), self.path.lower())
                        >
                        (self.major.lower(), self.minor.lower(), self.path.lower()))

    class OptionalContent:
        def __init__(self, description: dict, parent: Mod) -> None:
            self.logger = logging.getLogger('dem')

            self.name = str(description.get("name"))
            self.display_name = description.get("display_name")
            self.description = description.get("description")

            self.install_settings = description.get("install_settings")
            self.default_option = None
            if self.install_settings is not None:
                default_option = description.get("default_option")
                if default_option in [opt["name"] for opt in self.install_settings]:
                    self.default_option = default_option
                else:
                    er_message = (f"Incorrect default option '{default_option}' "
                                  f"for '{self.name}' in content manifest!")
                    self.logger.error(er_message)
                    raise KeyError(er_message)

            no_base_content = description.get("no_base_content")
            patcher_options = description.get("patcher_options")
            if patcher_options is not None:
                for option in patcher_options:
                    # optional content can overwrite base mode options
                    parent.patcher_options[option] = patcher_options[option]
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
                        er_message = f"Broken manifest for content '{self.name}'!"
                        self.logger.error(er_message)
                        raise ValueError(er_message)
