import argparse
import platform
import sys
from ctypes import windll

from console import commod_console
from gui import commod_flet


def main_gui() -> None:
    commod_flet.start()


def main_console(options: argparse.Namespace) -> None:
    commod_console.main(options)


def _init_input_parser():
    parser = argparse.ArgumentParser(description='DEM Community Mod Manager')
    parser.add_argument('-target_dir', help='path to game directory', required=False)
    parser.add_argument('-distribution_dir',
                        help=('path to root folder where "patch", "remaster", "libs" '
                              'and an optional folder "mods" are located'), required=False)
    parser.add_argument('-dev', help='developer mode',
                        action="store_true", default=False, required=False)
    parser.add_argument('-console', help='run in console',
                        action="store_true", default=False, required=False)
    installation_option = parser.add_mutually_exclusive_group()
    installation_option.add_argument('-compatch', help='base ComPatch setup, silent console mode',
                                     action="store_true", default=False)
    installation_option.add_argument('-comremaster', help='base ComRemaster, silent console mode',
                                     action="store_true", default=False)

    return parser


if __name__ == '__main__':
    options = _init_input_parser().parse_args()
    if "Windows" in platform.system():
        windll.shcore.SetProcessDpiAwareness(2)
    if options.console:
        sys.exit(main_console(options))
    else:
        sys.exit(main_gui())
