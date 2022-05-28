import os
from utils import format_text, loc_string, bcolors


class ConsoleUX:
    '''Helper class for printing and asking for a user input via console'''
    def __init__(self, context, dev_mode: bool = False) -> None:
        self.auto_clear = True
        self.context = context
        if dev_mode:
            self.dev_mode = True
            self.auto_clear = False
        else:
            self.dev_mode = False
        self.switch_header("default")

    def switch_header(self, identifier=str, exe_path: str | None = None):
        installation_title = f'{format_text(loc_string("installation_title"), bcolors.WARNING)}\n'
        if self.dev_mode:
            installation_title = format_text("DEVELOPER MODE\n", bcolors.RED) + installation_title
        patch_over_remaster = format_text(loc_string('cant_install_patch_over_remaster'), bcolors.OKBLUE)
        exe_info = ""
        if exe_path is not None:
            exe_info = f"{loc_string('patching_exe')}: {exe_path}\n"

        match identifier:
            case 'default':
                self.header = installation_title
            case 'patching_exe':
                self.header = installation_title + exe_info
            case 'patch_over_remaster':
                self.header = installation_title + exe_info + patch_over_remaster

    @classmethod
    def simple_end(self, message: str, err_msg) -> None:
        '''Simple info display shown before exiting the proccess as a result of exception'''
        gray_err_msg = format_text(f"Error: {err_msg}", bcolors.GRAY)
        self.prompt_for(accept_enter=True,
                        header="default",
                        description=f"{loc_string(message)}\n\n{gray_err_msg}",
                        stopping=True)

    @classmethod
    def prompt_for(self,
                   option_list: list = [], accept_enter: bool = False,
                   auto_clear: bool = False,
                   header: str | None = None,
                   description: str | None = None,
                   stopping: bool = False):
        '''Ask user to choose from a few options, accept answers from the predefined list given'''
        if auto_clear:
            os.system('cls')
        no_options = len(option_list) == 0
        if no_options and not accept_enter and not stopping:
            raise ValueError("There should be at least one option to confirm when asking user!")
        user_choice = None
        previous_prompt = None
        if header == "default":
            header = self.header
        while (user_choice not in option_list):
            if header is not None and not auto_clear:
                if previous_prompt is None:
                    print(header)
            elif header is not None:
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

        return user_choice
