
from asyncio import create_task, gather, create_subprocess_exec
from datetime import datetime
import logging
import os

from dataclasses import dataclass  # , field
from enum import Enum
from pathlib import Path

from asyncio_requests.asyncio_request import request

import localisation

from commod import _init_input_parser
from data import get_title
from environment import InstallationContext, GameCopy, GameInstallments, GameStatus, DistroStatus
from file_ops import dump_yaml, get_internal_file_path, read_yaml, process_markdown
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
    other = "assets\\flags\\openmoji_triangle.svg"


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

        self.page: ft.Page = page

    @staticmethod
    def sanitize_config(config: dict) -> bool:
        # TODO: validate and sanitize config from bad values
        return True

    def asdict(self):
        return {
            "current_game": self.current_game,
            "game_names": self.game_names,
            "current_distro": self.current_distro,
            "modder_mode": self.modder_mode,
            "current_section": self.current_section,
            "current_game_filter": self.current_game_filter,
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

        if self.sanitize_config(config):
            self.current_game = config["current_game"]
            self.game_names = config["game_names"]
            self.known_games = set([game_path.lower() for game_path in config["game_names"]])

            self.current_distro = config["current_distro"]
            self.known_distros = set([config["current_distro"]])

            self.modder_mode = config["modder_mode"]
            self.current_section = config["current_section"]
            self.current_game_filter = config["current_game_filter"]

            window_config = config.get("window")
            # ignoring broken partial configs for window
            if window_config is not None:
                if (window_config.get("width") is not None
                   and window_config.get("height") is not None
                   and window_config.get("pos_x") is not None
                   and window_config.get("pos_y") is not None):
                    self.init_height = config["window"]["height"]
                    self.init_width = config["window"]["width"]
                    self.init_pos_x = config["window"]["pos_x"]
                    self.init_pos_y = config["window"]["pos_y"]

            self.init_theme = ft.ThemeMode(config["theme"])

    def save_config(self, abs_dir_path: str | None = None):
        if abs_dir_path is not None and os.path.isdir(abs_dir_path):
            config_path = os.path.join(abs_dir_path, "commod.yaml")
        else:
            config_path = os.path.join(InstallationContext.get_local_path(), "commod.yaml")

        result = dump_yaml(self.asdict(), config_path, sort_keys=False)
        if not result:
            print("Couldn't write new config")


@dataclass
class App:
    '''Root level application class storing modding environment'''
    context: InstallationContext
    game: GameCopy
    config: Config | None = None
    session: InstallationContext.Session | None = None

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
                                 ref=self.game_name_label, width=300), margin=ft.margin.symmetric(vertical=10)),
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
            col={"sm": 12, "lg": 10, "xxl": 8})

        self.no_distro_warning = ft.Container(
            Row([Icon(ft.icons.INFO_OUTLINE_ROUNDED, color=ft.colors.ON_TERTIARY_CONTAINER, ),
                 Text(value=tr("commod_needs_remaster").replace("\n", " "),
                      weight=ft.FontWeight.BOLD,
                      color=ft.colors.ON_TERTIARY_CONTAINER)]),
            bgcolor=ft.colors.TERTIARY_CONTAINER, padding=10, border_radius=10,
            animate_size=ft.animation.Animation(500, ft.AnimationCurve.DECELERATE),
            visible=bool(not self.app.config.current_distro),
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            col={"sm": 12, "lg": 10, "xxl": 8})

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
                self.list_of_games], col={"sm": 12, "lg": 10, "xxl": 8}
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
           col={"sm": 12, "lg": 10, "xxl": 8})

        expanded_icon = ft.icons.KEYBOARD_ARROW_UP_OUTLINED
        collapsed_icon = ft.icons.KEYBOARD_ARROW_DOWN_OUTLINED
        self.add_game_manual_container = ft.Ref[ft.Container]()
        self.add_game_steam_container = ft.Ref[ft.Container]()
        self.add_distro_container = ft.Ref[ft.Container]()
        self.add_game_expanded = not self.app.config.known_distros
        self.add_steam_expanded = not self.app.config.known_distros
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
                        ], col={"sm": 12, "xl": 11, "xxl": 9}),
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
                                  col={"sm": 12, "lg": 10, "xxl": 7}
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
                             col={"sm": 12, "lg": 10, "xxl": 7}
                                  )
                    ], alignment=ft.MainAxisAlignment.CENTER),
                ft.ResponsiveRow(
                    # contols of distro/comrem/mods folders
                    controls=[
                        Row([
                            ft.Icon(ft.icons.CREATE_NEW_FOLDER, color=ft.colors.ON_BACKGROUND),
                            Text(value=tr("control_mod_folders").upper(), style=ft.TextThemeStyle.TITLE_SMALL)
                             ], col={"sm": 12, "xl": 11, "xxl": 9}),
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
                                     col={"sm": 12, "lg": 10, "xxl": 7}
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

    async def close_alert(self, e):
        self.app.page.dialog.open = False
        await self.app.page.update_async()

    async def show_alert(self, text, additional_text):
        dlg = ft.AlertDialog(
            title=Row([Icon(ft.icons.WARNING_OUTLINED, color=ft.colors.ERROR_CONTAINER),
                       Text(tr("error"))]),
            shape=ft.buttons.RoundedRectangleBorder(radius=10),
            content=Column([Text(text), Text(additional_text, color=ft.colors.ON_ERROR_CONTAINER)],
                           width=550, height=80),
            actions=[
                ft.TextButton("Ok", on_click=self.close_alert)]
            )
        self.app.page.dialog = dlg
        dlg.open = True
        await self.app.page.update_async()

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
            self.show_alert(tr('broken_game'), ex)
            print(f"[Game loading error] {ex}")
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
        print(f"Game is now: {self.app.game.target_exe}")
        await self.update_async()

    async def remove_game(self, item):
        if item.current:
            # if removing current, set dummy game as current
            self.app.game = GameCopy()
            self.app.settings_page.no_game_warning.height = None
            await self.app.settings_page.no_game_warning.update_async()
            self.app.config.current_game = ""

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
        print(f"Game is now: {self.app.game.target_exe}")
        print(f"Known games: {self.app.config.known_games}")

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

        self.tab_info = [self.main_info]

    async def toggle(self):
        self.expanded = not self.expanded
        self.container.current.height = 0 if not self.expanded else None
        await self.update_async()

    async def switch_tab(self, e):
        self.tab_index = e.data
        for index, widget in enumerate(self.tab_info):
            widget.current.visible = str(index) == self.tab_index
        await gather(*[widget.current.update_async() for widget in self.tab_info])

    async def did_mount_async(self):
        if self.mod.screenshots:
            self.tabs.current.tabs.append(Tab(text=tr("screenshots").capitalize()))
            self.tab_info.append(self.screenshots)
        if self.mod.change_log_content:
            self.tabs.current.tabs.append(Tab(text=tr("change_log").capitalize()))
            self.tab_info.append(self.change_log)
        if self.mod.other_info_content:
            self.tabs.current.tabs.append(Tab(text=tr("other_info").capitalize()))
            self.tab_info.append(self.other_info)

        if self.mod.screenshots:
            print(self.mod.screenshots[self.screenshot_index])
            self.screenshot_view.current.src = self.mod.screenshots[self.screenshot_index]["path"]
            self.screenshot_view.current.data = self.mod.screenshots[self.screenshot_index]
            self.screenshot_text.current.value = self.mod.screenshots[self.screenshot_index]["text"]
            self.screenshot_text.current.visible = bool(self.mod.screenshots[self.screenshot_index]["text"])
            await self.screenshot_view.current.update_async()
            await self.screenshot_text.current.update_async()

        if self.mod.is_known_lang(self.mod.language):
            main_lang_flag = get_internal_file_path(LangFlags[self.mod.language].value)
        else:
            main_lang_flag = get_internal_file_path(LangFlags.other.value)
        main_flag_btn = ft.IconButton(content=ft.Image(main_lang_flag, width=26),
                                      data=self.mod.language,
                                      on_click=self.change_lang)
        self.lang_list.current.controls.append(main_flag_btn)

        if self.mod.translations:
            for lang, known in self.mod.translations.items():
                if known:
                    flag = get_internal_file_path(LangFlags[lang].value)
                else:
                    flag = get_internal_file_path(LangFlags.other.value)
                flag_btn = ft.IconButton(content=ft.Image(flag, width=26),
                                         data=lang,
                                         on_click=self.change_lang)
                self.lang_list.current.controls.append(flag_btn)

    async def previous_screen(self, e):
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

    async def next_screen(self, e):
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
            print("Compare screen")

    async def launch_url(self, e):
        await self.app.page.launch_url_async(e.data)

    async def open_home_url(self, e):
        await self.app.page.launch_url_async(self.mod.url)

    async def change_lang(self, e):
        # TODO: All of this is bullshit and doesn't take into account that translations can have different
        # sets of screenshots and info views. Need to fully rebuild widgets on lang change ideally.
        # Or say to users not to make completely different translation manifests
        self.mod = self.main_mod.translations_loaded[e.control.data]
        await self.mod_item.change_lang(e)
        self.mod_description_text.current.value = self.mod.description
        await self.mod_description_text.current.update_async()
        if self.mod.screenshots:
            self.screenshot_text.current.value = self.mod.screenshots[self.screenshot_index]["text"]
            self.screenshot_text.current.visible = bool(self.mod.screenshots[self.screenshot_index]["text"])
            self.screenshot_view.current.src = self.mod.screenshots[self.screenshot_index]["path"]
            self.screenshot_view.current.data = self.mod.screenshots[self.screenshot_index]
            await self.screenshot_text.current.update_async()
            await self.screenshot_view.current.update_async()
        if self.mod.change_log:
            self.change_log_text.current.value = self.mod.change_log_content
            await self.change_log_text.current.update_async()
        if self.mod.other_info_content:
            self.other_info_text.current.value = self.mod.other_info_content
            await self.other_info_text.current.update_async()

    def build(self):
        return ft.Container(
            ft.Container(
                content=Column([
                    Tabs(
                        selected_index=self.tab_index,
                        animate_size=ft.animation.Animation(500, ft.AnimationCurve.DECELERATE),
                        height=40, on_change=self.switch_tab,
                        ref=self.tabs,
                        tabs=[Tab(text=tr("main_info").capitalize())]),
                    Column([ft.Container(
                                ft.ResponsiveRow([
                                    Column([
                                        Row([
                                            Icon(ft.icons.WARNING_OUTLINED,
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
                                             visible=bool(self.mod.prevalidated_err)),
                                        Text(self.mod.description, color=ft.colors.ON_SURFACE,
                                             ref=self.mod_description_text),
                                        ], col=9),
                                    Column([
                                        Row([
                                            ft.Container(Text(f'{tr("language").capitalize()}:'),
                                                         padding=ft.padding.only(left=10))
                                            ], ref=self.lang_list, spacing=2),
                                        ft.TextButton(tr("mod_url").replace(":", ""),
                                                      icon=ft.icons.HOME_ROUNDED,
                                                      icon_color=ft.colors.TERTIARY,
                                                      on_click=self.open_home_url,
                                                      tooltip=f'{tr("warn_external_address")}\n'
                                                              f'{self.mod.url}')
                                        ],
                                        col=3, alignment=ft.MainAxisAlignment.START,
                                        horizontal_alignment=ft.CrossAxisAlignment.START)
                                     ],
                                     vertical_alignment=ft.CrossAxisAlignment.START,
                                     spacing=0),
                                ref=self.main_info,
                                padding=ft.padding.only(bottom=15),
                                visible=self.tab_index == 0),
                            ft.Container(
                                Column([
                                    ft.ResponsiveRow([
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
                                        ], alignment=ft.MainAxisAlignment.CENTER),
                                    Text("Placeholder", ref=self.screenshot_text)
                                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                ref=self.screenshots,
                                visible=False,
                                padding=ft.padding.only(bottom=15)),
                            ft.Container(
                                ft.Column([ft.Markdown(self.mod.change_log_content,
                                                       ref=self.change_log_text,
                                                       extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                                                       on_tap_link=self.launch_url)],
                                          scroll=ft.ScrollMode.ADAPTIVE),
                                ref=self.change_log,
                                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                                height=300,
                                visible=False,
                                padding=ft.padding.only(bottom=15)),
                            ft.Container(
                                ft.Column([ft.Markdown(self.mod.other_info_content,
                                                       ref=self.other_info_text,
                                                       extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                                                       on_tap_link=self.launch_url)],
                                          scroll=ft.ScrollMode.AUTO),
                                ref=self.other_info,
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
        self.mod = mod

        self.info_container = ft.Ref[ModInfo]()
        self.mod_name_text = ft.Ref[Text]()
        self.author_text = ft.Ref[Text]()
        self.mod_logo_img = ft.Ref[Image]()

    async def install_mod(self, e):
        self.app.logger.debug("Pressed install mod")

    async def toggle_info(self, e):
        self.app.logger.debug("Pressed toggle info")
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
                              gapless_playback=True,
                              col={"sm": 4, "xl": 3}, border_radius=5),
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
                            col={"sm": 6, "xl": 8}),
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
                                              on_click=self.toggle_info)
                            ], col={"sm": 3, "xl": 2}, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                        ], spacing=15, columns=13),
                    ModInfo(self.app, self.mod, self, ref=self.info_container)
                ], spacing=0, scroll=ft.ScrollMode.HIDDEN),
                margin=15),
            margin=ft.margin.symmetric(vertical=1), elevation=3,
            )
            # on_secondary_tap=self.on_right_click
        # )

    # async def on_right_click(self, e):
    #     self.app.logger.debug("Right click on mod")
        # if not self.app.page.overlay:
        #     pb = ft.Container(Column(
        #         controls=[
        #             ft.TextButton("SomeText")
        #         ]),
        #         bgcolor=ft.colors.BACKGROUND, height=30,
        #         border=ft.border.all(2, ft.colors.SECONDARY))
        #     self.app.page.overlay.append(pb)
        #     await self.app.page.update_async()
        # await self.app.page.update_async()


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
        if self.app.session.mods:
            self.mods_list_view.current.controls.remove(self.no_mods_warning.current)
        for path, mod in self.app.session.mods.items():
            mod_identifier = f'{mod.name}{mod.version}{mod.build}'
            if mod_identifier not in self.tracked_mods:
                self.mods_list_view.current.controls.append(ModItem(self.app, mod))

    def build(self):
        return ft.Container(
            Column([
                Row([Text(tr("local_mods").capitalize(),
                          style=ft.TextThemeStyle.TITLE_MEDIUM)],
                    alignment=ft.MainAxisAlignment.CENTER),
                ft.Column([ft.Container(ft.ListView(
                    [Text(tr("no_local_mods_found").capitalize(), ref=self.no_mods_warning)],
                    spacing=10, padding=0,
                    ref=self.mods_list_view), padding=ft.padding.only(right=22))],
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
                print(f'bad response {response["api_response"]["status_code"]}')
        else:
            print("Unable to get url content for news")
            self.offline = True

    async def launch_url(self, e):
        await self.app.page.launch_url_async(e.data)

    async def launch_game(self, e):
        current_time = datetime.now()
        if self.app.current_game_process is None:
            print(f"Launching: {self.app.game.target_exe}")
            # TODO: only should be possible to get there if the game is not already running
            self.app.current_game_process = await create_subprocess_exec(self.app.game.target_exe,
                                                                         '-console' if self.game_console_switch.current.value else "",
                                                                         cwd=self.app.game.game_root_path)
            self.app.game_launch_time = datetime.now()
            # TODO: change the button prompt to "stop game" when it's already running
        else:
            # will this be 1 if we crash the game?
            if self.app.current_game_process.returncode == 1:
                # game exited
                self.app.current_game_process = None
            elif (current_time - self.app.game_launch_time).seconds < 1:
                # do not try to relaunch game immediately
                pass
            elif self.app.current_game_process.returncode is None:
                # stopping game on a next step, needs to be explained with a changing
                # button prompt
                self.app.current_game_process.terminate()
                self.app.current_game_process = None

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
                            Text(tr("launch_params").upper(),
                                 weight=ft.FontWeight.W_700),
                            Row([ft.Switch(value=False, scale=0.7),
                                 Text(tr("enable_console").capitalize(),
                                 ref=self.game_console_switch,
                                 weight=ft.FontWeight.W_500)],
                                spacing=0),
                            ft.FloatingActionButton(
                                content=ft.Row([
                                    ft.Text(tr("play").capitalize(), size=20,
                                            weight=ft.FontWeight.W_700, color=ft.colors.ON_PRIMARY)],
                                    alignment="center", spacing=5
                                ),
                                shape=ft.RoundedRectangleBorder(radius=5),
                                bgcolor="#FFA500",
                                on_click=self.launch_game,
                                aspect_ratio=2.5,
                            )])
                        ],
                        col={"sm": 4, "xl": 3}, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
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
                        scroll=ft.ScrollMode.ADAPTIVE), col={"sm": 8, "xl": 9})
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

    def proccess_game_and_distro_setup(app):
        load_mods(app)

    def load_mods(app):
        try:
            app.logger.info("Prevalidating Community Patch and Remaster state")
            app.context.validate_remaster()
            remaster_mod = Mod(app.context.remaster_config, app.context.remaster_path)
            # TODO: maybe check if remaster translation manifest is corrupted
            remaster_mod.load_translations(load_gui_info=True)
            remaster_mod.load_gui_info()

            app.session.mods[app.context.remaster_path] = remaster_mod
            commod_compatible, commod_compat_err = \
                remaster_mod.compatible_with_mod_manager(app.context.commod_version)
            compat_info = {
                "compatible_with_commod": commod_compatible,
                "compatible_with_commod_err": commod_compat_err}
            remaster_mod.load_session_compatibility(compat_info)
            manifest = app.context.remaster_config
            # TODO: understand if this id really needed and if it's working as intended (prevents dumplication)
            mod_identifier = f'{manifest["name"]}{manifest["version"]}{manifest["build"]}'
            app.session.tracked_mods.add(app.context.remaster_path)
        except CorruptedRemasterFiles as er:
            app.logger.error(er)
            app.context.remaster_path = None
            app.remaster_config = {}

        if not app.context.validated_mod_configs:
            try:
                app.context.load_mods()
            except ModsDirMissing:
                app.logger.info("No mods folder found, creating")
            except NoModsFound:
                app.logger.info("No mods found")

        if app.context.validated_mod_configs:
            for manifest_path, manifest in app.context.validated_mod_configs.items():
                mod_identifier = f'{manifest["name"]}{manifest["version"]}{manifest["build"]}'
                if mod_identifier not in app.session.tracked_mods:
                    mod = Mod(manifest, Path(manifest_path).parent)

                    try:
                        mod.load_translations(load_gui_info=True)
                    except Exception as ex:
                        app.logger.error(ex)
                        continue

                    mod.load_gui_info()

                    compatible_with_commod, commod_compat_error = \
                        mod.compatible_with_mod_manager(app.context.commod_version)

                    prevalidated, prevalid_errors = mod.check_requirements(app.game.installed_content,
                                                                           app.game.installed_descriptions)
                    compatible, incompatible_errors = mod.check_incompatibles(app.game.installed_content,
                                                                              app.game.installed_descriptions)
                    compat_info = {
                        "compatible_with_commod": compatible_with_commod,
                        "compatible_with_commod_err": commod_compat_error,
                        "prevalidated": prevalidated,
                        "prevalidated_err": prevalid_errors,
                        "compatible": compatible,
                        "compatible_err": incompatible_errors}
                    mod.load_session_compatibility(compat_info)
                    app.session.mods[manifest_path] = mod
                    app.session.tracked_mods.add(mod_identifier)

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
        print("closing")
        app.config.save_config()
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
    temp_config = InstallationContext.get_config()
    if temp_config is not None:
        if Config.sanitize_config(temp_config):
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

    print(f"Current lang: {localisation.LANG=}")

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
            print(f"[Game loading error] {ex}")

    if distribution_dir:
        try:
            app.context.add_distribution_dir(distribution_dir)
        except Exception as ex:
            # TODO: Handle exceptions properly
            print(f"[Distro loading error] {ex}")

    need_quick_start = (not app.config.game_names
                        and app.context.distribution_dir is None
                        and app.game.game_root_path is None
                        and not options.skip_wizard)

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
        ft.Container(ft.Row([
                             rail,
                            #  ft.VerticalDivider(width=1),
                             app.content_column,
                             ]),
                     expand=True,
                     padding=ft.padding.only(left=10, right=10, bottom=10)
                     )
    )

    app.context.current_session.load_steam_game_paths()
    if need_quick_start:
        print("showing quick start")
        await app.show_guick_start_wizard()
    else:
        proccess_game_and_distro_setup(app)
        await app.change_page(index=app.config.current_section)

    await page.update_async()


def start():
    ft.app(target=main)
