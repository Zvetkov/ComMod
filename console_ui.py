import os
import sys
import file_ops
from data import loc_string


class bcolors:
    HEADER = '\033[95m'   # Bright Magenta
    OKBLUE = '\033[94m'   # Bright Blue
    OKCYAN = '\033[96m'   # Bright Cyan
    OKGREEN = '\033[92m'  # Bright Green
    WARNING = '\033[93m'  # Bright Yellow
    RED = '\033[91m'      # Bright Red
    GRAY = '\033[90m'     # Bright Black (Gray)
    ENDC = '\033[0m'      # closing code 'tag'
    BOLD = '\033[1m'
    FAINT = '\033[2m'     # decreased intensity or dim
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'


def format_text(string: str, style: bcolors = bcolors.BOLD) -> str:
    return f"{style}{string}{bcolors.ENDC}"


class ConsoleUX:
    '''Helper class for printing and asking for a user input via console'''
    def __init__(self, dev_mode: bool = False) -> None:
        self.auto_clear = True
        if dev_mode:
            self.dev_mode = True
            self.auto_clear = False
        else:
            self.dev_mode = False
        self.switch_header("default")

    def switch_header(self, identifier=str, exe_path: str | None = None,
                      additional_string: str = "") -> None:
        installation_title = f'{format_text(loc_string("installation_title"), bcolors.WARNING)}\n'
        if self.dev_mode:
            installation_title = format_text("DEVELOPER MODE\n", bcolors.RED) + installation_title
        advanced = f'{format_text(loc_string("advanced"), bcolors.WARNING)} '

        if exe_path is not None:
            exe_info = f"{loc_string('patching_exe')}: {exe_path}\n"
        else:
            exe_info = ""

        match identifier:
            case "default":
                self.header = installation_title
            case "leftovers":
                self.header = installation_title + format_text(loc_string("install_leftovers"), bcolors.RED)
            case "patching_exe":
                self.header = installation_title + exe_info
            case "patch":
                self.header = format_text(loc_string("patch_title"), bcolors.WARNING) + '\n'
            case "remaster":
                self.header = format_text(loc_string("remaster_title"), bcolors.WARNING) + '\n'
            case "remaster_custom":
                self.header = additional_string
            case "patch_over_remaster":
                self.header = (format_text(loc_string("remaster_title"), bcolors.WARNING) + '\n' + exe_info
                               + format_text(loc_string("cant_install_patch_over_remaster"), bcolors.OKBLUE))
            case "advanced":
                self.header = advanced + installation_title
            case "mod_manager":
                self.header = format_text(loc_string("mod_manager_title"), bcolors.OKBLUE) + '\n'
            case "mod_install_custom":
                self.header = (format_text(loc_string("mod_manager_title"), bcolors.OKBLUE) + '\n'
                               + additional_string)

    def simple_end(self, message: str, err_msg: Exception | None = None, **kwargs) -> None:
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
    def format_mod_title(display_name: str, version: str, option_name: str = "") -> str:
        title = format_text(f"{loc_string('installation')} {display_name} - "
                            f"{loc_string('version')} {version}\n",
                            bcolors.WARNING)
        if option_name:
            title += f'{format_text(option_name, bcolors.OKGREEN)} ({loc_string("optional_content")})\n'
        return title

    def prompt_for(self,
                   option_list: list = [], accept_enter: bool = False,
                   description: str | None = None,
                   stopping: bool = False):
        '''Ask user to choose from a few options, accept answers from the predefined list given'''
        auto_clear = self.auto_clear
        if auto_clear:
            os.system('cls')
        no_options = len(option_list) == 0
        if no_options and not accept_enter and not stopping:
            raise ValueError("There should be at least one option to confirm when asking user!")
        user_choice = None
        previous_prompt = None
        header = self.header
        while (user_choice not in option_list):
            if not auto_clear:
                if previous_prompt is None:
                    print(header)
            else:
                print(header)

            if previous_prompt is not None:
                print(format_text(f"'{previous_prompt}' - {loc_string('incorrect_prompt_answer')}",
                                  bcolors.RED))

            if description is not None and not auto_clear:
                if previous_prompt is None:
                    print(description)
            elif description is not None:
                print(description)

            formatted_msg = ""
            if stopping:
                formatted_msg = f"{format_text(loc_string('stopping_patching'), bcolors.RED)}"
            elif accept_enter:
                formatted_msg = f"{format_text(loc_string('enter_accepted_prompt'), bcolors.OKGREEN)}: "
            elif option_list:
                formatted_msg = f"{format_text(loc_string('base_prompt'), bcolors.OKGREEN)}: "

            if stopping:
                pass
            elif no_options and accept_enter:
                formatted_msg += f"{format_text(loc_string('press_enter_to_continue'))}"
            else:
                formatted_msg += f"{', '.join([format_text(opt) for opt in option_list])}"

            print(formatted_msg)

            try:
                user_choice = input()
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
                self.simple_end("installation_aborted")
                sys.exit()

        return user_choice

    def final_screen_print(self, installed_description: list) -> None:
        if self.auto_clear:
            os.system('cls')
        print(format_text(self.header, bcolors.WARNING))
        print(format_text(loc_string("installed_listing"), bcolors.OKBLUE))
        for line in installed_description:
            print(line)

    def final_screen_mod_manager_print(self, installed_content_description, mod_installation_errors):
        if self.auto_clear:
            os.system('cls')
        print(format_text(f'{loc_string("mod_manager_title")}', bcolors.OKGREEN))
        self.print_lines(installed_content_description)
        if mod_installation_errors:
            self.print_lines(mod_installation_errors, color=bcolors.RED)
        else:
            print(format_text(loc_string("installation_finished"), bcolors.OKGREEN))

    def copy_patch_files(self, distribution_dir: str, game_root: str) -> None:
        if self.auto_clear:
            os.system('cls')
        print(format_text(loc_string("copying_patch_files_please_wait"), bcolors.RED))
        try:
            file_ops.copy_from_to([os.path.join(distribution_dir, "patch")], os.path.join(game_root, "data"),
                                  console=True)
            file_ops.copy_from_to([os.path.join(distribution_dir, "libs")], game_root,
                                  console=True)
        except KeyboardInterrupt:
            self.simple_end("installation_aborted")
            sys.exit()

    @staticmethod
    def print_lines(lines: list, color=None):
        for text in lines:
            if color is not None:
                text = format_text(text, color)
            print(text)

    def configure_mod_install(self, mod,  #: Mod,
                              full_install: bool = False,
                              skip_to_options: bool = False) -> list:
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
                           f"{format_text(loc_string('mod_url'), bcolors.OKBLUE)} {mod.url}\n\n"

                           f"{loc_string('install_mod_ask')} ({loc_string('yes_no')}) ")
            base_install = self.prompt_for(["yes", "no"],
                                           accept_enter=False,
                                           description=description)
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
                               f"{mod.description} \n{loc_string('default_options')}\n\n"
                               f"{default_options}\n{format_text(loc_string('just_enter'), bcolors.HEADER)}"
                               f"{loc_string('or_options')}")

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

        return install_settings
