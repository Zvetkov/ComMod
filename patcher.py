import argparse
import logging
import os
import sys

from pathlib import Path
from ctypes import windll

from errors import ExeIsRunning, ExeNotFound, ExeNotSupported, HasManifestButUnpatched, InvalidGameDirectory,\
                   PatchedButDoesntHaveManifest, WrongGameDirectoryPath,\
                   DistributionNotFound, FileLoggingSetupError, InvalidExistingManifest, ModsDirMissing,\
                   NoModsFound, CorruptedRemasterFiles, DXRenderDllNotFound

from environment import InstallationContext, GameCopy

from console_ui import format_text, bcolors
from data import loc_string

import console_ui
import data
import file_ops

from mod import Mod


def main_console(options: argparse.Namespace) -> None:
    data.set_title()
    # helper to interact with user through console
    console = console_ui.ConsoleUX()

    # creating installation context - description of content versions we can install
    try:
        context = InstallationContext(options.distribution_dir)
        session = context.current_session
    except DistributionNotFound as er:
        console.simple_end('patcher_missing_distribution', er)
        return

    # file and console logging setup
    try:
        context.setup_logging_folder()
        context.setup_loggers()
    except FileLoggingSetupError as er:
        console.simple_end('error_logging_setup', er)
        return
    logger = context.logger

    try:
        context.validate_remaster()
    except CorruptedRemasterFiles as er:
        logger.error(er)
        console.simple_end('corrupted_installation', er)
        return

    # adding a single target game copy and process it
    game = GameCopy()
    if options.target_dir is None:
        logger.info("No target_dir provided explicitly, will try to find a game in the patcher directory")
        target_dir = context.distribution_dir
    else:
        target_dir = os.path.normpath(options.target_dir)

    try:
        game.process_game_install(target_dir)
    except WrongGameDirectoryPath:
        logger.error(f"path doesn't exist: '{target_dir}'")
        console.simple_end("target_game_dir_doesnt_exist")
        return
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
        logger.error(f'{loc_string("exe_not_supported")}: {er.exe_version}')
        console.simple_end("exe_not_supported", er)
        return
    except InvalidExistingManifest as er:
        logger.error(f"Invalid existing manifest at {er.manifest_path}")
        console.simple_end("invalid_existing_manifest", er)
    except HasManifestButUnpatched as er:
        logger.warning(f"Found existing compatch manifest, but exe version is unexpected: {er.exe_version}"
                       f"\nManifest contents: {er.manifest_content}")
        console.switch_header("leftovers")
        game.leftovers = True
    except PatchedButDoesntHaveManifest as er:
        logger.warning(f"Executable is patched, but install manifest is missing, exe version: {er.exe_version}")
        console.switch_header("leftovers")
        game.leftovers = True

    logger.debug(f"Target exe: {game.target_exe}")

    try:
        # loads mods into current context, saves errors in current session
        context.load_mods()
    except ModsDirMissing:
        logger.info(loc_string("no_mods_folder_found"))
    except NoModsFound:
        logger.info(loc_string("no_mods_found"))

    if (game.patched_version or game.leftovers) and not (options.comremaster or options.compatch):
        # we only offer to launch mod manager on startup if the game is already patched
        # otherwise mod manager will start work after ComPatch/ComRem installation
        if context.validated_mod_configs and not game.leftovers:
            description = loc_string("reinstalling_intro") + format_text(loc_string("warn_reinstall"),
                                                                         bcolors.OKBLUE)
            reinstall_prompt = console.prompt_for(["mods", "reinstall"], accept_enter=False,
                                                  description=description)
        else:
            description = loc_string("reinstalling_intro_no_mods") + format_text(loc_string("warn_reinstall"),
                                                                                 bcolors.OKBLUE)
            reinstall_prompt = console.prompt_for(["reinstall", "exit"], accept_enter=False,
                                                  description=description)
        if reinstall_prompt == "exit":
            console.switch_header("default")
            console.simple_end("installation_aborted")
            return

        if reinstall_prompt == "mods":
            mod_manager_console(console, game, context)
            return

    if "ComRemaster" in game.exe_version:
        console.switch_header("patch_over_remaster", game.target_exe)
    else:
        console.switch_header("patching_exe", game.target_exe)

    # skipping console interaction if launched with argument or if exe is already patched
    if options.comremaster:
        version_choice = "remaster"
        remaster_options = "all"
    elif options.compatch and not ("ComRemaster" in game.exe_version):
        version_choice = "patch"
    else:
        description_intro = (f"{loc_string('simple_intro')}"
                             f"{format_text(loc_string('just_enter'), bcolors.HEADER)}"
                             f"{loc_string('or_options')}")
        version_choice = console.prompt_for(["options"], accept_enter=True,
                                            description=description_intro)

    # removes note about exe path from title
    console.switch_header("default")

    # if user decided to install full Remaster default config by pressing Enter on previous prompt
    if version_choice is None:
        version_choice = "remaster"
        remaster_options = "all"
    elif version_choice == "options":
        if "ComRemaster" in game.exe_version:
            version_choice = "remaster"
        else:
            console.switch_header("advanced")
            description = (format_text(loc_string("first_choose_base_option"), bcolors.OKBLUE)
                           + loc_string("intro_version_choice"))
            version_choice = console.prompt_for(["remaster", "patch"], accept_enter=False,
                                                description=description)
        if version_choice == "remaster":
            remaster_options = "options"

    console.switch_header(version_choice)

    remaster_mod = Mod(context.remaster_config, context.remaster_path)

    session.content_in_processing["community_patch"] = {"base": "yes",
                                                        "version": remaster_mod.version,
                                                        "build": remaster_mod.build}

    if version_choice == "patch":
        logger.debug(session.content_in_processing)
        console.copy_patch_files(context.distribution_dir, game.game_root_path)
        patch_description = [loc_string(line) for line in install_base(version_choice, game, context)]
        file_ops.rename_effects_bps(game.game_root_path)
        console.final_screen_print(patch_description)
        session.installed_content_description.append("")  # separator

        print(format_text(loc_string("installation_finished"), bcolors.OKGREEN))
    elif version_choice == "remaster":
        full_install = remaster_options == "all"

        installed_remaster_settings = console.configure_mod_install(mod=remaster_mod,
                                                                    full_install=full_install,
                                                                    skip_to_options=True)
        session.content_in_processing["community_remaster"] = installed_remaster_settings.copy()
        session.content_in_processing["community_remaster"]["version"] = remaster_mod.version
        exe_options = remaster_mod.patcher_options

        if not remaster_mod.compatible_with_patcher(data.VERSION):
            logger.debug("ComRemaster manifest asks for a newer patch version. "
                         f"Required: {remaster_mod.patcher_version_requirement}, available: {data.VERSION}")
            console.simple_end("usupported_patcher_version",
                               new_version=remaster_mod.patcher_version_requirement,
                               current_version=data.VERSION)
            return

        console.copy_patch_files(context.distribution_dir, game.game_root_path)
        # for comrem we don't count what is already installed, we use the current session content to determine
        # if remaster is compatible with the local compatch verison
        status_ok, error_messages = remaster_mod.install(game_data_path=game.data_path,
                                                         install_settings=installed_remaster_settings,
                                                         existing_content=session.content_in_processing)

        if error_messages:
            session.mod_installation_errors.extend(error_messages)

        try:
            patch_description = install_base(version_choice, game, context, exe_options)
            patch_description = [loc_string(line) for line in patch_description]
        except DXRenderDllNotFound:
            console.simple_end("dll_not_found")
            return
        file_ops.rename_effects_bps(game.game_root_path)

        console.switch_header("remaster")
        console.final_screen_print(patch_description)

        if not status_ok:
            logger.debug("Status of mod installation is not ok")
            print(format_text(f"\n{loc_string('installation_error')}: Community Remaster!", bcolors.RED))
        else:
            session.installed_content_description.extend(
                remaster_mod.get_install_description(installed_remaster_settings))
            console.print_lines(session.installed_content_description)
            print(format_text(loc_string("installation_finished"), bcolors.OKGREEN))
    else:
        raise NameError(f"Unsupported installation option '{version_choice}'!")

    try:
        new_content_status = game.installed_content | session.content_in_processing
        if new_content_status:
            file_ops.dump_yaml(new_content_status, game.installed_manifest_path)
    except Exception as ex:
        er_message = f"Couldn't dump install manifest to '{game.installed_manifest_path}'!"
        logger.debug(ex)
        logger.debug(er_message)
        console.simple_end("installation_error", er_message)
        return

    if context.validated_mod_configs:
        input(loc_string("press_enter_to_continue"))
        console.switch_header("mod_manager")
        description = (f"{loc_string('install_mods')}\n"
                       f"({loc_string('yes_no')})\n")
        install_custom_mods = console.prompt_for(["yes", "no"], accept_enter=False,
                                                 description=description)
        if install_custom_mods == "yes":
            mod_manager_console(console, game, context)
            return

    if options.compatch or options.comremaster:
        sys.exit()

    console.switch_header("default")
    console.final_screen_print(session.installed_content_description)
    input(loc_string("press_enter_to_exit"))


def install_base(version_choice: str, game: GameCopy, context: InstallationContext, exe_options={}):
    if version_choice == "remaster":
        target_dll = os.path.join(game.game_root_path, "dxrender9.dll")

        if os.path.exists(target_dll):
            file_ops.patch_render_dll(target_dll)
        else:
            raise DXRenderDllNotFound

    build_id = context.remaster_config["build"]

    changes_description = file_ops.patch_game_exe(game.target_exe, version_choice, build_id, exe_options)
    return changes_description


def mod_manager_console(console: console_ui.ConsoleUX, game: GameCopy, context: InstallationContext):
    logger = logging.getLogger('dem')
    session = context.current_session

    mods_to_install_configs = []
    for mod_manifest in context.validated_mod_configs:
        mod_config = context.validated_mod_configs[mod_manifest]
        mod = Mod(mod_config, Path(mod_manifest).parent)
        if not mod.compatible_with_patcher(data.VERSION):
            logger.debug("Mod asks for a newer patch version."
                         f" Required: {mod.patcher_version_requirement}, available: {data.VERSION}")
            session.mod_installation_errors.append(f"{loc_string('usupported_patcher_version')}: "
                                                   f"{mod.display_name} - {mod.patcher_version_requirement}"
                                                   f" > {data.VERSION     }")
            continue
        mod_install_settings = console.configure_mod_install(mod)
        if not mod_install_settings:
            continue

        mods_to_install_configs.append(mod_install_settings)
        session.installed_content_description.extend(mod.get_install_description(mod_install_settings))
    for mod_configuration in mods_to_install_configs:
        if (mod_install_settings.get("base") == "yes") or (mod_install_settings.get("base") == "no"
                                                           and len(mod_install_settings) > 1):
            status_ok, mod_error_msgs = mod.install(game.data_path,
                                                    mod_configuration,
                                                    game.installed_content)
            if not status_ok:
                session.mod_installation_errors.append(f"\n{loc_string('installation_error')}: "
                                                       f"{mod.display_name}")
            else:
                session.content_in_processing[mod.name] = mod_install_settings.copy()
                session.content_in_processing[mod.name]["version"] = mod.version
                if mod.patcher_options is not None:
                    file_ops.patch_configurables(game.target_exe, mod.patcher_options)
                    if mod.patcher_options.get('gravity') is not None:
                        file_ops.correct_damage_coeffs(options.game_root_path, mod.patcher_options.get('gravity'))
            if mod_error_msgs:
                session.mod_installation_errors.extend(mod_error_msgs)
        else:
            logger.debug(f"Skipping installation of mod '{mod.name} - install manifest: "
                         f"{str(mod_configuration)}")

    if console.auto_clear:
        os.system('cls')
    print(format_text(f'{loc_string("mod_manager_title")}', bcolors.OKGREEN))
    console.print_lines(session.installed_content_description)
    if session.mod_installation_errors:
        session.mod_installation_errors.append("")  # separator
        console.print_lines(session.mod_installation_errors, color=bcolors.RED)
        session.notified_on_errors = True
    else:
        print(format_text(loc_string("installation_finished"), bcolors.OKGREEN))

    if session.mod_installation_errors and not session.notified_on_errors:
        console.print_lines(session.mod_installation_errors, color=bcolors.RED)

    try:
        new_content_status = game.installed_content.extend(session.content_in_processing)
        if new_content_status:
            file_ops.dump_yaml(new_content_status, game.installed_manifest_path)
    except Exception as ex:
        er_message = f"Couldn't dump install manifest to '{game.installed_manifest_path}'!"
        logger.debug(ex)
        logger.debug(er_message)

    console.final_screen_mod_manager_print(session.installed_content_description,
                                           session.mod_installation_errors)
    input(loc_string("press_enter_to_exit"))


def _init_input_parser():
    parser = argparse.ArgumentParser(description='DEM exe patcher')
    parser.add_argument('-target_dir', help='path to game directory', required=False)
    parser.add_argument('-distribution_dir',
                        help=('path to root folder where "patch", "remaster", "libs" '
                              'and optional folder "mods" are located'), required=False)
    parser.add_argument('-dev', help='developer mode',
                        action="store_true", default=False, required=False)
    parser.add_argument('-console', help='run in console',
                        action="store_true", default=True, required=False)
    installation_option = parser.add_mutually_exclusive_group()
    installation_option.add_argument('-compatch', help='base ComPatch setup, no console interaction required',
                                     action="store_true", default=False)
    installation_option.add_argument('-comremaster', help='base ComRemaster, no console interaction required',
                                     action="store_true", default=False)

    return parser


if __name__ == '__main__':
    windll.shcore.SetProcessDpiAwareness(2)
    options = _init_input_parser().parse_args()
    if options.console:
        sys.exit(main_console(options))
