import argparse
import os
import sys
import struct
import logging

from pathlib import Path
from ctypes import windll

from utils import ExeIsRunning, ExeNotFound, ExeNotSupported, InvalidGameDirectory, WrongGameDirectoryPath,\
                  DistributionNotFound, FileLoggingSetupError, InvalidExistingManifest, ModsDirMissing,\
                  NoModsFound, loc_string, format_text, bcolors
from environment import InstallationContext, GameCopy

import data
import hd_ui
import console_ui

from mod import Mod


def main_console(options: argparse.Namespace) -> None:
    data.set_title()
    # helper to interact with user through console
    console = console_ui.ConsoleUX()

    # creating installation context - description of content versions we can install
    try:
        if options.distribution_dir:
            context = InstallationContext(options.distribution_dir)
        else:
            context = InstallationContext()
            context.add_default_distribution_dir()
    except DistributionNotFound as er:
        console.simple_end(loc_string('patcher_missing_distribution'), er)
        return

    # logging setup
    try:
        context.setup_logging_folder()
        context.setup_console_loggers()
    except FileLoggingSetupError as er:
        console.simple_end('error_logging_setup', er)
        return
    logger = context.logger

    # adding a single target game copy and process it
    game = GameCopy()
    if options.target_dir is None:
        logger.info("No target_dir provided explicitly, will try to find a game in the patcher directory")
        target_dir = context.distribution_dir
    else:
        target_dir = os.path.normpath(options.target_dir)

    try:
        game.process_game_install(target_dir)
    except WrongGameDirectoryPath as er:
        logger.error(f"path doesn't exist: '{options.data_path}'")
        console.simple_end("target_game_dir_doesnt_exist", er)
    except InvalidGameDirectory as er:
        logger.error(f"not all expected files were found in game dir: '{options.data_path}'")
        console.simple_end("cant_find_game_data", er)
        return
    except ExeNotFound as er:
        logger.error(loc_string("exe_not_found"))
        console.simple_end("exe_not_found", er)
        return
    except ExeIsRunning as er:
        logger.error(loc_string("exe_is_running"))
        console.simple_end("exe_is_running", er)
        return
    except ExeNotSupported as er:
        logger.error(loc_string("exe_not_supported"))
        console.simple_end("exe_not_supported", er)
        return
    except InvalidExistingManifest as er:
        logger.error(f"invalid existing manifest at {er.manifest_path = }")
        console.simple_end("invalid_existing_manifest", er)

    logger.debug(f"Target exe: {context.target_exe}")

    # TODO: Check previously existing clause to display this
    # cant_install_patch = f"{format_text(loc_string('cant_install_patch_over_remaster'), bcolors.OKBLUE)}"

    # print(console.header)

    try:
        # loads mods into current context, saves errors in current session
        context.load_mods()
    except ModsDirMissing as er:
        raise NotImplementedError
    except NoModsFound as er:
        raise NotImplementedError


    if os.path.exists(options.mods_path):
        description = loc_string("reinstalling_intro") + format_text(loc_string("warn_reinstall"),
                                                                        bcolors.OKBLUE)
        reinstall_prompt = prompt_for(["mods", "reinstall"], accept_enter=False,
                                        header=title_header, auto_clear=auto_clear,
                                        description=description)
    else:
        description = loc_string("reinstalling_intro_no_mods") + format_text(loc_string("warn_reinstall"),
                                                                                bcolors.OKBLUE)
        reinstall_prompt = prompt_for(["exit", "reinstall"], accept_enter=False,
                                        header=title_header, auto_clear=auto_clear,
                                        description=description)
    if reinstall_prompt == "exit":
        input(loc_string("press_enter_to_exit"))
        return
    elif valid_manifest and reinstall_prompt == "mods":
        options.installed_content = existing_install_manifest
        validated_mod_configs = {}
        if os.path.exists(options.mods_path):
            mods_configs = get_existing_mods(options.mods_path)
            for mod_config in mods_configs:
                yaml_config = utils.read_yaml(mod_config)
                if yaml_config is None:
                    logger.debug(f"Couldn't read Mod manifest: {mod_config}")
                    mod_installation_errors.append(f"\n{loc_string('empty_mod_manifest')}: "
                                                    f"{Path(mod_config).parent.name} - {Path(mod_config).name}")
                    continue
                config_validated = Mod.validate_install_config(options, yaml_config)
                if config_validated:
                    validated_mod_configs[mod_config] = yaml_config
                else:
                    logger.debug(f"Couldn't validate Mod manifest: {mod_config}")
                    mod_installation_errors.append(f"\n{loc_string('not_validated_mod_manifest')}: "
                                                    f"{Path(mod_config).parent.name} - {Path(mod_config).name}")

        if validated_mod_configs:
            mods_to_install_configs = []
            for mod_manifest in validated_mod_configs:
                mod_config = validated_mod_configs[mod_manifest]
                mod = Mod(mod_config, Path(mod_manifest).parent)
                if not mod.compatible_with_patcher(data.VERSION):
                    logger.debug("Mod asks for a newer patch version."
                                    f" Required: {mod.patcher_version_requirement}, available: {data.VERSION}")
                    mod_installation_errors.append(f"{loc_string('usupported_patcher_version')}: "
                                                    f"{mod.display_name} - {mod.patcher_version_requirement}"
                                                    f" > {data.VERSION}")
                    continue
                mod_install_settings = mod.configure_install(options, auto_clear=auto_clear)

                mods_to_install_configs.append(mod_install_settings)
                installed_mods.extend(mod.get_install_description(mod_install_settings))
            for mod_configuration in mods_to_install_configs:
                if (mod_install_settings.get("base") == "yes") or (mod_install_settings.get("base") == "no"
                                                                    and len(mod_install_settings) > 1):
                    status_ok, mod_error_msgs = mod.install(options, mod_configuration)
                    if not status_ok:
                        mod_installation_errors.append(f"{loc_string('installation_error')}: "
                                                        f"{mod.display_name}")
                    else:
                        options.installed_content[mod.name] = mod_install_settings.copy()
                        options.installed_content[mod.name]["version"] = mod.version
                    if mod.patcher_options is not None:
                        patch_configurables(target_exe, mod.patcher_options)
                        if mod.patcher_options.get('gravity') is not None:
                            correct_damage_coeffs(options.game_root_path, mod.patcher_options.get('gravity'))
                    if mod_error_msgs:
                        mod_installation_errors.extend(mod_error_msgs)
                else:
                    logger.debug(f"Skipping installation of mod '{mod.name} - install manifest: "
                                    f"{str(mod_configuration)}")

            if auto_clear:
                os.system('cls')
            print(format_text(f'{loc_string("mod_manager_title")}', bcolors.OKGREEN))
            print_lines(installed_mods)
            if mod_installation_errors:
                mod_installation_errors.append("")  # separator
                print_lines(mod_installation_errors, color=bcolors.RED)
                notified_on_errors = True
            else:
                print(format_text(loc_string("installation_finished"), bcolors.OKGREEN))
        else:
            print(format_text(loc_string("no_validated_mods"), bcolors.WARNING))

        if mod_installation_errors and not notified_on_errors:
            print_lines(mod_installation_errors, color=bcolors.RED)

        try:
            utils.dump_yaml(options.installed_content, options.installed_manifest_path)
        except Exception as ex:
            er_message = f"Couldn't dump install manifest to '{options.installed_manifest_path}'!"
            logger.debug(ex)
            logger.debug(er_message)

        input(loc_string("press_enter_to_exit"))
        return

    title_header += patching_exe_note
    if "ComRemaster" in exe_version:
        title_header += cant_install_patch

    # skipping console interaction if launched with argument or if exe is already patched
    if options.comremaster:
        version_choice = "remaster"
        remaster_options = "all"
    elif options.compatch:
        version_choice = "patch"
    else:
        description_intro = (f"{loc_string('simple_intro')}{format_text(loc_string('just_enter'), bcolors.HEADER)}"
                                f"{loc_string('or_options')}")
        version_choice = utils.prompt_for(["options"], accept_enter=True,
                                            header=title_header, auto_clear=auto_clear,
                                            description=description_intro)

    # remove note about exe path from title
    title_header = title_header.replace(patching_exe_note, '')

    # if user decided to install full default config - Remaster with all options
    if version_choice is None:
        version_choice = "remaster"
        remaster_options = "all"
    elif version_choice == "options":
        if "ComRemaster" in exe_version:
            version_choice = "remaster"
        else:
            title_header = format_text(f'{loc_string("advanced")} {loc_string("installation_title")}',
                                        bcolors.WARNING) + '\n'
            version_choice = utils.prompt_for(["remaster", "patch"], accept_enter=False,
                                                header=format_text(title_header, bcolors.WARNING),
                                                auto_clear=auto_clear,
                                                description=(format_text(loc_string("first_choose_base_option"),
                                                                        bcolors.OKBLUE)
                                                            + loc_string("intro_version_choice")))
        if version_choice == "remaster":
            remaster_options = "options"

    if version_choice == "patch":
        title_header = format_text(loc_string("patch_title"), bcolors.WARNING) + '\n'

    # will remove warning about installation of patch over remaster if present in header
    title_header = title_header.replace(cant_install_patch, "")

    distribution_dir = os.path.join(context.distribution_dir, "remaster")

    yaml_path = os.path.join(distribution_dir, "manifest.yaml")
    yaml_config = utils.read_yaml(yaml_path)
    if yaml_config is None:
        logger.debug(f"Couldn't read ComRemaster manifest: {yaml_path}")
        print(loc_string("corrupted_installation"))
        input(loc_string("stopping_patching"))
        return

    config_validated = Mod.validate_install_config(options, yaml_config, skip_data_validation=True)
    if not config_validated:
        logger.debug(f"ComRemaster manifest haven't passed validation: {yaml_path}")
        print(loc_string("corrupted_installation"))
        input(loc_string("stopping_patching"))
        return

    remaster_mod = Mod(yaml_config, distribution_dir)

    options.installed_content["community_patch"] = {"base": "yes",
                                                    "version": remaster_mod.version,
                                                    "build": remaster_mod.build}
    logger.debug(options.installed_content)

    if version_choice == "patch":
        copy_patch_files(options)

        patch_description = install_base(version_choice, distribution_dir, target_exe, options)
        rename_effects_bps(options)
        final_screen_print(options, title_header, patch_description)
        installed_mods.append("")  # separator

        print(format_text(loc_string("installation_finished"), bcolors.OKGREEN))
    elif version_choice == "remaster":
        full_install = remaster_options == "all"

        installed_remaster_settings = remaster_mod.configure_install(options, full_install,
                                                                        skip_to_options=True,
                                                                        auto_clear=auto_clear)
        options.installed_content["community_remaster"] = installed_remaster_settings.copy()
        options.installed_content["community_remaster"]["version"] = remaster_mod.version
        exe_options = remaster_mod.patcher_options

        if not remaster_mod.compatible_with_patcher(data.VERSION):
            logger.debug("ComRemaster manifest asks for a newer patch version. "
                            f"Required: {remaster_mod.patcher_version_requirement}, available: {data.VERSION}")
            print(loc_string("usupported_patcher_version"))
            input(loc_string("stopping_patching"))
            return

        copy_patch_files(options)
        status_ok, error_messages = remaster_mod.install(options, installed_remaster_settings)
        patch_description = install_base(version_choice, distribution_dir, target_exe, options, exe_options)
        rename_effects_bps(options)

        final_screen_print(options, title_header, patch_description)

        if not status_ok:
            logger.debug("Status of mod installation is not ok")
            print(format_text(f"{loc_string('installation_error')}: Community Remaster!", bcolors.RED))
        else:
            installed_mods.extend(remaster_mod.get_install_description(installed_remaster_settings))
            print_lines(installed_mods)
            print(format_text(loc_string("installation_finished"), bcolors.OKGREEN))
    else:
        raise NameError(f"Unsupported installation option '{version_choice}'!")

    notified_on_errors = False
    if error_messages:
        mod_installation_errors.extend(error_messages)

    validated_mod_configs = {}
    if os.path.exists(options.mods_path):
        mods_configs = get_existing_mods(options.mods_path)
        for mod_config in mods_configs:
            yaml_config = utils.read_yaml(mod_config)
            if yaml_config is None:
                logger.debug(f"Couldn't read Mod manifest: {mod_config}")
                mod_installation_errors.append(f"\n{loc_string('empty_mod_manifest')}: "
                                                f"{Path(mod_config).parent.name} - {Path(mod_config).name}")
                continue
            config_validated = Mod.validate_install_config(options, yaml_config)
            if config_validated:
                validated_mod_configs[mod_config] = yaml_config
            else:
                logger.debug(f"Couldn't validate Mod manifest: {mod_config}")
                mod_installation_errors.append(f"\n{loc_string('not_validated_mod_manifest')}: "
                                                f"{Path(mod_config).parent.name} - {Path(mod_config).name}")

    if validated_mod_configs:
        input(loc_string("press_enter_to_continue"))

        description = f"{loc_string('install_mods')}\n{loc_string('install_mod_ask')} ({loc_string('yes_no')}) "
        install_custom_mods = prompt_for(["yes", "no"], accept_enter=False,
                                            header=title_header, auto_clear=auto_clear,
                                            description=description)
        mods_to_install_configs = []
        if install_custom_mods == "yes":
            for mod_manifest in validated_mod_configs:
                mod_config = validated_mod_configs[mod_manifest]
                mod = Mod(mod_config, Path(mod_manifest).parent)
                if not mod.compatible_with_patcher(data.VERSION):
                    logger.debug(f"Mod asks for a newer patch version. "
                                    f"Required: {mod.patcher_version_requirement}, available: {data.VERSION}")
                    mod_installation_errors.append(f"{loc_string('usupported_patcher_version')}:"
                                                    f" {mod.display_name} - {mod.patcher_version_requirement} "
                                                    f"> {data.VERSION}")
                    continue
                mod_install_settings = mod.configure_install(options, auto_clear=auto_clear)

                options.installed_content[mod.name] = mod_install_settings.copy()
                options.installed_content[mod.name]["version"] = mod.version

                mods_to_install_configs.append(mod_install_settings)
                installed_mods.extend(mod.get_install_description(mod_install_settings))
            for mod_configuration in mods_to_install_configs:
                status_ok, mod_error_msgs = mod.install(options, mod_configuration)
                if not status_ok:
                    mod_installation_errors.append(f"{loc_string('installation_error')}: {mod.display_name}")
                if mod.patcher_options is not None:
                    patch_configurables(target_exe, mod.patcher_options)
                    if mod.patcher_options.get('gravity') is not None:
                        correct_damage_coeffs(options.game_root_path, mod.patcher_options.get('gravity'))
                if mod_error_msgs:
                    mod_installation_errors.extend(mod_error_msgs)

            if auto_clear:
                os.system('cls')
            print(format_text(f'{loc_string("advanced")} {loc_string("installation_title")}', bcolors.OKGREEN))
            print_lines(installed_mods)
            if mod_installation_errors:
                mod_installation_errors.append("")  # separator
                print_lines(mod_installation_errors, color=bcolors.RED)
                notified_on_errors = True
            else:
                print(format_text(loc_string("installation_finished"), bcolors.OKGREEN))

    else:
        mod_installation_errors.append("")

    if mod_installation_errors and not notified_on_errors:
        print_lines(mod_installation_errors, color=bcolors.RED)

    try:
        utils.dump_yaml(options.installed_content, options.installed_manifest_path)
    except Exception as ex:
        er_message = f"Couldn't dump install manifest to '{options.installed_manifest_path}'!"
        logger.debug(ex)
        logger.debug(er_message)

    input(loc_string("press_enter_to_exit"))


def copy_patch_files(options: argparse.Namespace) -> None:
    if not options.dev:
        os.system('cls')
    print(format_text(loc_string("copying_patch_files_please_wait"), bcolors.RED))
    utils.copy_from_to([os.path.join(options.distribution_dir, "patch")], options.data_path)
    utils.copy_from_to([os.path.join(options.distribution_dir, "libs")], options.game_root_path)


def install_base(version_choice: str, distribution_dir, target_exe, options, exe_options={}):
    try:
        if version_choice == "remaster":
            target_dll = os.path.join(distribution_dir, "dxrender9.dll")

            if not os.path.exists(target_dll):
                target_dll = os.path.join(Path(target_exe).parent, "dxrender9.dll")

            if not os.path.exists(target_dll):
                print(loc_string("dll_not_found"))
                input(loc_string("stopping_patching"))
                return
            else:
                patch_render_dll(target_dll)

        changes_description = patch_game_exe(target_exe, version_choice, exe_options, options)
        return changes_description

    except Exception as ex:
        print(ex)
        input(loc_string("press_enter_to_exit"))


def patch_game_exe(target_exe, version_choice, exe_options={}, options=False):
    changes_description = []
    with open(target_exe, 'rb+') as f:
        game_root_path = Path(target_exe).parent
        offsets_exe = data.offsets_exe_fixes
        width, height = hd_ui.get_monitor_resolution()

        if version_choice == "remaster":
            for offset in data.offsets_abs_sizes.keys():
                f.seek(offset)
                if type(data.offsets_abs_sizes[offset]) == int:
                    f.write(struct.pack("i", round(data.offsets_abs_sizes[offset] * data.ENLARGE_UI_COEF)))
                elif type(data.offsets_abs_sizes[offset]) == str:  # hex address
                    f.write(struct.pack('<L', int(data.offsets_abs_sizes[offset], base=16)))
                elif type(data.offsets_abs_sizes[offset]) == float:
                    f.write(struct.pack("f", round(data.offsets_abs_sizes[offset] * data.ENLARGE_UI_COEF)))
            for offset in data.offsets_abs_move_x.keys():
                original_x = data.offsets_abs_move_x[offset]
                f.seek(offset)
                f.write(struct.pack("f", round((original_x * data.ENLARGE_UI_COEF * data.PARTIAL_STRETCH)
                                               + (data.PARTIAL_STRETCH_OFFSET * data.TARGET_RES_X))))

            offsets_exe = data.offsets_exe_fixes
            offsets_exe.update(data.offsets_exe_ui)

            hd_ui.toggle_16_9_UI_xmls(game_root_path, width, height, enable=True)
            hd_ui.toggle_16_9_glob_prop(game_root_path, enable=True)
            changes_description.append(loc_string("widescreen_interface_patched"))

        for offset in data.binary_inserts.keys():
            f.seek(offset)
            f.write(bytes.fromhex(data.binary_inserts[offset]))
        changes_description.append(loc_string("binary_inserts_patched"))

        for offset in data.mm_inserts.keys():
            f.seek(offset)
            f.write(bytes.fromhex(data.mm_inserts[offset]))
        changes_description.append(loc_string("mm_inserts_patched"))

        utils.patch_offsets(f, offsets_exe)

        changes_description.append(loc_string("numeric_fixes_patched"))
        changes_description.append(loc_string("general_compatch_fixes"))
        if version_choice == "remaster":
            logging.debug(loc_string("ui_fixes_patched"))
            hd_ui.scale_fonts(game_root_path, data.OS_SCALE_FACTOR)

            width_list = []
            if width in data.PREFERED_RESOLUTIONS.keys():
                width_list = data.PREFERED_RESOLUTIONS[width]
            else:
                width_possible = reversed(list(data.possible_resolutions.keys()))
                for width_candidate in width_possible:
                    if width_candidate <= width:
                        width_list.append(width_candidate)
                if len(width_list) >= 5:
                    if width not in width_list:
                        width_list.insert(0, width)
                        data.possible_resolutions[width] = height
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
                f.write(struct.pack("i", data.possible_resolutions[width_list[i]]))

        offsets_text = data.get_text_offsets(version_choice)
        for offset in offsets_text.keys():
            text_fin = offsets_text[offset][0]
            if "ExMachina - " in offsets_text[offset][0]:
                text_fin += f' [{options.installed_content["community_patch"]["build"]}]'
            text_str = bytes(text_fin, 'utf-8')
            allowed_len = offsets_text[offset][1]
            f.seek(offset)
            f.write(struct.pack(f'{allowed_len}s', text_str))

        correct_damage_coeffs(game_root_path, data.GRAVITY)
        increase_phys_step(game_root_path)
        logging.debug(loc_string("damage_coeff_patched"))

    patch_configurables(target_exe, exe_options)
    return changes_description


def final_screen_print(options, header, installed_description):
    if not options.dev:
        os.system('cls')
    print(format_text(header, bcolors.WARNING))
    print(format_text(loc_string("installed_listing"), bcolors.OKBLUE))
    for line in installed_description:
        print(line)


def patch_configurables(target_exe, exe_options={}):
    with open(target_exe, 'rb+') as f:
        configurable_values = {"gravity": data.GRAVITY,
                               "skins_in_shop_0": (8,),
                               "skins_in_shop_1": (8,),
                               "skins_in_shop_2": (8,),
                               "blast_damage_friendly_fire": False
                               }

        if exe_options.get("gravity") is not None:
            configurable_values["gravity"] = float(exe_options.get("gravity"))

        if exe_options.get("skins_in_shop") is not None:
            configurable_values["skins_in_shop_0"] = (int(exe_options.get("skins_in_shop")),)
            configurable_values["skins_in_shop_1"] = (int(exe_options.get("skins_in_shop")),)
            configurable_values["skins_in_shop_2"] = (int(exe_options.get("skins_in_shop")),)

        if exe_options.get("blast_damage_friendly_fire") is not None:
            blast_config = exe_options.get("blast_damage_friendly_fire")
            if not isinstance(blast_config, bool):
                blast_config = str(blast_config)
                if blast_config.lower() == "true":
                    blast_config = True
                else:
                    blast_config = False
            configurable_values["blast_damage_friendly_fire"] = blast_config

        configured_offesets = {}
        for key in data.configurable_offsets.keys():
            configured_offesets[data.configurable_offsets.get(key)] = configurable_values[key]

        utils.patch_offsets(f, configured_offesets)


def patch_render_dll(target_dll):
    with open(target_dll, 'rb+') as f:
        for offset in data.offsets_dll.keys():
            f.seek(offset)
            if type(data.offsets_dll[offset]) == str:  # hex address
                f.write(struct.pack('<Q', int(data.offsets_dll[offset], base=16))[:4])
            elif type(data.offsets_dll[offset]) == float:
                f.write(struct.pack("f", data.offsets_dll[offset]))


def rename_effects_bps(options):
    bps_path = os.path.join(options.game_root_path, "data", "models", "effects.bps")
    new_bps_path = os.path.join(options.game_root_path, "data", "models", "stock_effects.bps")
    if os.path.exists(bps_path):
        os.rename(bps_path, new_bps_path)
        logging.debug(f"Renamed effects.bps in path '{bps_path}'")
    elif not os.path.exists(new_bps_path):
        logging.warning(f"Can't find effects.bps not in normal path '{bps_path}', "
                        "nor in renamed form, probably was deleted by user")




def print_lines(lines: list, color=None):
    for text in lines:
        if color is not None:
            text = format_text(text, color)
        print(text)


def correct_damage_coeffs(root_dir: str, gravity):
    config = utils.get_config(root_dir)
    if config.attrib.get("ai_clash_coeff") is not None:
        ai_clash_coeff = 0.001 / ((gravity / -9.8))
        config.attrib["ai_clash_coeff"] = f"{ai_clash_coeff:.4f}"
        utils.save_to_file(config, os.path.join(root_dir, "data", "config.cfg"))


def increase_phys_step(root_dir: str, enable=True):
    glob_props_full_path = os.path.join(root_dir, utils.get_glob_props_path(root_dir))
    glob_props = utils.xml_to_objfy(glob_props_full_path)
    physics = utils.child_from_xml_node(glob_props, "Physics")
    if physics is not None:
        if enable:
            physics.attrib["PhysicStepTime"] = "0.0166"
        else:
            physics.attrib["PhysicStepTime"] = "0.033"
    utils.save_to_file(glob_props, glob_props_full_path)





def _init_input_parser():
    parser = argparse.ArgumentParser(description=u'DEM exe patcher')
    parser.add_argument('-target_dir', help=u'path to game directory', required=False)
    parser.add_argument('-distribution_dir',
                        help=(u'path to root folder where "patch", "remaster", "libs" '
                              u'and optional folder "mods" are located'), required=False)
    parser.add_argument('-dev', help=u'developer mode',
                        action="store_true", default=False, required=False)
    parser.add_argument('-console', help=u'run in console',
                        action="store_true", default=True, required=False)
    installation_option = parser.add_mutually_exclusive_group()
    installation_option.add_argument('-compatch', help=u'base ComPatch setup',
                                     action="store_true", default=False)
    installation_option.add_argument('-comremaster', help=u'base ComRemaster installation',
                                     action="store_true", default=False)

    return parser


if __name__ == '__main__':
    windll.shcore.SetProcessDpiAwareness(2)
    options = _init_input_parser().parse_args()
    if options.console:
        sys.exit(main_console(options))
