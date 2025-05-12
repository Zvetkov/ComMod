import platform
import sys

from commod.gui import commod_flet
from commod.helpers.parse_ops import init_input_parser


def main_gui() -> None:
    commod_flet.start()



if __name__ == "__main__":
    options = init_input_parser().parse_args()
    if "Windows" in platform.system():
        try:
            from ctypes import windll
            windll.shcore.SetProcessDpiAwareness(2)
        except (ImportError, NameError):
            pass
    if options.console:
        print("Console mode is not functional in this version, use earlier version.")
        sys.exit()
    else:
        sys.exit(main_gui())
