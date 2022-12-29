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

from console_color import format_text, bcolors, remove_colors, remove_colors_from_list
from data import loc_string

import console_ui
import data
import file_ops

from mod import Mod


def main_console(options: argparse.Namespace) -> None:
    data.set_title()
    # helper to interact with user through console
    console = console_ui.ConsoleUX(dev_mode=options.dev)

    # creating installation context - description of content versions we can install
    try:
        context = InstallationContext(options.distribution_dir, dev_mode=options.dev)
        session = context.current_session
    except DistributionNotFound as er:
        console.simple_end('missing_distribution', er)
        return

    # file and console logging setup
    try:
        context.setup_logging_folder()
        context.setup_loggers()
    except FileLoggingSetupError as er:
        console.simple_end('error_logging_setup', er)
        return
    logger = context.logger
    console.logger = context.logger

    try:
        logger.info("Prevalidating Community Patch and Remaster state")
        context.validate_remaster()
    except CorruptedRemasterFiles as er:
        logger.error(er)
        console.simple_end('corrupted_installation', er)
        return

    logger.info("***")
    # adding a single target game copy and process it
    game = GameCopy()
    if options.target_dir is None:
        logger.info("No target_dir provided explicitly, will try to find a game in the patcher directory")
        target_dir = context.distribution_dir
    else:
        target_dir = os.path.normpath(options.target_dir)
        logger.info(f"Working on game dir: {target_dir}")

    try:
        game.process_game_install(target_dir)
    except WrongGameDirectoryPath:
        logger.error(f"path doesn't exist: '{target_dir}'")
        console.simple_end("target_game_dir_doesnt_exist")
        return
    except InvalidGameDirectory as er:
        logger.error(f"not all expected files were found in game dir: '{target_dir}'")
        console.simple_end("cant_find_game_data", er)
        return
    except ExeNotFound:
        logger.error("Exe not found")
        console.simple_end("exe_not_found")
        return
    except ExeIsRunning:
        logger.error(loc_string("exe_is_running"))
        console.simple_end("exe_is_running")
        return
    except ExeNotSupported as er:
        logger.error(f"Exe version is not supported. Version: {er.exe_version}")
        console.simple_end("exe_not_supported", f'unsupported exe version - {er.exe_version}')
        return
    except InvalidExistingManifest as er:
        logger.error(f"Invalid existing manifest at {er.manifest_path}")
        console.simple_end("invalid_existing_manifest", er)
        return
    except HasManifestButUnpatched as er:
        logger.warning(f"Found existing compatch manifest, but exe version is unexpected: {er.exe_version}"
                       f"\nManifest contents: {er.manifest_content}")
        console.switch_header("leftovers")
        game.leftovers = True
    except PatchedButDoesntHaveManifest as er:
        logger.warning(f"Executable is patched (version: {er.exe_version}), but install manifest is missing")
        console.switch_header("leftovers")
        game.leftovers = True

    logger.info(f"Target exe [{game.exe_version}]: {game.target_exe}")
    if game.installed_content:
        logger.info(f"Game copy has installed content: {game.installed_content}")

    try:
        # loads mods into current context, saves errors in current session
        logger.info("Starting loading mods")
        context.load_mods()
    except ModsDirMissing:
        logger.info("No mods folder found, creating")
    except NoModsFound:
        logger.info("No mods found")

    game.load_installed_descriptions(context.validated_mod_configs, colourise=True)

    if (game.patched_version or game.leftovers) and not (options.comremaster or options.compatch):
        # we only offer to launch mod manager on startup if the game is already patched
        # otherwise mod manager will start work after ComPatch/ComRem installation
        if context.validated_mod_configs and not game.leftovers:
            if game.is_modded():
                console.switch_header("mod_manager")
                description = f'{format_text(loc_string("already_installed"), bcolors.OKGREEN)}:\n'
                for content_piece in game.installed_descriptions.values():
                    description += content_piece
                description += loc_string("intro_modded_game")
                reinstall_prompt = console.prompt_for(["mods", "exit"], accept_enter=False,
                                                      description=description)
            else:
                description = f'{format_text(loc_string("already_installed"), bcolors.OKGREEN)}:\n'
                for content_piece in game.installed_descriptions.values():
                    description += content_piece
                description += ("\n" + loc_string("reinstalling_intro")
                                + format_text(loc_string("warn_reinstall"), bcolors.OKBLUE))

                reinstall_prompt = console.prompt_for(["mods", "reinstall"], accept_enter=False,
                                                      description=description)
        elif not game.is_modded():
            description = f'{format_text(loc_string("already_installed"), bcolors.OKGREEN)}:\n'
            for content_piece in game.installed_descriptions.values():
                description += content_piece

            description += (loc_string("reinstalling_intro_no_mods")
                            + format_text(loc_string("warn_reinstall"), bcolors.OKBLUE))

            if session.mod_loading_errors:
                description += console.format_lines(session.mod_loading_errors, color=bcolors.RED)

            reinstall_prompt = console.prompt_for(["reinstall", "exit"], accept_enter=False,
                                                  description=description)
        else:
            console.switch_header("mod_manager")
            description = f'{format_text(loc_string("already_installed"), bcolors.OKGREEN)}:\n'
            for content_piece in game.installed_descriptions.values():
                description += content_piece

            description += f'{format_text(loc_string("intro_modded_no_available_mods"), bcolors.OKGREEN)}'

            if session.mod_installation_errors or session.mod_loading_errors:
                if session.mod_installation_errors:
                    description += console.format_lines(session.mod_installation_errors, color=bcolors.RED)
                if session.mod_loading_errors:
                    description += console.format_lines(session.mod_loading_errors, color=bcolors.RED)

            console.prompt_for(accept_enter=True,
                               description=description)
            return

        if reinstall_prompt == "exit":
            logger.info("Exited normally")
            console.switch_header("default")
            console.simple_end("installation_aborted")
            return

        if reinstall_prompt == "mods":
            mod_manager_console(console, game, context)
            console.finilize_manifest(game, session)
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
                                                        "build": remaster_mod.build,
                                                        "display_name": "Community Patch"}

    if version_choice == "patch":
        logger.info(session.content_in_processing)
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
        session.content_in_processing["community_remaster"]["build"] = remaster_mod.build
        session.content_in_processing["community_remaster"]["display_name"] = remaster_mod.display_name
        exe_options = remaster_mod.patcher_options

        if not remaster_mod.compatible_with_mod_manager(data.VERSION):
            logger.warning("ComRemaster manifest asks for a newer patch version. "
                           f"Required: {remaster_mod.patcher_version_requirement}, available: {data.VERSION}")
            console.simple_end("usupported_patcher_version",
                               new_version=remaster_mod.patcher_version_requirement,
                               current_version=data.VERSION)
            return

        console.switch_header("remaster")
        console.copy_patch_files(context.distribution_dir, game.game_root_path)
        # for comrem we don't count what is already installed, we use the current session content to determine
        # if remaster is compatible with the local compatch verison
        status_ok, error_messages = remaster_mod.install(game.data_path,
                                                         installed_remaster_settings,
                                                         game.installed_content,
                                                         game.installed_descriptions,
                                                         console=True)

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
            logger.error("Status of mod installation is not ok")
            print(format_text(f"\n{loc_string('installation_error')}: Community Remaster!", bcolors.RED))
        else:
            session.installed_content_description.extend(
                remaster_mod.get_install_description(installed_remaster_settings))
            console.print_lines(session.installed_content_description)
            print(format_text(loc_string("installation_finished"), bcolors.OKGREEN))
    else:
        raise NameError(f"Unsupported installation option '{version_choice}'!")

    console.finilize_manifest(game, session)

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

    if version_choice == "patch":
        console.switch_header("patch")
        console.final_screen_print(patch_description)
    else:
        console.switch_header("default")
        console.final_screen_print(session.installed_content_description)

    print(loc_string("demteam_links",
                     discord_url=format_text(data.DEM_DISCORD, bcolors.HEADER),
                     deuswiki_url=format_text(data.WIKI_COMPATCH, bcolors.HEADER),
                     github_url=format_text(data.COMPATCH_GITHUB, bcolors.HEADER)))
    input(format_text(loc_string("press_enter_to_exit"), bcolors.OKGREEN))


def install_base(version_choice: str, game: GameCopy, context: InstallationContext,
                 exe_options: dict = {}) -> list[str]:
    if version_choice == "remaster":
        target_dll = os.path.join(game.game_root_path, "dxrender9.dll")

        if os.path.exists(target_dll):
            file_ops.patch_render_dll(target_dll)
        else:
            raise DXRenderDllNotFound

    build_id = context.remaster_config["build"]

    changes_description = file_ops.patch_game_exe(game.target_exe, version_choice, build_id, exe_options)
    return changes_description


def mod_manager_console(console: console_ui.ConsoleUX, game: GameCopy, context: InstallationContext) -> None:
    logger = logging.getLogger('dem')
    session = context.current_session

    logger.info("Starting mod manager")
    for mod_manifest in context.validated_mod_configs:
        mod_config = context.validated_mod_configs[mod_manifest]
        mod = Mod(mod_config, Path(mod_manifest).parent)
        if not mod.compatible_with_mod_manager(data.VERSION):
            logger.warning(f"Mod '{mod.name}' asks for a newer patcher version."
                           f" Required: {mod.patcher_version_requirement}, available: {data.VERSION}")
            session.mod_installation_errors.append(f"{loc_string('usupported_patcher_version')}: "
                                                   f"{mod.display_name} - {mod.patcher_version_requirement}"
                                                   f" > {data.VERSION}")
            continue

        prevalidated, prevalidation_errors = mod.check_requirements(game.installed_content,
                                                                    game.installed_descriptions)
        compatible, incompatible_errors = mod.check_incompatibles(game.installed_content,
                                                                  game.installed_descriptions)
        if not prevalidated or not compatible:
            errors_info = console.format_mod_title(mod.display_name, mod.version, incompatible=True)
            console.switch_header("mod_install_custom", additional_string=errors_info)

            console.notify_on_mod_with_errors(mod, prevalidation_errors + incompatible_errors)
            continue

        mod_install_settings = console.configure_mod_install(mod, game=game)
        if not mod_install_settings:
            continue

        if (mod_install_settings.get("base") == "yes") or (mod_install_settings.get("base") == "no"
                                                           and len(mod_install_settings) > 1):
            logger.info("***")
            if console.auto_clear:
                os.system('cls')
            logger.info(f"Starting mod {mod.name} installation with config {mod_install_settings}")

            try:
                print(console.header)
                status_ok, mod_error_msgs = mod.install(game.data_path,
                                                        mod_install_settings,
                                                        game.installed_content,
                                                        game.installed_descriptions,
                                                        console=True)
            except KeyboardInterrupt:
                console.switch_header("mod_manager")
                console.simple_end("installation_aborted")
                sys.exit()

            if not status_ok:
                session.mod_installation_errors.append(f"\n{loc_string('installation_error')}: "
                                                       f"{mod.display_name}")
            else:
                session.content_in_processing[mod.name] = mod_install_settings.copy()
                session.content_in_processing[mod.name]["version"] = mod.version
                session.content_in_processing[mod.name]["build"] = mod.build
                session.content_in_processing[mod.name]["display_name"] = mod.display_name
                if mod.patcher_options is not None:
                    file_ops.patch_configurables(game.target_exe, mod.patcher_options)
                    if mod.patcher_options.get('gravity') is not None:
                        file_ops.correct_damage_coeffs(options.game_root_path,
                                                       mod.patcher_options.get('gravity'))
            if mod_error_msgs:
                session.mod_installation_errors.extend(mod_error_msgs)
                logger.error(f"mod errors: {mod_error_msgs}")
                console.notify_on_mod_with_errors(mod, mod_error_msgs)
            else:
                installed_mod_description = mod.get_install_description(mod_install_settings)
                mod_info = console.format_mod_info(mod)

                description_ends_with_new_line = False
                if installed_mod_description:
                    if isinstance(installed_mod_description[-1], str):
                        description_ends_with_new_line = installed_mod_description[-1][-1:] == "\n"
                if not description_ends_with_new_line:
                    mod_info = "\n" + mod_info

                installed_mod_description.append(mod_info)
                session.installed_content_description.extend(installed_mod_description)

                description = (console.format_lines(installed_mod_description)
                               + format_text(loc_string("installation_finished"),
                                             bcolors.OKGREEN))
                console.finilize_manifest(game, session)
                logger.info(f"Mod {mod.name} has been installed")
                console.prompt_for(accept_enter=True,
                                   description=description)
        else:
            logger.info(f"Skipping installation of mod '{mod.name} - install manifest: "
                        f"{str(mod_install_settings)}")

    console.finilize_manifest(game, session)

    console.final_screen_mod_manager_print(session.installed_content_description,
                                           session.mod_installation_errors,
                                           session.mod_loading_errors)
    print(loc_string("demteam_links",
                     discord_url=format_text(data.DEM_DISCORD, bcolors.HEADER),
                     deuswiki_url=format_text(data.WIKI_COMPATCH, bcolors.HEADER),
                     github_url=format_text(data.COMPATCH_GITHUB, bcolors.HEADER)))
    logger.info("Finished work")
    input(format_text(loc_string("press_enter_to_exit"), bcolors.OKGREEN))
    logger.info("Exited normally")


def _init_input_parser():
    parser = argparse.ArgumentParser(description='DEM CommunityModManager')
    parser.add_argument('-target_dir', help='path to game directory', required=False)
    parser.add_argument('-distribution_dir',
                        help=('path to root folder where "patch", "remaster", "libs" '
                              'and an optional folder "mods" are located'), required=False)
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
