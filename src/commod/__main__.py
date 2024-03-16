import platform
import sys
from ctypes import windll

from commod.gui import commod_flet
from commod.helpers.parse_ops import init_input_parser


def main_gui() -> None:
    commod_flet.start()



if __name__ == "__main__":
    options = init_input_parser().parse_args()
    if "Windows" in platform.system():
        windll.shcore.SetProcessDpiAwareness(2)
    if options.console:
        print("Console mode is not functional in this version, use earlier version.")
        sys.exit()
    else:
        sys.exit(main_gui())
