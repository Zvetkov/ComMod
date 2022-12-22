import logging
from math import isclose
import os
from pathlib import Path

from console_ui import bcolors, format_text
from data import loc_string
from file_ops import copy_from_to

logger = logging.getLogger('dem')


class Mod:
    def __init__(self, yaml_config, distribution_dir) -> None:
        self.logger = logging.getLogger('dem')
        try:
            self.name = str(yaml_config.get("name"))
            self.display_name = yaml_config.get("display_name")
            self.description = yaml_config.get("description")
            self.authors = yaml_config.get("authors")
            self.version = str(yaml_config.get("version"))
            self.build = str(yaml_config.get("build"))
            self.url = str(yaml_config.get("link"))
            if self.build is not None:
                self.build = self.build[:7]
            self.prerequisites = yaml_config.get("prerequisites")
            self.incompatible = yaml_config.get("incompatible")
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
            if optional_content is not None:
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

    def install(self, game_data_path, install_settings, existing_content):
        try:
            mod_files = []
            requirements_met, error_msgs = self.check_requirements(existing_content)
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
                        print(format_text(loc_string("copying_base_files_please_wait"), bcolors.RED))
                        mod_files.append(base_path)
                    else:
                        wip_setting = self.options_dict[install_setting]
                        base_work_path = os.path.join(self.distibution_dir, wip_setting.name, "data")
                        installation_prompt_result = install_settings[install_setting]
                        if installation_prompt_result == "yes":
                            print(format_text(loc_string("copying_options_please_wait"), bcolors.RED))
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
                copy_from_to(mod_files, game_data_path)
                return True, []
            else:
                return False, error_msgs
        except Exception as ex:
            self.logger.error(ex)
            return False, []

    def check_requirements(self, existing_content):
        error_msg = []
        content_validated = True
        version_validated = True

        for prereq in self.prerequisites:
            if existing_content.get(prereq["name"]) is not None:
                if (prereq["name"] == "community_patch"
                   and existing_content.get("community_remaster") is not None
                   and self.name != "community_remaster"):
                    version_validated = False
                    error_msg.append(f"{loc_string('compatch_mod_incompatible_with_comrem')}:"
                                     f" {self.display_name}")
                versions = prereq.get("versions")
                if versions is not None:
                    installed_version = existing_content.get(prereq["name"]).get("version")
                    supported_version = installed_version in versions
                    if not supported_version:
                        self.logger.debug(f"{loc_string('version_needed')}: {str(versions)} - "
                                          f"{loc_string('version_available')}: {installed_version}")
                        error_msg.extend([f"{loc_string('version_requirement_not_met')}: {prereq['name']}",
                                          (f"{loc_string('version_needed')}: {str(versions)} - "
                                           f"{loc_string('version_available')}: {installed_version}\n")])
                    version_validated = (installed_version in versions) and version_validated
                else:
                    version_validated = True and version_validated

                optional_content = prereq.get("optional_content")
                if optional_content is not None:
                    # content_validated = True and content_validated
                    for content_req in optional_content:
                        if existing_content.get(prereq["name"]).get(content_req) is None:
                            content_validated = False
                            error_msg.append(f"{loc_string('content_requirement_not_met')}: '{content_req}' "
                                             f"{loc_string('for_mod')}: '{prereq['name']}'")
                        else:
                            self.logger.debug(f"content validated: {content_req} - "
                                              f"{loc_string('for_mod')}: {prereq['name']}")
                # else:
                    # content_validated = True and content_validated
            else:
                content_validated = False
                error_msg.append(f"{loc_string('required_mod_not_found')}: {prereq['name']} - "
                                 f"{loc_string('for_mod')}: {self.display_name}")
        validated = all([version_validated, content_validated])
        if error_msg:
            error_msg.append(loc_string("check_for_a_new_version"))
            if self.url is not None:
                error_msg.append(f"\n{loc_string('mod_url')} {self.url}")
        return validated, error_msg

    def validate_install_config(install_config, mod_config_path, skip_data_validation=False):
        mod_path = Path(mod_config_path).parent.parent
        is_dict = isinstance(install_config, dict)
        if is_dict:
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
                logger.debug(f"Initial mod '{display_name}' validation result: True")
                patcher_options = install_config.get("patcher_options")
                optional_content = install_config.get("optional_content")
                if patcher_options is not None:
                    validated = Mod.validate_dict_constrained(patcher_options, schema_patcher_options) and validated
                    logger.debug(f"Patcher options for mod '{display_name}' validation result: {validated}")
                if optional_content is not None:
                    validated = Mod.validate_list(optional_content, schema_optional_content) and validated
                    logger.debug(f"Optional content for mod '{display_name}' validation result: {validated}")
                    if validated:
                        for option in optional_content:
                            install_settings = option.get("install_settings")
                            if install_settings is not None:
                                validated = (len(install_settings) > 1) or validated
                                logger.debug(f"More than one install setting if they exist check for content '"
                                              f"{option.get('name')}' of mod '{display_name}' "
                                              f"validation result: {validated}")
                                validated = Mod.validate_list(install_settings, schema_install_settins) and validated
                                logger.debug(f"Install settings for content '{option.get('name')}' "
                                              f"of mod '{display_name}' validation result: {validated}")
                            patcher_options_additional = option.get('patcher_options')
                            if patcher_options_additional is not None:
                                validated = Mod.validate_dict_constrained(patcher_options_additional,
                                                                          schema_patcher_options) and validated
                                logger.debug(f"Patcher options for additional content of the mod '{display_name}' "
                                              f"validation result: {validated}")

                if not skip_data_validation:
                    # community remaster is a mod, but it has a special folder name, we handle it here
                    if install_config.get("name") == "community_remaster":
                        mod_identifier = "remaster"
                    else:
                        mod_identifier = install_config.get("name")

                    if not install_config.get("no_base_content"):
                        validated = (os.path.isdir(os.path.join(mod_path, mod_identifier, "data"))
                                     and validated)
                        logger.debug(f"Mod '{display_name}' data folder validation result: {validated}")
                    if optional_content is not None:
                        for option in optional_content:
                            validated = (os.path.isdir(os.path.join(mod_path,
                                                                    mod_identifier,
                                                                    option.get("name")))
                                         and validated)
                            if option.get("install_settings") is not None:
                                for setting in option.get("install_settings"):
                                    validated = (os.path.isdir(os.path.join(mod_path,
                                                                            mod_identifier,
                                                                            option.get("name"),
                                                                            setting.get("name")))
                                                 and validated)
                                    logger.debug(f"Mod '{display_name}' optional content '{option.get('name')}' "
                                                 f"setting '{setting.get('name')}' "
                                                 f"folder validation result: {validated}")
                            logger.debug(f"Mod '{display_name}' optional content '{option.get('name')}' "
                                         f"data folder validation result: {validated}")

            return validated
        else:
            logger.debug("Broken config encountered, couldn't be read as dictionary")
            return False

    def compatible_with_patcher(self, patcher_version):
        if (isclose(float(self.patcher_version_requirement), float(patcher_version)) or
           (float(patcher_version) > float(self.patcher_version_requirement))):
            return True
        else:
            return False

    @staticmethod
    def validate_dict(validating_dict, scheme):
        logger.debug(f"Validating dict with scheme {scheme.keys()}")
        for field in scheme:
            types = scheme[field][0]
            required = scheme[field][1]
            value = validating_dict.get(field)
            if required and value is None:
                logger.debug(f"key '{field}' is required but couldn't be found in manifest")
                return False
            elif required or (not required and value is not None):
                valid_type = any([isinstance(value, type_entry) for type_entry in types])
                if not valid_type:
                    logger.debug(f"key '{field}' is of invalid type '{type(field)}', expected '{types}'")
                    return False
        return True

    @staticmethod
    def validate_dict_constrained(validating_dict, scheme):
        logger.debug(f"Validating constrained dict with scheme {scheme.keys()}")
        for field in scheme:
            types = scheme[field][0]
            required = scheme[field][1]
            value = validating_dict.get(field)
            if (float in types) or (int in types):
                min_req = scheme[field][2][0]
                max_req = scheme[field][2][1]

            if required and value is None:
                logger.debug(f"key '{field}' is required but couldn't be found in manifest")
                return False
            elif required or (not required and value is not None):
                valid_type = any([isinstance(value, type_entry) for type_entry in types])
                if not valid_type:
                    logger.debug(f"key '{field}' is of invalid type '{type(field)}', expected '{types}'")
                    return False
                if float in types:
                    try:
                        value = float(value)
                    except ValueError:
                        logger.debug(f"key '{field}' can't be converted to float as supported - found value '{value}'")
                        return False
                if int in types:
                    try:
                        value = int(value)
                    except ValueError:
                        logger.debug(f"key '{field}' can't be converted to int as supported - found value '{value}'")
                        return False
                if ((float in types) or (int in types)) and (not(min_req <= value <= max_req)):
                    logger.debug(f"key '{field}' is not in supported range '{min_req}-{max_req}'")
                    return False
        return True

    @staticmethod
    def validate_list(validating_list, scheme):
        logger.debug(f"Validating list of length: '{len(validating_list)}'")
        to_validate = [element for element in validating_list if isinstance(element, dict)]
        result = all([Mod.validate_dict(element, scheme) for element in to_validate])
        logger.debug(f"Result: {result}")
        return result

    def get_full_install_settings(self):
        install_settings = {}
        install_settings["base"] = "yes"
        if self.optional_content is not None:
            for option in self.optional_content:
                if option.default_option is not None:
                    install_settings[option.name] = option.default_option
                else:
                    install_settings[option.name] = "yes"
        return install_settings

    def get_install_description(self, install_config_original):
        install_config = install_config_original.copy()

        descriptions = []

        base_part = install_config.pop("base")
        if base_part == 'yes':
            description = format_text(f"\n{self.display_name}\n", bcolors.WARNING) + self.description
            descriptions.append(description)
        if len(install_config) > 0:
            ok_to_install = [entry for entry in install_config if install_config[entry] != 'skip']
            if len(ok_to_install) > 0:
                descriptions.append(f"{loc_string('including_options')}:")
        for mod_part in install_config:
            setting_obj = self.options_dict.get(mod_part)
            if install_config[mod_part] == "yes":
                description = format_text(f"* {setting_obj.display_name}\n", bcolors.OKBLUE) + setting_obj.description
                descriptions.append(description)
            elif install_config[mod_part] != "skip":
                description = format_text(f"* {setting_obj.display_name}\n", bcolors.OKBLUE) + setting_obj.description
                if setting_obj.install_settings is not None:
                    for setting in setting_obj.install_settings:
                        if setting.get("name") == install_config[mod_part]:
                            install_description = setting.get("description")
                            description += f"\t** {loc_string('install_setting_title')}: {install_description}"
                descriptions.append(description)
        return descriptions

    class OptionalContent:
        def __init__(self, description, parent) -> None:
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
                    er_message = f"Incorrect default option '{default_option}' for '{self.name}' in content manifest!"
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
