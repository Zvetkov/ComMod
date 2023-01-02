import os
import sys
import file_ops

from console_color import bcolors, format_text
from localisation import loc_string
from environment import GameCopy, InstallationContext

from mod import Mod


class ConsoleUX:
    '''Helper class for printing and asking for a user input via console'''
    def __init__(self, dev_mode: bool = False) -> None:
        self.auto_clear = True
        self.logger = None
        if dev_mode:
            self.dev_mode = True
            self.auto_clear = False
        else:
            self.dev_mode = False
        self.switch_header("default")

    def switch_header(self, identifier=str, exe_path: str | None = None,
                      additional_string: str = "") -> None:
        bold_red = [bcolors.RED, bcolors.BOLD]
        bold_orange = [bcolors.WARNING, bcolors.BOLD]
        bold_blue = [bcolors.OKBLUE, bcolors.BOLD]

        installation_title = f'{format_text(loc_string("installation_title"), bold_orange)}\n'
        if self.dev_mode:
            installation_title = format_text("DEVELOPER MODE\n", bold_red) + installation_title
        advanced = f'{format_text(loc_string("advanced"), bold_orange)} '

        if exe_path is not None:
            exe_info = f"{loc_string('patching_exe')}: {exe_path}\n"
        else:
            exe_info = ""

        match identifier:
            case "default":
                self.header = installation_title
            case "leftovers":
                self.header = (installation_title + format_text(loc_string("install_leftovers"), bold_red)
                               + "\n")
            case "patching_exe":
                self.header = installation_title + exe_info
            case "patch":
                self.header = format_text(loc_string("patch_title"), bold_orange) + '\n'
            case "remaster":
                self.header = format_text(loc_string("remaster_title"), bold_orange) + '\n'
            case "remaster_custom":
                self.header = additional_string
            case "patch_over_remaster":
                self.header = (format_text(loc_string("remaster_title"), bold_orange) + '\n'
                               + exe_info
                               + format_text(loc_string("cant_install_patch_over_remaster"), bold_blue)
                               + "\n")
            case "advanced":
                self.header = advanced + installation_title
            case "mod_manager":
                self.header = format_text(loc_string("mod_manager_title"), bold_blue) + '\n'
            case "mod_install_custom":
                self.header = (format_text(loc_string("mod_manager_title"), bold_blue) + '\n'
                               + additional_string)

    def simple_end(self, message: str, err_msg: str | Exception | None = None, **kwargs) -> None:
        '''Simple info display shown before exiting the proccess,
        by user's choice or as a result of exception'''
        # self.switch_header("default")
        if err_msg is not None:
            gray_err_msg = format_text(f"Error: {err_msg}", bcolors.GRAY)
            description = f"{loc_string(message)}\n\n{gray_err_msg}"
        else:
            description = loc_string(message)
        if kwargs:
            description = description.format(**kwargs)
        self.prompt_for(accept_enter=True,
                        description=description,
                        stopping=True)

    @staticmethod
    def format_mod_title(display_name: str, version: str, option_name: str = "",
                         incompatible: bool = False) -> str:
        if incompatible:
            title = format_text(f"{loc_string('cant_be_installed')}: {display_name} - "
                                f"{loc_string('version')} {version}\n",
                                bcolors.RED)
        else:
            title = format_text(f"{loc_string('installation')} {display_name} - "
                                f"{loc_string('version')} {version}\n",
                                bcolors.WARNING)

        if option_name:
            title += f'{format_text(option_name, bcolors.OKGREEN)} ({loc_string("optional_content")})\n'
        return title

    def prompt_for(self,
                   option_list: list[str] = [], accept_enter: bool = False,
                   description: str | None = None,
                   stopping: bool = False) -> str:
        '''Ask user to choose from a few options, accept answers from the predefined list given'''
        auto_clear = self.auto_clear
        if auto_clear:
            os.system('cls')
        no_options = len(option_list) == 0
        if no_options and not accept_enter and not stopping:
            raise ValueError("There should be at least one option to confirm when asking user!")
        user_choice = None
        previous_prompt = None

        try:
            while (user_choice not in option_list):
                if not auto_clear:
                    if previous_prompt is None:
                        print(self.header)
                else:
                    print(self.header)

                if previous_prompt is not None:
                    print(format_text(f"'{previous_prompt}' - {loc_string('incorrect_prompt_answer')}\n",
                                      bcolors.RED))

                if description is not None and not auto_clear:
                    if previous_prompt is None:
                        print(description)
                elif description is not None:
                    print(description)

                formatted_msg = ""
                if stopping:
                    formatted_msg = f"\n{format_text(loc_string('stopping_patching'), bcolors.RED)}"
                elif no_options and accept_enter:
                    formatted_msg = f"{format_text(loc_string('press_enter_to_continue'))}"
                elif accept_enter:
                    formatted_msg = f"{format_text(loc_string('enter_accepted_prompt'), bcolors.OKGREEN)}: "
                elif option_list:
                    formatted_msg = f"{format_text(loc_string('base_prompt'), bcolors.OKGREEN)}: "

                if stopping:
                    pass
                else:
                    formatted_msg += f"{', '.join([format_text(opt) for opt in option_list])}"

                print(formatted_msg)

                user_choice = input("")
                if user_choice != '':
                    user_choice.strip("'").strip('"')
                if user_choice not in option_list:
                    # if accept_enter and user presses enter with no other input
                    if user_choice == '' and accept_enter:
                        if auto_clear:
                            os.system('cls')
                        return None
                    elif user_choice == '':
                        previous_prompt = "[ENTER]"
                    else:
                        previous_prompt = user_choice
                    if auto_clear:
                        os.system('cls')
        except KeyboardInterrupt:
            self.switch_header("default")
            self.simple_end("installation_aborted")
            sys.exit()

        return user_choice

    def final_screen_print(self, installed_description: list[str]) -> None:
        if self.auto_clear:
            os.system('cls')
        print(self.header)
        print(format_text(loc_string("installed_listing"), bcolors.OKBLUE))
        for line in installed_description:
            print(line)

    def final_screen_mod_manager_print(self, installed_content_description: list[str],
                                       mod_installation_errors: list[str],
                                       mod_loading_errors: list[str]) -> None:
        if self.auto_clear:
            os.system('cls')
        print(format_text(f'{loc_string("mod_manager_title")}', bcolors.OKGREEN))

        if installed_content_description:
            print("\n" + format_text(loc_string("installed_listing"), bcolors.OKBLUE))
            self.print_lines(installed_content_description)

        if mod_installation_errors or mod_loading_errors:
            if mod_installation_errors:
                self.print_lines(mod_installation_errors, color=bcolors.RED)
            if mod_loading_errors:
                self.print_lines(mod_loading_errors, color=bcolors.RED)
        elif installed_content_description:
            print(format_text(loc_string("installation_finished"), bcolors.OKGREEN) + "\n")
        else:
            print(format_text(loc_string("nothing_to_install"), bcolors.OKGREEN) + "\n")

    def copy_patch_files(self, distribution_dir: str, game_root: str) -> None:
        if self.auto_clear:
            os.system('cls')
        print(self.header)
        print(format_text(loc_string("copying_patch_files_please_wait"), bcolors.RED) + "\n")
        try:
            file_ops.copy_from_to([os.path.join(distribution_dir, "patch")], os.path.join(game_root, "data"),
                                  console=True)
            file_ops.copy_from_to([os.path.join(distribution_dir, "libs")], game_root,
                                  console=True)
        except KeyboardInterrupt:
            self.switch_header("default")
            self.simple_end("installation_aborted")
            sys.exit()

    @staticmethod
    def format_lines(lines: list, color: bcolors | None = None) -> str:
        text_full = ""
        for text in lines:
            if color is not None:
                text_full += f"{format_text(text, color)}\n"
            else:
                text_full += f"{text}\n"
        return text_full

    @staticmethod
    def print_lines(lines: list[str], color: bcolors | None = None) -> None:
        print(ConsoleUX.format_lines(lines, color))

    def format_mod_description(self, mod: Mod) -> str:

        mod_info = self.format_mod_info(mod)
        return f"{format_text(loc_string('description'), bcolors.OKBLUE)}\n{mod.description}\n{mod_info}"

    def finilize_manifest(self, game: GameCopy, session: InstallationContext.Session) -> None:
        er_message = f"Couldn't dump install manifest to '{game.installed_manifest_path}'!"

        try:
            game.installed_content = game.installed_content | session.content_in_processing
            if game.installed_content:
                dumped_yaml = file_ops.dump_yaml(game.installed_content, game.installed_manifest_path)
                if not dumped_yaml:
                    self.simple_end("installation_error", er_message)
        except Exception as ex:
            self.logger.error(ex)
            self.logger.error(er_message)
            self.simple_end("installation_error", er_message)
            return

    def format_mod_info(self, mod: Mod) -> str:
        if ", " in mod.authors:
            developer_title = "authors"
        else:
            developer_title = "author"

        return (f"{format_text(loc_string(developer_title), bcolors.OKBLUE)} "
                f"{mod.authors}\n"
                f"{format_text(loc_string('mod_url'), bcolors.OKBLUE)} "
                f"{format_text(mod.url, bcolors.HEADER)}\n")

    def notify_on_mod_with_errors(self, mod: Mod, errors: list[str]) -> None:
        description = self.format_mod_description(mod)
        description += "\n" + format_text(loc_string("cant_be_installed") + ":\n", [bcolors.RED,
                                                                                    bcolors.BOLD])
        description += format_text("\n".join([line for line in errors]), bcolors.RED) + "\n"

        self.logger.info(f"Mod {mod.name} can't be installed, errors: {errors}")
        self.prompt_for(accept_enter=True,
                        description=description)

    def configure_mod_install(self, mod: Mod,
                              full_install: bool = False,
                              skip_to_options: bool = False,
                              validation_failed: bool = False,
                              game=None) -> list:
        install_settings = {}
        requres_custom_install = False

        if full_install:
            return mod.get_full_install_settings()

        if mod.name != "community_remaster":
            custom_header = "mod_install_custom"
            self.switch_header(custom_header,
                               additional_string=self.format_mod_title(mod.display_name, mod.version))
        else:
            custom_header = "remaster_custom"

        if mod.optional_content is not None:
            for option in mod.optional_content:
                if option.install_settings is not None and option.default_option is None:
                    # if any option doesn't have a default, we will ask user to make a choice
                    requres_custom_install = True
                    break

        if skip_to_options:
            install_settings["base"] = "yes"
        else:
            if ", " in mod.authors:
                developer_title = "authors"
            else:
                developer_title = "author"

            description = (f"{format_text(loc_string('description'), bcolors.OKBLUE)}\n{mod.description}\n"
                           f"{format_text(loc_string(developer_title), bcolors.OKBLUE)} "
                           f"{mod.authors}\n"
                           f"{format_text(loc_string('mod_url'), bcolors.OKBLUE)} "
                           f"{format_text(mod.url, bcolors.HEADER)}\n\n"
                           f"{loc_string('install_mod_ask')}")

            if game.installed_content.get(mod.name) is not None:
                options_to_offer = ["reinstall", "skip"]
                description = (format_text(loc_string("reinstalling_intro_mods")) + "\n\n"
                               + description + "\n\n"
                               + format_text(loc_string("warn_reinstall_mods"), bcolors.OKBLUE) + "\n")
            else:
                options_to_offer = ["yes", "no"]
                description += f" ({loc_string('yes_no')})"

            base_install = self.prompt_for(options_to_offer,
                                           accept_enter=False,
                                           description=description)
            if base_install == "reinstall":
                base_install = "yes"
            elif base_install == "skip":
                base_install = "no"

            install_settings["base"] = base_install

        if install_settings["base"] == "no":
            return

        custom_install_prompt = None

        if mod.optional_content is not None:
            if not requres_custom_install:
                default_options = []
                for option in mod.optional_content:
                    description = (format_text(f"* {option.display_name}\n", bcolors.OKBLUE)
                                   + option.description)
                    if option.install_settings is not None:
                        for setting in option.install_settings:
                            if setting.get("name") == option.default_option:
                                description += (f"\t** {loc_string('install_setting_title')}: "
                                                f"{setting.get('description')}")

                    default_options.append(description)
                default_options = '\n'.join(default_options)

                description = (f"{format_text(loc_string('description'), bcolors.OKBLUE)}\n"
                               f"{mod.description}\n"
                               f"{format_text(loc_string('default_options'), bcolors.HEADER)}\n\n"
                               f"{format_text(loc_string('default_options_prompt'))}\n\n"
                               f"{default_options}\n"
                               f"{format_text(loc_string('just_enter'), bcolors.HEADER)}\n"
                               f"{loc_string('or_options')}\n")

                custom_install_prompt = self.prompt_for(["options"], accept_enter=True,
                                                        description=description)
                if custom_install_prompt is None:
                    # using default settings then
                    install_settings = mod.get_full_install_settings()

            if requres_custom_install or custom_install_prompt == "options":
                for option in mod.optional_content:
                    custom_install_setting = None
                    if option.install_settings is not None:
                        available_settins = [f"* {setting.get('name')} - {setting.get('description')}"
                                             for setting in option.install_settings]
                        available_settins = '\n'.join(available_settins)
                        description = (f"{format_text(loc_string('description'), bcolors.OKBLUE)}\n"
                                       f"{option.description}"
                                       f"\n{loc_string('install_settings')}\n\n{available_settins}\n"
                                       f"{loc_string('install_setting_ask')} ({loc_string('skip')}) ")
                        available_options = [setting.get("name") for setting in option.install_settings]
                        available_options.append("skip")

                        self.switch_header(custom_header,
                                           additional_string=self.format_mod_title(mod.display_name,
                                                                                   mod.version,
                                                                                   option.display_name))
                        custom_install_setting = self.prompt_for(available_options,
                                                                 accept_enter=False,
                                                                 description=description)
                    else:
                        description = (f"{format_text(loc_string('description'), bcolors.OKBLUE)}\n"
                                       f"{option.description}"
                                       f"\n{loc_string('install_setting_ask')} ({loc_string('yes_no')}) ")
                        self.switch_header(custom_header,
                                           additional_string=self.format_mod_title(mod.display_name,
                                                                                   mod.version,
                                                                                   option.display_name))
                        custom_install_setting = self.prompt_for(["yes", "no"],
                                                                 accept_enter=False,
                                                                 description=description)
                        if custom_install_setting == "no":
                            custom_install_setting = "skip"
                    install_settings[option.name] = custom_install_setting
            if mod.name != "community_remaster":
                custom_header = "mod_install_custom"
                self.switch_header(custom_header,
                                   additional_string=self.format_mod_title(mod.display_name, mod.version))

        return install_settings
