import argparse
import logging
import os
import sys
from pathlib import Path

from commod.console import console_ui
from commod.console.color import bcolors, fconsole
from commod.game import data
from commod.game.data import COMPATCH_GITHUB, DEM_DISCORD, WIKI_COMPATCH
from commod.game.environment import GameCopy, InstallationContext
from commod.game.mod import Mod
from commod.helpers import file_ops
from commod.helpers.errors import (
    CorruptedRemasterFilesError,
    DistributionNotFoundError,
    DXRenderDllNotFoundError,
    ExeIsRunningError,
    ExeNotFoundError,
    ExeNotSupportedError,
    FileLoggingSetupError,
    HasManifestButUnpatchedError,
    InvalidExistingManifestError,
    InvalidGameDirectoryError,
    ModsDirMissingError,
    NoModsFoundError,
    PatchedButDoesntHaveManifestError,
    WrongGameDirectoryPathError,
)
from commod.localisation.service import tr


# Console UI to be deprecated in future release
def main(options: argparse.Namespace) -> None:  # noqa: PLR0911
    data.set_title()
    # helper to interact with user through console
    console = console_ui.ConsoleUX(dev_mode=options.dev)

    # creating installation context - description of content versions we can install
    try:
        context = InstallationContext(options.distribution_dir, dev_mode=options.dev, legacy_checks=True)
        session = context.current_session
    except DistributionNotFoundError as ex:
        console.simple_end("missing_distribution", ex)
        return

    # file and console logging setup
    try:
        context.setup_logging_folder()
        context.setup_loggers()
    except FileLoggingSetupError as ex:
        console.simple_end("error_logging_setup", ex)
        return
    logger = context.logger
    console.logger = context.logger
    context.load_system_info()

    try:
        logger.info("Prevalidating Community Patch and Remaster state")
        context.validate_remaster()
    except CorruptedRemasterFilesError as ex:
        logger.error(ex)
        console.simple_end("corrupted_installation", ex)
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
        if game.installed_content:
            logger.info(f"Installed content: {game.installed_content}")
    except WrongGameDirectoryPathError:
        logger.error(f"path doesn't exist: '{target_dir}'")
        console.simple_end("target_game_dir_doesnt_exist")
        return
    except InvalidGameDirectoryError as ex:
        logger.error(f"not all expected files were found in game dir: '{target_dir}'")
        console.simple_end("cant_find_game_data", ex)
        return
    except ExeNotFoundError:
        logger.error("Exe not found")
        console.simple_end("exe_not_found")
        return
    except ExeIsRunningError:
        logger.error(tr("exe_is_running") + ". " + tr("exe_is_running_fix"))
        console.simple_end("exe_is_running", tr("exe_is_running_fix"))
        return
    except ExeNotSupportedError as ex:
        logger.error(f"Exe version is not supported. Version: {ex.exe_version}")
        console.simple_end("exe_not_supported", f"unsupported exe version - {ex.exe_version}")
        return
    except InvalidExistingManifestError as ex:
        logger.error(f"Invalid existing manifest at {ex.manifest_path}")
        console.simple_end("invalid_existing_manifest", ex)
        return
    except HasManifestButUnpatchedError as ex:
        logger.warning(f"Found existing compatch manifest, but exe version is unexpected: {ex.exe_version}"
                       f"\nManifest contents: {ex.manifest_content}")
        console.switch_header("leftovers")
    except PatchedButDoesntHaveManifestError as ex:
        logger.warning(f"Executable is patched (version: {ex.exe_version}), but install manifest is missing")
        console.switch_header("leftovers")

    logger.info(f"Target exe [{game.exe_version}]: {game.target_exe}")
    if game.installed_content:
        logger.info(f"Game copy has installed content: {game.installed_content}")

    try:
        # loads mods into current context, saves errors in current session
        logger.info("Starting loading mods")
        context.load_mods()
    except ModsDirMissingError:
        logger.info("No mods folder found, creating")
    except NoModsFoundError:
        logger.info("No mods found")

    try:
        game.load_installed_descriptions(context.validated_mod_configs, colourise=True)

        remaster_mod = Mod(context.remaster_config, context.remaster_path)

        commod_compatible, commod_compat_err = remaster_mod.compatible_with_mod_manager(
            context.commod_version)

        if not commod_compatible:
            console.prompt_for(accept_enter=True,
                               description=commod_compat_err,
                               stopping=True)
            return

        if (game.patched_version or game.leftovers) and not (options.comremaster or options.compatch):
            # we only offer to launch mod manager on startup if the game is already patched
            # otherwise mod manager will start work after ComPatch/ComRem installation
            if context.validated_mod_configs and not game.leftovers:
                if game.is_modded():
                    console.switch_header("mod_manager")
                    description = f'{fconsole(tr("already_installed"), bcolors.OKGREEN)}:\n'
                    for content_piece in game.installed_descriptions.values():
                        description += content_piece
                    description += "\n" + tr("intro_modded_game") + "\n"
                    reinstall_prompt = console.prompt_for(["mods", "exit"], accept_enter=False,
                                                          description=description)
                else:
                    description = f'{fconsole(tr("already_installed"), bcolors.OKGREEN)}:\n'
                    for content_piece in game.installed_descriptions.values():
                        description += content_piece
                    description += ("\n" + tr("reinstalling_intro") + "\n\n"
                                    + fconsole(tr("warn_reinstall"), bcolors.OKBLUE) + "\n")

                    reinstall_prompt = console.prompt_for(["mods", "reinstall"], accept_enter=False,
                                                          description=description)
            elif not game.is_modded():
                description = f'{fconsole(tr("already_installed"), bcolors.OKGREEN)}:\n'
                for content_piece in game.installed_descriptions.values():
                    description += content_piece

                description += (f'\n{tr("reinstalling_intro_no_mods")}\n\n'
                                + fconsole(tr("warn_reinstall"), bcolors.OKBLUE) + "\n")

                if session.mod_loading_errors:
                    description += console.format_lines(session.mod_loading_errors, color=bcolors.RED)

                reinstall_prompt = console.prompt_for(["reinstall", "exit"], accept_enter=False,
                                                      description=description)
            else:
                console.switch_header("mod_manager")
                description = f'{fconsole(tr("already_installed"), bcolors.OKGREEN)}:\n'
                for content_piece in game.installed_descriptions.values():
                    description += content_piece

                description += \
                    f'\n{fconsole(tr("intro_modded_no_available_mods"), bcolors.OKGREEN)}\n'

                if session.mod_installation_errors or session.mod_loading_errors:
                    if session.mod_installation_errors:
                        description += console.format_lines(session.mod_installation_errors,
                                                            color=bcolors.RED)
                    if session.mod_loading_errors:
                        description += console.format_lines(session.mod_loading_errors,
                                                            color=bcolors.RED)

                console.prompt_for(accept_enter=True,
                                   description=description)
                return

            if reinstall_prompt == "exit":
                logger.info("Exited normally")
                console.switch_header("default")
                console.simple_end("installation_aborted_by_user")
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
        elif options.compatch and "ComRemaster" not in game.exe_version:
            version_choice = "patch"
        else:
            description_intro = (f"{tr('simple_intro')}\n\n"
                                 f"{fconsole(tr('just_enter'), bcolors.HEADER)}\n"
                                 f"{tr('or_options')}\n")
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
                description = (fconsole(tr("first_choose_base_option"), bcolors.OKBLUE) + "\n\n"
                               + fconsole("Community Remaster", bcolors.HEADER) + ": "
                               + tr("comrem_description") + " [remaster]"
                               + "\n\n"
                               + fconsole("Community Patch", bcolors.HEADER) + ": "
                               + tr("compatch_description") + " [patch]"
                               + "\n")
                version_choice = console.prompt_for(["remaster", "patch"], accept_enter=False,
                                                    description=description)
            if version_choice == "remaster":
                remaster_options = "options"

        console.switch_header(version_choice)

        session.content_in_processing["community_patch"] = {"base": "yes",
                                                            "version": remaster_mod.version,
                                                            "installment": remaster_mod.installment,
                                                            "build": remaster_mod.build,
                                                            "language": remaster_mod.language,
                                                            "display_name": "Community Patch"}

        if version_choice == "patch":
            logger.info("- Starting installation of ComPatch -")
            logger.info(session.content_in_processing)
            console.copy_patch_files(context.distribution_dir, game.game_root_path)
            patch_description = [tr(line) for line in install_base(version_choice, game, context)]
            patch_description.append("")  # separator
            file_ops.rename_effects_bps(game.game_root_path)
            console.final_screen_print(patch_description)
            # session.installed_content_description.append("")  # separator

            print(fconsole(tr("installation_finished"), bcolors.OKGREEN) + "\n")
        elif version_choice == "remaster":
            full_install = remaster_options == "all"

            installed_remaster_settings = console.configure_mod_install(mod=remaster_mod,
                                                                        full_install=full_install,
                                                                        skip_to_options=True)
            session.content_in_processing["community_remaster"] = installed_remaster_settings.copy()
            session.content_in_processing["community_remaster"]["version"] = remaster_mod.version
            session.content_in_processing["community_remaster"]["build"] = remaster_mod.build
            session.content_in_processing["community_remaster"]["language"] = remaster_mod.language
            session.content_in_processing["community_remaster"]["installment"] = remaster_mod.installment
            session.content_in_processing["community_remaster"]["display_name"] = remaster_mod.display_name
            exe_options = remaster_mod.patcher_options

            console.switch_header("remaster")
            console.copy_patch_files(context.distribution_dir, game.game_root_path)
            logger.info("***")
            logger.info(f"Starting {remaster_mod.name} {remaster_mod.version} installation"
                        f" with config {installed_remaster_settings}")
            # for comrem we don't count what is already installed, we use the current session content
            # to determine if remaster is compatible with the local compatch verison
            status_ok, error_messages = remaster_mod.install(game.data_path,
                                                             installed_remaster_settings,
                                                             session.content_in_processing,
                                                             game.installed_descriptions,
                                                             console=True)

            if error_messages:
                session.mod_installation_errors.extend(error_messages)

            try:
                patch_description = install_base(version_choice, game, context, exe_options)
                patch_description = [tr(line) for line in patch_description]
                patch_description.append("")  # separator
            except DXRenderDllNotFoundError:
                console.simple_end("dll_not_found")
                return
            file_ops.rename_effects_bps(game.game_root_path)

            console.switch_header("remaster")
            console.final_screen_print(patch_description)

            if not status_ok:
                if error_messages:
                    logger.error(error_messages)
                logger.error("Status of mod installation is not ok")
                print(fconsole(f"\n{tr('installation_error')}: Community Remaster!", bcolors.RED))
            else:
                session.installed_content_description.extend(
                    remaster_mod.get_install_description(installed_remaster_settings))
                console.print_lines(session.installed_content_description)
                print(fconsole(tr("installation_finished"), bcolors.OKGREEN) + "\n")
        else:
            raise NameError(f"Unsupported installation option '{version_choice}'!")

        game.load_installed_descriptions(context.validated_mod_configs, colourise=True)
        console.finilize_manifest(game, session)

        if context.validated_mod_configs:
            input(tr("press_enter_to_continue") + "\n")
            console.switch_header("mod_manager")
            description = (f"{tr('install_mods')}\n"
                           f"({tr('yes_no')})\n")
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

        print(tr("demteam_links",
                 discord_url=fconsole(DEM_DISCORD, bcolors.HEADER),
                 deuswiki_url=fconsole(WIKI_COMPATCH, bcolors.HEADER),
                 github_url=fconsole(COMPATCH_GITHUB, bcolors.HEADER)) + "\n")
        input(fconsole(tr("press_enter_to_exit"), bcolors.OKGREEN) + "\n")
    # near-global exception handler
    except Exception as ex:
        logger.exception("Encountered unhandled error, exiting")
        console.simple_end("failed_and_cleaned", err_msg=ex)


def install_base(version_choice: str, game: GameCopy, context: InstallationContext,
                 exe_options: dict = {}) -> list[str]:
    if version_choice == "remaster":
        target_dll = os.path.join(game.game_root_path, "dxrender9.dll")

        if os.path.exists(target_dll):
            file_ops.patch_render_dll(target_dll)
        else:
            raise DXRenderDllNotFoundError

    build_id = context.remaster_config["build"]

    changes_description = file_ops.patch_game_exe(game.target_exe,
                                                  version_choice,
                                                  build_id,
                                                  context.monitor_res,
                                                  exe_options,
                                                  context.under_windows)
    return changes_description  # noqa: RET504


def mod_manager_console(console: console_ui.ConsoleUX, game: GameCopy, context: InstallationContext) -> None:
    logger = logging.getLogger("dem")
    session = context.current_session

    logger.info("Starting mod manager")
    for mod_manifest in context.validated_mod_configs:
        mod_config = context.validated_mod_configs[mod_manifest]
        mod = Mod(mod_config, Path(mod_manifest).parent)

        compatible_with_commod, commod_compat_error = mod.compatible_with_mod_manager(context.commod_version)

        prevalidated, prevalidation_errors = mod.check_requirements(game.installed_content,
                                                                    game.installed_descriptions)
        compatible, incompatible_errors = mod.check_incompatibles(game.installed_content,
                                                                  game.installed_descriptions)
        if not prevalidated or not compatible or not compatible_with_commod:
            errors_info = console.format_mod_title(mod.display_name, mod.version, incompatible=True)
            console.switch_header("mod_install_custom", additional_string=errors_info)

            errors_to_notify = []
            if commod_compat_error:
                errors_to_notify.append(commod_compat_error)
            if prevalidation_errors:
                errors_to_notify.extend(prevalidation_errors)
            if incompatible_errors:
                errors_to_notify.extend(incompatible_errors)

            console.notify_on_mod_with_errors(mod, errors_to_notify)
            continue

        mod_install_settings = console.configure_mod_install(mod, game=game)
        if not mod_install_settings:
            continue

        if (mod_install_settings.get("base") == "yes"
           or (mod_install_settings.get("base") == "no" and len(mod_install_settings) > 1)):
            logger.info("***")
            if console.auto_clear:
                os.system("cls")
            logger.info(f"Starting mod {mod.name} {mod.version} installation "
                        f"with config {mod_install_settings}")

            try:
                print(console.header)
                status_ok, mod_error_msgs = mod.install(game.data_path,
                                                        mod_install_settings,
                                                        game.installed_content,
                                                        game.installed_descriptions,
                                                        console=True)
            except KeyboardInterrupt:
                console.switch_header("mod_manager")
                console.simple_end("installation_aborted_by_user")
                sys.exit()

            if not status_ok:
                session.mod_installation_errors.append(f"\n{tr('installation_error')}: "
                                                       f"{mod.display_name}")
            else:
                session.content_in_processing[mod.name] = mod_install_settings.copy()
                session.content_in_processing[mod.name]["version"] = mod.version
                session.content_in_processing[mod.name]["build"] = mod.build
                session.content_in_processing[mod.name]["language"] = mod.language
                session.content_in_processing[mod.name]["installment"] = mod.installment
                session.content_in_processing[mod.name]["display_name"] = mod.display_name
                if mod.patcher_options is not None:
                    file_ops.patch_configurables(game.target_exe, mod.patcher_options)
                    if mod.patcher_options.get("gravity") is not None:
                        file_ops.correct_damage_coeffs(game.game_root_path,
                                                       mod.patcher_options.get("gravity"))
            if mod_error_msgs:
                session.mod_installation_errors.extend(mod_error_msgs)
                logger.error(f"mod errors: {mod_error_msgs}")
                console.notify_on_mod_with_errors(mod, mod_error_msgs)
            else:
                installed_mod_description = mod.get_install_description(mod_install_settings)
                mod_info = console.format_mod_info(mod)

                description_ends_with_new_line = False
                if installed_mod_description and isinstance(installed_mod_description[-1], str):
                    description_ends_with_new_line = installed_mod_description[-1].endswith("\n")
                if not description_ends_with_new_line:
                    mod_info = "\n" + mod_info

                installed_mod_description.append(mod_info)
                session.installed_content_description.extend(installed_mod_description)

                description = (console.format_lines(installed_mod_description)
                               + fconsole(tr("installation_finished"),
                                          bcolors.OKGREEN) + "\n")
                console.finilize_manifest(game, session)
                logger.info(f"Mod {mod.name} has been installed")
                console.prompt_for(accept_enter=True,
                                   description=description)
        else:
            logger.info(f"Skipping installation of mod '{mod.name} - install manifest: "
                        f"{mod_install_settings!s}")

    console.finilize_manifest(game, session)

    console.final_screen_mod_manager_print(session.installed_content_description,
                                           session.mod_installation_errors,
                                           session.mod_loading_errors)
    print(tr("demteam_links",
             discord_url=fconsole(DEM_DISCORD, bcolors.HEADER),
             deuswiki_url=fconsole(WIKI_COMPATCH, bcolors.HEADER),
             github_url=fconsole(COMPATCH_GITHUB, bcolors.HEADER)) + "\n")
    logger.info("Finished work")
    input(fconsole(tr("press_enter_to_exit"), bcolors.OKGREEN) + "\n")
    logger.info("Exited normally")
