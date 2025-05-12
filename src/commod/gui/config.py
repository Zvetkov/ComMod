import os
from enum import Enum
from pathlib import Path
from typing import Any

import flet as ft

import commod.localisation.service as localisation
from commod.game.data import GameFilter
from commod.game.environment import GameCopy, InstallationContext
from commod.helpers.file_ops import dump_yaml, read_yaml


class AppSections(Enum):
    LAUNCH = 0
    LOCAL_MODS = 1
    DOWNLOAD_MODS = 2
    SETTINGS = 3
    MODDING_TOOLS = 4

    @classmethod
    def list_values(cls) -> list[int]:
        return [c.value for c in cls]


class Config:
    def __init__(self, page: ft.Page) -> None:
        self.init_width: int = 900
        self.init_height: int = 700
        self.init_pos_x: int = 0
        self.init_pos_y: int = 0
        self.init_theme: ft.ThemeMode = ft.ThemeMode.SYSTEM

        self._lang: str = localisation.stored.language

        self.current_game: str = ""
        self.game_names: dict[str, str] = {}
        self.loaded_games: dict[str, GameCopy] = {}

        self.current_distro: str = ""
        self.last_differ_source: str = ""
        self.last_differ_modded: str = ""
        # pretty much useless right now as only single distro is supported at the same time
        self.known_distros: set[str] = set()

        self.modder_mode: bool = False
        self.override_incompat: bool = False

        self.current_section: int = AppSections.SETTINGS.value
        self.current_game_filter: int = GameFilter.ALL.value
        self.game_with_console: bool = False
        self.linux_run_cmd = "flatpak run net.lutris.Lutris lutris:rungame/HTA"
        self.code_editor = "code"

        self.page: ft.Page = page

    def asdict(self) -> dict[str, Any]:
        return {
            "current_game": self.current_game,
            "game_names": self.game_names,
            "current_distro": self.current_distro,
            "modder_mode": self.modder_mode,
            "override_incompat": self.override_incompat,
            "current_section": self.current_section,
            "current_game_filter": self.current_game_filter,
            "game_with_console": self.game_with_console,
            "window": {"width": self.page.window.width,
                       "height": self.page.window.height,
                       "pos_x":  self.page.window.left,
                       "pos_y": self.page.window.top},
            "theme": self.page.theme_mode.value,
            "lang": self.lang,
            "linux_run_cmd": self.linux_run_cmd,
            "code_editor": self.code_editor,
            "last_differ_source": self.last_differ_source,
            "last_differ_modded": self.last_differ_modded,
        }

    @property
    def known_games(self) -> set[str]:
        return {game_path.lower() for game_path in self.game_names}

    def get_game_copy(self, game_path: str | None = None,
                      reset_cache: bool = False) -> GameCopy:
        cached_game = self.loaded_games.get(game_path)
        if game_path and cached_game and not reset_cache:
            return cached_game
        new_game = GameCopy()
        self.loaded_games[game_path] = new_game
        return new_game

    @property
    def lang(self) -> str:
        return self._lang

    @lang.setter
    def lang(self, new_lang: localisation.SupportedLanguages) -> None:
        if isinstance(new_lang, str) and new_lang in localisation.SupportedLanguages.list_values():
            self._lang = new_lang
            localisation.stored.language = new_lang

    def load_from_file(self, abs_path: str | None = None) -> None:
        if abs_path is not None and os.path.exists(abs_path):
            config = read_yaml(abs_path)
        else:
            config = InstallationContext.get_commod_config()

        if isinstance(config, dict):
            lang = config.get("lang")
            if isinstance(lang, str) and lang in localisation.SupportedLanguages.list_values():
                self._lang = lang
                localisation.stored.language = lang

            current_game = config.get("current_game")
            if isinstance(current_game, str) and os.path.isdir(current_game):
                self.current_game = current_game

            game_names = config.get("game_names")
            if isinstance(game_names, dict):
                for path, name in game_names.items():
                    if isinstance(path, str) and os.path.isdir(path) and (name is not None):
                        self.game_names[path] = str(name)

            current_distro = config.get("current_distro")
            if isinstance(current_distro, str) and os.path.isdir(current_distro):
                self.current_distro = current_distro

            last_differ_source = config.get("last_differ_source")
            if isinstance(last_differ_source, str) and os.path.isdir(last_differ_source):
                self.last_differ_source = last_differ_source

            last_differ_modded = config.get("last_differ_modded")
            if isinstance(last_differ_modded, str) and os.path.isdir(last_differ_modded):
                self.last_differ_modded = last_differ_modded

            self.known_distros = {self.current_distro}

            modder_mode = config.get("modder_mode")
            if isinstance(modder_mode, bool):
                self.modder_mode = modder_mode

            override_incompat = config.get("override_incompat")
            if isinstance(override_incompat, bool):
                self.override_incompat = override_incompat

            current_section = config.get("current_section")
            if current_section in AppSections.list_values():
                if self.modder_mode is False and current_section == AppSections.MODDING_TOOLS.value:
                    current_section = AppSections.LAUNCH.value
                self.current_section = current_section

            current_game_filter = config.get("current_game_filter")
            if current_game_filter in GameFilter.list_values():
                self.current_game_filter = current_game_filter

            game_with_console = config.get("game_with_console")
            if isinstance(game_with_console, bool):
                self.game_with_console = game_with_console

            linux_run_cmd = config.get("linux_run_cmd")
            if isinstance(linux_run_cmd, str):
                self.linux_run_cmd = linux_run_cmd

            code_editor = config.get("code_editor")
            if isinstance(code_editor, str):
                self.code_editor = code_editor

            window_config = config.get("window")
            # ignoring broken partial configs for window
            if (isinstance(window_config, dict)
                and isinstance(window_config.get("width"), float)
                and isinstance(window_config.get("height"), float)
                and isinstance(window_config.get("pos_x"), float)
                and isinstance(window_config.get("pos_y"), float)):
                # TODO: validate that window is not completely outside the screen area
                self.init_height = window_config["height"]
                self.init_width = window_config["width"]
                self.init_pos_x = window_config["pos_x"]
                self.init_pos_y = window_config["pos_y"]

            theme = config.get("theme")
            if theme in ("system", "light", "dark"):
                self.init_theme = ft.ThemeMode(theme)

    def add_game_to_config(self, game_path: str, name: str = "Ex Machina") -> None:
        if os.path.isdir(game_path):
            self.game_names[game_path] = name
            self.known_games.add(game_path.lower())
            self.current_game = game_path

    def add_distro_to_config(self, distro_path: str) -> None:
        if os.path.isdir(distro_path):
            self.known_distros.add(distro_path)
            self.current_distro = distro_path

    def set_last_differ_source(self, dir_path: str | Path) -> None:
        if Path(dir_path).is_dir():
            self.last_differ_source = str(dir_path)

    def set_last_differ_modded(self, dir_path: str | Path) -> None:
        if Path(dir_path).is_dir():
            self.last_differ_modded = str(dir_path)

    def save_config(self, abs_dir_path: str | None = None) -> None:
        if abs_dir_path is not None and os.path.isdir(abs_dir_path):
            config_path = os.path.join(abs_dir_path, "commod.yaml")
        else:
            config_path = os.path.join(InstallationContext.get_local_config_path(), "commod.yaml")

        result = dump_yaml(self.asdict(), config_path, sort_keys=False)
        if not result:
            self.page.app.logger.debug("Couldn't write new config")
