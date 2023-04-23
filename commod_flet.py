
from asyncio import create_task, gather, create_subprocess_exec
import asyncio
from datetime import datetime
import os

from dataclasses import dataclass  # , field
from enum import Enum
from pathlib import Path

from asyncio_requests.asyncio_request import request

import localisation

from commod import _init_input_parser
from data import get_title
from environment import InstallationContext, GameCopy, GameInstallments, GameStatus, DistroStatus
import file_ops
from file_ops import dump_yaml, get_internal_file_path, get_proc_by_names, read_yaml,\
                     process_markdown
from localisation import tr, SupportedLanguages
from mod import Mod

# logging.basicConfig(level=logging.DEBUG)

from errors import ExeIsRunning, ExeNotFound, ExeNotSupported, HasManifestButUnpatched, InvalidGameDirectory,\
                   PatchedButDoesntHaveManifest, WrongGameDirectoryPath,\
                   DistributionNotFound, FileLoggingSetupError, InvalidExistingManifest, ModsDirMissing,\
                   NoModsFound, CorruptedRemasterFiles, DXRenderDllNotFound


import flet as ft
from flet import (
    Column,
    FloatingActionButton,
    IconButton,
    Page,
    Row,
    Tab,
    Tabs,
    Text,
    TextField,
    UserControl,
    colors,
    icons,
    ThemeVisualDensity,
    Theme,
    Image,
    Icon
)


class AppSections(Enum):
    LAUNCH = 0
    LOCAL_MODS = 1
    DOWNLOAD_MODS = 2
    SETTINGS = 3


class LangFlags(Enum):
    eng = "assets\\flags\\openmoji_uk.svg"
    us = "assets\\flags\\openmoji_us.svg"
    ru = "assets\\flags\\openmoji_ru.svg"
    ua = "assets\\flags\\openmoji_ua.svg"
    de = "assets\\flags\\openmoji_de.svg"
    tr = "assets\\flags\\openmoji_tr.svg"
    pl = "assets\\flags\\openmoji_pl.svg"
    other = "assets\\flags\\openmoji_orange.svg"


class Config:
    def __init__(self, page) -> None:
        self.init_width: int = 900
        self.init_height: int = 700
        self.init_pos_x: int = 0
        self.init_pos_y: int = 0
        self.init_theme: ft.ThemeMode = ft.ThemeMode.SYSTEM

        self.lang: SupportedLanguages = SupportedLanguages.SYS

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

    def asdict(self):
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
            "lang": self.lang.value
        }

    def load_from_file(self, abs_path: str | None = None):
        if abs_path is not None and os.path.exists(abs_path):
            config = read_yaml(abs_path)
        else:
            config = InstallationContext.get_config()

        if isinstance(config, dict):
            current_game = config.get("current_game")
            if isinstance(current_game, str) and os.path.isdir(current_game):
                self.current_game = current_game

            game_names = config.get("game_names")
            if isinstance(game_names, dict):
                for path, name in game_names.items():
                    if isinstance(path, str) and os.path.isdir(path) and (name is not None):
                        self.game_names[path] = str(name)

            self.known_games = set([game_path.lower() for game_path in self.game_names])

            current_distro = config.get("current_distro")
            if isinstance(current_distro, str) and os.path.isdir(current_distro):
                self.current_distro = current_distro

            self.known_distros = set([config["current_distro"]])

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
            if isinstance(window_config, dict):
                if (isinstance(window_config.get("width"), float)
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

    def save_config(self, abs_dir_path: str | None = None):
        if abs_dir_path is not None and os.path.isdir(abs_dir_path):
            config_path = os.path.join(abs_dir_path, "commod.yaml")
        else:
            config_path = os.path.join(InstallationContext.get_local_path(), "commod.yaml")

        result = dump_yaml(self.asdict(), config_path, sort_keys=False)
        if not result:
            self.page.app.logger.debug("Couldn't write new config")


@dataclass
class App:
    '''Root level application class storing modding environment'''
    context: InstallationContext
    game: GameCopy
    config: Config | None = None
    session: InstallationContext.Session | None = None
    game_change_time: None | datetime = None

    def __post_init__(self):
        self.session = self.context.current_session

    async def change_page(self, e=None, index: int | AppSections = AppSections.LAUNCH):
        if e is None:
            new_index = index
        else:
            new_index = e.control.selected_index

        if self.content_column.content:
            real_index = self.config.current_section
        else:
            real_index = -1

        if new_index != real_index:
            self.rail.selected_index = new_index

            self.content_column.content = self.content_pages[new_index]
            await self.content_column.update_async()
            await self.content_pages[new_index].update_async()
            self.config.current_section = new_index
        await self.rail.update_async()

    async def show_guick_start_wizard(self):
        await self.change_page(index=AppSections.SETTINGS.value)
        await self.content_column.update_async()

    async def close_alert(self, e):
        self.page.dialog.open = False
        await self.page.update_async()

    async def show_alert(self, text, additional_text=""):
        if self.page.dialog is not None:
            if self.page.dialog.open:
                return

        dlg = ft.AlertDialog(
            title=Row([Icon(ft.icons.WARNING_OUTLINED, color=ft.colors.ERROR_CONTAINER),
                       Text(tr("error"))]),
            shape=ft.buttons.RoundedRectangleBorder(radius=10),
            content=Column([Text(text),
                            Text(additional_text,
                                 visible=bool(additional_text),
                                 color=ft.colors.ON_ERROR_CONTAINER)],
                           spacing=5,
                           tight=True),
            actions=[
                ft.TextButton("Ok", on_click=self.close_alert)],
            actions_padding=ft.padding.only(left=20, bottom=20, right=20)
            )
        self.page.dialog = dlg
        dlg.open = True
        await self.page.update_async()

    def load_distro(self):
        print("loading distro")
        try:
            if not self.context.validated_mod_configs:
                try:
                    self.context.load_mods()
                    print("loaded mods")
                except ModsDirMissing:
                    self.logger.info("No mods folder found, creating")
                except NoModsFound:
                    self.logger.info("No mods found")

            self.logger.info("Prevalidating Community Patch and Remaster state")
            self.context.validate_remaster()
            self.game.load_installed_descriptions(self.context.validated_mod_configs)
            remaster_mod = Mod(self.context.remaster_config, self.context.remaster_path)
            remaster_mod.load_translations(load_gui_info=True)
            remaster_mod.load_gui_info()

            for translation in remaster_mod.translations_loaded.values():
                commod_compatible_tr, commod_compat_err_tr = \
                    translation.compatible_with_mod_manager(self.context.commod_version)
                compat_info_tr = {
                    "compatible_with_commod": commod_compatible_tr,
                    "compatible_with_commod_err": commod_compat_err_tr}
                translation.load_session_compatibility(compat_info_tr)

            self.session.mods[self.context.remaster_path] = remaster_mod

            manifest = self.context.remaster_config
            # TODO: understand if this id really needed
            # and if it's working as intended (prevents dumplication)
            mod_identifier = f'{manifest["name"]}{manifest["version"]}{manifest["build"]}'
            self.session.tracked_mods.add(self.context.remaster_path)
        except CorruptedRemasterFiles as er:
            self.logger.error(er)
            self.context.remaster_path = None
            self.remaster_config = {}

        if self.context.validated_mod_configs:
            for manifest_path, manifest in self.context.validated_mod_configs.items():
                mod_identifier = f'{manifest["name"]}{manifest["version"]}{manifest["build"]}'
                if mod_identifier not in self.session.tracked_mods:
                    mod = Mod(manifest, Path(manifest_path).parent)

                    try:
                        mod.load_translations(load_gui_info=True)
                    except Exception as ex:
                        self.logger.error(ex)
                        continue

                    mod.load_gui_info()

                    for translation in mod.translations_loaded.values():
                        commod_compatible_tr, commod_compat_err_tr = \
                            translation.compatible_with_mod_manager(self.context.commod_version)
                        prevalidated_tr, prevalid_errors_tr = translation.check_requirements(
                            self.game.installed_content,
                            self.game.installed_descriptions)
                        compatible_tr, incompatible_errors_tr = translation.check_incompatibles(
                            self.game.installed_content,
                            self.game.installed_descriptions)
                        compat_info_tr = {
                            "compatible_with_commod": commod_compatible_tr,
                            "compatible_with_commod_err": commod_compat_err_tr,
                            "prevalidated": prevalidated_tr,
                            "prevalidated_err": prevalid_errors_tr,
                            "compatible": compatible_tr,
                            "compatible_err": incompatible_errors_tr}
                        translation.load_session_compatibility(compat_info_tr)

                    self.session.mods[manifest_path] = mod
                    self.session.tracked_mods.add(mod_identifier)


class GameCopyListItem(UserControl):
    def __init__(self, game_name, game_path,
                 game_installment, game_version,
                 warning, current,
                 select_game_func, remove_game_func,
                 config, visible):
        super().__init__()
        self.current = current
        self.game_name = game_name
        self.game_path = game_path
        self.installment = game_installment
        self.version = game_version.replace("Remaster", "Rem")
        self.warning = warning
        self.select_game = select_game_func
        self.remove_game = remove_game_func
        self.config = config
        self.visible = visible

    def build(self):
        self.game_name_label = ft.Ref[Text]()
        self.current_icon = ft.Ref[IconButton]()
        self.item_container = ft.Ref[ft.Container]()

        self.current_game = Row([
                ft.Tooltip(
                    message=tr("use_this_game"),
                    wait_duration=500,
                    content=IconButton(
                        icon=ft.icons.DONE_OUTLINE_ROUNDED if self.current else ft.icons.DONE_OUTLINE,
                        icon_color=colors.GREEN if self.current else ft.colors.SURFACE_VARIANT,
                        on_click=self.make_current,
                        width=45, height=45,
                        ref=self.current_icon,
                        )
                ),
                Row([ft.Container(Column([
                    ft.Tooltip(
                        message=tr("exe_version"),
                        wait_duration=500,
                        content=ft.Container(
                            Text(self.version,
                                 weight=ft.FontWeight.W_600,
                                 color=ft.colors.PRIMARY,
                                 text_align=ft.TextAlign.CENTER),
                            width=120,
                            bgcolor=ft.colors.BACKGROUND,
                            border=ft.border.all(2, ft.colors.SECONDARY_CONTAINER),
                            border_radius=16, padding=ft.padding.only(left=10, right=10, top=5, bottom=5))
                    ),
                    ft.Tooltip(
                        visible=bool(self.warning),
                        message=f"{self.warning} ",
                        wait_duration=300,
                        content=ft.Container(
                            Text(tr("dirty_copy"),
                                 weight=ft.FontWeight.W_600,
                                 color=ft.colors.ON_ERROR_CONTAINER,
                                 text_align=ft.TextAlign.CENTER),
                            bgcolor=ft.colors.ERROR_CONTAINER,
                            border_radius=15, padding=ft.padding.only(left=10, right=10, top=5, bottom=5),
                            visible=bool(self.warning)),
                    )], spacing=5), padding=ft.padding.symmetric(vertical=5)),
                    ft.Tooltip(
                        message=self.game_path,
                        content=ft.Container(
                            Text(self.game_name,
                                 weight=ft.FontWeight.W_500,
                                 ref=self.game_name_label, width=300),
                            margin=ft.margin.symmetric(vertical=10)),
                        wait_duration=300)
                    ])
                    ], spacing=5, expand=True)

        self.edit_name = TextField(prefix_text=f'{tr("new_name")}:  ',
                                   expand=True,
                                   dense=True,
                                   border_radius=20,
                                   border_width=2,
                                   focused_border_width=3,
                                   border_color=ft.colors.ON_SECONDARY_CONTAINER,
                                   text_style=ft.TextStyle(size=13,
                                                           color=ft.colors.ON_SECONDARY_CONTAINER,
                                                           weight=ft.FontWeight.W_500),
                                   focused_border_color=ft.colors.PRIMARY,
                                   text_size=13,
                                   max_length=256,
                                   on_submit=self.save_clicked)

        self.display_view = Row(
            alignment=ft.MainAxisAlignment.END,
            vertical_alignment="center",
            controls=[
                self.current_game,
                Row(controls=[
                        ft.Tooltip(
                            message=tr("open_in_explorer"),
                            wait_duration=300,
                            content=IconButton(
                                icon=icons.FOLDER_OPEN,
                                on_click=self.open_clicked),
                        ),
                        ft.Tooltip(
                            message=tr("remove_from_list"),
                            wait_duration=300,
                            content=IconButton(
                                icons.DELETE_OUTLINE,
                                on_click=self.delete_clicked)
                        ),
                        ft.Tooltip(
                            message=tr("edit_name"),
                            wait_duration=300,
                            content=IconButton(
                                icon=icons.CREATE_OUTLINED,
                                on_click=self.edit_clicked)
                        )], spacing=5
                    )]
                )

        self.edit_view = Row(
            visible=False,
            alignment=ft.MainAxisAlignment.SPACE_AROUND,
            vertical_alignment=ft.CrossAxisAlignment.START,
            spacing=20,
            controls=[
                self.edit_name,
                IconButton(
                    icon=ft.icons.SAVE,
                    icon_color=colors.GREEN,
                    tooltip="Update game name",
                    on_click=self.save_clicked,
                    width=40, height=40,
                    icon_size=24
                ),
            ],
        )
        return ft.Container(Column(controls=[self.display_view, self.edit_view]),
                            bgcolor=ft.colors.SECONDARY_CONTAINER if self.current else ft.colors.TRANSPARENT,
                            border_radius=25,
                            padding=ft.padding.only(right=10),
                            ref=self.item_container)

    async def make_current(self, e):
        if not self.current:
            await self.select_game(self)
        await self.update_async()

    async def open_clicked(self, e):
        # open game directory in Windows Explorer
        if os.path.isdir(self.game_path):
            os.startfile(self.game_path)
        await self.update_async()

    async def display_as_current(self):
        self.current = True
        self.current_icon.current.icon = ft.icons.DONE_OUTLINE_ROUNDED
        self.current_icon.current.icon_color = ft.colors.GREEN
        await self.current_icon.current.update_async()
        self.item_container.current.bgcolor = ft.colors.SECONDARY_CONTAINER
        await self.item_container.current.update_async()
        await self.update_async()

    async def display_as_reserve(self):
        self.current = False
        self.current_icon.current.icon = ft.icons.DONE_OUTLINE
        self.current_icon.current.icon_color = ft.colors.SURFACE_VARIANT
        await self.current_icon.current.update_async()
        self.item_container.current.bgcolor = ft.colors.TRANSPARENT
        await self.item_container.current.update_async()
        await self.update_async()

    async def edit_clicked(self, e):
        self.edit_name.value = self.game_name_label.current.value
        self.display_view.visible = False
        self.edit_view.visible = True
        await self.update_async()

    async def save_clicked(self, e):
        self.game_name_label.current.value = self.edit_name.value
        self.game_name = self.edit_name.value
        self.display_view.visible = True
        self.edit_view.visible = False
        self.config.game_names[self.game_path] = self.game_name
        await self.update_async()

    async def status_changed(self, e):
        self.completed = self.current_game.value
        self.task_status_change(self)
        await self.update_async()

    async def delete_clicked(self, e):
        await self.remove_game(self)
        await self.update_async()


class SettingsScreen(UserControl):
    def __init__(self, app, **kwargs):
        super().__init__(self, **kwargs)
        self.app = app

    def build(self):
        game_icon = Image(src=get_internal_file_path("icons/hta_comrem.png"),
                          width=24,
                          height=24,
                          fit=ft.ImageFit.FIT_HEIGHT)

        dem_icon = Image(src=get_internal_file_path("icons/dem_logo.svg"),
                         width=24,
                         height=24,
                         fit=ft.ImageFit.FIT_HEIGHT)

        steam_icon = Image(src=get_internal_file_path("icons/steampowered.svg"),
                           width=24,
                           height=24,
                           fit=ft.ImageFit.FIT_HEIGHT)

        self.get_game_dir_dialog = ft.FilePicker(on_result=self.get_game_dir_result)
        self.get_distro_dir_dialog = ft.FilePicker(on_result=self.get_distro_dir_result)

        self.no_game_warning = ft.Container(
            Row([Icon(ft.icons.INFO_OUTLINE_ROUNDED, color=ft.colors.ON_TERTIARY_CONTAINER, ),
                 Text(value=tr("commod_needs_game"),
                      weight=ft.FontWeight.BOLD,
                      color=ft.colors.ON_TERTIARY_CONTAINER)]),
            bgcolor=ft.colors.TERTIARY_CONTAINER, padding=10, border_radius=10,
            animate_size=ft.animation.Animation(500, ft.AnimationCurve.DECELERATE),
            height=50 if bool(not self.app.config.current_game) else 0,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            col={"xs": 12, "lg": 10, "xxl": 8})

        self.no_distro_warning = ft.Container(
            Row([Icon(ft.icons.INFO_OUTLINE_ROUNDED, color=ft.colors.ON_TERTIARY_CONTAINER, ),
                 Text(value=tr("commod_needs_remaster").replace("\n", " "),
                      weight=ft.FontWeight.BOLD,
                      color=ft.colors.ON_TERTIARY_CONTAINER)]),
            bgcolor=ft.colors.TERTIARY_CONTAINER, padding=10, border_radius=10,
            animate_size=ft.animation.Animation(500, ft.AnimationCurve.DECELERATE),
            visible=bool(not self.app.config.current_distro),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            col={"xs": 12, "lg": 10, "xxl": 8})

        self.env_warnings = ft.Ref[Column]()

        self.game_location_field = TextField(
            label=tr("where_is_game"),
            label_style=ft.TextStyle(size=13, weight=ft.FontWeight.BOLD),
            text_style=ft.TextStyle(size=13, weight=ft.FontWeight.BOLD),
            border_color=ft.colors.OUTLINE,
            focused_border_color=ft.colors.PRIMARY,
            on_change=self.check_game_fields,
            dense=True,
            height=42,
            text_size=13,
            expand=True)

        self.steam_locations_dropdown = ft.Dropdown(
            height=42,
            text_size=13,
            dense=True,
            border_color=ft.colors.OUTLINE,
            hint_text=tr("steam_add_hint"),
            on_change=self.handle_dropdown_onchange,
            label=tr("steam_game_found"),
            label_style=ft.TextStyle(size=13, weight=ft.FontWeight.BOLD),
            text_style=ft.TextStyle(size=13, weight=ft.FontWeight.BOLD),
            hint_style=ft.TextStyle(size=13, weight=ft.FontWeight.BOLD),
            options=[
                ft.dropdown.Option(path) for path in self.app.context.current_session.steam_game_paths
            ],
        )

        self.distro_location_field = TextField(
            label=tr("where_is_distro"),
            label_style=ft.TextStyle(size=13, weight=ft.FontWeight.BOLD),
            text_style=ft.TextStyle(size=13, weight=ft.FontWeight.BOLD),
            border_color=ft.colors.OUTLINE,
            focused_border_color=ft.colors.PRIMARY,
            on_change=self.check_distro_field,
            on_blur=self.check_distro_field,
            dense=True,
            height=42,
            text_size=13,
            expand=True
            )

        self.add_from_steam_btn = ft.FilledButton(
            tr("add_to_list").capitalize(),
            icon=icons.ADD,
            on_click=self.add_steam,
            visible=False,
            disabled=True,
            )

        self.add_game_manual_btn = ft.FilledButton(
            tr("add_to_list").capitalize(),
            icon=ft.icons.ADD,
            on_click=self.add_game_manual,
            visible=False,
            disabled=True,
            )

        self.add_distro_btn = ft.FilledButton(
            tr("confirm_choice").capitalize(),
            icon=ft.icons.CHECK_ROUNDED,
            on_click=self.add_distro,
            visible=False,
            disabled=True,
            )

        self.open_game_button = FloatingActionButton(
            tr("choose_path").capitalize(),
            icon=icons.FOLDER_OPEN,
            on_click=self.get_game_dir_dialog.get_directory_path_async,
            mini=True, height=40, width=135,
            )

        self.open_distro_button = FloatingActionButton(
            tr("choose_path").capitalize(),
            icon=icons.FOLDER_OPEN,
            on_click=self.get_distro_dir_dialog.get_directory_path_async,
            mini=True, height=40, width=135,
            )

        self.game_copy_warning_text = ft.Ref[Text]()
        self.steam_game_copy_warning_text = ft.Ref[Text]()
        self.distro_warning_text = ft.Ref[Text]()

        self.game_copy_warning = ft.Container(
            Row([Icon(ft.icons.WARNING, color=ft.colors.ON_ERROR_CONTAINER),
                 Text(value=tr("unsupported_exe_version"),
                      color=ft.colors.ON_ERROR_CONTAINER,
                      weight=ft.FontWeight.W_500,
                      ref=self.game_copy_warning_text)]),
            bgcolor=ft.colors.ERROR_CONTAINER, padding=10, border_radius=10, visible=False)

        self.steam_game_copy_warning = ft.Container(
            Row([Icon(ft.icons.WARNING, color=ft.colors.ON_ERROR_CONTAINER),
                 Text(value=tr("unsupported_exe_version"),
                      color=ft.colors.ON_ERROR_CONTAINER,
                      weight=ft.FontWeight.W_500,
                      ref=self.steam_game_copy_warning_text)]),
            bgcolor=ft.colors.ERROR_CONTAINER, padding=10, border_radius=10, visible=False)

        self.distro_warning = ft.Container(
            Row([Icon(ft.icons.WARNING, color=ft.colors.ON_ERROR_CONTAINER),
                 Text(value=tr("target_dir_missing_files"),
                      color=ft.colors.ON_ERROR_CONTAINER,
                      weight=ft.FontWeight.W_500,
                      ref=self.distro_warning_text)]),
            bgcolor=ft.colors.ERROR_CONTAINER, padding=10, border_radius=10, visible=False)

        self.list_of_games = Column(height=None if bool(self.app.config.known_games) else 0,
                                    animate_size=ft.animation.Animation(500, ft.AnimationCurve.DECELERATE))

        self.filter = Tabs(
            selected_index=self.app.config.current_game_filter,
            height=40, on_change=self.tabs_changed,
            animate_size=ft.animation.Animation(500, ft.AnimationCurve.DECELERATE),
            tabs=[Tab(text=tr("all_versions").capitalize()),
                  Tab(text="Ex Machina"),
                  Tab(text="M113"),
                  Tab(text="Arcade")])

        self.view_list_of_games = Column(
            height=None if bool(self.app.config.known_games) else 0,
            controls=[
                self.filter,
                self.list_of_games], col={"xs": 12, "lg": 10, "xxl": 8}
        )
        if self.app.config.game_names:
            for game_path in self.app.config.game_names:
                can_be_added, warning, game_info = self.check_compatible_game(game_path)
                if can_be_added:
                    is_current = game_path == self.app.config.current_game
                    installment = game_info.game_installment
                    exe_version = game_info.exe_version
                else:
                    is_current = False
                    installment = GameInstallments.UNKNOWN
                    exe_version = "Unknown"
                    warning = f"{tr('broken_game')}\n\n{warning}"
                visible = not self.is_installment_filtered(installment)
                game_item = GameCopyListItem(self.app.config.game_names[game_path],
                                             game_path,
                                             installment,
                                             exe_version,
                                             warning, is_current,
                                             self.select_game,
                                             self.remove_game,
                                             self.app.config, visible)
                self.list_of_games.controls.append(game_item)

        self.distro_location_text = ft.Ref[Text]()
        self.distro_locaiton_open_btn = ft.Ref[FloatingActionButton]()

        self.distro_display = ft.Container(Column(
            controls=[
                Row([
                    dem_icon,
                    Text(self.app.config.current_distro,
                         weight=ft.FontWeight.W_500,
                         ref=self.distro_location_text, expand=True),
                    IconButton(
                        icon=icons.FOLDER_OPEN,
                        tooltip=tr("open_in_explorer"),
                        on_click=self.open_distro_dir,
                        ref=self.distro_locaiton_open_btn,
                        )
                ])
            ]
        ), height=None if bool(self.app.config.current_distro) else 0,
           animate_size=ft.animation.Animation(500, ft.AnimationCurve.EASE_IN_OUT),
           bgcolor=ft.colors.SECONDARY_CONTAINER, border_radius=20,
           padding=ft.padding.symmetric(horizontal=10),
           col={"xs": 12, "lg": 10, "xxl": 8})

        expanded_icon = ft.icons.KEYBOARD_ARROW_UP_OUTLINED
        collapsed_icon = ft.icons.KEYBOARD_ARROW_DOWN_OUTLINED
        self.add_game_manual_container = ft.Ref[ft.Container]()
        self.add_game_steam_container = ft.Ref[ft.Container]()
        self.add_distro_container = ft.Ref[ft.Container]()
        self.add_game_expanded = not self.app.config.known_games
        self.add_steam_expanded = not self.app.config.known_games
        self.add_distro_expanded = not self.app.config.current_distro

        self.icon_expand_add_game_manual = ft.Ref[Icon]()
        self.icon_expand_add_game_steam = ft.Ref[Icon]()
        self.icon_expand_add_distro = ft.Ref[Icon]()

        # hide dialogs in overlay
        # self.page.overlay.extend([get_directory_dialog])  # pick_files_dialog, save_file_dialog,
        return ft.Container(ft.Column(
            controls=[
                ft.ResponsiveRow(controls=[
                    self.no_game_warning,
                    self.no_distro_warning,
                    Row([
                        Icon(ft.icons.VIDEOGAME_ASSET_ROUNDED, color=ft.colors.ON_BACKGROUND),
                        Text(value=tr("control_game_copies").upper(), style=ft.TextThemeStyle.TITLE_SMALL)
                        ], col={"xs": 12, "xl": 11, "xxl": 9}),
                    self.view_list_of_games,
                    ft.Container(content=Column(
                        [ft.Container(Row([game_icon,
                                           Text(tr("choose_game_path_manually"), weight=ft.FontWeight.W_500),
                                           Icon(expanded_icon if self.add_game_expanded else collapsed_icon,
                                                ref=self.icon_expand_add_game_manual),
                                           self.get_game_dir_dialog
                                           ]),
                                      on_click=self.toggle_adding_game_manual,
                                      margin=ft.margin.only(bottom=1)),
                         Row([
                            self.game_location_field,
                            self.open_game_button
                              ]),
                         self.game_copy_warning,
                         Row([self.add_game_manual_btn], alignment=ft.MainAxisAlignment.CENTER),
                         ], spacing=13),
                                  padding=11, border_radius=10,
                                  border=ft.border.all(2, ft.colors.SECONDARY_CONTAINER),
                                  clip_behavior=ft.ClipBehavior.HARD_EDGE,
                                  animate=ft.animation.Animation(300, ft.AnimationCurve.DECELERATE),
                                  ref=self.add_game_manual_container,
                                  height=104 if self.add_game_expanded else 48,
                                  col={"xs": 12, "lg": 10, "xxl": 7}
                                  ),
                    ft.Container(content=Column(
                        [ft.Container(Row([steam_icon,
                                           Text(tr("choose_from_steam"), weight=ft.FontWeight.W_500),
                                           Icon(expanded_icon if self.add_steam_expanded else collapsed_icon,
                                                ref=self.icon_expand_add_game_steam)
                                           ]),
                                      on_click=self.toggle_adding_game_steam),
                         self.steam_locations_dropdown,
                         self.steam_game_copy_warning,
                         Row([self.add_from_steam_btn], alignment=ft.MainAxisAlignment.CENTER),
                         ], spacing=13),
                             padding=11, border_radius=10,
                             border=ft.border.all(2, ft.colors.SECONDARY_CONTAINER),
                             clip_behavior=ft.ClipBehavior.HARD_EDGE,
                             animate=ft.animation.Animation(300, ft.AnimationCurve.DECELERATE),
                             ref=self.add_game_steam_container,
                             height=104 if self.add_steam_expanded else 48,
                             col={"xs": 12, "lg": 10, "xxl": 7}
                                  )
                    ], alignment=ft.MainAxisAlignment.CENTER),
                ft.ResponsiveRow(
                    # contols of distro/comrem/mods folders
                    controls=[
                        Row([
                            ft.Icon(ft.icons.CREATE_NEW_FOLDER, color=ft.colors.ON_BACKGROUND),
                            Text(value=tr("control_mod_folders").upper(), style=ft.TextThemeStyle.TITLE_SMALL)
                             ], col={"xs": 12, "xl": 11, "xxl": 9}),
                        self.distro_display,
                        ft.Container(content=Column(
                            [ft.Container(Row([dem_icon,
                                          Text(tr("choose_distro_path"), weight=ft.FontWeight.W_500),
                                          Icon(expanded_icon if self.add_distro_expanded else collapsed_icon,
                                               ref=self.icon_expand_add_distro),
                                          self.get_distro_dir_dialog
                                               ]),
                                          on_click=self.toggle_adding_distro,
                                          margin=ft.margin.only(bottom=1)),
                             Row([
                                self.distro_location_field,
                                self.open_distro_button
                                  ]),
                             self.distro_warning,
                             Row([self.add_distro_btn], alignment=ft.MainAxisAlignment.CENTER),
                             ], spacing=13),
                                     padding=11, border_radius=10,
                                     border=ft.border.all(2, ft.colors.SECONDARY_CONTAINER),
                                     clip_behavior=ft.ClipBehavior.HARD_EDGE,
                                     animate=ft.animation.Animation(300, ft.AnimationCurve.DECELERATE),
                                     ref=self.add_distro_container,
                                     height=104 if self.add_distro_expanded else 48,
                                     col={"xs": 12, "lg": 10, "xxl": 7}
                                     )], alignment=ft.MainAxisAlignment.CENTER
                                 )
            ], spacing=20,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER, scroll=ft.ScrollMode.ADAPTIVE,
            alignment=ft.MainAxisAlignment.START
        ), margin=ft.margin.only(right=20))

    # Open directory dialog
    async def get_game_dir_result(self, e: ft.FilePickerResultEvent):
        if e.path:
            self.game_location_field.value = e.path
            await self.game_location_field.update_async()
            await self.check_game_fields(e)
            await self.expand_adding_game_manual()
            await self.game_location_field.focus_async()
        await self.update_async()

    async def get_distro_dir_result(self, e: ft.FilePickerResultEvent):
        if e.path:
            self.distro_location_field.value = e.path
            await self.distro_location_field.update_async()
            await self.check_distro_field(e)
            await self.distro_location_field.focus_async()
        await self.update_async()

    async def toggle_adding_game_manual(self, e):
        if self.add_game_expanded:
            await self.minimize_adding_game_manual()
        else:
            await self.expand_adding_game_manual()
        await self.update_async()

    async def toggle_adding_game_steam(self, e):
        if self.add_steam_expanded:
            await self.minimize_adding_game_steam()
        else:
            await self.expand_adding_game_steam()
        await self.update_async()

    async def toggle_adding_distro(self, e):
        if self.add_distro_expanded:
            await self.minimize_adding_distro()
        else:
            await self.expand_adding_distro()
        await self.update_async()

    async def expand_adding_game_manual(self):
        final_height = 104
        if self.add_game_manual_btn.visible:
            final_height += 45
        if self.game_copy_warning.visible:
            final_height += 60

        self.add_game_manual_container.current.height = final_height
        self.add_game_expanded = True
        self.icon_expand_add_game_manual.current.name = ft.icons.KEYBOARD_ARROW_UP_OUTLINED
        await self.add_game_manual_container.current.update_async()
        await self.update_async()

    async def minimize_adding_game_manual(self):
        self.game_location_field.value = ""
        await self.game_location_field.update_async()
        self.add_game_manual_btn.visible = False
        await self.add_game_manual_btn.update_async()
        self.game_copy_warning.visible = False
        await self.game_copy_warning.update_async()
        self.icon_expand_add_game_manual.current.name = ft.icons.KEYBOARD_ARROW_DOWN_OUTLINED
        self.add_game_manual_container.current.height = 48
        await self.add_game_manual_container.current.update_async()
        self.add_game_expanded = False
        await self.update_async()

    async def expand_adding_game_steam(self):
        final_height = 104
        if self.add_from_steam_btn.visible:
            final_height += 45
        if self.steam_game_copy_warning.visible:
            final_height += 60

        self.add_game_steam_container.current.height = final_height
        self.add_steam_expanded = True
        self.icon_expand_add_game_steam.current.name = ft.icons.KEYBOARD_ARROW_UP_OUTLINED
        await self.add_game_steam_container.current.update_async()
        self.steam_locations_dropdown.visible = True
        await self.steam_locations_dropdown.update_async()
        await self.update_async()

    async def minimize_adding_game_steam(self):
        self.add_game_steam_container.current.height = 48
        self.add_steam_expanded = False
        self.icon_expand_add_game_steam.current.name = ft.icons.KEYBOARD_ARROW_DOWN_OUTLINED
        await self.add_game_steam_container.current.update_async()
        self.steam_locations_dropdown.visible = False
        self.steam_locations_dropdown.value = ""
        await self.steam_locations_dropdown.update_async()
        self.add_from_steam_btn.visible = False
        self.steam_game_copy_warning.visible = False
        await self.steam_game_copy_warning.update_async()
        await self.add_from_steam_btn.update_async()
        await self.update_async()

    async def expand_adding_distro(self):
        final_height = 104
        if self.add_distro_btn.visible:
            final_height += 45
        if self.distro_warning.visible:
            final_height += 60

        self.add_distro_container.current.height = final_height
        self.add_distro_expanded = True
        self.icon_expand_add_distro.current.name = ft.icons.KEYBOARD_ARROW_UP_OUTLINED
        await self.add_distro_container.current.update_async()
        await self.update_async()

    async def minimize_adding_distro(self):
        self.add_distro_container.current.height = 48
        self.add_distro_expanded = False
        self.icon_expand_add_distro.current.name = ft.icons.KEYBOARD_ARROW_DOWN_OUTLINED
        await self.add_distro_container.current.update_async()
        await self.page.update_async()
        await self.update_async()

    async def add_steam(self, e):
        new_path = self.steam_locations_dropdown.value
        await self.add_game_to_list(new_path, from_steam=True)

        self.steam_locations_dropdown.value = ""
        await self.update_async()

    async def add_game_manual(self, e):
        new_path = self.game_location_field.value
        await self.add_game_to_list(new_path, from_steam=False)

        self.game_location_field.value = None
        await self.game_location_field.update_async()
        await self.switch_add_game_btn(GameStatus.NOT_EXISTS)
        await self.update_async()

    async def add_distro(self, e):
        self.distro_display.height = None
        await self.distro_display.update_async()
        self.distro_location_text.current.value = self.distro_location_field.value.strip()
        await self.distro_location_text.current.update_async()
        self.distro_locaiton_open_btn.current.visible = True
        await self.distro_locaiton_open_btn.current.update_async()
        await self.minimize_adding_distro()
        self.no_distro_warning.height = 0
        await self.no_distro_warning.update_async()

        self.app.config.current_distro = self.distro_location_text.current.value
        self.app.config.known_distros = set([self.app.config.current_distro])
        self.distro_location_field.value = None
        await self.update_async()
        # await self.app.local_mods.update_list()
        # TODO: sort out the duplicating functions of context, session and config
        # TODO: exception handling for add_distribution_dir,
        # check that overwriting distro is working correctly
        self.app.context = InstallationContext(self.app.config.current_distro)
        if self.app.config.current_game:
            self.app.load_distro()
        else:
            print("No current game in config")

    async def handle_dropdown_onchange(self, e):
        if e.data:
            await self.check_game_fields(e)
            await self.expand_adding_game_steam()
        await self.update_async()

    @staticmethod
    def check_compatible_game(game_path):
        can_be_added = True
        warning = ''
        test_game = GameCopy()
        try:
            test_game.process_game_install(game_path)
        except PatchedButDoesntHaveManifest as ex:
            warning += (f"{tr('install_leftovers')}\n\n" +
                        f"{tr('error')}: Executable is patched (version: {ex.exe_version}), "
                        "but install manifest is missing")
        except HasManifestButUnpatched as ex:
            warning = (f"{tr('install_leftovers')}\n\n" +
                       f"{tr('error')}: Found existing compatch manifest, but exe version is unexpected: ",
                       f"{ex.exe_version}")
        except InvalidExistingManifest:
            can_be_added = False
            warning = tr("invalid_existing_manifest")
        except Exception as ex:
            can_be_added = False
            warning = f"{tr('error')}: {ex!r}"
        return can_be_added, warning, test_game

    async def add_game_to_list(self, game_path, game_name="", current=True, from_steam=False):
        if game_name:
            set_game_name = game_name
        else:
            set_game_name = Path(game_path).parts[-1]

        can_be_added, warning, game_info = self.check_compatible_game(game_path)

        if can_be_added:
            self.view_list_of_games.height = None
            self.filter.height = None
            self.list_of_games.height = None
            await self.view_list_of_games.update_async()
            await self.filter.update_async()
            # deselect all other games if any exist
            await gather(*[control.display_as_reserve() for control in self.list_of_games.controls])

            visible = not self.is_installment_filtered(game_info.game_installment)
            new_game = GameCopyListItem(set_game_name,
                                        game_path,
                                        game_info.game_installment,
                                        game_info.exe_version,
                                        warning, current,
                                        self.select_game,
                                        self.remove_game,
                                        self.app.config, visible)
            self.list_of_games.controls.append(new_game)
            await self.list_of_games.update_async()
            await self.select_game(new_game)

            await self.minimize_adding_game_manual()
            await self.minimize_adding_game_steam()
            self.no_game_warning.height = 0
            await self.no_game_warning.update_async()

            self.app.config.known_games.add(game_path.lower())
            self.app.config.game_names[game_path] = set_game_name
            self.filter.selected_index = 0
            for control in self.list_of_games.controls:
                control.visible = True

        else:
            if from_steam:
                await self.switch_steam_game_copy_warning(GameStatus.GENERAL_ERROR, additional_info=warning)
            # automatic addition will explicitly pass game_name, so we can check this for manual addition
            elif not game_name:
                await self.switch_game_copy_warning(GameStatus.GENERAL_ERROR, additional_info=warning)
        await self.update_async()
        return can_be_added

    async def select_game(self, item):
        try:
            self.app.game = GameCopy()
            self.app.game.process_game_install(item.game_path)
        except PatchedButDoesntHaveManifest:
            pass
        except HasManifestButUnpatched:
            pass
        except Exception as ex:
            # TODO: Handle exceptions properly
            await self.app.show_alert(tr('broken_game'), ex)
            self.app.logger.error(f"[Game loading error] {ex}")
            return

        group = []
        for control in self.list_of_games.controls:
            if control is not item:
                group.append(control.display_as_reserve())
        await gather(*group)

        await item.display_as_current()
        self.app.settings_page.no_game_warning.height = 0
        await self.app.settings_page.no_game_warning.update_async()
        self.app.config.current_game = item.game_path
        self.app.logger.info(f"Game is now: {self.app.game.target_exe}")
        await self.update_async()

        if self.app.context.distribution_dir:
            self.app.context.validated_mod_configs.clear()
            self.app.context.current_session = InstallationContext.Session()
            self.app.session = self.app.context.current_session
            self.app.load_distro()
        else:
            print("No distro dir in context")

    async def remove_game(self, item):
        if item.current:
            # if removing current, set dummy game as current
            self.app.game = GameCopy()
            self.app.settings_page.no_game_warning.height = None
            await self.app.settings_page.no_game_warning.update_async()
            self.app.config.current_game = ""
            # TODO: handler removal of the game
            self.app.load_distro()

        self.list_of_games.controls.remove(item)
        await self.list_of_games.update_async()

        # hide list if there are zero games tracked
        if not self.list_of_games.controls:
            self.view_list_of_games.height = 0
            self.filter.height = 0
            self.list_of_games.height = 0
            await self.list_of_games.update_async()
            await self.filter.update_async()
            await self.view_list_of_games.update_async()

        self.app.config.known_games.discard(item.game_path.lower())
        self.app.config.game_names.pop(item.game_path)
        self.app.logger.debug(f"Game is now: {self.app.game.target_exe}")
        self.app.logger.debug(f"Known games: {self.app.config.known_games}")

        await self.minimize_adding_game_manual()
        await self.minimize_adding_game_steam()

        await self.update_async()

    def check_game(self, game_path):
        status = None
        additional_info = ""

        if os.path.exists(game_path):
            if game_path.lower() not in self.app.config.known_games:
                validated, additional_info = GameCopy.validate_game_dir(game_path)
                if validated:
                    exe_name = GameCopy.get_exe_name(game_path)
                    exe_version = GameCopy.get_exe_version(exe_name)
                    if exe_version is not None:
                        validated_exe = GameCopy.is_compatch_compatible_exe(exe_version)
                        if validated_exe:
                            status = GameStatus.COMPATIBLE
                        else:
                            status = GameStatus.BAD_EXE
                            additional_info = exe_version
                    else:
                        status = GameStatus.EXE_RUNNING
                else:
                    status = GameStatus.MISSING_FILES
            else:
                status = GameStatus.ALREADY_ADDED
        else:
            status = GameStatus.NOT_EXISTS

        return status, additional_info

    async def check_game_fields(self, e):
        if e.control is self.game_location_field or e.control is self.get_game_dir_dialog:
            game_path = self.game_location_field.value.strip()
            manual_control = True
            if not self.add_game_expanded:
                return
        elif e.control is self.steam_locations_dropdown:
            game_path = e.data
            manual_control = False

        if game_path:
            status, additional_info = self.check_game(game_path)
        else:
            status, additional_info = None, ""

        if manual_control:
            await self.switch_game_copy_warning(status, additional_info)
            await self.switch_add_game_btn(status)
            if game_path:
                await self.expand_adding_game_manual()
        else:
            await self.switch_steam_game_copy_warning(status, additional_info)
            await self.switch_add_from_steam_btn(status)
            await self.expand_adding_game_steam()
        await self.update_async()

    def check_distro(self, distro_path):
        if distro_path:
            if os.path.exists(distro_path):
                if distro_path not in self.app.config.known_distros:
                    validated = InstallationContext.validate_distribution_dir(distro_path)
                    if validated:
                        status = DistroStatus.COMPATIBLE
                    else:
                        status = DistroStatus.MISSING_FILES
                else:
                    status = DistroStatus.ALREADY_ADDED
            else:
                status = DistroStatus.NOT_EXISTS
        else:
            status = None

        return status

    async def check_distro_field(self, e):
        distro_path = self.distro_location_field.value.strip()

        status = self.check_distro(distro_path)
        if status is not None:
            await self.switch_distro_warning(status)
            await self.switch_add_distro_btn(status)
            await self.expand_adding_distro()
            await self.update_async()

    async def switch_add_game_btn(self, status: GameStatus = GameStatus.COMPATIBLE):
        if status is None:
            status = GameStatus.NOT_EXISTS
        self.add_game_manual_btn.disabled = status is not GameStatus.COMPATIBLE
        self.add_game_manual_btn.visible = status is GameStatus.COMPATIBLE
        await self.add_game_manual_btn.update_async()
        await self.update_async()

    async def switch_add_from_steam_btn(self, status: GameStatus = GameStatus.COMPATIBLE):
        if status is None:
            status = GameStatus.NOT_EXISTS
        self.add_from_steam_btn.disabled = status is not GameStatus.COMPATIBLE
        self.add_from_steam_btn.visible = status is GameStatus.COMPATIBLE
        await self.add_from_steam_btn.update_async()
        await self.update_async()

    async def switch_add_distro_btn(self, status: DistroStatus = DistroStatus.COMPATIBLE):
        if status is None:
            status = DistroStatus.NOT_EXISTS
        self.add_distro_btn.disabled = status is not DistroStatus.COMPATIBLE
        self.add_distro_btn.visible = status is DistroStatus.COMPATIBLE
        await self.add_distro_btn.update_async()
        await self.update_async()

    async def switch_game_copy_warning(self,
                                       status: GameStatus = GameStatus.COMPATIBLE,
                                       additional_info: str = ""):
        if status is None:
            status = GameStatus.COMPATIBLE
        self.game_copy_warning.visible = status is not GameStatus.COMPATIBLE
        full_text = tr(GameStatus(status).value)
        if status is GameStatus.BAD_EXE:
            full_text += f": {additional_info}"
        self.game_copy_warning_text.current.value = full_text
        await self.game_copy_warning.update_async()
        await self.update_async()

    async def switch_steam_game_copy_warning(self,
                                             status: GameStatus = GameStatus.COMPATIBLE,
                                             additional_info: str = ""):
        if status is None:
            status = GameStatus.COMPATIBLE
        self.steam_game_copy_warning.visible = status is not GameStatus.COMPATIBLE
        full_text = tr(GameStatus(status).value)
        if status is GameStatus.BAD_EXE:
            full_text += f": {additional_info}"
        self.steam_game_copy_warning_text.current.value = full_text
        await self.steam_game_copy_warning.update_async()
        await self.update_async()

    async def switch_distro_warning(self,
                                    status: DistroStatus = DistroStatus.COMPATIBLE):
        if status is None:
            status = DistroStatus.COMPATIBLE
        self.distro_warning.visible = status is not DistroStatus.COMPATIBLE
        self.distro_warning_text.current.value = tr(DistroStatus(status).value)
        await self.distro_warning.update_async()
        await self.update_async()

    async def open_distro_dir(self, e):
        # open distro directory in Windows Explorer
        if os.path.isdir(self.distro_location_text.current.value):
            os.startfile(self.distro_location_text.current.value)
        await self.update_async()

    async def tabs_changed(self, e):
        filter = "All"
        match int(e.data):
            case GameInstallments.ALL.value:
                filter = "All"
            case GameInstallments.EXMACHINA.value:
                filter = "Ex Machina"
            case GameInstallments.M113.value:
                filter = "Ex Machina: Meridian 113"
            case GameInstallments.ARCADE.value:
                filter = "Ex Machina: Arcade"
        for control in self.list_of_games.controls:
            if filter == "All":
                control.visible = True
            else:
                if control.installment == filter:
                    control.visible = True
                else:
                    control.visible = False
            await control.update_async()
        self.app.config.current_game_filter = int(e.data)
        await self.update_async()

    def is_installment_filtered(self, installment):
        match self.filter.selected_index:
            case GameInstallments.ALL.value:
                return False
            case GameInstallments.EXMACHINA.value:
                return installment != "Ex Machina"
            case GameInstallments.M113.value:
                return installment != "Ex Machina: Meridian 113"
            case GameInstallments.ARCADE.value:
                return installment != "Ex Machina: Arcade"


class ModInfo(UserControl):
    def __init__(self, app: App, mod: Mod, mod_item, **kwargs):
        super().__init__(self, **kwargs)
        self.app = app
        self.mod = mod
        self.main_mod = mod
        self.mod_item = mod_item
        self.tabs = ft.Ref[ft.Tabs]()
        self.tab_index = 0
        self.expanded = False
        self.container = ft.Ref[ft.Container]()

        self.main_info = ft.Ref[ft.Container]()
        self.compatibility = ft.Ref[ft.Container]()
        self.lang_list = ft.Ref[Row]()
        self.release_date = ft.Ref[Text]()
        self.home_url_btn = ft.Ref[ft.TextButton]()
        self.trailer_btn = ft.Ref[ft.TextButton]()
        self.mod_info_column = ft.Ref[Column]()
        self.mod_screens_row = ft.Ref[Column]()
        self.mod_description_text = ft.Ref[Text]()

        self.screenshot_index = 0
        self.max_screenshot_index = len(self.mod.screenshots) - 1
        self.screenshots = ft.Ref[ft.Container]()
        self.screenshot_view = ft.Ref[Image]()
        self.screenshot_text = ft.Ref[Text]()

        self.change_log = ft.Ref[ft.Container]()
        self.change_log_text = ft.Ref[ft.Markdown]()

        self.other_info = ft.Ref[ft.Container]()
        self.other_info_text = ft.Ref[ft.Markdown]()

        self.tab_info = []

    async def toggle(self):
        self.expanded = not self.expanded
        self.container.current.height = 0 if not self.expanded else None
        await self.update_async()

    async def switch_tab(self, e):
        self.tab_index = e.data
        for index, widget in enumerate(self.tab_info):
            widget.current.visible = str(index) == self.tab_index
        await gather(*[widget.current.update_async() for widget in self.tab_info])

    async def update_screens(self):
        if self.mod.screenshots:
            self.screenshot_index = 0
            self.max_screenshot_index = len(self.mod.screenshots) - 1
            self.screenshot_view.current.src = self.mod.screenshots[self.screenshot_index]["path"]
            self.screenshot_view.current.data = self.mod.screenshots[self.screenshot_index]
            self.screenshot_text.current.value = self.mod.screenshots[self.screenshot_index]["text"]
            self.screenshot_text.current.visible = bool(self.mod.screenshots[self.screenshot_index]["text"])
            await self.screenshot_view.current.update_async()
            await self.screenshot_text.current.update_async()

    async def update_change_log(self):
        pass

    async def update_other_info(self):
        pass

    async def update_tabs(self):
        self.tabs.current.tabs.clear()
        self.tabs.current.tabs.append(Tab(text=tr("main_info").capitalize()))
        self.tab_info = [self.main_info]
        if self.mod.screenshots:
            self.tabs.current.tabs.append(Tab(text=tr("screenshots").capitalize()))
            self.tab_info.append(self.screenshots)
        if self.mod.change_log_content:
            self.tabs.current.tabs.append(Tab(text=tr("change_log").capitalize()))
            self.tab_info.append(self.change_log)
        if self.mod.other_info_content:
            self.tabs.current.tabs.append(Tab(text=tr("other_info").capitalize()))
            self.tab_info.append(self.other_info)

        await self.tabs.current.update_async()

    async def did_mount_async(self):
        await self.set_mod_info_column()
        await self.update_tabs()
        await self.set_mod_screens_row()
        await self.update_screens()

        if self.main_mod.translations_loaded:
            for lang, mod in self.main_mod.translations_loaded.items():
                if mod.known_language:
                    flag = get_internal_file_path(LangFlags[lang].value)
                else:
                    flag = get_internal_file_path(LangFlags.other.value)

                icon = ft.Image(flag, width=26)
                icon.tooltip = mod.lang_label.capitalize()

                if not mod.can_install:
                    icon.color = ft.colors.BLACK87
                    icon.color_blend_mode = ft.BlendMode.COLOR
                    icon.tooltip += f' ({tr("cant_be_installed")})'

                flag_btn = ft.IconButton(
                    content=icon,
                    data=lang,
                    on_click=self.change_lang)

                self.lang_list.current.controls.append(flag_btn)

    async def next_screen(self, e):
        if self.mod.screenshots:
            if self.screenshot_index == self.max_screenshot_index:
                self.screenshot_index = 0
            else:
                self.screenshot_index += 1
            self.screenshot_view.current.src = self.mod.screenshots[self.screenshot_index]["path"]
            self.screenshot_view.current.data = self.mod.screenshots[self.screenshot_index]
            self.screenshot_text.current.value = self.mod.screenshots[self.screenshot_index]["text"]
            self.screenshot_text.current.visible = bool(self.mod.screenshots[self.screenshot_index]["text"])
            await self.screenshot_view.current.update_async()
            await self.screenshot_text.current.update_async()

    async def previous_screen(self, e):
        if self.mod.screenshots:
            if self.screenshot_index == 0:
                self.screenshot_index = self.max_screenshot_index
            else:
                self.screenshot_index -= 1
            self.screenshot_view.current.src = self.mod.screenshots[self.screenshot_index]["path"]
            self.screenshot_view.current.data = self.mod.screenshots[self.screenshot_index]
            self.screenshot_text.current.value = self.mod.screenshots[self.screenshot_index]["text"]
            self.screenshot_text.current.visible = bool(self.mod.screenshots[self.screenshot_index]["text"])
            await self.screenshot_view.current.update_async()
            await self.screenshot_text.current.update_async()

    async def compare_screen(self, e):
        screen_widget = self.screenshot_view.current
        if screen_widget.data["compare_path"]:
            if screen_widget.src == self.mod.screenshots[self.screenshot_index]["path"]:
                screen_widget.src = self.mod.screenshots[self.screenshot_index]["compare_path"]
            else:
                screen_widget.src = self.mod.screenshots[self.screenshot_index]["path"]
            await screen_widget.update_async()

    async def launch_url(self, e):
        await self.app.page.launch_url_async(e.data)

    async def open_home_url(self, e):
        await self.app.page.launch_url_async(self.mod.url)

    async def open_trailer_url(self, e):
        await self.app.page.launch_url_async(self.mod.trailer_url)

    async def change_lang(self, e):
        # TODO: All of this is bullshit and doesn't take into account that translations can have different
        # sets of screenshots and info views. Need to fully rebuild widgets on lang change ideally.
        # Or say to users not to make completely different translation manifests
        if e.control.data == self.mod.language:
            return

        self.mod = self.main_mod.translations_loaded[e.control.data]

        await self.set_mod_info_column()
        await self.update_tabs()
        await self.set_mod_screens_row()
        await self.update_screens()

        self.release_date.current.value = self.mod.release_date
        self.release_date.current.visible = bool(self.mod.release_date)
        await self.release_date.current.update_async()
        self.home_url_btn.current.tooltip = f'{tr("warn_external_address")}\n{self.mod.url}'
        self.home_url_btn.current.visible = bool(self.mod.url)
        await self.home_url_btn.current.update_async()
        self.trailer_btn.current.tooltip = f'{tr("warn_external_address")}\n{self.mod.trailer_url}'
        self.trailer_btn.current.visible = bool(self.mod.trailer_url)
        await self.trailer_btn.current.update_async()

        if self.mod.change_log:
            self.change_log_text.current.value = self.mod.change_log_content
            await self.change_log_text.current.update_async()
        if self.mod.other_info_content:
            self.other_info_text.current.value = self.mod.other_info_content
            await self.other_info_text.current.update_async()

        await self.mod_item.change_lang(e)

    async def set_mod_info_column(self):
        self.mod_info_column.current.controls = [
            Text(self.mod.description, color=ft.colors.ON_SURFACE,
                 ref=self.mod_description_text),
            ft.Divider(visible=self.mod.name != "community_remaster"),
            Column(controls=self.get_pretty_compatibility(),
                   visible=self.mod.name != "community_remaster"),
            ft.Divider(visible=not self.mod.can_install),
            Row([
                Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                     color=ft.colors.ERROR),
                Text(f'{tr("cant_be_installed")}',
                     weight=ft.FontWeight.BOLD,
                     color=ft.colors.ERROR)],
                visible=not self.mod.can_install),
            Text(self.mod.commod_compatible_err,
                 color=ft.colors.ERROR,
                 visible=bool(self.mod.commod_compatible_err)),
            Text(self.mod.compatible_err,
                 color=ft.colors.ERROR,
                 visible=bool(self.mod.compatible_err)),
            Text(self.mod.prevalidated_err,
                 color=ft.colors.ERROR,
                 visible=bool(self.mod.prevalidated_err))
            ]
        await self.mod_info_column.current.update_async()

    async def set_mod_screens_row(self):
        self.mod_screens_row.current.controls = [
            Column([IconButton(ft.icons.CHEVRON_LEFT,
                               visible=len(self.mod.screenshots) > 1,
                               on_click=self.previous_screen)],
                   col=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ft.GestureDetector(
                Image(src=get_internal_file_path("assets/no_logo.png"),
                      gapless_playback=True,
                      fit=ft.ImageFit.FIT_HEIGHT,
                      ref=self.screenshot_view),
                on_tap=self.compare_screen, col=10),
            Column([IconButton(ft.icons.CHEVRON_RIGHT,
                               visible=len(self.mod.screenshots) > 1,
                               on_click=self.next_screen)],
                   col=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
            ]
        await self.mod_screens_row.current.update_async()

    def get_pretty_compatibility(self) -> list:
        point_list = []
        or_word = f" {tr('or')} "
        and_word = f" {tr('and')} "
        but_word = f", {tr('but')} "

        req_list = []
        for req_tuple in self.mod.individual_require_status:
            req = req_tuple[0]
            ok_status = req_tuple[1]
            req_errors = [line.strip() for line in req_tuple[2]]

            version = req.get("versions")
            if version is None:
                version = ""
            else:
                if self.mod.requirements_style == "strict":
                    version = [ver_str.replace("=", "") for ver_str in version]
                    if len(version) <= 2:
                        version = or_word.join(version)
                    else:
                        version = (", ".join(version[:-2])
                                   + ", " + or_word.join(version[-2:]))
                elif self.mod.requirements_style == "range":
                    version = but_word.join(version)
                else:
                    version = and_word.join(version)

            optional = req.get("optional_content")
            if optional is None:
                optional = ""
            elif len(optional) <= 2:
                optional = and_word.join(optional)
            else:
                optional = (", ".join(optional[:-2])
                            + ", " + and_word.join(optional[-2:]))

            if ok_status:
                icon = ft.Icon(ft.icons.CHECK_CIRCLE_ROUNDED,
                               color=ft.colors.TERTIARY,
                               tooltip=tr("requirements_met"))
            else:
                icon = ft.Icon(ft.icons.WARNING_ROUNDED,
                               color=ft.colors.ERROR,
                               tooltip=tr("requirements_not_met"))

            if not version:
                version_string = f'({tr("of_any_version")})'
            else:
                version_string = f'({tr("of_version").capitalize()}: {version})'

            req_list.append(Row([
                icon,
                Column([
                    Row([Text(req["name_label"],
                              weight=ft.FontWeight.W_500,
                              color=ft.colors.ON_PRIMARY_CONTAINER),
                         Text(version_string,
                              weight=ft.FontWeight.W_100),
                         Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                              visible=not ok_status,
                              size=20,
                              tooltip="\n".join(req_errors),
                              color=ft.colors.ERROR)
                         ]),
                    Text(f'{tr("including_options").capitalize()}: {optional}',
                         visible=bool(optional),
                         weight=ft.FontWeight.W_100,
                         no_wrap=False, width=500)
                        ])
                     ])
            )

        incomp_list = []
        for incomp_tuple in self.mod.individual_incomp_status:
            incomp = incomp_tuple[0]
            incomp_ok_status = incomp_tuple[1]
            incomp_errors = [line.strip() for line in incomp_tuple[2]]

            version = incomp.get("versions")
            if version is None:
                version = ""
            else:
                if self.mod.incompatibles_style == "strict":
                    version = [ver_str.replace("=", "") for ver_str in version]
                    if len(version) <= 2:
                        version = or_word.join(version)
                    else:
                        version = (", ".join(version[:-2])
                                   + ", " + or_word.join(version[-2:]))

                    version = or_word.join(version)
                elif self.mod.incompatibles_style == "range":
                    version = but_word.join(version)
                else:
                    version = and_word.join(version)

            optional = incomp.get("optional_content")
            if optional is None:
                optional = ""
            elif len(optional) <= 2:
                optional = and_word.join(optional)
            else:
                optional = (", ".join(optional[:-2])
                            + ", " + and_word.join(optional[-2:]))

            if incomp_ok_status:
                icon = ft.Icon(ft.icons.CHECK_CIRCLE_ROUNDED,
                               color=ft.colors.TERTIARY,
                               tooltip=tr("requirements_met"))
            else:
                icon = ft.Icon(ft.icons.WARNING_ROUNDED,
                               color=ft.colors.ERROR,
                               tooltip=tr("requirements_not_met"))

            if not version:
                version_string = f'({tr("of_any_version")})'
            else:
                version_string = f'({tr("of_version").capitalize()}: {version})'

            incomp_list.append(Row([
                icon,
                Column([
                    Row([Text(incomp["name_label"],
                              weight=ft.FontWeight.W_500,
                              color=ft.colors.ON_PRIMARY_CONTAINER),
                         Text(version_string,
                              weight=ft.FontWeight.W_100),
                         Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                              visible=not incomp_ok_status,
                              size=20,
                              tooltip="\n".join(incomp_errors),
                              color=ft.colors.ERROR)]),
                    Text(f'{tr("including_options").capitalize()}: {optional}',
                         visible=bool(optional),
                         weight=ft.FontWeight.W_100,
                         no_wrap=False, width=500)
                        ])
                     ])
            )

        if req_list:
            point_list.append(Text(tr("required_base").capitalize() + ":",
                              weight=ft.FontWeight.BOLD))
            point_list.extend(req_list)
        if incomp_list:
            point_list.append(Text(tr("incompatible_base").capitalize() + ":",
                              weight=ft.FontWeight.BOLD))
            point_list.extend(incomp_list)

        return point_list

    def build(self):
        return ft.Container(
            ft.Container(
                content=Column([
                    Tabs(
                        selected_index=self.tab_index,
                        animate_size=ft.animation.Animation(500, ft.AnimationCurve.DECELERATE),
                        height=40, on_change=self.switch_tab,
                        ref=self.tabs,
                        tabs=[]),
                    Column([ft.Container(
                                ft.ResponsiveRow([
                                    Column([], ref=self.mod_info_column, col={"xs": 11, "xl": 12},
                                           opacity=0.9),
                                    ft.Container(
                                        Column([
                                            Row([ft.Container(Text(f'{tr("language").capitalize()}:'),
                                                              padding=ft.padding.only(left=10),
                                                              margin=0),
                                                 Row([], ref=self.lang_list, spacing=0,
                                                     width=130, wrap=True, run_spacing=0)]),
                                            ft.Container(
                                                ft.Row([
                                                    Text(f"{tr('release').capitalize()}:  "),
                                                    Text(self.mod.release_date,
                                                         self.release_date)
                                                ], spacing=5),
                                                visible=bool(self.mod.release_date),
                                                margin=ft.margin.only(left=10, top=3, bottom=6)),
                                            ft.TextButton(content=ft.Row(
                                                [
                                                 ft.Container(
                                                    ft.Icon(
                                                        name=ft.icons.HOME_ROUNDED,
                                                        color=ft.colors.PRIMARY, size=20),
                                                    padding=ft.padding.symmetric(horizontal=6)),
                                                 ft.Container(
                                                     Row([Text(tr("mod_url").replace(":", ""),
                                                               size=14,
                                                               weight=ft.FontWeight.NORMAL)],
                                                         alignment=ft.MainAxisAlignment.CENTER),
                                                     margin=ft.margin.only(bottom=2), expand=True)
                                                ],
                                                alignment=ft.MainAxisAlignment.SPACE_AROUND),
                                             ref=self.home_url_btn,
                                             on_click=self.open_home_url,
                                             visible=bool(self.mod.url),
                                             tooltip=f'{tr("warn_external_address")}\n'
                                                     f'{self.mod.url}'),
                                            ft.TextButton(content=ft.Row(
                                                [
                                                 ft.Container(
                                                     ft.Icon(name=ft.icons.ONDEMAND_VIDEO_OUTLINED,
                                                             color=ft.colors.PRIMARY, size=17),
                                                     padding=ft.padding.only(left=8, right=8, top=2)),
                                                 ft.Container(
                                                     Row([ft.Text(tr("trailer_watch").capitalize(),
                                                                  size=14,
                                                                  weight=ft.FontWeight.NORMAL)],
                                                         alignment=ft.MainAxisAlignment.CENTER),
                                                     margin=ft.margin.only(bottom=2), expand=True)
                                                ],
                                                # vertical_alignment=ft.MainAxisAlignment.CENTER,
                                                alignment=ft.MainAxisAlignment.SPACE_AROUND),
                                             ref=self.trailer_btn,
                                             on_click=self.open_trailer_url,
                                             visible=bool(self.mod.trailer_url),
                                             tooltip=f'{tr("warn_external_address")}\n'
                                                     f'{self.mod.trailer_url}')
                                            ],
                                            spacing=2,
                                            alignment=ft.MainAxisAlignment.START,
                                            horizontal_alignment=ft.CrossAxisAlignment.START),
                                        col={"xs": 4, "xl": 3}, padding=ft.padding.only(left=5),
                                        clip_behavior=ft.ClipBehavior.HARD_EDGE)
                                    ],
                                    vertical_alignment=ft.CrossAxisAlignment.START,
                                    spacing=0, columns=15),
                                ref=self.main_info,
                                padding=ft.padding.only(bottom=15),
                                visible=self.tab_index == 0),
                            ft.Container(
                                Column([
                                    ft.ResponsiveRow([], ref=self.mod_screens_row,
                                                     alignment=ft.MainAxisAlignment.CENTER),
                                    Text("Placeholder", ref=self.screenshot_text)
                                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                ref=self.screenshots,
                                visible=False,
                                padding=ft.padding.only(bottom=15)),
                            ft.Container(
                                Column([
                                    ft.Container(
                                        ft.Markdown(self.mod.change_log_content,
                                                    ref=self.change_log_text,
                                                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                                                    on_tap_link=self.launch_url),
                                        padding=ft.padding.only(right=22))],
                                       scroll=ft.ScrollMode.ADAPTIVE),
                                ref=self.change_log,
                                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                                height=400,
                                visible=False,
                                padding=ft.padding.only(bottom=15)),
                            ft.Container(
                                Column([
                                    ft.Container(
                                        ft.Markdown(self.mod.other_info_content,
                                                    ref=self.other_info_text,
                                                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                                                    on_tap_link=self.launch_url),
                                        padding=ft.padding.only(right=22))],
                                       scroll=ft.ScrollMode.ADAPTIVE),
                                ref=self.other_info,
                                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                                height=400,
                                visible=False,
                                padding=ft.padding.only(bottom=15))],
                           animate_size=ft.animation.Animation(300, ft.AnimationCurve.EASE_IN_OUT)),
                    ], alignment=ft.MainAxisAlignment.START),
                margin=ft.margin.only(top=15),
                padding=ft.padding.only(left=15, right=15, top=5, bottom=0),
                border_radius=10,
                bgcolor=ft.colors.SURFACE, alignment=ft.alignment.top_left),
            height=0 if not self.expanded else None,
            ref=self.container)


class ModItem(UserControl):
    def __init__(self, app: App, mod: Mod, **kwargs):
        super().__init__(self, **kwargs)
        self.app = app
        self.main_mod = mod
        self.mod = self.main_mod

        self.about_mod_btn = ft.Ref[ft.OutlinedButton]()
        self.info_container = ft.Ref[ModInfo]()
        self.mod_name_text = ft.Ref[Text]()
        self.author_text = ft.Ref[Text]()
        self.mod_logo_img = ft.Ref[Image]()

    async def install_mod(self, e):
        if not self.app.page.overlay:
            bg = ft.Container(Row([Column(
                controls=[], alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER)]),
                bgcolor=ft.colors.BLACK87)

            fg = ModInstallWizard(self, self.app, self.main_mod)

            self.app.page.overlay.clear()
            self.app.page.overlay.append(bg)
            self.app.page.overlay.append(fg)
            await self.app.page.update_async()

    async def toggle_info(self, e):
        if self.about_mod_btn.current.text == tr("about_mod").capitalize():
            self.about_mod_btn.current.text = tr("hide_menu").capitalize()
        else:
            self.about_mod_btn.current.text = tr("about_mod").capitalize()
        await self.about_mod_btn.current.update_async()
        await self.info_container.current.toggle()

    async def change_lang(self, e):
        self.mod = self.main_mod.translations_loaded[e.control.data]

        self.mod_name_text.current.value = self.mod.display_name
        await self.mod_name_text.current.update_async()
        self.author_text.current.value = f"{tr(self.mod.developer_title)} {self.mod.authors}"
        await self.author_text.current.update_async()
        self.mod_logo_img.current.src = self.mod.logo_path
        await self.mod_logo_img.current.update_async()

    def build(self):
        tr_tags = [tr(tag.lower()).capitalize() for tag in self.mod.tags]
        # return ft.GestureDetector(
        return ft.Card(
            ft.Container(
                Column([
                    ft.ResponsiveRow([
                        Image(src=self.mod.logo_path,
                              ref=self.mod_logo_img,
                              fit=ft.ImageFit.FIT_WIDTH,
                              gapless_playback=True,
                              aspect_ratio=2,
                              col={"xs": 8, "xl": 6},
                              border_radius=6),
                        ft.Container(col={"xs": 0, "xl": 1}),
                        Column([
                            Text(self.mod.display_name,
                                 ref=self.mod_name_text,
                                 weight=ft.FontWeight.W_700,
                                 size=18),
                            Text(f"{tr(self.mod.developer_title)} {self.mod.authors}",
                                 ref=self.author_text,
                                 max_lines=2,
                                 overflow=ft.TextOverflow.ELLIPSIS,
                                 size=13,
                                 weight=ft.FontWeight.W_200),
                            Row([*[ft.Container(Text(tag, color=ft.colors.ON_TERTIARY_CONTAINER, size=12),
                                                padding=ft.padding.only(left=4, right=3, bottom=2),
                                                border_radius=3,
                                                bgcolor=ft.colors.TERTIARY_CONTAINER) for tag in tr_tags[:3]],
                                 ft.Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                                         color=ft.colors.ON_TERTIARY_CONTAINER,
                                         size=15,
                                         tooltip=", ".join(tr_tags),
                                         visible=len(self.mod.tags) > 3)],
                                wrap=True, spacing=5, run_spacing=5)
                            ],
                            col={"xs": 11, "xl": 14}),
                        Column([
                            Row([ft.Container(
                                    Text(f"{self.mod.version} [{self.mod.build}]",
                                         no_wrap=True,
                                         color=ft.colors.ON_PRIMARY_CONTAINER
                                         if self.mod.can_install else ft.colors.ERROR,
                                         overflow=ft.TextOverflow.ELLIPSIS), margin=ft.margin.only(bottom=3)),
                                 Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                                      color=ft.colors.ERROR,
                                      size=15,
                                      visible=not self.mod.commod_compatible,
                                      tooltip=self.mod.commod_compatible_err),
                                 Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                                      color=ft.colors.ERROR,
                                      size=15,
                                      visible=not self.mod.compatible,
                                      tooltip=self.mod.compatible_err),
                                 Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                                      color=ft.colors.ERROR,
                                      size=15,
                                      visible=not self.mod.prevalidated,
                                      tooltip=self.mod.prevalidated_err)
                                 ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True),
                            ft.ElevatedButton(tr("install").capitalize(),
                                              style=ft.ButtonStyle(
                                                color={
                                                    ft.MaterialState.HOVERED: ft.colors.ON_SECONDARY,
                                                    ft.MaterialState.DEFAULT: ft.colors.ON_PRIMARY,
                                                    ft.MaterialState.DISABLED: ft.colors.ON_SURFACE_VARIANT
                                                    },
                                                bgcolor={
                                                    ft.MaterialState.HOVERED: ft.colors.SECONDARY,
                                                    ft.MaterialState.DEFAULT: ft.colors.PRIMARY,
                                                    ft.MaterialState.DISABLED: ft.colors.SURFACE_VARIANT
                                                }
                                              ),
                                              disabled=not self.mod.can_install,
                                              on_click=self.install_mod),
                            ft.OutlinedButton(tr("about_mod").capitalize(),
                                              animate_size=ft.animation.Animation(
                                                66, ft.AnimationCurve.EASE_IN),
                                              ref=self.about_mod_btn,
                                              on_click=self.toggle_info)
                            ], col={"xs": 7, "xl": 5}, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                        ], spacing=10, columns=26),
                    ModInfo(self.app, self.mod, self, ref=self.info_container)
                ], spacing=0, scroll=ft.ScrollMode.HIDDEN, alignment=ft.MainAxisAlignment.START),
                margin=15),
            margin=ft.margin.symmetric(vertical=1), elevation=3,
            )


class ModInstallWizard(UserControl):
    def __init__(self, parent: ModItem, app: App, mod: Mod, **kwargs):
        super().__init__(self, **kwargs)
        self.mod_item = parent
        self.app: App = app
        self.main_mod: Mod | None = mod
        self.mod: Mod | None = None
        self.current_screen = None
        self.options = []

        self.mod_title = ft.Ref[Text]()
        self.mod_title_text = (f"{tr('installation')} {self.main_mod.display_name} - "
                               f"{tr('version')} {self.main_mod.version}")

        self.can_have_custom_install = False
        self.requires_custom_install = False

        self.main_row = ft.Ref[ft.ResponsiveRow]()
        self.screen = ft.Ref[ft.Container]()
        self.default_install_btn = ft.Ref[ft.FilledButton]()
        self.status_capsules = Row([])
        self.status_capsules_container = ft.Container(
            Column([
                ft.Container(Text(tr("install_steps").capitalize(), weight=ft.FontWeight.BOLD),
                             padding=ft.padding.symmetric(horizontal=5)),
                self.status_capsules
                ]), padding=ft.padding.symmetric(horizontal=40)
        )

        self.language_choice_required = False

    class Steps(Enum):
        WELCOME = 0
        INSTALLING = 1
        SETTING_UP = 2
        RESULTS = 3

    class ModOption(UserControl):
        def __init__(self, parent, option: Mod.OptionalContent, **kwargs):
            super().__init__(self, **kwargs)
            self.option = option
            self.parent = parent
            self.active = True
            self.card = ft.Ref[ft.Card]()
            self.warning_text = ft.Ref[Text]()
            self.choice = None
            self.complex_selector = False
            self.checkboxes = []

        async def set_active(self):
            if self.active:
                return
            self.card.current.elevation = 5
            self.card.current.opacity = 1.0
            self.card.current.scale = 1.0
            self.warning_text.current.visible = False
            await self.card.current.update_async()
            self.active = True

        async def set_inactive(self):
            if not self.active:
                return
            self.card.current.elevation = 0
            self.card.current.opacity = 0.8
            self.card.current.scale = 0.99
            self.warning_text.current.visible = True
            await self.card.current.update_async()
            self.active = False

        async def update_state(self):
            if any([check.value for check in self.checkboxes]):
                await self.set_active()
            else:
                await self.set_inactive()

        async def checkbox_action(self, e):
            changed_from_default = False
            if self.option.install_settings is None:
                if self.option.default_option == "skip":
                    changed_from_default = e.data == "true"
                else:
                    changed_from_default = e.data == "false"
                self.choice = e.data
            else:
                self.choice = e.control.data
                changed_from_default = e.data != self.option.default_option
                if e.data != 'false':
                    for check in self.checkboxes:
                        if check.data != self.choice:
                            check.value = False
                            await check.update_async()
            await self.update_state()

            if changed_from_default:
                await self.parent.changed_from_default()
            else:
                await self.parent.changed_to_default()

        def build(self):
            self.active = self.option.default_option != 'skip'
            if self.option.install_settings is not None:
                selector = []
                self.complex_selector = True
                for setting in self.option.install_settings:
                    check = ft.Checkbox(data=setting["name"],
                                        on_change=self.checkbox_action,
                                        value=setting["name"] == self.option.default_option)
                    self.checkboxes.append(check)
                    selector.append(
                        ft.Row([
                            check,
                            # TODO: check that validation for the existance of name and description exists
                            Text(setting["name"], weight=ft.FontWeight.BOLD),
                            Text(setting["description"].strip(), no_wrap=False)
                            ], wrap=True, run_spacing=5))
            else:
                selector = ft.Checkbox(data='default',
                                       value=self.option.default_option is None,
                                       on_change=self.checkbox_action)
                self.checkboxes.append(selector)

            if self.complex_selector:
                return ft.Card(ft.Container(
                    Column([
                        Row([
                            Text(self.option.display_name,
                                 color=ft.colors.SECONDARY, weight=ft.FontWeight.BOLD),
                            Text(f"[{self.option.name}]", opacity=0.6),
                            Text(tr("will_not_be_installed").capitalize(),
                                 color=ft.colors.TERTIARY,
                                 visible=not self.active,
                                 ref=self.warning_text,
                                 opacity=0.8)
                            ], wrap=True, run_spacing=5),
                        Column([
                            Text(self.option.description, no_wrap=False),
                            Text(f'{tr("choose_one_of_the_options").capitalize()}:',
                                 color=ft.colors.SECONDARY),
                            *selector,
                            ])
                    ]),
                    margin=ft.margin.only(left=20, right=15, top=15, bottom=20)
                ),
                 animate_opacity=ft.animation.Animation(100, ft.AnimationCurve.EASE_IN),
                 elevation=5 if self.active else 0,
                 opacity=1 if self.active else 0.8,
                 scale=1 if self.active else 0.99,
                 ref=self.card)
            else:
                return ft.Card(ft.Container(
                    Column([
                        Row([
                            selector,
                            Text(self.option.display_name,
                                 color=ft.colors.SECONDARY, weight=ft.FontWeight.BOLD),
                            Text(f"[{self.option.name}]", opacity=0.6),
                            Text(tr("will_not_be_installed").capitalize(),
                                 color=ft.colors.TERTIARY,
                                 visible=not self.active,
                                 ref=self.warning_text,
                                 opacity=0.8)
                            ], wrap=True, run_spacing=5),
                        Row([
                            Text(self.option.description, no_wrap=False, expand=True)
                            ]),
                    ]), margin=ft.margin.only(left=20, right=15, top=15, bottom=20)
                ),
                 elevation=5 if self.active else 0,
                 opacity=1 if self.active else 0.8,
                 scale=1 if self.active else 0.99,
                 ref=self.card)

    async def close_wizard(self, e):
        # self.visible = False
        # await self.update_async()
        self.app.page.overlay.clear()
        await self.app.page.update_async()

    async def disable(self, container):
        container.current.bgcolor = ft.colors.SURFACE
        container.current.on_click = None
        self.text.current.color = ft.colors.ON_SURFACE
        await container.current.update_async()
        await self.text.current.update_async()

    async def select(self, container):
        container.current.bgcolor = ft.colors.SURFACE
        container.current.on_click = None
        self.text.current.color = ft.colors.ON_SURFACE
        await container.current.update_async()
        await self.text.current.update_async()

    async def deselect(self, container):
        container.current.bgcolor = ft.colors.PRIMARY_CONTAINER
        container.current.on_click = self.on_click_action
        self.text.current.color = ft.colors.ON_PRIMARY_CONTAINER
        await container.current.update_async()
        await self.text.current.update_async()

    async def did_mount_async(self):
        validated_translations = []
        for lang, mod in self.main_mod.translations_loaded.items():
            if mod.can_install:
                validated_translations.append(mod)

        num_valid_translations = len(validated_translations)
        if num_valid_translations == 0:
            # TODO: handle gracefully or remove entirely
            raise NoModsFound("No available for installation versions")
        # elif num_valid_translations == 1:
        self.mod = validated_translations[0]
        await self.show_welcome_mod_screen()

    async def agree_to_install(self, e):
        if self.can_have_custom_install and not e.control.data["is_compatch"]:
            await self.show_settings_screen(e)
        else:
            await self.show_install_progress(e)

    async def show_install_progress(self, e):
        print("Pressed yes when asked to start install or not")
        is_comrem_or_patch = self.mod.name == "community_remaster"
        is_compatch = False
        if isinstance(e.control.data, dict):
            is_compatch = e.control.data["is_compatch"]
        is_comrem = is_comrem_or_patch and not is_compatch

        await self.update_status_capsules(self.Steps.INSTALLING)
        install_settings = {}

        install_settings["base"] = "yes"
        for option_card in self.options:
            option = option_card.option
            if option_card.complex_selector:
                pass
            else:
                check = option_card.checkboxes[0]
                install_settings[option.name] = "yes" if check.value else "skip"

        game = self.app.game
        session = self.app.session
        mod = self.mod
        distribution_dir = self.app.context.distribution_dir
        game_root = game.game_root_path

        if is_comrem_or_patch:
            session.content_in_processing["community_patch"] = {
                "base": "yes",
                "version": mod.version,
                "build": mod.build,
                "display_name": "Community Patch"
            }

            file_ops.copy_from_to([os.path.join(distribution_dir, "patch")],
                                  os.path.join(game_root, "data"),
                                  console=False)
            file_ops.copy_from_to([os.path.join(distribution_dir, "libs")],
                                  game_root,
                                  console=False)
            file_ops.rename_effects_bps(game_root)

        if not is_compatch:
            status_ok, error_messages = mod.install(
                game.data_path,
                install_settings,
                session.content_in_processing,
                game.installed_descriptions)
            print(status_ok)
            print(error_messages)

            session.content_in_processing[mod.name] = install_settings.copy()
            session.content_in_processing[mod.name]["version"] = mod.version
            session.content_in_processing[mod.name]["build"] = mod.build
            session.content_in_processing[mod.name]["display_name"] = mod.display_name

        if not is_comrem_or_patch:
            if mod.patcher_options is not None:
                file_ops.patch_configurables(game.target_exe, mod.patcher_options)
                if mod.patcher_options.get('gravity') is not None:
                    file_ops.correct_damage_coeffs(game.game_root_path,
                                                   mod.patcher_options.get('gravity'))

        if is_comrem_or_patch:
            if is_comrem:
                target_dll = os.path.join(game_root, "dxrender9.dll")
                if os.path.exists(target_dll):
                    file_ops.patch_render_dll(target_dll)
                else:
                    raise DXRenderDllNotFound

            # TODO: check what is going on with context.remaster_config, why?
            # build_id = self.app.context.remaster_config["build"]
            build_id = mod.build
            file_ops.patch_game_exe(game.target_exe,
                                    "patch" if is_compatch else "remaster",
                                    build_id,
                                    self.app.context.monitor_res,
                                    mod.exe_options if is_comrem else {},
                                    self.app.context.under_windows)

        er_message = f"Couldn't dump install manifest to '{game.installed_manifest_path}'!"
        try:
            game.installed_content = game.installed_content | session.content_in_processing
            if game.installed_content:
                dumped_yaml = file_ops.dump_yaml(game.installed_content, game.installed_manifest_path)
                installed_mod_description = mod.get_install_description(install_settings)
                session.installed_content_description.extend(installed_mod_description)
                if not dumped_yaml:
                    self.app.logger.error(tr("installation_error"), er_message)
        except Exception as ex:
            self.app.logger.error(ex)
            self.app.logger.error(er_message)
            return

    def get_flag_buttons(self):
        flag_buttons = []
        for lang, mod in self.main_mod.translations_loaded.items():
            if mod.known_language:
                flag = get_internal_file_path(LangFlags[lang].value)
            else:
                flag = get_internal_file_path(LangFlags.other.value)

            icon = ft.Image(flag, fit=ft.ImageFit.FILL)

            flag_tooltip = mod.lang_label.capitalize()

            if not mod.can_install:
                icon.color = ft.colors.BLACK87
                icon.color_blend_mode = ft.BlendMode.COLOR
                flag_tooltip += f' ({tr("cant_be_installed")})'

            flag_btn = ft.IconButton(
                    content=icon,
                    data=lang,
                    tooltip=flag_tooltip,
                    bgcolor=ft.colors.BLACK12,
                    aspect_ratio=1,
                    expand=1)

            if mod.can_install:
                flag_btn.on_click = self.set_install_lang

            flag_buttons.append(flag_btn)

        num_langs = len(flag_buttons)
        return ft.ResponsiveRow([
            ft.Row(flag_buttons, alignment=ft.MainAxisAlignment.CENTER, col=num_langs)
            ],
            visible=num_langs > 1,
            alignment=ft.MainAxisAlignment.CENTER, columns=12 if num_langs <= 12 else num_langs)

    async def changed_from_default(self):
        self.default_install_btn.current.content = Row([
            Icon(ft.icons.STAR, color=ft.colors.ON_PRIMARY, size=22),
            Text(tr("choose_recommended_install").capitalize())
        ], alignment=ft.MainAxisAlignment.CENTER)
        self.default_install_btn.current.disabled = False

        await self.default_install_btn.current.update_async()

    async def changed_to_default(self):
        is_default_install = True
        for option_card in self.options:
            option = option_card.option
            if option.install_settings is None:
                value = option.default_option
                if value is None:
                    value = True
                if option_card.checkboxes[0].value != value:
                    is_default_install = False

        if is_default_install:
            await self.set_to_default(cards_are_set=True)

    async def set_option_cards_default(self):
        for option_card in self.options:
            changed = False
            option = option_card.option
            default_value = option.default_option
            if option.install_settings is None:
                if default_value is None:
                    default_value = True
                elif default_value == "skip":
                    default_value = False
                if option_card.checkboxes[0].value != default_value:
                    changed = True
                    option_card.checkboxes[0].value = default_value
                    await option_card.checkboxes[0].update_async()
            else:
                for check in option_card.checkboxes:
                    is_default = check.data == default_value
                    if check.value != is_default:
                        check.value = is_default
                        changed = True
                    await check.update_async()
            print(f"card: {option.name} changed: {changed}")
            if changed:
                await option_card.update_state()

    async def set_to_default(self, e=None, cards_are_set=False):
        if not cards_are_set:
            await self.set_option_cards_default()

        self.default_install_btn.current.content = ft.Row([
                    Icon(ft.icons.RECOMMEND_ROUNDED, color=ft.colors.TERTIARY),
                    Text(tr("recommended_install_chosen").capitalize())
        ], alignment=ft.MainAxisAlignment.CENTER)
        self.default_install_btn.current.disabled = True

        await self.default_install_btn.current.update_async()

    async def show_comrem_welcome(self, e):
        if e.control.data == "compatch":
            await self.show_welcome_mod_screen(e, is_compatch=True)
        else:
            await self.show_welcome_mod_screen(e, is_compatch=False)

    async def show_welcome_mod_screen(self, e=None, is_compatch=False):
        mod = self.mod

        is_comrem = mod.name == "community_remaster"
        self.can_have_custom_install = False
        self.requires_custom_install = False

        mod_name = "Community Patch" if is_compatch else self.mod.display_name
        title = (f"{tr('installation')} {mod_name} - "
                 f"{tr('version')} {self.mod.version}")
        await self.switch_title(title)

        remaster_button = ft.FloatingActionButton(
            content=Row([
                Icon(ft.icons.CHECK, visible=not is_compatch),
                Text("ComRemaster")
            ], alignment=ft.MainAxisAlignment.CENTER),
            data="comrem",
            bgcolor=ft.colors.PRIMARY_CONTAINER if not is_compatch else ft.colors.SECONDARY_CONTAINER,
            on_click=self.show_comrem_welcome,
            width=170, height=60,
            scale=1.0 if not is_compatch else 0.95)
        patch_button = ft.FloatingActionButton(
            content=Row([
                Icon(ft.icons.CHECK, visible=is_compatch),
                Text("ComPatch")
            ], alignment=ft.MainAxisAlignment.CENTER),
            bgcolor=ft.colors.PRIMARY_CONTAINER if is_compatch else ft.colors.SECONDARY_CONTAINER,
            data="compatch",
            disabled=self.mod.language != "ru",
            opacity=1.0 if self.mod.language == "ru" else 0.7,
            tooltip=tr("cant_be_installed") if self.mod.language != "ru" else None,
            on_click=self.show_comrem_welcome,
            width=170, height=60,
            scale=1.0 if is_compatch else 0.95)

        if mod.optional_content is not None:
            self.can_have_custom_install = True
            for option in mod.optional_content:
                if option.install_settings is not None and option.default_option is None:
                    # if any option doesn't have a default, we will ask user to make a choice
                    self.requires_custom_install = True
                    break

        description = (f"{tr('description')}\n{mod.description}\n\n"
                       f"{tr(mod.developer_title)} {mod.authors}")

        reinstall_warning = ""
        if self.app.game.installed_content.get(mod.name) is not None:
            if mod.name == "community_remaster":
                reinstall_warning = tr("warn_reinstall")
            else:
                reinstall_warning = tr("warn_reinstall_mods")
        # TODO: check that compatch over compatch reinstall triggers reinstall warning
        if mod.name == "community_remaster" and self.app.game.patched_version:
            reinstall_warning = tr("warn_reinstall")

        user_answer_buttons = [
            ft.ElevatedButton(tr("yes").capitalize(),
                              width=100,
                              on_click=self.agree_to_install,
                              data={"is_compatch": is_compatch},
                              style=ft.ButtonStyle(
                                 color={
                                     ft.MaterialState.HOVERED: ft.colors.ON_SECONDARY,
                                     ft.MaterialState.DEFAULT: ft.colors.ON_PRIMARY,
                                     ft.MaterialState.DISABLED: ft.colors.ON_SURFACE_VARIANT
                                     },
                                 bgcolor={
                                     ft.MaterialState.HOVERED: ft.colors.SECONDARY,
                                     ft.MaterialState.DEFAULT: ft.colors.PRIMARY,
                                     ft.MaterialState.DISABLED: ft.colors.SURFACE_VARIANT
                                 })),
            ft.FilledTonalButton(tr("no").capitalize(),
                                 width=100,
                                 on_click=self.close_wizard)
            ]

        if reinstall_warning:
            welcome_install_prompt = tr("reinstall_mod_ask")
        elif self.can_have_custom_install and not is_compatch:
            welcome_install_prompt = tr("setup_mod_ask")
        else:
            welcome_install_prompt = tr('install_mod_ask')

        if is_compatch:
            mod_banner_path = get_internal_file_path("assets/compatch_logo.png")
        else:
            mod_banner_path = self.mod.banner_path

        self.screen.current.content = ft.Column([
            ft.ResponsiveRow([
                Image(src=mod_banner_path,
                      visible=self.mod.banner_path is not None,
                      fit=ft.ImageFit.CONTAIN,
                      col={"xs": 12, "xl": 11, "xxl": 10})
                ], alignment=ft.MainAxisAlignment.CENTER),
            ft.ResponsiveRow([
                ft.Container(Column([
                    Text(description, no_wrap=False),
                    ft.Row([remaster_button, patch_button],
                           visible=is_comrem,
                           alignment=ft.MainAxisAlignment.CENTER),
                    ft.Container(Row([
                        Icon(ft.icons.WARNING_OUTLINED, color=ft.colors.ERROR),
                        Text(reinstall_warning, no_wrap=False, color=ft.colors.ERROR, expand=True),
                        ]),
                        visible=bool(reinstall_warning), border_radius=10, padding=10,
                        bgcolor=ft.colors.ERROR_CONTAINER)
                    ]), padding=ft.padding.only(bottom=5),
                             col={"xs": 12, "xl": 11, "xxl": 10})
                ], alignment=ft.MainAxisAlignment.CENTER),
            ft.ResponsiveRow([ft.Container(ft.Divider(height=3), col={"xs": 12, "xl": 11, "xxl": 10})],
                             alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(Column([
                self.get_flag_buttons() if not is_compatch else ft.Container(visible=False),
                Text(welcome_install_prompt,
                     text_align=ft.TextAlign.CENTER),
                Text(f"({tr('mod_install_language').capitalize()}: {mod.lang_label})",
                     color=ft.colors.SECONDARY)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=5), padding=5),
            Row(controls=user_answer_buttons,
                alignment=ft.MainAxisAlignment.CENTER)
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        await self.screen.current.update_async()
        self.current_screen = self.Steps.WELCOME
        await self.update_status_capsules(self.Steps.WELCOME)

    async def show_settings_screen(self, e=None):
        self.options.clear()
        await self.update_status_capsules(self.Steps.SETTING_UP)
        mod = self.mod

        if self.requires_custom_install:
            cancel_label = tr("cancel_install").capitalize()
        else:
            cancel_label = tr("no").capitalize()
        user_choice_buttons = [
            ft.ElevatedButton(tr("yes").capitalize(),
                              width=100,
                              on_click=self.show_install_progress,
                              style=ft.ButtonStyle(
                                 color={
                                     ft.MaterialState.HOVERED: ft.colors.ON_SECONDARY,
                                     ft.MaterialState.DEFAULT: ft.colors.ON_PRIMARY,
                                     ft.MaterialState.DISABLED: ft.colors.ON_SURFACE_VARIANT
                                     },
                                 bgcolor={
                                     ft.MaterialState.HOVERED: ft.colors.SECONDARY,
                                     ft.MaterialState.DEFAULT: ft.colors.PRIMARY,
                                     ft.MaterialState.DISABLED: ft.colors.SURFACE_VARIANT
                                 }),
                              visible=not self.requires_custom_install,
                              ),
            ft.FilledTonalButton(cancel_label,
                                 width=200 if self.requires_custom_install else 100,
                                 on_click=self.close_wizard),
        ]

        default_install_btn_row = ft.ResponsiveRow([], alignment=ft.MainAxisAlignment.CENTER)

        if self.requires_custom_install:
            raise NotImplementedError("requires_custom_install")
        else:
            for option in mod.optional_content:
                self.options.append(self.ModOption(self, option))

            default_install_btn_row.controls.append(ft.ElevatedButton(
                content=ft.Container(Row([
                    Icon(ft.icons.RECOMMEND_ROUNDED,
                         color=ft.colors.TERTIARY),
                    Text(tr("recommended_install_chosen").capitalize())
                    ], alignment=ft.MainAxisAlignment.CENTER), clip_behavior=ft.ClipBehavior.HARD_EDGE),
                col=6,
                on_click=self.set_to_default,
                disabled=True,
                style=ft.ButtonStyle(
                                 side={
                                     ft.MaterialState.DISABLED: ft.BorderSide(width=1,
                                                                              color=ft.colors.TERTIARY)
                                 },
                                 color={
                                     ft.MaterialState.DEFAULT: ft.colors.ON_PRIMARY,
                                     ft.MaterialState.DISABLED: ft.colors.TERTIARY
                                     },
                                 bgcolor={
                                     ft.MaterialState.DEFAULT: ft.colors.PRIMARY,
                                     ft.MaterialState.DISABLED: ft.colors.SURFACE_VARIANT
                                 }),
                ref=self.default_install_btn))

        self.screen.current.content = ft.Column([
            ft.ResponsiveRow([
                Image(src=self.mod.banner_path, visible=self.mod.banner_path is not None,
                      col={"xs": 6, "xl": 5, "xxl": 4})
                ], alignment=ft.MainAxisAlignment.CENTER),
            ft.ResponsiveRow([
                ft.Container(Column([
                    Text(tr('default_options')),
                    default_install_btn_row,
                    Column(controls=self.options, scroll=ft.ScrollMode.AUTO, spacing=5),
                    ]),
                    padding=ft.padding.only(top=5, bottom=10),
                    col={"xs": 12, "xl": 11, "xxl": 10})
                ], alignment=ft.MainAxisAlignment.CENTER),
            ft.ResponsiveRow([ft.Container(ft.Divider(height=3), col={"xs": 10, "xl": 9, "xxl": 8})],
                             alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(Column([
                Text(f"{tr('install_mod_with_options_ask')}",
                     text_align=ft.TextAlign.CENTER),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=5), padding=5),
            Row(controls=user_choice_buttons,
                alignment=ft.MainAxisAlignment.CENTER)
            ],
            spacing=5,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        await self.screen.current.update_async()
        self.current_screen = self.Steps.SETTING_UP

    async def set_install_lang(self, e):
        self.mod = self.main_mod.translations_loaded[e.control.data]
        await self.show_welcome_mod_screen()

    async def update_status_capsules(self, step: Steps):
        # colors of capsule representing currently active installation step
        active_clr = ft.colors.ON_PRIMARY_CONTAINER
        active_cont = ft.colors.PRIMARY_CONTAINER

        # colors of capsule representing step that can't be directly chosen by pressing the capsule
        bg_clr = ft.colors.ON_SURFACE
        bg_cont = ft.colors.SURFACE

        # colors of capsule representing step that was already processed but we can go back to it
        deflt_clr = ft.colors.ON_SECONDARY_CONTAINER
        deflt_cont = ft.colors.SECONDARY_CONTAINER

        welcome = step == self.Steps.WELCOME
        setting_up = step == self.Steps.SETTING_UP
        installing = step == self.Steps.INSTALLING
        results = step == self.Steps.RESULTS

        if welcome:
            welcome_clr = active_clr
            welcome_cont = active_cont
        else:
            if setting_up:
                welcome_clr = deflt_clr
                welcome_cont = deflt_cont
            else:
                welcome_clr = bg_clr
                welcome_cont = bg_cont

        capsules = [
                    ft.Container(
                        Text(tr("welcoming").capitalize(),
                             weight=ft.FontWeight.W_500 if welcome else ft.FontWeight.W_400,
                             size=12,
                             color=welcome_clr,
                             opacity=0.5 if self.mod is None else 1.0),
                        bgcolor=welcome_cont,
                        border_radius=10,
                        padding=ft.padding.symmetric(horizontal=10, vertical=2),
                        ink=True,
                        expand=1,
                        disabled=installing or results,
                        on_click=self.show_welcome_mod_screen),
                    ft.Container(
                        Text(tr("setting_up").capitalize(),
                             weight=ft.FontWeight.W_500 if setting_up else ft.FontWeight.W_400,
                             size=12,
                             color=active_clr if setting_up else bg_clr,
                             opacity=0.5 if self.mod is None else 1.0),
                        bgcolor=active_cont if setting_up else bg_cont,
                        border_radius=10,
                        padding=ft.padding.symmetric(horizontal=10, vertical=2),
                        ink=True,
                        expand=1,
                        visible=self.can_have_custom_install,
                        disabled=installing or results),
                    ft.Container(
                        Text(tr("installation").capitalize(),
                             weight=ft.FontWeight.W_500 if installing else ft.FontWeight.W_400,
                             size=12,
                             color=active_clr if installing else bg_clr,
                             opacity=0.5 if self.mod is None else 1.0),
                        bgcolor=active_cont if installing else bg_cont,
                        border_radius=10,
                        padding=ft.padding.symmetric(horizontal=10, vertical=2),
                        ink=True,
                        expand=1,
                        disabled=True),
                    ft.Container(
                        Text(tr("install_results").capitalize(),
                             weight=ft.FontWeight.W_500 if results else ft.FontWeight.W_400,
                             size=12,
                             color=active_clr if results else bg_clr,
                             opacity=0.5 if self.mod is None else 1.0),
                        bgcolor=active_cont if results else bg_cont,
                        border_radius=10,
                        padding=ft.padding.symmetric(horizontal=10, vertical=2),
                        disabled=True,
                        ink=True,
                        expand=1)
                    ]

        self.status_capsules.controls = capsules
        await self.status_capsules.update_async()

    async def switch_title(self, title):
        self.mod_title.current.value = title
        await self.mod_title.current.update_async()

    def build(self):
        return ft.Container(Column([ft.ResponsiveRow([
            Column(controls=[
                ft.Card(ft.Container(
                    ft.Column(
                        [Row([
                            ft.WindowDragArea(ft.Container(
                                Row([
                                    Text(self.mod_title_text,
                                         ref=self.mod_title,
                                         color=ft.colors.PRIMARY,
                                         weight=ft.FontWeight.BOLD)],
                                    alignment=ft.MainAxisAlignment.CENTER),
                                padding=12), expand=True),
                            ft.Tooltip(
                                message=tr("cancel_install").capitalize(),
                                wait_duration=50,
                                content=ft.IconButton(ft.icons.CLOSE_ROUNDED,
                                                      on_click=self.close_wizard,
                                                      icon_color=ft.colors.RED,
                                                      icon_size=22))
                              ],
                             alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                             vertical_alignment=ft.CrossAxisAlignment.START),
                         self.status_capsules_container,
                         ft.Container(ref=self.screen,
                                      padding=ft.padding.only(bottom=20, left=40, right=40)),
                         ])
                    ))
                ], alignment=ft.MainAxisAlignment.CENTER,
                col={"xs": 10, "lg": 9, "xl": 8, "xxl": 7}),
            ], alignment=ft.MainAxisAlignment.CENTER)], scroll=ft.ScrollMode.ADAPTIVE),
            alignment=ft.alignment.center, padding=ft.padding.symmetric(vertical=15, horizontal=10))


class LocalModsScreen(UserControl):
    def __init__(self, app: App, **kwargs):
        super().__init__(self, **kwargs)
        self.app = app
        self.tracked_mods = set()
        self.mods_list_view = ft.Ref[ft.ListView]()
        self.no_mods_warning = ft.Ref[Text]()

    # TODO: is not working properly when first starting with no distro and then adding it
    # shows no_local_mods_found warning
    async def did_mount_async(self):
        await self.update_list()
        print("did mount local mods screen")

    async def update_list(self):
        # if self.no_mods_warning.current is None:
        #     return

        if self.app.config.current_distro:
            print(f"Have current distro {self.app.config.current_distro}")
        else:
            print("No current distro")

        if self.app.config.current_game:
            print(f"Have current game {self.app.config.current_game}")
        else:
            print("No current game")
        
        if not self.app.config.current_distro:
            self.no_mods_warning.current.visible = True
            self.mods_list_view.current.visible = False
            self.no_mods_warning.current.value = "No current distro!"
        elif not self.app.config.current_game:
            self.no_mods_warning.current.visible = True
            self.mods_list_view.current.visible = False
            self.no_mods_warning.current.value = "No current game!"
        elif not self.app.session.mods:
            self.no_mods_warning.current.visible = True
            self.mods_list_view.current.visible = False
            self.no_mods_warning.current.value = tr("no_local_mods_found").capitalize()
        else:
            self.no_mods_warning.current.visible = False
            self.mods_list_view.current.visible = True

        # await self.no_mods_warning.current.update_async()

        for path, mod in self.app.session.mods.items():
            # mod_identifier = f'{mod.name}{mod.version}{mod.build}'
            self.mods_list_view.current.controls.append(ModItem(self.app, mod))
            # if mod_identifier not in self.tracked_mods:
                # self.tracked_mods.add(mod_identifier)
            
        # await self.mods_list_view.current.update_async()
        print(f"{len(self.mods_list_view.current.controls)} elements in mods list view")

    def build(self):
        return ft.Container(
            Column([
                Row([Text(tr("local_mods").capitalize(),
                          style=ft.TextThemeStyle.TITLE_MEDIUM)],
                    alignment=ft.MainAxisAlignment.CENTER),
                ft.Column([
                    ft.Container(
                        ft.ResponsiveRow([
                            Text(tr("no_local_mods_found").capitalize(), ref=self.no_mods_warning),
                            ft.ListView([], spacing=10, padding=0,
                                        ref=self.mods_list_view, col={"md": 12, "lg": 11, "xxl": 10})],
                            alignment=ft.MainAxisAlignment.CENTER),
                        padding=ft.padding.only(right=22))
                    ],
                    expand=True, scroll=ft.ScrollMode.ALWAYS)
            ]),
            margin=ft.margin.only(bottom=5), expand=True)


class DownloadModsScreen(UserControl):
    def __init__(self, app: App, **kwargs):
        super().__init__(self, **kwargs)
        self.app = app

    def build(self):
        return Text("DownloadModsScreen")


class HomeScreen(UserControl):
    def __init__(self, app: App, **kwargs):
        super().__init__(self, **kwargs)
        self.app = app
        self.markdown_content = ft.Ref[ft.Markdown]()
        self.checking_online = ft.Ref[Row]()
        self.news_text = None
        self.game_console_switch = ft.Ref[ft.Switch]()
        self.launch_game_btn = ft.Ref[ft.FloatingActionButton]()
        self.launch_game_btn_text = ft.Ref[Text]()
        self.checkbox_windowed_game = ft.Ref[ft.PopupMenuItem]()

    async def did_mount_async(self):
        self.got_news = False
        self.offline = False
        create_task(self.get_news())

    async def get_news(self):
        if not self.offline:
            if self.news_text is not None:
                self.markdown_content.current.value = self.news_text
                await self.markdown_content.current.update_async()
                return

            # await asyncio.sleep(1)
            dem_news = 'https://raw.githubusercontent.com/DeusExMachinaTeam/EM-CommunityPatch/main/README.md'
            # pavlik_news = 'https://raw.githubusercontent.com/zatinu322/hta_kazakh_autotranslation/main/README.md'
            response = await request(
                url=dem_news,
                protocol="HTTPS",
                protocol_info={
                    "request_type": "GET",
                    "timeout": 5
                }
            )

            if response["api_response"]["status_code"] == 200:
                md_raw = response["api_response"]["text"]
                md = process_markdown(md_raw)
                self.markdown_content.current.value = md
                self.checking_online.current.visible = False
                await self.checking_online.current.update_async()
                await self.markdown_content.current.update_async()
                self.news_text = md
                self.got_news = True
            else:
                self.app.logger.error(f'bad response {response["api_response"]["status_code"]}')
        else:
            self.app.logger.error("Unable to get url content for news")
            self.offline = True

    async def launch_url(self, e):
        await self.app.page.launch_url_async(e.data)

    async def check_for_game(self):
        if self.app.current_game_process is None:
            proc = get_proc_by_names(("hta.exe", "ExMachina.exe"))
            return proc is not None

        if self.app.current_game_process.returncode is None:
            pass

    async def switch_to_windowed(self, e):
        # temporarily disabling game launch
        self.launch_game_btn.current.disabled = True
        await self.launch_game_btn.current.update_async()

        self.checkbox_windowed_game.current.checked = not self.checkbox_windowed_game.current.checked
        await self.checkbox_windowed_game.current.update_async()
        if self.app.game.game_root_path is not None:
            # just an additional safeguard, all actions on game are delayed by 1 second after game_change_time
            self.app.game_change_time = datetime.now()
            await self.app.game.switch_windowed(enable=not self.checkbox_windowed_game.current.checked)

        self.launch_game_btn.current.disabled = False
        await self.launch_game_btn.current.update_async()

    async def launch_game(self, e):
        current_time = datetime.now()
        if self.app.game_change_time is not None:
            if (current_time - self.app.game_change_time).seconds < 1:
                # do not try to relaunch game immediately after a change
                return
        if self.app.current_game_process is None:
            other_game_running = await self.check_for_game()
            if other_game_running:
                await self.app.show_alert(tr('game_is_running'))
                return
            self.app.logger.info(f"Launching: {self.app.game.target_exe}")
            self.app.current_game_process = \
                await create_subprocess_exec(self.app.game.target_exe,
                                             '-console' if self.app.config.game_with_console else "",
                                             cwd=self.app.game.game_root_path)
            self.app.game_change_time = datetime.now()
            await self.synchronise_launch_btn_prompt(starting=True)
            await self.keep_track_of_game_proc()
        else:
            # will this be 1 if we crash the game?
            if self.app.current_game_process.returncode == 1:
                # game exited
                self.app.current_game_process = None
                await self.synchronise_launch_btn_prompt(starting=False)
            elif self.app.current_game_process.returncode is None:
                # stopping game on a next step, needs to be explained with a changing
                # button prompt
                self.app.current_game_process.terminate()
                self.app.current_game_process = None
                await self.synchronise_launch_btn_prompt(starting=False)

    async def keep_track_of_game_proc(self):
        while True:
            if self.app.current_game_process is None:
                break
            if self.app.current_game_process.returncode is None:
                pass
            else:
                await self.synchronise_launch_btn_prompt(starting=False)
                break
            await asyncio.sleep(3)

    async def synchronise_launch_btn_prompt(self, starting=True):
        if starting:
            self.launch_game_btn_text.current.value = "Launching..."
            await self.launch_game_btn_text.current.update_async()
            await asyncio.sleep(1)
            self.launch_game_btn_text.current.value = "Stop game"
            await self.launch_game_btn_text.current.update_async()
        else:
            self.launch_game_btn_text.current.value = tr("play").capitalize()
            await self.launch_game_btn_text.current.update_async()

    async def game_console_mode_change(self, e):
        self.app.config.game_with_console = e.data == 'true'

    def build(self):
        # TODO: preload md or use placeholder by default
        with open(get_internal_file_path("assets/placeholder.md"), "r", encoding="utf-8") as fh:
            md1 = fh.read()
            md1 = process_markdown(md1)

            if self.app.game.game_installment_id == GameInstallments.EXMACHINA.value:
                logo_path = "assets/em_logo.png"
            elif self.app.game.game_installment_id == GameInstallments.M113.value:
                logo_path = "assets/m113_logo.png"
            elif self.app.game.game_installment_id == GameInstallments.ARCADE.value:
                logo_path = "assets/arcade_logo.png"
            else:
                logo_path = None

            if logo_path is not None:
                image = Image(src=get_internal_file_path(logo_path),
                              fit=ft.ImageFit.FILL)
            else:
                image = ft.Stack([Image(src=get_internal_file_path("icons/em_logo.png"),
                                        fit=ft.ImageFit.FILL, opacity=0.4),
                                  ft.Container(Icon(ft.icons.QUESTION_MARK_ROUNDED,
                                                    size=90,
                                                    color='red'),
                                               alignment=ft.alignment.center)])

            if self.app.game.target_exe is None:
                # TODO: create proper placeholder screen when there is no game
                return ft.Container(Text("No game found"))

            return ft.Container(
                ft.ResponsiveRow([
                    Column(controls=[
                        ft.Container(Column([
                            ft.Container(
                                Column([image],
                                       horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                margin=ft.margin.only(top=10)),
                            Row([
                                Icon(ft.icons.INFO_ROUNDED, color=ft.colors.PRIMARY, size=20),
                                Text(self.app.game.exe_version,
                                     color=ft.colors.PRIMARY,
                                     weight=ft.FontWeight.W_700)]),
                            Row([
                                Icon(ft.icons.BADGE_ROUNDED, color=ft.colors.PRIMARY, size=20),
                                ft.Column([Text(self.app.config.game_names[self.app.config.current_game],
                                                color=ft.colors.PRIMARY,
                                                overflow=ft.TextOverflow.ELLIPSIS,
                                                weight=ft.FontWeight.W_400)], expand=True)
                                ]),
                        ]), clip_behavior=ft.ClipBehavior.ANTI_ALIAS),
                        # Text(self.app.context.distribution_dir),
                        # Text(self.app.context.commod_version),
                        # Text(self.app.game.game_root_path),
                        # Text(self.app.game.display_name),
                        Column([
                            Row([Text(tr("launch_params").upper(),
                                      weight=ft.FontWeight.W_700),
                                 ft.PopupMenuButton(items=[
                                    ft.PopupMenuItem(
                                        content=Text(tr("windowed_mode").capitalize(), size=14),
                                        checked=not self.app.game.fullscreen_game,
                                        on_click=self.switch_to_windowed,
                                        ref=self.checkbox_windowed_game)],
                                    # TODO: is this working as intended?
                                    disabled=self.app.game.exe_version == "Unknown")
                                 ], alignment=ft.MainAxisAlignment.SPACE_AROUND),
                            Row([ft.Switch(value=self.app.config.game_with_console,
                                           scale=0.7,
                                           on_change=self.game_console_mode_change,
                                           ref=self.game_console_switch),
                                 Text(tr("enable_console").capitalize(),
                                 weight=ft.FontWeight.W_500)],
                                spacing=0),
                            ft.FloatingActionButton(
                                content=ft.Row([
                                    ft.Text(tr("play").capitalize(), size=20,
                                            weight=ft.FontWeight.W_700,
                                            ref=self.launch_game_btn_text,
                                            color=ft.colors.ON_PRIMARY)],
                                    alignment="center", spacing=5
                                ),
                                shape=ft.RoundedRectangleBorder(radius=5),
                                bgcolor="#FFA500",
                                ref=self.launch_game_btn,
                                on_click=self.launch_game,
                                aspect_ratio=2.5,
                            )])
                        ],
                        col={"xs": 4, "xl": 3}, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Container(Column([
                        Row([ft.ProgressRing(scale=0.5), Text("Checking online news...")],
                            ref=self.checking_online, visible=self.news_text is None),
                        ft.Container(ft.Markdown(
                            md1,
                            expand=True,
                            code_theme="atom-one-dark",
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                            on_tap_link=self.launch_url,
                            ref=self.markdown_content,
                        ), padding=ft.padding.only(left=10, right=22)),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        spacing=20,
                        scroll=ft.ScrollMode.ADAPTIVE), col={"xs": 8, "xl": 9})
                    ], vertical_alignment=ft.CrossAxisAlignment.START, spacing=30),
                margin=ft.margin.only(bottom=20), expand=True)


async def main(page: Page):
    async def maximize(e):
        page.window_maximized = not page.window_maximized
        await page.update_async()

    async def minimize(e):
        page.window_minimized = True
        await page.update_async()

    async def change_theme_mode(e):
        theme = page._Page__theme_mode
        if theme == ft.ThemeMode.SYSTEM:
            page.theme_mode = ft.ThemeMode.DARK
            page.theme_icon_btn.current.icon = ft.icons.WB_SUNNY_OUTLINED
            await page.theme_icon_btn.current.update_async()
        elif theme == ft.ThemeMode.DARK:
            page.theme_mode = ft.ThemeMode.LIGHT
            page.theme_icon_btn.current.icon = ft.icons.NIGHTLIGHT_OUTLINED
            await page.theme_icon_btn.current.update_async()
        else:
            page.theme_mode = ft.ThemeMode.SYSTEM
            page.theme_icon_btn.current.icon = ft.icons.BRIGHTNESS_AUTO
            await page.theme_icon_btn.current.update_async()

        await page.update_async()

    def title_btn_style(hover_color: ft.colors = None):
        color_dict = {ft.MaterialState.DEFAULT: ft.colors.ON_BACKGROUND}
        if hover_color is not None:
            color_dict[ft.MaterialState.HOVERED] = ft.colors.RED
        return ft.ButtonStyle(
            color=color_dict,
            padding={ft.MaterialState.DEFAULT: 0},
            shape={ft.MaterialState.DEFAULT: ft.buttons.RoundedRectangleBorder(radius=2)}
        )

    def create_sections(app: App):
        app.home = HomeScreen(app)
        app.local_mods = LocalModsScreen(app)
        app.download_mods = DownloadModsScreen(app)
        app.settings_page = SettingsScreen(app)

        app.content_pages = [app.home, app.local_mods, app.download_mods, app.settings_page]

    async def wrap_on_window_event(e):
        if e.data == "close":
            await finalize(e)
        elif e.data == "unmaximize" or e.data == "maximize":
            if page.window_maximized:
                page.icon_maximize.current.icon = ft.icons.FILTER_NONE
                page.icon_maximize.current.icon_size = 15
            else:
                page.icon_maximize.current.icon = ft.icons.CHECK_BOX_OUTLINE_BLANK_ROUNDED
                page.icon_maximize.current.icon_size = 17
            await page.icon_maximize.current.update_async()

    async def finalize(e):
        app.logger.debug("closing")
        app.config.save_config()
        app.logger.debug("config saved")
        await page.window_close_async()

    options = _init_input_parser().parse_args()

    page.window_title_bar_hidden = True
    page.title = "ComMod"
    page.scroll = None
    page.on_window_event = wrap_on_window_event
    page.window_min_width = 900
    page.window_min_height = 600
    page.theme_mode = ft.ThemeMode.SYSTEM

    page.padding = 0
    page.theme = Theme(color_scheme_seed="#FFA500", visual_density=ThemeVisualDensity.COMPACT)
    page.dark_theme = Theme(color_scheme_seed="#FFA500", visual_density=ThemeVisualDensity.COMPACT)

    app = App(context=InstallationContext(dev_mode=options.dev, can_skip_adding_distro=True),
              game=GameCopy(),
              config=Config(page))

    page.app = app
    app.page = page
    # TODO: pass 'dev' options further, it's needed in case of changing the context

    # TODO: move to app init
    app.current_game_process = None

    app.context.setup_loggers(stream_only=True)
    app.logger = app.context.logger
    app.context.load_system_info()

    distribution_dir = InstallationContext.get_local_path()
    target_dir = distribution_dir

    # if nothing else is known, we expect commod to launch inside the game folder
    # with distibution files (ComRem files and optional "mods" directory) around
    distribution_dir = InstallationContext.get_local_path()
    target_dir = distribution_dir

    # at the end of each operation, commod tries to create config near itself
    # if we can load it - we will use the data from it, except when overriden from console args
    app.config = Config(page)
    app.config.load_from_file()

    page.window_width = app.config.init_width
    page.window_height = app.config.init_height
    page.window_left = app.config.init_pos_x
    page.window_top = app.config.init_pos_y

    page.theme_mode = app.config.init_theme
    match app.config.lang:
        case SupportedLanguages.ENG:
            localisation.LANG = "eng"
        case SupportedLanguages.UKR:
            localisation.LANG = "ukr"
        case SupportedLanguages.RUS:
            localisation.LANG = "rus"
        case _:
            app.config.lang = SupportedLanguages.SYS

    localisation.STRINGS = localisation.get_strings_dict()

    app.logger.info(f"Current lang: {localisation.LANG=}")

    target_dir = app.config.current_game
    distribution_dir = app.config.current_distro

    # console params can override this early
    if options.distribution_dir:
        distribution_dir = options.distribution_dir
    if options.target_dir:
        target_dir = options.target_dir

    # we checked everywhere, so we can try to properly load distribution and game
    if target_dir:
        try:
            app.game.process_game_install(target_dir)
        except Exception as ex:
            # TODO: Handle exceptions properly
            app.logger.error(f"[Game loading error] {ex}")

    if distribution_dir:
        try:
            app.context.add_distribution_dir(distribution_dir)
        except Exception as ex:
            # TODO: Handle exceptions properly
            app.logger.error(f"[Distro loading error] {ex}")

    need_quick_start = (not app.config.game_names
                        and app.context.distribution_dir is None
                        and app.game.game_root_path is None)

    create_sections(app)

    page.theme_icon_btn = ft.Ref[IconButton]()
    theme_icon = ft.icons.BRIGHTNESS_AUTO
    match page.theme_mode:
        case ft.ThemeMode.SYSTEM:
            theme_icon = ft.icons.BRIGHTNESS_AUTO
        case ft.ThemeMode.DARK:
            theme_icon = ft.icons.WB_SUNNY_OUTLINED
        case ft.ThemeMode.LIGHT:
            theme_icon = ft.icons.NIGHTLIGHT_OUTLINED

    rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.SELECTED,
        min_extended_width=160,
        animate_size=ft.animation.Animation(200, ft.AnimationCurve.DECELERATE),
        destinations=[
            ft.NavigationRailDestination(
                icon=ft.icons.ROCKET_LAUNCH_OUTLINED,
                selected_icon=ft.icons.ROCKET_LAUNCH,
                label=tr("launch").capitalize()
            ),
            ft.NavigationRailDestination(
                icon=ft.icons.BOOKMARK_BORDER,
                selected_icon=ft.icons.BOOKMARK,
                label=tr("local_mods").capitalize(),
            ),
            ft.NavigationRailDestination(
                icon=ft.icons.DOWNLOAD_OUTLINED,
                selected_icon=ft.icons.DOWNLOAD,
                label=tr("download").capitalize()
            ),
            ft.NavigationRailDestination(
                icon=ft.icons.SETTINGS_OUTLINED,
                selected_icon=ft.icons.SETTINGS,
                label=tr("settings").capitalize()
            )
        ],
        trailing=ft.Tooltip(
                message=tr("theme_mode"),
                wait_duration=500,
                content=ft.IconButton(icon=theme_icon,
                                      on_click=change_theme_mode,
                                      ref=page.theme_icon_btn,
                                      selected_icon_color=ft.colors.ON_SURFACE_VARIANT)),
        on_change=app.change_page,
    )
    page.rail = rail
    app.rail = rail

    page.icon_maximize = ft.Ref[IconButton]()
    # title bar to replace system one
    await page.add_async(
        ft.Row(
            [ft.WindowDragArea(ft.Container(
                 ft.Row([
                     Image(src=get_internal_file_path("icons/dem_logo.svg"),
                           width=20,
                           height=20,
                           fit=ft.ImageFit.COVER),
                     ft.Text(get_title(), size=13, weight=ft.FontWeight.W_500)]), padding=6),
                     expand=True),
             ft.IconButton(ft.icons.MINIMIZE_ROUNDED, on_click=minimize, icon_size=20,
                           style=title_btn_style()),
             ft.IconButton(ft.icons.CHECK_BOX_OUTLINE_BLANK_ROUNDED,
                           on_click=maximize,
                           icon_size=17,
                           style=title_btn_style(),
                           ref=page.icon_maximize),
             ft.IconButton(ft.icons.CLOSE_ROUNDED, on_click=finalize, icon_size=22,
                           style=title_btn_style(hover_color=ft.colors.RED))
             ],
            spacing=0,
            height=31
        )
    )
    app.content_column = ft.Container(expand=True,
                                      alignment=ft.alignment.top_center,
                                      margin=ft.margin.only(left=0, right=0))

    # add application's root control to the page
    await page.add_async(
        ft.Container(ft.Row([rail, app.content_column]),
                     expand=True,
                     padding=ft.padding.only(left=10, right=10, bottom=10)
                     )
    )

    app.context.current_session.load_steam_game_paths()
    if need_quick_start:
        app.logger.debug("showing quick start")
        await app.show_guick_start_wizard()
    else:
        app.load_distro()
        await app.change_page(index=app.config.current_section)

    await page.update_async()


def start():
    ft.app(target=main)
