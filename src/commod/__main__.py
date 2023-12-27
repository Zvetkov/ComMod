import argparse
import platform
import sys
from ctypes import windll

from commod.console import commod_console
from commod.gui import commod_flet
from commod.helpers.parse_ops import init_input_parser


def main_gui() -> None:
    commod_flet.start()


def main_console(options: argparse.Namespace) -> None:
    commod_console.main(options)


if __name__ == "__main__":
    options = init_input_parser().parse_args()
    if "Windows" in platform.system():
        windll.shcore.SetProcessDpiAwareness(2)
    if options.console:
        sys.exit(main_console(options))
    else:
        sys.exit(main_gui())
