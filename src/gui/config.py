import os
from enum import Enum

import flet as ft
import localisation.service as localisation
from game.environment import GameInstallments, InstallationContext
from helpers.file_ops import dump_yaml, read_yaml


class AppSections(Enum):
    LAUNCH = 0
    LOCAL_MODS = 1
    DOWNLOAD_MODS = 2
    SETTINGS = 3


class Config:
    def __init__(self, page: ft.Page) -> None:
        self.init_width: int = 900
        self.init_height: int = 700
        self.init_pos_x: int = 0
        self.init_pos_y: int = 0
        self.init_theme: ft.ThemeMode = ft.ThemeMode.SYSTEM

        self.lang: str = localisation.LANG

        self.current_game: str = ""
        self.known_games: set = set()
        self.game_names: dict = {}

        self.current_distro: str = ""
        self.known_distros: set = set()

        self.modder_mode: bool = False

        self.current_section = AppSections.SETTINGS.value
        self.current_game_filter = GameInstallments.ALL.value
        self.game_with_console = False

        self.page: ft.Page = page

    def asdict(self) -> dict:
        return {
            "current_game": self.current_game,
            "game_names": self.game_names,
            "current_distro": self.current_distro,
            "modder_mode": self.modder_mode,
            "current_section": self.current_section,
            "current_game_filter": self.current_game_filter,
            "game_with_console": self.game_with_console,
            "window": {"width": self.page.window_width,
                       "height": self.page.window_height,
                       "pos_x":  self.page.window_left,
                       "pos_y": self.page.window_top},
            "theme": self.page.theme_mode.value,
            "lang": self.lang
        }

    def load_from_file(self, abs_path: str | None = None) -> None:
        if abs_path is not None and os.path.exists(abs_path):
            config = read_yaml(abs_path)
        else:
            config = InstallationContext.get_config()

        if isinstance(config, dict):
            lang = config.get("lang")
            if isinstance(lang, str):
                self.lang = lang

            current_game = config.get("current_game")
            if isinstance(current_game, str) and os.path.isdir(current_game):
                self.current_game = current_game

            game_names = config.get("game_names")
            if isinstance(game_names, dict):
                for path, name in game_names.items():
                    if isinstance(path, str) and os.path.isdir(path) and (name is not None):
                        self.game_names[path] = str(name)

            self.known_games = {game_path.lower() for game_path in self.game_names}

            current_distro = config.get("current_distro")
            if isinstance(current_distro, str) and os.path.isdir(current_distro):
                self.current_distro = current_distro

            self.known_distros = {config["current_distro"]}

            modder_mode = config.get("modder_mode")
            if isinstance(modder_mode, bool):
                self.modder_mode = modder_mode

            current_section = config.get("current_section")
            if current_section in (0, 1, 2, 3):
                self.current_section = current_section

            current_game_filter = config.get("current_game_filter")
            if current_game_filter in (0, 1, 2, 3):
                self.current_game_filter = current_game_filter

            game_with_console = config.get("game_with_console")
            if isinstance(game_with_console, bool):
                self.game_with_console = game_with_console

            window_config = config.get("window")
            # ignoring broken partial configs for window
            if (isinstance(window_config, dict) and
                all(isinstance(window_config.get("width"), float),
                    isinstance(window_config.get("height"), float),
                    isinstance(window_config.get("pos_x"), float),
                    isinstance(window_config.get("pos_y"), float))):
                # TODO: validate that window is not completely outside the screen area
                self.init_height = window_config["height"]
                self.init_width = window_config["width"]
                self.init_pos_x = window_config["pos_x"]
                self.init_pos_y = window_config["pos_y"]

            theme = config.get("theme")
            if theme in ("system", "light", "dark"):
                self.init_theme = ft.ThemeMode(theme)

    def save_config(self, abs_dir_path: str | None = None) -> None:
        if abs_dir_path is not None and os.path.isdir(abs_dir_path):
            config_path = os.path.join(abs_dir_path, "commod.yaml")
        else:
            config_path = os.path.join(InstallationContext.get_local_path(), "commod.yaml")

        result = dump_yaml(self.asdict(), config_path, sort_keys=False)
        if not result:
            self.page.app.logger.debug("Couldn't write new config")
