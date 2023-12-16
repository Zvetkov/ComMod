import asyncio
import os
import subprocess
from asyncio import create_subprocess_exec, create_task, gather
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
import platform
import sys, traceback

import aiofiles.os
import aioshutil
import flet as ft
from asyncio_requests.asyncio_request import request
from flet import (Column, FloatingActionButton, Icon, IconButton, Image, Row,
                  Tab, Tabs, Text, TextField, UserControl, colors, icons)

import localisation.service as localisation
from game.data import DATE, OWN_VERSION, is_known_lang
from game.environment import (DistroStatus, GameCopy, GameStatus,
                              InstallationContext)
from game.mod import GameInstallments, Mod
from helpers import file_ops
from helpers.errors import (DXRenderDllNotFound, ExeIsRunning,
                            HasManifestButUnpatched, InvalidExistingManifest,
                            ModsDirMissing, NoModsFound,
                            PatchedButDoesntHaveManifest)
from helpers.file_ops import (extract_from_to, get_internal_file_path,
                              get_proc_by_names, load_yaml, process_markdown)
from localisation.service import (COMPATCH_GITHUB, DEM_DISCORD,
                                  DEM_DISCORD_MODS_DOWNLOAD_SCREEN,
                                  WIKI_COMPATCH, LangFlags, SupportedLanguages,
                                  tr)

from .common_widgets import ExpandableContainer
from .config import AppSections, Config


# TODO: separate to different submodules for different app screens

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

    async def refresh_page(self, index=None):
        if index is not None:
            if index != self.rail.selected_index:
                print("Not on the target page, skipping refresh")
                return
        content = self.content_column.content
        if not content.refreshing:
            content.refreshing = True
            self.content_column.content = None
            await self.content_column.update_async()
            self.content_column.content = content
            await self.content_column.update_async()
            await self.content_column.content.update_async()
            content.refreshing = False

    async def upd_pressed(self, e):
        await self.refresh_page(self.config.current_section)

    async def change_page(self, e=None, index: int | AppSections = AppSections.LAUNCH):
        if e is None:
            new_index = index
        else:
            new_index = e.control.selected_index

        if self.content_column.content:
            real_index = self.config.current_section
        else:
            real_index = -1

        if new_index == AppSections.DOWNLOAD_MODS.value:
            self.page.floating_action_button.visible = False
        else:
            self.page.floating_action_button.visible = True
        await self.page.update_async()

        if new_index != real_index:
            self.rail.selected_index = new_index
            self.content_column.content = self.content_pages[new_index]
            await self.content_column.update_async()
            await self.content_pages[new_index].update_async()
            self.config.current_section = new_index
        await self.rail.update_async()

    async def show_settings(self, e=None):
        await self.change_page(index=AppSections.SETTINGS.value)
        await self.content_column.update_async()

    async def close_alert(self, e=None):
        self.page.dialog.open = False
        await self.page.update_async()

    async def show_modal(self, text, additional_text="", title=None, on_yes=None, on_no=None):
        if self.page.dialog is not None:
            if self.page.dialog.open:
                return

        no_options = on_yes is None and on_no is None
        if title is None:
            title_text = tr("attention").capitalize()
        else:
            title_text = title

        dlg = ft.AlertDialog(
            title=Row([Icon(ft.icons.INFO_OUTLINE, color=ft.colors.PRIMARY),
                       Text(title_text, color=ft.colors.PRIMARY)]),
            shape=ft.buttons.RoundedRectangleBorder(radius=10),
            content=Column([Text(text),
                            Text(additional_text,
                                 visible=bool(additional_text))],
                           spacing=5,
                           tight=True),
            actions=[
                ft.TextButton("Ok", on_click=self.close_alert,
                              visible=no_options),
                ft.TextButton(tr("yes").capitalize(),
                              visible=not no_options,
                              on_click=on_yes if on_yes is not None else self.close_alert),
                ft.TextButton(tr("no").capitalize(),
                              visible=not no_options,
                              on_click=on_no if on_no is not None else self.close_alert)
                ],
            actions_padding=ft.padding.only(left=20, bottom=20, right=20)
            )
        self.page.dialog = dlg
        dlg.open = True
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

    async def show_loading(self, text, additional_text=""):
        if self.page.dialog is not None:
            if self.page.dialog.open:
                return

        loading_text = Text()
        dlg = ft.AlertDialog(
            open=True,
            modal=True,
            title=Row([Icon(ft.icons.HOURGLASS_BOTTOM_ROUNDED,
                            color=ft.colors.PRIMARY),
                       Text(tr("is_loading").capitalize())]),
            shape=ft.buttons.RoundedRectangleBorder(radius=10),
            content=Row([
                ft.ProgressRing(),
                Column([Text(text),
                        Text(additional_text,
                             visible=bool(additional_text),
                             color=ft.colors.ON_ERROR_CONTAINER),
                        loading_text
                        ],
                       spacing=5,
                       tight=True)]
            ))
        self.page.dialog = dlg
        dlg.open = True
        await self.page.update_async()
        return loading_text

    async def load_distro_async(self):
        self.logger.debug("-- Loading distro --")
        try:
            await self.context.load_mods_async()
            self.logger.debug("-- Loaded mods --")
        except ModsDirMissing:
            self.logger.info("-- No mods folder found, creating --")
        except NoModsFound:
            self.logger.info("-- No mods found --")

        self.game.load_installed_descriptions(self.context.validated_mod_configs)

        if self.context.validated_mod_configs:
            for manifest_path, manifest in self.context.validated_mod_configs.items():
                mod = Mod(manifest, Path(manifest_path).parent)

                if mod.id in self.session.tracked_mods:
                    if (self.session.tracked_mods_hashes[mod.id]
                       == self.context.hashed_mod_manifests[manifest_path]):
                        # self.logger.debug(f"{mod.id} already loaded to distro, skipping")
                        continue
                    else:
                        self.session.tracked_mods.remove(mod.id)
                        self.session.tracked_mods_hashes.pop(mod.id, None)
                        self.session.mods.pop(manifest_path, None)
                        self.logger.debug(f"{mod.id} was tracked but hash is different, removing from distro")
                try:
                    self.logger.debug(f"--- Loading {mod.id} to distro ---")
                    mod.load_translations(load_gui_info=True)
                    mod.load_commod_compatibility(self.context.commod_version)
                    mod.load_game_compatibility(self.game.installment)
                    mod.load_session_compatibility(self.game.installed_content,
                                                   self.game.installed_descriptions)
                    self.session.mods[manifest_path] = mod
                    self.session.tracked_mods.add(mod.id)
                    self.session.tracked_mods_hashes[mod.id] = \
                        self.context.hashed_mod_manifests[manifest_path]
                except Exception as ex:
                    self.logger.error(f'{ex!r}')
                    continue
        self.logger.debug("-- Loaded distro --")

        removed_mods = set(self.session.mods.keys()) - set(self.context.validated_mod_configs.keys())
        for mod_path in removed_mods:
            mod_id = self.session.mods[mod_path].id
            self.session.tracked_mods.remove(mod_id)
            self.session.tracked_mods_hashes.pop(mod_id, None)
            self.session.mods.pop(mod_path, None)
            self.logger.debug(f"Removed {mod_id} from session as it was deleted")


class GameCopyListItem(UserControl):
    def __init__(self, game_name, game_path,
                 game_installment, game_version,
                 warning, game_is_running, current,
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
        self.game_is_running = game_is_running

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
                            width=130,
                            bgcolor=ft.colors.BACKGROUND,
                            border=ft.border.all(2, ft.colors.SECONDARY_CONTAINER),
                            border_radius=16, padding=ft.padding.only(left=10, right=10, top=5, bottom=5))
                    ),
                    ft.Tooltip(
                        visible=bool(self.warning),
                        message=f"{self.warning} ",
                        wait_duration=300,
                        content=ft.Container(
                            Text(tr("dirty_copy") if not self.game_is_running else tr("game_is_running"),
                                 weight=ft.FontWeight.W_600,
                                 color=ft.colors.ON_ERROR_CONTAINER,
                                 text_align=ft.TextAlign.CENTER),
                            bgcolor=ft.colors.ERROR_CONTAINER,
                            border_radius=15, padding=ft.padding.only(left=10, right=10, top=5, bottom=5),
                            visible=bool(self.warning)),
                    )], spacing=5, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=ft.padding.symmetric(vertical=5)),
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
                                on_click=self.open_clicked)),
                        ft.Tooltip(
                            message=tr("remove_from_list"),
                            wait_duration=300,
                            content=IconButton(
                                icons.DELETE_OUTLINE,
                                on_click=self.delete_clicked)),
                        ft.Tooltip(
                            message=tr("edit_name"),
                            wait_duration=300,
                            content=IconButton(
                                icon=icons.CREATE_OUTLINED,
                                on_click=self.edit_clicked))
                        ], spacing=5
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

    async def make_current(self, e=None):
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
        self.refreshing = False

    async def change_app_lang(self, e):
        # TODO: hacky, probably need to replace
        localisation.LANG = e.data
        self.app.config.lang = e.data
        self.app.config.prefered_mod_lang = e.data
        await self.app.refresh_page(AppSections.SETTINGS.value)

    async def get_game_dir(self, e):
        await self.get_game_dir_dialog.get_directory_path_async(
            dialog_title=f'{tr("where_is_game")} ({tr("ask_to_choose_path")})'
        )

    async def get_distro_dir(self, e):
        await self.get_distro_dir_dialog.get_directory_path_async(
            dialog_title=f'{tr("where_is_distro")} ({tr("ask_to_choose_path")})'
        )

    def build(self):
        game_icon = Image(src=get_internal_file_path("assets/icons/hta_comrem.png"),
                          width=24,
                          height=24,
                          fit=ft.ImageFit.FIT_HEIGHT)

        dem_icon = Image(src=get_internal_file_path("assets/icons/dem_logo.svg"),
                         width=24,
                         height=24,
                         fit=ft.ImageFit.FIT_HEIGHT)

        steam_icon = Image(src=get_internal_file_path("assets/icons/steampowered.svg"),
                           width=24,
                           height=24,
                           fit=ft.ImageFit.FIT_HEIGHT)

        self.get_game_dir_dialog = ft.FilePicker(on_result=self.get_game_dir_result)
        self.get_distro_dir_dialog = ft.FilePicker(on_result=self.get_distro_dir_result)

        self.no_game_warning = ft.ResponsiveRow([
            ft.Container(
                Row([Icon(ft.icons.INFO_OUTLINE_ROUNDED, color=ft.colors.ON_TERTIARY_CONTAINER,
                          expand=1),
                     Text(value=tr("commod_needs_game"),
                          weight=ft.FontWeight.BOLD,
                          no_wrap=False,
                          color=ft.colors.ON_TERTIARY_CONTAINER,
                          expand=15)]),
                bgcolor=ft.colors.TERTIARY_CONTAINER, padding=10, border_radius=10,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                col={"xs": 12, "lg": 10, "xxl": 8},
                margin=ft.margin.only(right=20, bottom=15))
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            animate_size=ft.animation.Animation(500, ft.AnimationCurve.DECELERATE),
            visible=bool(not self.app.config.current_game),
            )

        self.no_distro_warning = ft.ResponsiveRow([
            ft.Container(
                Row([Icon(ft.icons.INFO_OUTLINE_ROUNDED, color=ft.colors.ON_TERTIARY_CONTAINER,
                          expand=1),
                     Text(value=tr("commod_needs_distro").replace("\n", " "),
                          weight=ft.FontWeight.BOLD,
                          no_wrap=False,
                          color=ft.colors.ON_TERTIARY_CONTAINER,
                          expand=15)]),
                bgcolor=ft.colors.TERTIARY_CONTAINER, padding=10, border_radius=10,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                col={"xs": 12, "lg": 10, "xxl": 8},
                margin=ft.margin.only(right=20, bottom=15))
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            animate_size=ft.animation.Animation(500, ft.AnimationCurve.DECELERATE),
            visible=bool(not self.app.config.current_distro),
            )

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
            on_click=self.get_game_dir,
            mini=True, height=40, width=135,
            )

        self.open_distro_button = FloatingActionButton(
            tr("choose_path").capitalize(),
            icon=icons.FOLDER_OPEN,
            on_click=self.get_distro_dir,
            mini=True, height=40, width=135,
            )

        self.game_copy_warning_text = ft.Ref[Text]()
        self.steam_game_copy_warning_text = ft.Ref[Text]()
        self.distro_warning_text = ft.Ref[Text]()

        self.game_copy_warning = ft.Container(
            Row([Icon(ft.icons.WARNING, color=ft.colors.ON_ERROR_CONTAINER),
                 Text(value="placeholder",
                      color=ft.colors.ON_ERROR_CONTAINER,
                      weight=ft.FontWeight.W_500,
                      overflow=ft.TextOverflow.ELLIPSIS,
                      ref=self.game_copy_warning_text,
                      expand=True)]),
            bgcolor=ft.colors.ERROR_CONTAINER, padding=10, border_radius=10, visible=False)

        self.steam_game_copy_warning = ft.Container(
            Row([Icon(ft.icons.WARNING, color=ft.colors.ON_ERROR_CONTAINER),
                 Text(value="placeholder",
                      color=ft.colors.ON_ERROR_CONTAINER,
                      weight=ft.FontWeight.W_500,
                      overflow=ft.TextOverflow.ELLIPSIS,
                      ref=self.steam_game_copy_warning_text,
                      expand=True)]),
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

        self.no_games_for_filter_warning = ft.Ref[ft.Container]()
        self.filter = Tabs(
            height=35,
            selected_index=self.app.config.current_game_filter,
            on_change=self.tabs_changed,
            animate_size=ft.animation.Animation(500, ft.AnimationCurve.DECELERATE),
            tabs=[Tab(text=tr("all_versions").capitalize()),
                  Tab(text="Ex Machina"),
                  Tab(text="M113"),
                  Tab(text="Arcade")])

        self.view_list_of_games = Column(
            height=None if bool(self.app.config.known_games) else 0,
            controls=[
                self.filter,
                ft.Container(
                    Text(tr("not_yet_added_games_of_type"),
                         weight=ft.FontWeight.BOLD,
                         color=ft.colors.OUTLINE),
                    margin=ft.margin.symmetric(horizontal=15, vertical=5),
                    ref=self.no_games_for_filter_warning,
                    visible=not bool(self.app.config.known_games)),
                self.list_of_games
                ], col={"xs": 12, "lg": 10, "xxl": 8})

        if self.app.config.game_names:
            for game_path in self.app.config.game_names:
                can_be_added, warning, game_info, game_is_running = self.check_compatible_game(game_path)
                if can_be_added:
                    is_current = game_path == self.app.config.current_game
                    installment = game_info.installment
                    exe_version = game_info.exe_version
                else:
                    is_current = False
                    installment = GameInstallments.UNKNOWN
                    exe_version = "Unknown"
                    if warning == "ExeIsRunning":
                        warning = f"{tr('game_is_running_cant_select')}"
                    else:
                        warning = f"{tr('broken_game')}\n\n{warning}"
                visible = not self.is_installment_filtered(installment)
                game_item = GameCopyListItem(self.app.config.game_names[game_path],
                                             game_path,
                                             installment,
                                             exe_version,
                                             warning, game_is_running,
                                             is_current,
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

        langs = SupportedLanguages.list_values()

        self.language_select = ft.Container(
                Row([
                    ft.Dropdown(
                        height=42,
                        text_size=13,
                        width=200,
                        dense=True,
                        # border_color=ft.colors.SECONDARY_CONTAINER,
                        border_width=2,
                        border_radius=5,
                        on_change=self.change_app_lang,
                        label=tr("app_lang").capitalize(),
                        value=self.app.config.lang,
                        prefix_icon=ft.icons.LANGUAGE_ROUNDED,
                        label_style=ft.TextStyle(size=13, weight=ft.FontWeight.BOLD),
                        text_style=ft.TextStyle(size=13, weight=ft.FontWeight.BOLD),
                        hint_style=ft.TextStyle(size=13, weight=ft.FontWeight.BOLD),
                        options=[
                            ft.dropdown.Option(key=lang, text=tr(lang).capitalize()) for lang in langs
                            ]),
                    Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                         opacity=0.7,
                         color=ft.colors.TERTIARY),
                    Text(tr("restart_to_change_lang"),
                         color=ft.colors.TERTIARY,
                         opacity=0.7,
                         no_wrap=False)
                    ]), col={"xs": 12, "lg": 10, "xxl": 8})

        self.about = ft.Card(
            ft.Container(
                Row([
                    Column([
                        Image(src=get_internal_file_path("assets/icons/dem_logo.svg"),
                              fit=ft.ImageFit.CONTAIN),
                        ft.Text(f'{(tr("version").capitalize())} {OWN_VERSION}\n{DATE}',
                                size=10, weight=ft.FontWeight.W_300, text_align=ft.TextAlign.CENTER),
                              ],
                           spacing=5,
                           alignment=ft.MainAxisAlignment.CENTER,
                           horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    Column([
                        ft.Text(f'{tr("developers").capitalize()} DEM Community Mod Manager',
                                weight=ft.FontWeight.BOLD, size=12,
                                color=ft.colors.PRIMARY),
                        ft.Text('Aleksandr "Seel" Parfenenkov', size=12),
                        ft.Text(f'Aleksandr "ThePlain" Fateev ({tr("binary_fixes")})', size=12),
                        ft.Markdown(f"[{tr('our_github')}]"
                                    f"({COMPATCH_GITHUB})  • "
                                    f"[{tr('our_discord')}]"
                                    f"({DEM_DISCORD})  • "
                                    f"[DeusWiki]({WIKI_COMPATCH})",
                                    extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                                    auto_follow_links=True,
                                    scale=0.9),
                            ],
                           alignment=ft.MainAxisAlignment.CENTER,
                           horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                ], spacing=25, alignment=ft.MainAxisAlignment.CENTER),
                padding=ft.padding.only(left=35, right=75, top=15, bottom=15),
                clip_behavior=ft.ClipBehavior.HARD_EDGE),
            elevation=5,
            margin=ft.margin.only(right=20, bottom=15),
            # col={"xs": 8, "xl": 7, "xxl": 6},
        )

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
                self.no_game_warning,
                self.no_distro_warning,
                ft.Container(ft.ResponsiveRow(controls=[
                    Row([
                        Icon(ft.icons.VIDEOGAME_ASSET_ROUNDED, color=ft.colors.ON_BACKGROUND),
                        Text(value=tr("control_game_copies").upper(),
                             style=ft.TextThemeStyle.TITLE_SMALL)
                        ], col={"xs": 12, "lg": 10, "xxl": 8}),
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
                        col={"xs": 12, "lg": 10, "xxl": 7},
                        visible=bool(self.app.session.steam_game_paths)
                        )
                    ], alignment=ft.MainAxisAlignment.CENTER), border_radius=10, padding=15,
                    margin=ft.margin.only(right=20, bottom=15),
                    border=ft.border.all(1, ft.colors.SURFACE_VARIANT)),
                ft.Container(ft.ResponsiveRow(
                    # contols of distro/comrem/mods folders
                    controls=[
                        Row([
                            ft.Icon(ft.icons.CREATE_NEW_FOLDER, color=ft.colors.ON_BACKGROUND),
                            Text(value=tr("control_mod_folders").upper(), style=ft.TextThemeStyle.TITLE_SMALL)
                             ], col={"xs": 12, "lg": 10, "xxl": 8}),
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
                                 ), border_radius=10, padding=15,
                                 margin=ft.margin.only(right=20, bottom=15),
                    border=ft.border.all(1, ft.colors.SURFACE_VARIANT)),
                ft.Container(
                    ft.ResponsiveRow(
                        # contols of distro/comrem/mods folders
                        controls=[
                            Row([
                                ft.Icon(ft.icons.SETTINGS, color=ft.colors.ON_BACKGROUND),
                                Text(value=tr("other_settings").upper(), style=ft.TextThemeStyle.TITLE_SMALL)
                                 ], col={"xs": 12, "lg": 10, "xxl": 8}),
                            self.language_select,
                            ], alignment=ft.MainAxisAlignment.CENTER, run_spacing=15
                    ), border_radius=10, padding=15, margin=ft.margin.only(right=20, bottom=15),
                    border=ft.border.all(1, ft.colors.SURFACE_VARIANT)),
                ft.Row([self.about], alignment=ft.MainAxisAlignment.CENTER)
            ], spacing=0,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            scroll=ft.ScrollMode.ADAPTIVE,
            alignment=ft.MainAxisAlignment.START
        ), margin=ft.margin.only(right=3))

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
        self.app.logger.debug(f"New path get from steam dropdown: '{new_path}'")
        await self.add_game_to_list(new_path, from_steam=True)

        self.steam_locations_dropdown.value = ""
        await self.update_async()

    async def add_game_manual(self, e):
        new_path = self.game_location_field.value
        self.app.logger.debug(f"New path get from game location field: '{new_path}'")
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
        # TODO: sort out the duplicating functions of context, session and config
        # TODO: exception handling for add_distribution_dir,
        # check that overwriting distro is working correctly
        loaded_steam_game_paths = self.app.context.current_session.steam_game_paths
        self.app.context = InstallationContext(self.app.config.current_distro,
                                               self.app.context.dev_mode)

        self.app.context.setup_logging_folder()
        self.app.context.setup_loggers()
        self.app.logger = self.app.context.logger
        self.app.context.load_system_info()
        self.app.session = self.app.context.current_session
        self.app.session.steam_game_paths = loaded_steam_game_paths
        if self.app.config.current_game:
            # self.app.load_distro()
            await self.app.load_distro_async()
        else:
            self.app.logger.debug("No current game found in config")

    async def handle_dropdown_onchange(self, e):
        if e.data:
            await self.check_game_fields(e)
            await self.expand_adding_game_steam()
        await self.update_async()

    def check_compatible_game(self, game_path):
        can_be_added = True
        warning = ''
        test_game = GameCopy()
        game_is_running = False
        try:
            test_game.process_game_install(game_path)
        except PatchedButDoesntHaveManifest as ex:
            warning += (f"{tr('install_leftovers')}\n\n" +
                        f"{tr('error')}: Executable is patched (version: {ex.exe_version}), "
                        "but install manifest is missing")
        except HasManifestButUnpatched as ex:
            warning = (f"{tr('install_leftovers')}\n\n" +
                       f"{tr('error')}: Found existing compatch manifest, but exe version is unexpected: " +
                       f"{ex.exe_version}")
        except InvalidExistingManifest:
            can_be_added = False
            warning = tr("invalid_existing_manifest")
        except ExeIsRunning:
            can_be_added = False
            warning = "ExeIsRunning"
            game_is_running = True
        except Exception as ex:
            can_be_added = False
            warning = f"{tr('error')}: {ex} ({ex!r}): '{game_path}'"
        if warning:
            if can_be_added:
                self.app.logger.warning(warning)
            else:
                self.app.logger.error(warning)
        return can_be_added, warning, test_game, game_is_running

    async def add_game_to_list(self, game_path, game_name="", is_current=True, from_steam=False):
        if game_name:
            set_game_name = game_name
        else:
            set_game_name = Path(game_path).parts[-1]

        self.app.logger.debug("Starting checking game compatibility")
        can_be_added, warning, game_info, game_is_running = self.check_compatible_game(game_path)

        self.app.logger.debug(f"Finished. Can be added: {can_be_added}")
        if can_be_added:
            self.view_list_of_games.height = None
            # self.filter.height = None
            self.no_games_for_filter_warning.current.visible = False
            self.list_of_games.height = None
            await self.view_list_of_games.update_async()
            await self.filter.update_async()
            # deselect all other games if any exist
            await gather(*[control.display_as_reserve() for control in self.list_of_games.controls])

            visible = not self.is_installment_filtered(game_info.installment)
            new_game = GameCopyListItem(set_game_name,
                                        game_path,
                                        game_info.installment,
                                        game_info.exe_version,
                                        warning, game_is_running,
                                        is_current,
                                        self.select_game,
                                        self.remove_game,
                                        self.app.config, visible)
            self.list_of_games.controls.append(new_game)
            await self.list_of_games.update_async()
            await self.select_game(new_game)

            await self.minimize_adding_game_manual()
            await self.minimize_adding_game_steam()

            self.app.config.known_games.add(game_path.lower())
            self.app.config.game_names[game_path] = set_game_name
            self.filter.selected_index = 0
            for control in self.list_of_games.controls:
                control.visible = True
            self.no_game_warning.height = 0
            await self.no_game_warning.update_async()

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
            new_game = GameCopy()
            new_game.process_game_install(item.game_path)
        except PatchedButDoesntHaveManifest:
            pass
        except HasManifestButUnpatched:
            pass
        except ExeIsRunning:
            await self.app.show_alert(tr("game_is_running_cant_select"))
            return
        except Exception as ex:
            # TODO: Handle exceptions properly
            await self.app.show_alert(tr("broken_game"), ex)
            self.app.logger.error(f"[Game loading error] {ex}")
            return

        self.app.game = new_game

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
            # self.app.context.validated_mod_configs.clear()
            loaded_steam_game_paths = self.app.context.current_session.steam_game_paths
            self.app.context.current_session = InstallationContext.Session()
            self.app.session = self.app.context.current_session
            # TODO: maybe do a full steam path reload?
            # or maybe also copy steam_parsing_error
            self.app.session.steam_game_paths = loaded_steam_game_paths
            # self.app.load_distro()
            await self.app.load_distro_async()
        else:
            self.app.logger.debug("No distro dir found in context")

    async def remove_game(self, item):
        if item.current:
            # if removing current, set dummy game as current
            self.app.game = GameCopy()
            self.app.settings_page.no_game_warning.height = None
            self.app.settings_page.no_game_warning.visible = True
            await self.app.settings_page.no_game_warning.update_async()
            self.app.config.current_game = ""

            if self.app.context.distribution_dir:
                # self.app.context.validated_mod_configs.clear()
                loaded_steam_game_paths = self.app.context.current_session.steam_game_paths
                self.app.context.current_session = InstallationContext.Session()
                self.app.session = self.app.context.current_session
                # TODO: maybe do a full steam path reload?
                # or maybe also copy steam_parsing_error
                self.app.session.steam_game_paths = loaded_steam_game_paths
                # self.app.load_distro()
                await self.app.load_distro_async()
            else:
                self.app.logger.debug("No distro dir found in context")

        self.list_of_games.controls.remove(item)
        await self.list_of_games.update_async()

        # hide list if there are zero games tracked
        if not self.list_of_games.controls:
            self.view_list_of_games.height = 0
            # self.filter.height = 0
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
        try:
            status = GameStatus.GENERAL_ERROR
            additional_info = ""

            if os.path.exists(game_path):
                if game_path.lower() not in self.app.config.known_games:
                    validated, additional_info = GameCopy.validate_game_dir(game_path)
                    if validated:
                        self.app.logger.debug(f"Getting exe name for path: {game_path}")
                        exe_name = GameCopy.get_exe_name(game_path)
                        self.app.logger.debug(f"Getting exe version for exe path: {exe_name}")
                        exe_version = GameCopy.get_exe_version(exe_name)
                        if exe_version is not None:
                            self.app.logger.debug(f"Checking compatibility for exe version: {exe_version}")
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
        except Exception as ex:
            return GameStatus.GENERAL_ERROR, f"{tr('error')}: {ex!r} {ex}"

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
            status, additional_info = GameStatus.COMPATIBLE, ""

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
        # if status is None:
        #     status = GameStatus.COMPATIBLE
        self.game_copy_warning.visible = status is not GameStatus.COMPATIBLE
        if self.game_copy_warning.visible:
            full_text = tr(GameStatus(status).value)
            if additional_info:
                full_text += f": {additional_info}"
            self.game_copy_warning_text.current.value = full_text
        await self.game_copy_warning.update_async()
        await self.update_async()

    async def switch_steam_game_copy_warning(self,
                                             status: GameStatus = GameStatus.COMPATIBLE,
                                             additional_info: str = ""):
        # if status is None:
        #     status = GameStatus.COMPATIBLE
        self.steam_game_copy_warning.visible = status is not GameStatus.COMPATIBLE
        if self.steam_game_copy_warning.visible:
            full_text = tr(GameStatus(status).value)
            if additional_info:
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
        filter = "all"
        match int(e.data):
            case GameInstallments.ALL.value:
                filter = "all"
            case GameInstallments.EXMACHINA.value:
                filter = "exmachina"
            case GameInstallments.M113.value:
                filter = "m113"
            case GameInstallments.ARCADE.value:
                filter = "arcade"
        for control in self.list_of_games.controls:
            if filter == "all":
                control.visible = True
            else:
                if control.installment == filter:
                    control.visible = True
                else:
                    control.visible = False
            await control.update_async()
        if all([not control.visible for control in self.list_of_games.controls]):
            self.no_games_for_filter_warning.current.visible = True
        else:
            self.no_games_for_filter_warning.current.visible = False
        await self.no_games_for_filter_warning.current.update_async()

        self.app.config.current_game_filter = int(e.data)
        await self.update_async()

    def is_installment_filtered(self, installment):
        match self.filter.selected_index:
            case GameInstallments.ALL.value:
                return False
            case GameInstallments.EXMACHINA.value:
                return installment != "exmachina"
            case GameInstallments.M113.value:
                return installment != "m113"
            case GameInstallments.ARCADE.value:
                return installment != "arcade"


class ModInfo(UserControl):
    def __init__(self, app: App, mod: Mod, mod_item, **kwargs):
        super().__init__(self, **kwargs)
        self.app = app
        self.main_mod = mod
        self.mod = mod
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
        self.mod_delete_btn = ft.Ref[ft.TextButton]()
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

                icon = Image(flag, width=26)
                icon.tooltip = mod.lang_label.capitalize()

                if not mod.can_install:
                    icon.opacity = 0.5
                    icon.tooltip += f' ({tr("cant_be_installed")})'

                flag_btn = ft.IconButton(
                    content=icon,
                    data=lang,
                    on_click=self.mod_item.change_lang)

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

    # async def launch_url(self, e):
        # await self.app.page.launch_url_async(e.data)

    async def open_home_url(self, e):
        await self.app.page.launch_url_async(self.mod.url)

    async def open_trailer_url(self, e):
        await self.app.page.launch_url_async(self.mod.trailer_url)

    async def delete_mod_ask(self, e):
        await self.app.show_modal(tr("this_will_delete_mod").capitalize()+".",
                                  tr("ask_confirm_deletion").capitalize(),
                                  on_yes=self.delete_mod_runner)

    async def delete_mod_runner(self, e):
        await self.app.close_alert(e)
        await self.app.local_mods.delete_mod(self.main_mod)

    async def update_info(self):
        self.mod = self.mod_item.mod
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

    async def set_mod_info_column(self):
        self.mod_info_column.current.controls = [
            Text(self.mod.description, color=ft.colors.ON_SURFACE,
                 ref=self.mod_description_text),
            ft.Divider(visible=self.mod.name != "community_remaster"
                       or not self.mod.can_install or self.mod.is_reinstall),
            Column(controls=self.get_pretty_compatibility(),
                   visible=self.mod.name != "community_remaster"
                   or not self.mod.can_install or self.mod.is_reinstall),
            ft.Divider(
                visible=(not (self.mod.commod_compatible
                              and self.mod.compatible
                              and self.mod.prevalidated)
                         and self.mod.installment_compatible)),
            Row([
                Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                     color=ft.colors.ERROR),
                Text(tr("cant_be_installed"),
                     weight=ft.FontWeight.BOLD,
                     color=ft.colors.ERROR)],
                visible=(not (self.mod.commod_compatible
                              and self.mod.compatible
                              and self.mod.prevalidated)
                         and self.mod.installment_compatible)),
            Text(self.mod.commod_compatible_err,
                 color=ft.colors.ERROR,
                 visible=bool(self.mod.commod_compatible_err) and self.mod.installment_compatible),
            Text(self.mod.compatible_err,
                 color=ft.colors.ERROR,
                 visible=bool(self.mod.compatible_err) and self.mod.installment_compatible),
            Text(self.mod.prevalidated_err,
                 color=ft.colors.ERROR,
                 visible=bool(self.mod.prevalidated_err) and self.mod.installment_compatible)
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

        installment_compat_content = []
        if not self.mod.installment_compatible:
            icon = ft.Icon(ft.icons.WARNING_ROUNDED,
                           color=ft.colors.ERROR,
                           tooltip=tr("incompatible_game_installment"))

            if self.app.game.installment is None:
                game_label = tr("no_game_selected").capitalize()
                has_game = False
            else:
                game_label = tr(self.app.game.installment)
                has_game = True

            installment_compat_content = [
                icon,
                Column([
                    Row([Text(game_label,
                              weight=ft.FontWeight.W_500,
                              color=ft.colors.ON_PRIMARY_CONTAINER),
                         Text(f'[{self.app.game.exe_version}]',
                              weight=ft.FontWeight.W_300,
                              visible=has_game)]),
                    Row([Text(tr("incompatible_game_installment"),
                         weight=ft.FontWeight.W_300,
                         no_wrap=False,
                         visible=has_game),
                         Text(f'({tr("mod_for_game")} {tr(self.mod.installment)})',
                         weight=ft.FontWeight.W_300,
                         no_wrap=False)], spacing=5, wrap=True)
                ], expand=True)]

        req_list = []
        for req_tuple in self.mod.individual_require_status:
            req = req_tuple[0]
            ok_status = req_tuple[1]
            req_errors = [line.strip() for line in req_tuple[2]]

            version = req.get("versions")
            mention_versions = req.get("mention_versions")

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

            if version:
                version_string = f'({tr("of_version").capitalize()}: {version})'
            else:
                version_string = f'({tr("of_any_version")})'

            req_list.append(Row([
                icon,
                Column([
                    Row([Text(req["name_label"],
                              weight=ft.FontWeight.W_500,
                              color=ft.colors.ON_PRIMARY_CONTAINER),
                         Text(version_string,
                              weight=ft.FontWeight.W_300,
                              visible=mention_versions),
                         Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                              visible=not ok_status,
                              size=20,
                              tooltip="\n".join(req_errors),
                              color=ft.colors.ERROR)
                         ]),
                    Text(f'{tr("including_options").capitalize()}: {optional}',
                         visible=bool(optional),
                         weight=ft.FontWeight.W_300,
                         no_wrap=False)
                        ], expand=True)
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
                              weight=ft.FontWeight.W_300),
                         Text(f'({tr("not_installed")})',
                              weight=ft.FontWeight.W_300,
                              color=ft.colors.TERTIARY,
                              visible=incomp_ok_status),
                         Text(f'({tr("installed")})',
                              weight=ft.FontWeight.W_300,
                              color=ft.colors.ERROR,
                              visible=not incomp_ok_status),
                         Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                              visible=not incomp_ok_status,
                              size=20,
                              tooltip="\n".join(incomp_errors),
                              color=ft.colors.ERROR)]),
                    Text(f'{tr("including_options").capitalize()}: {optional}',
                         visible=bool(optional),
                         weight=ft.FontWeight.W_300,
                         no_wrap=False),
                        ], expand=True)
                     ])
            )

        reinstall_content = []
        if self.mod.is_reinstall:
            if self.mod.can_be_reinstalled:
                icon = ft.Icon(ft.icons.CHECK_CIRCLE_ROUNDED,
                               color=ft.colors.TERTIARY,
                               tooltip=tr("can_reinstall"))
            else:
                icon = ft.Icon(ft.icons.WARNING_ROUNDED,
                               color=ft.colors.ERROR,
                               tooltip=tr("cant_reinstall"))

            mod_name = self.mod.existing_version.get("display_name")
            if mod_name is None:
                mod_name = self.mod.display_name
            lang_name = self.mod.existing_version.get("language")
            if is_known_lang(lang_name) or lang_name == "not_specified":
                lang_name = tr(lang_name)

            reinstall_warning = self.mod.reinstall_warning
            if self.mod.can_be_reinstalled:
                reinstall_warning += "\n" + tr("install_from_scratch_if_issues")
            else:
                reinstall_warning += "\n" + tr("install_from_scratch")

            reinstall_content = [
                icon,
                Column([
                    Row([Text(mod_name,
                              weight=ft.FontWeight.W_500,
                              color=ft.colors.ON_PRIMARY_CONTAINER),
                         Text(f'({self.mod.existing_version.get("version")})',
                              weight=ft.FontWeight.W_300),
                         Text(f'[{self.mod.existing_version.get("build")}]',
                              weight=ft.FontWeight.W_300),
                         Text((f'{tr("language").capitalize()}: '
                               f'{lang_name}'),
                              weight=ft.FontWeight.W_300)]),
                    Row([Text(reinstall_warning,
                         visible=True,
                         weight=ft.FontWeight.W_300,
                         no_wrap=False)], wrap=True)
                        ], expand=True)
                     ]
        if installment_compat_content:
            point_list.append(Text(tr("game_compatibility").capitalize() + ":",
                              weight=ft.FontWeight.BOLD))
            point_list.append(Row(controls=installment_compat_content))
        else:
            if req_list:
                point_list.append(Text(tr("required_base").capitalize() + ":",
                                  weight=ft.FontWeight.BOLD))
                point_list.extend(req_list)
            if incomp_list:
                point_list.append(Text(tr("incompatible_base").capitalize() + ":",
                                  weight=ft.FontWeight.BOLD))
                point_list.extend(incomp_list)
            if reinstall_content:
                point_list.append(Text(tr("check_reinstallability").capitalize() + ":",
                                  weight=ft.FontWeight.BOLD))
                point_list.append(Row(controls=reinstall_content))

        return point_list

    def build(self):
        return ft.Container(
            ft.Container(
                content=Column([
                    Tabs(
                        height=40,
                        selected_index=self.tab_index,
                        animate_size=ft.animation.Animation(500, ft.AnimationCurve.DECELERATE),
                        on_change=self.switch_tab,
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
                                                    Text(f"{tr('game').capitalize()}:  "),
                                                    Text(tr(self.mod.installment))
                                                ], spacing=5),
                                                visible=bool(self.mod.release_date),
                                                margin=ft.margin.only(left=10, top=3, bottom=10)),
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
                                                               size=14)],
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
                                                                  size=14)],
                                                         alignment=ft.MainAxisAlignment.CENTER),
                                                     margin=ft.margin.only(bottom=2), expand=True)
                                                ],
                                                # vertical_alignment=ft.MainAxisAlignment.CENTER,
                                                alignment=ft.MainAxisAlignment.SPACE_AROUND),
                                             ref=self.trailer_btn,
                                             on_click=self.open_trailer_url,
                                             visible=bool(self.mod.trailer_url),
                                             tooltip=f'{tr("warn_external_address")}\n'
                                                     f'{self.mod.trailer_url}'),
                                            ft.Container(ft.Row([ft.ElevatedButton(
                                                    elevation=3,
                                                    icon=ft.icons.DELETE_FOREVER_ROUNDED,
                                                    icon_color=ft.colors.ERROR,
                                                    text=tr("delete_mod_short").capitalize(),
                                                    color=ft.colors.ERROR,
                                                    ref=self.mod_delete_btn,
                                                    on_click=self.delete_mod_ask,
                                                    tooltip=tr("delete_mod_from_library").capitalize())],
                                                alignment=ft.MainAxisAlignment.CENTER),
                                                margin=7, padding=ft.padding.only(left=3))
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
                                                     alignment=ft.MainAxisAlignment.CENTER,
                                                     vertical_alignment=ft.CrossAxisAlignment.CENTER),
                                    Text("Placeholder", ref=self.screenshot_text)
                                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                ref=self.screenshots,
                                visible=False,
                                padding=ft.padding.only(bottom=15)),
                            ft.Container(
                                Column([
                                    ft.Container(
                                        Row([ft.Markdown(
                                                self.mod.change_log_content,
                                                ref=self.change_log_text,
                                                auto_follow_links=True,
                                                code_theme="atom-one-dark",
                                                expand=1,
                                                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB)],
                                            expand=True),
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
                                        Row([ft.Markdown(
                                                self.mod.other_info_content,
                                                ref=self.other_info_text,
                                                auto_follow_links=True,
                                                code_theme="atom-one-dark",
                                                expand=1,
                                                extension_set=ft.MarkdownExtensionSet.GITHUB_WEB)],
                                            expand=True),
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


class ModArchiveItem(UserControl):
    def __init__(self, app: App, parent, archive_path: str,
                 mod_dummy: Mod, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        self.app: App = app
        self.parent: LocalModsScreen = parent
        self.archive_path: str = archive_path
        self.archive_extension = Path(self.archive_path).suffix.replace(".", "").upper()
        self.mod = mod_dummy
        self.key = self.mod.id

        self.extract_btn = ft.Ref[ft.ElevatedButton]()
        self.about_archived_mod = ft.Ref[ft.OutlinedButton]()
        self.about_info = ft.Ref[ft.Container]()
        self.progress_ring = ft.Ref[ft.ProgressRing]()

        self.expanded = False
        self.extracting = False
        self.file_counter = 0
        self.callback_time = datetime.now()
        self.file_counting_text = ft.Ref[Text]()
        self.version_label = ft.Ref[ft.Container]()

    async def progress_show(self, files_num, chunk_size=1):
        now_time = datetime.now()
        self.file_counter += chunk_size
        if (now_time - self.callback_time).microseconds > 16000:
            self.progress_ring.current.value = self.file_counter/files_num
            await self.progress_ring.current.update_async()
            self.file_counting_text.current.value = f"{self.file_counter} {tr('one_of_many')} {files_num}"
            await self.file_counting_text.current.update_async()
            await asyncio.sleep(0.001)
            self.callback_time = now_time

    async def extract(self, e):
        self.extracting = True
        loading_text = await self.app.show_loading(
            f"{self.mod.display_name} {self.mod.version} [{self.mod.build}]",
            tr("unpacking").capitalize())
        self.progress_ring.current.visible = True
        self.file_counting_text.current.visible = True
        self.version_label.current.visible = False
        await self.version_label.current.update_async()
        mods_path = os.path.join(self.app.context.distribution_dir, "mods")
        await extract_from_to(self.archive_path, os.path.join(mods_path, self.mod.id),
                              self.progress_show, loading_text)
        self.extracting = False
        self.app.context.archived_mods.pop(self.archive_path, None)
        await self.app.close_alert()
        await asyncio.sleep(0.1)
        await self.app.refresh_page(AppSections.LOCAL_MODS.value)

    async def toggle_archived_info(self, e):
        self.expanded = not self.expanded
        if self.expanded:
            self.about_archived_mod.current.text = tr("hide_menu").capitalize()
            self.about_info.current.height = None
            await self.about_info.current.update_async()
            await self.parent.mods_list_view.current.scroll_to_async(
                key=self.mod.id, duration=500)
        else:
            self.about_archived_mod.current.text = tr("about_mod").capitalize()
            self.about_info.current.height = 0
            await self.about_info.current.update_async()
        await self.about_archived_mod.current.update_async()

    def build(self):
        return ft.Card(
            ft.Container(
                Column([
                    ft.ResponsiveRow([
                        Column([
                            ft.ProgressRing(visible=False,
                                            ref=self.progress_ring,
                                            value=0),
                            ft.Container(
                                    Text(f"{self.mod.version} [{self.mod.build}]",
                                         no_wrap=True,
                                         size=18,
                                         weight=ft.FontWeight.W_500,
                                         tooltip=tr("mod_version_and_build").capitalize(),
                                         color=ft.colors.ON_PRIMARY_CONTAINER,
                                         overflow=ft.TextOverflow.ELLIPSIS),
                                    margin=ft.margin.only(bottom=3),
                                    alignment=ft.alignment.center,
                                    ref=self.version_label),
                            Text(ref=self.file_counting_text, visible=False)
                            ], col={"xs": 8, "xl": 6}, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Container(col={"xs": 0, "xl": 1}),
                        Column([
                            Text(f"[{self.archive_extension}] {self.mod.display_name}",
                                 opacity=0.9,
                                 weight=ft.FontWeight.W_500,
                                 size=18),
                            ft.Row([
                                Icon(ft.icons.WARNING_OUTLINED,
                                     size=20,
                                     color=ft.colors.SECONDARY),
                                Text(tr("mod_in_archive"),
                                     color=ft.colors.SECONDARY,
                                     weight=ft.FontWeight.W_300)]),
                            ],
                            col={"xs": 11, "xl": 14}),
                        Column([
                            Row([
                                 ft.Container(ft.ElevatedButton(
                                    tr("extract").capitalize(),
                                    icon=ft.icons.UNARCHIVE_ROUNDED,
                                    ref=self.extract_btn,
                                    disabled=self.extracting,
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
                                    tooltip=tr("extract_mod").capitalize(),
                                    on_click=self.extract), alignment=ft.alignment.center)
                                 ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=True),
                            ft.OutlinedButton(tr("about_mod").capitalize(),
                                              animate_size=ft.animation.Animation(
                                                66, ft.AnimationCurve.EASE_IN),
                                              ref=self.about_archived_mod,
                                              on_click=self.toggle_archived_info)
                            ], col={"xs": 7, "xl": 5}, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                        ], spacing=10, columns=26, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(
                        ft.Row([ft.Container(ft.Column([
                            Text(f"{tr('game').capitalize()}: {tr(self.mod.installment)}",
                                 color=ft.colors.SECONDARY,
                                 weight=ft.FontWeight.W_500),
                            Text(tr("main_info").capitalize()),
                            Text(self.mod.description,
                                 no_wrap=False)]),
                            bgcolor=ft.colors.SURFACE,
                            border_radius=10,
                            padding=ft.padding.symmetric(horizontal=20, vertical=15),
                            expand=1
                            )]),
                        ref=self.about_info,
                        padding=ft.padding.only(top=15),
                        height=None if self.expanded else 0)
                ], spacing=0, scroll=ft.ScrollMode.HIDDEN, alignment=ft.MainAxisAlignment.START),
                margin=15),
            margin=ft.margin.symmetric(vertical=1), elevation=2,
            )


class ModItem(UserControl):
    def __init__(self, app: App, mod: Mod, *args, **kwargs):
        super().__init__(self, *args, **kwargs)
        self.app = app
        self.main_mod = mod
        self.mod = self.main_mod
        self.other_versions = {}
        self.primary = True
        self.key = self.main_mod.id

        self.version_info = ft.Ref[ft.Container]()
        self.install_btn = ft.Ref[ft.ElevatedButton]()
        self.about_mod_btn = ft.Ref[ft.OutlinedButton]()
        self.info_container = ft.Ref[ModInfo]()
        self.mod_name_text = ft.Ref[Text]()
        self.author_text = ft.Ref[Text]()
        self.mod_logo_img = ft.Ref[Image]()

    async def install_mod(self, e):
        if self.app.game.check_is_running():
            await self.app.show_alert(tr("game_is_running"))
            self.app.local_mods.game_is_running = True
            await self.app.refresh_page()
            return
        if not self.app.page.overlay:
            bg = ft.Container(Row([Column(
                controls=[], alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER)]),
                bgcolor=ft.colors.BLACK87)

            fg = ModInstallWizard(self, self.app, self.main_mod, self.mod.language)

            self.app.page.overlay.clear()
            self.app.page.overlay.append(bg)
            self.app.page.overlay.append(fg)
            await self.app.page.update_async()

    async def toggle_info(self, e):
        if self.about_mod_btn.current.text == tr("about_mod").capitalize():
            self.about_mod_btn.current.text = tr("hide_menu").capitalize()
            await self.info_container.current.toggle()
            await self.app.local_mods.mods_list_view.current.scroll_to_async(
                key=self.main_mod.id, duration=500)
        else:
            self.about_mod_btn.current.text = tr("about_mod").capitalize()
            await self.info_container.current.toggle()
        await self.about_mod_btn.current.update_async()

    async def change_lang(self, e=None, lang=None):
        if e is not None:
            lang_to_switch = e.control.data
        else:
            lang_to_switch = lang

        if lang_to_switch == self.mod.language:
            return

        self.mod = self.main_mod.translations_loaded[lang_to_switch]

        self.mod_name_text.current.value = self.mod.display_name
        await self.mod_name_text.current.update_async()
        self.author_text.current.value = f"{tr(self.mod.developer_title)} {self.mod.authors}"
        await self.author_text.current.update_async()
        self.mod_logo_img.current.src = self.mod.logo_path
        await self.mod_logo_img.current.update_async()
        await self.update_install_btn()
        await self.info_container.current.update_info()

    async def update_install_btn(self):
        btn = self.install_btn.current

        btn.icon = ft.icons.CHECK_ROUNDED if self.mod.is_reinstall else None

        if not self.mod.is_reinstall:
            btn.text = tr("install").capitalize()
        else:
            btn.text = tr("installed").capitalize()

        btn.style = ft.ButtonStyle(
            color={
                ft.MaterialState.HOVERED: ft.colors.ON_SECONDARY,
                ft.MaterialState.DEFAULT: ft.colors.ON_PRIMARY if not self.mod.is_reinstall
                else ft.colors.ON_PRIMARY_CONTAINER,
                ft.MaterialState.DISABLED: ft.colors.ON_SURFACE_VARIANT
                },
            bgcolor={
                ft.MaterialState.HOVERED: ft.colors.SECONDARY,
                ft.MaterialState.DEFAULT: ft.colors.PRIMARY if not self.mod.is_reinstall
                else ft.colors.PRIMARY_CONTAINER,
                ft.MaterialState.DISABLED: ft.colors.SURFACE_VARIANT
            })

        btn.disabled = (not self.mod.can_install
                        or (self.mod.is_reinstall and not self.mod.can_be_reinstalled))

        if self.mod.can_be_reinstalled and self.mod.is_reinstall:
            btn.tooltip = tr("reinstall_mod_ask")
        else:
            btn.tooltip = None

        await btn.update_async()

    async def switch_mod_version(self, e):
        version_to_change = self.other_versions.get(e.control.text)
        if version_to_change is not None:
            self.switcher.content = version_to_change
            await self.switcher.update_async()
            if self.info_container.current.expanded:
                await version_to_change.info_container.current.toggle()

    async def did_mount_async(self):
        mod_cant_install = (not self.mod.can_install
                            or (self.mod.is_reinstall and not self.mod.can_be_reinstalled))
        if self.other_versions:
            options = [ft.PopupMenuItem(text=ver,
                                        on_click=self.switch_mod_version)
                       for ver in self.other_versions]
            self_version = f"{self.mod.version} [{self.mod.build}]"
            self_version = self_version[:22]
            self.version_info.current.content = Row([
                ft.Container(ft.PopupMenuButton(
                    tooltip=tr("mod_version_and_build").capitalize(),
                    content=ft.Container(
                        Row([
                            Text(self_version,
                                 no_wrap=True,
                                 color=ft.colors.ON_PRIMARY_CONTAINER
                                 if not mod_cant_install else ft.colors.ERROR,
                                 overflow=ft.TextOverflow.ELLIPSIS),
                            Icon(ft.icons.KEYBOARD_ARROW_DOWN_OUTLINED,
                                 color=ft.colors.ON_BACKGROUND)
                        ], spacing=5),
                        padding=ft.padding.only(left=8, right=6, top=2, bottom=2)),
                    items=options),
                    border_radius=5,
                    bgcolor=ft.colors.BACKGROUND)
            ], alignment=ft.MainAxisAlignment.CENTER, spacing=0)
            self.version_info.current.margin = 0

            await self.version_info.current.update_async()

        if self.app.config.prefered_mod_lang != self.mod.language:
            if self.app.config.prefered_mod_lang in self.main_mod.translations_loaded.keys():
                await self.change_lang(lang=self.app.config.prefered_mod_lang)

    def build(self):
        tr_tags = [tr(tag.lower()).capitalize() for tag in self.mod.tags]
        mod_cant_install = (not self.mod.can_install
                            or (self.mod.is_reinstall and not self.mod.can_be_reinstalled))
        if self.app.local_mods.game_is_running:
            install_tooltip = tr("game_is_running")
        elif self.mod.can_be_reinstalled and self.mod.is_reinstall:
            install_tooltip = tr("reinstall_mod_ask")
        elif not self.mod.installment_compatible:
            install_tooltip = tr("incompatible_game_installment")
        else:
            install_tooltip = None

        has_validation_errors = (not (self.mod.commod_compatible
                                      and self.mod.compatible
                                      and self.mod.prevalidated
                                      and self.mod.installment_compatible))
        cant_reinstall = self.mod.is_reinstall and not self.mod.can_be_reinstalled

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
                        ft.Container(Column([
                            Row([Text(self.mod.display_name,
                                      ref=self.mod_name_text,
                                      weight=ft.FontWeight.W_700,
                                      size=18,
                                      no_wrap=True,
                                      overflow=ft.TextOverflow.ELLIPSIS),
                                 ft.Container(
                                    Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                                         color=ft.colors.ERROR,
                                         size=14,
                                         tooltip=tr("cant_be_installed")),
                                    opacity=0.9,
                                    visible=has_validation_errors and not cant_reinstall,
                                    margin=ft.margin.only(top=3)),
                                 ft.Container(
                                    Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                                         size=14,
                                         tooltip=tr("cant_reinstall")),
                                    opacity=0.8,
                                    visible=not has_validation_errors and cant_reinstall,
                                    margin=ft.margin.only(top=3))
                                 ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            Text(f"{tr(self.mod.developer_title)} {self.mod.authors}",
                                 ref=self.author_text,
                                 max_lines=2,
                                 overflow=ft.TextOverflow.ELLIPSIS,
                                 size=13,
                                 weight=ft.FontWeight.W_300),
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
                            ]), clip_behavior=ft.ClipBehavior.HARD_EDGE, col={"xs": 11, "xl": 14}),
                        Column([
                            Column([Row([ft.Container(
                                    Text(f"{self.mod.version} [{self.mod.build}]",
                                         no_wrap=True,
                                         tooltip=tr("mod_version_and_build").capitalize(),
                                         color=ft.colors.ON_PRIMARY_CONTAINER
                                         if not has_validation_errors else ft.colors.ERROR,
                                         overflow=ft.TextOverflow.ELLIPSIS),
                                    margin=ft.margin.only(bottom=3),
                                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                                    ref=self.version_info),
                                 ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                wrap=True)]),
                            ft.ElevatedButton(
                                tr("install").capitalize() if not self.mod.is_reinstall
                                else tr("installed").capitalize(),
                                icon=ft.icons.CHECK_ROUNDED if self.mod.is_reinstall else None,
                                style=ft.ButtonStyle(
                                  color={
                                      ft.MaterialState.HOVERED: ft.colors.ON_SECONDARY,
                                      ft.MaterialState.DEFAULT: ft.colors.ON_PRIMARY
                                      if not self.mod.is_reinstall
                                      else ft.colors.ON_PRIMARY_CONTAINER,
                                      ft.MaterialState.DISABLED: ft.colors.ON_SURFACE_VARIANT
                                      },
                                  bgcolor={
                                      ft.MaterialState.HOVERED: ft.colors.SECONDARY,
                                      ft.MaterialState.DEFAULT: ft.colors.PRIMARY
                                      if not self.mod.is_reinstall
                                      else ft.colors.PRIMARY_CONTAINER,
                                      ft.MaterialState.DISABLED: ft.colors.SURFACE_VARIANT
                                  }
                                ),
                                ref=self.install_btn,
                                disabled=mod_cant_install or self.app.local_mods.game_is_running,
                                tooltip=install_tooltip,
                                on_click=self.install_mod),
                            ft.OutlinedButton(tr("about_mod").capitalize(),
                                              animate_size=ft.animation.Animation(
                                                66, ft.AnimationCurve.EASE_IN),
                                              ref=self.about_mod_btn,
                                              on_click=self.toggle_info)
                            ], col={"xs": 7, "xl": 5}, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
                        ], spacing=7, columns=26, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    ModInfo(self.app, self.mod, self, ref=self.info_container)
                ], spacing=0, scroll=ft.ScrollMode.HIDDEN, alignment=ft.MainAxisAlignment.START),
                margin=10),
            margin=ft.margin.symmetric(vertical=1), elevation=3,
            )


class ModInstallWizard(UserControl):
    def __init__(self, parent: ModItem, app: App, mod: Mod, language: str, **kwargs):
        super().__init__(self, **kwargs)
        self.mod_item = parent
        self.app: App = app
        self.main_mod: Mod | None = mod
        self.mod: Mod | None = self.main_mod.translations_loaded[language]
        self.current_lang = language
        self.current_screen = None
        self.options = []

        self.can_close = True

        self.callback_time = datetime.now()

        self.close_wizard_btn = ft.Ref[IconButton]()
        self.close_wizard_btn_tooltip = ft.Ref[ft.Tooltip]()
        self.ok_button = ft.Ref[ft.ElevatedButton]()

        self.mod_title = ft.Ref[Text]()
        self.mod_title_text = (f"{tr('installation')} {self.mod.display_name} - "
                               f"{tr('version')} {self.mod.version}")

        self.can_have_custom_install = False
        self.requires_custom_install = False

        self.main_row = ft.Ref[ft.ResponsiveRow]()
        self.screen = ft.Ref[ft.Container]()
        self.default_install_btn = ft.Ref[ft.FilledButton]()
        self.install_ask = ft.Ref[Text]()
        self.no_base_content_mod_warning = ft.Ref[ft.Container]()

        self.install_status_text = ft.Ref[Text]()
        self.install_details_text = ft.Ref[Text]()
        self.install_details_number_text = ft.Ref[Text]()
        self.install_progress_bar = ft.Ref[ft.ProgressBar]()

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
        def __init__(self, parent, option: Mod.OptionalContent,
                     existing_content: str = "", **kwargs):
            super().__init__(self, **kwargs)
            self.option = option
            self.parent = parent
            self.active = True
            self.existing_content = existing_content
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
            await self.parent.keep_track_of_options()

        async def set_inactive(self):
            if not self.active:
                return
            self.card.current.elevation = 0
            self.card.current.opacity = 0.8
            self.card.current.scale = 0.99
            self.warning_text.current.visible = True
            await self.card.current.update_async()
            self.active = False
            await self.parent.keep_track_of_options()

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
                self.choice = e.control.data if e.data == "true" else "skip"
                changed_from_default = self.choice != self.option.default_option
                if e.data != 'false':
                    for check in self.checkboxes:
                        if check.data != self.choice:
                            check.value = False
                            await check.update_async()
            await self.update_state()

            if not self.existing_content:
                if changed_from_default:
                    await self.parent.changed_from_default()
                else:
                    await self.parent.changed_to_default()

        def build(self):
            self.active = (self.option.default_option != "skip"
                           and self.existing_content != "skip")
            if self.option.install_settings is not None:
                selector = []
                self.complex_selector = True
                for setting in self.option.install_settings:
                    if self.existing_content:
                        value = setting["name"] == self.existing_content
                    else:
                        value = setting["name"] == self.option.default_option

                    check = ft.Checkbox(data=setting["name"],
                                        disabled=bool(self.existing_content)
                                        and self.existing_content != "skip",
                                        on_change=self.checkbox_action,
                                        value=value)
                    self.checkboxes.append(check)
                    selector.append(
                        ft.Row([
                            check,
                            Text(setting["name"], weight=ft.FontWeight.BOLD),
                            Text(setting["description"].strip(), no_wrap=False)
                            ], wrap=True, run_spacing=5))
            else:
                if self.existing_content:
                    value = self.existing_content == "yes"
                else:
                    value = self.option.default_option is None

                selector = ft.Checkbox(data='default',
                                       disabled=bool(self.existing_content or self.option.forced_option)
                                       and self.existing_content != "skip",
                                       value=value,
                                       on_change=self.checkbox_action)
                self.checkboxes.append(selector)

            if self.complex_selector:
                if not self.existing_content:
                    self.active = self.active and self.option.default_option is not None
                return ft.Card(ft.Row([ft.Container(
                    Column([
                        Row([
                            Text(self.option.display_name,
                                 color=ft.colors.SECONDARY, weight=ft.FontWeight.BOLD),
                            Text(f"[{self.option.name}]", opacity=0.6),
                            Text(tr("will_not_be_installed").capitalize(),
                                 color=ft.colors.TERTIARY,
                                 visible=not self.active,
                                 ref=self.warning_text,
                                 opacity=0.8),
                            Text(tr("cant_change_choice").capitalize(),
                                 color=ft.colors.ERROR,
                                 visible=bool(self.existing_content)
                                 and self.existing_content != "skip",
                                 opacity=0.8)
                            ], wrap=True, run_spacing=5),
                        Column([
                            Text(self.option.description, no_wrap=False),
                            Text(f'{tr("choose_one_of_the_options").capitalize()}:',
                                 color=ft.colors.SECONDARY),
                            *selector,
                            ])
                    ]),
                    margin=ft.margin.only(left=20, right=15, top=15, bottom=20),
                )], expand=True),
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
                                 opacity=0.8),
                            Text(tr("cant_change_choice").capitalize(),
                                 color=ft.colors.ERROR,
                                 visible=bool(self.existing_content) and not self.option.forced_option
                                 and self.existing_content != "skip",
                                 opacity=0.8),
                            Text(tr("forced_option").capitalize(),
                                 color=ft.colors.TERTIARY,
                                 visible=self.option.forced_option,
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
        if self.can_close:
            self.app.page.overlay.clear()
            if e.control.data == "close":
                await self.app.refresh_page()
            self.app.page.floating_action_button.visible = True
            await self.app.page.floating_action_button.update_async()
            await self.app.page.update_async()

    async def did_mount_async(self):
        self.app.page.floating_action_button.visible = False
        await self.app.page.floating_action_button.update_async()
        validated_translations = []
        for lang, mod in self.main_mod.translations_loaded.items():
            if mod.can_install:
                validated_translations.append(mod)

        num_valid_translations = len(validated_translations)
        if num_valid_translations == 0:
            # TODO: handle gracefully or remove entirely
            raise NoModsFound("No available for installation versions")
        # elif num_valid_translations == 1:
        await self.show_welcome_mod_screen()

    async def agree_to_install(self, e):
        if self.can_have_custom_install and not e.control.data["is_compatch"]:
            await self.show_settings_screen(e)
        else:
            await self.show_install_progress(e)

    async def callable_for_progbar(self, file_num, files_count, file_name, file_size):
        now_time = datetime.now()
        if (now_time - self.callback_time).microseconds > 16000:
            file_counting_text = f"{file_num} {tr('one_of_many')} {files_count}"
            description = f"{tr('copying_file').capitalize()}: {file_name} - {file_size} KB"
            self.install_details_number_text.current.value = file_counting_text
            self.install_details_text.current.value = description
            await self.install_details_number_text.current.update_async()
            await self.install_details_text.current.update_async()

            self.install_progress_bar.current.value = file_num / files_count
            await self.install_progress_bar.current.update_async()
            self.callback_time = now_time

    async def callable_for_status(self, status):
        now_time = datetime.now()
        if (now_time - self.callback_time).microseconds > 16000:
            self.install_status_text.current.value = status
            await self.install_status_text.current.update_async()
            self.callback_time = now_time

    async def show_install_progress(self, e):
        await self.update_status_capsules(self.Steps.INSTALLING)

        is_comrem_or_patch = self.mod.name == "community_remaster"
        is_compatch = False
        if isinstance(e.control.data, dict):
            is_compatch = e.control.data["is_compatch"]
        is_comrem = is_comrem_or_patch and not is_compatch

        if is_compatch:
            mod_banner_path = get_internal_file_path("assets/compatch_logo.png")
        else:
            mod_banner_path = self.mod.banner_path

        self.screen.current.content = ft.Column([
            Text(f"{tr('install_in_progress').capitalize()}...",
                 style=ft.TextThemeStyle.HEADLINE_SMALL),
            ft.ResponsiveRow([
                Image(src=mod_banner_path,
                      visible=self.mod.banner_path is not None,
                      fit=ft.ImageFit.CONTAIN,
                      col={"xs": 12, "xl": 11, "xxl": 10})
                ], alignment=ft.MainAxisAlignment.CENTER),
            ft.ProgressRing(width=100, height=100),
            ft.ResponsiveRow([Text(ref=self.install_details_number_text,
                                   text_align=ft.TextAlign.CENTER,
                                   no_wrap=False, col=12)],
                             alignment=ft.MainAxisAlignment.CENTER),
            ft.ProgressBar(ref=self.install_progress_bar),
            ft.ResponsiveRow([Text(ref=self.install_details_text,
                                   text_align=ft.TextAlign.CENTER,
                                   no_wrap=False, col=12)],
                             alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(),
            ft.ResponsiveRow([Text(ref=self.install_status_text,
                                   text_align=ft.TextAlign.CENTER,
                                   no_wrap=False, col=12)],
                             alignment=ft.MainAxisAlignment.CENTER),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)
        await self.screen.current.update_async()
        self.close_wizard_btn.current.disabled = True
        self.close_wizard_btn.current.selected = True
        await self.close_wizard_btn.current.update_async()
        self.close_wizard_btn_tooltip.current.message = tr("install_please_wait")
        await self.close_wizard_btn_tooltip.current.update_async()

        install_settings = {}

        if self.mod.no_base_content:
            install_settings["base"] = "skip"
        else:
            install_settings["base"] = "yes"
        for option_card in self.options:
            option = option_card.option
            if option_card.complex_selector:
                # if no options is chosen this will be the default
                install_settings[option.name] = "skip"
                for check in option_card.checkboxes:
                    if check.value:
                        install_settings[option.name] = check.data
            else:
                check = option_card.checkboxes[0]
                install_settings[option.name] = "yes" if check.value else "skip"

        game = self.app.game
        session = self.app.session
        mod = self.mod
        distribution_dir = str(Path(mod.distribution_dir).parent)
        game_root = game.game_root_path

        try:
            if is_comrem_or_patch:
                session.content_in_processing["community_patch"] = {
                    "base": "yes",
                    "version": mod.version,
                    "installment": mod.installment,
                    "build": mod.build,
                    "language": mod.language,
                    "display_name": "Community Patch"
                }

                await self.callable_for_status(tr("copying_patch_files_please_wait"))

                await file_ops.copy_from_to_async_fast(
                    [os.path.join(distribution_dir, "patch")],
                    os.path.join(game_root, "data"),
                    self.callable_for_progbar)

                await file_ops.copy_from_to_async_fast(
                    [os.path.join(distribution_dir, "libs")],
                    game_root,
                    self.callable_for_progbar)
                file_ops.rename_effects_bps(game_root)

            status_ok = False
            if not is_compatch:
                status_ok = await mod.install_async(
                    game.data_path,
                    install_settings,
                    game.installed_content,
                    self.callable_for_progbar,
                    self.callable_for_status
                    )
                self.app.logger.info(f'Installation status: {"ok" if status_ok else "error"}')

                session.content_in_processing[mod.name] = install_settings.copy()
                session.content_in_processing[mod.name]["version"] = mod.version
                session.content_in_processing[mod.name]["build"] = mod.build
                session.content_in_processing[mod.name]["language"] = mod.language
                session.content_in_processing[mod.name]["installment"] = mod.installment
                session.content_in_processing[mod.name]["display_name"] = mod.display_name
            else:
                status_ok = True

            if mod.config_options:
                await game.change_config_values(mod.config_options)

            if not is_comrem_or_patch:
                if mod.patcher_options is not None and not mod.vanilla_mod:
                    file_ops.patch_configurables(game.target_exe, mod.patcher_options)
                    if mod.patcher_options.get('gravity') is not None:
                        file_ops.correct_damage_coeffs(game.game_root_path,
                                                       mod.patcher_options.get('gravity'))

            changes_description = []
            if is_comrem_or_patch:
                if is_comrem:
                    target_dll = os.path.join(game_root, "dxrender9.dll")
                    if os.path.exists(target_dll):
                        file_ops.patch_render_dll(target_dll)
                    else:
                        raise DXRenderDllNotFound

                build_id = mod.build

                changes_description = file_ops.patch_game_exe(
                    game.target_exe,
                    "patch" if is_compatch else "remaster",
                    build_id,
                    self.app.context.monitor_res,
                    mod.patcher_options if is_comrem else {},
                    self.app.context.under_windows)
            elif mod.vanilla_mod:
                changes_description = file_ops.patch_memory(game.target_exe)

            if status_ok:
                er_message = f"Couldn't dump install manifest to '{game.installed_manifest_path}'!"
                try:
                    game.installed_content = game.installed_content | session.content_in_processing
                    game.load_installed_descriptions(self.app.context.validated_mod_configs)
                    if game.installed_content:
                        dumped_yaml = file_ops.dump_yaml(game.installed_content, game.installed_manifest_path)
                        if not dumped_yaml:
                            self.app.logger.error(tr("installation_error"), er_message)
                except Exception as ex:
                    self.app.logger.error(ex)
                    self.app.logger.error(er_message)
                    return

            if is_comrem_or_patch or mod.vanilla_mod:
                self.app.game.process_game_install(self.app.game.game_root_path)
        except Exception as ex:
            self.app.logger.error(ex)
            print(traceback.format_exc())
            await self.show_install_results(False, [], ex)
            return

        await self.show_install_results(status_ok, changes_description)

    async def show_install_results(self, status_ok, changes_description, ex=None):
        # TODO: check if it's a good idea to clear session.content_in_processing
        await self.update_status_capsules(self.Steps.RESULTS)

        if status_ok:
            info_color = ft.colors.TERTIARY
            result_text = Text(tr("successfully").capitalize(),
                               color=info_color,
                               weight=ft.FontWeight.BOLD)
        else:
            info_color = ft.colors.ERROR
            result_text = Text(tr("error_occurred").capitalize(),
                               color=info_color,
                               weight=ft.FontWeight.BOLD)

        mod_names = [mod_name for mod_name in self.app.session.content_in_processing]
        mod_basic_info = []
        mod_name = self.mod.name
        mod_display_name = self.mod.display_name
        mod_description = self.mod.description

        if self.mod.name == "community_remaster":
            if set(mod_names) != set(["community_patch", "community_remaster"]):
                mod_name = "community_patch"
                mod_display_name = "Community Patch"
                mod_description = tr("compatch_description")

        install_info = self.app.session.content_in_processing[mod_name]
        mod_basic_info.append(Text(mod_display_name,
                                   style=ft.TextThemeStyle.HEADLINE_SMALL,
                                   no_wrap=False, color=ft.colors.PRIMARY))
        mod_basic_info.append(Text(mod_description, no_wrap=False))
        mod_basic_info.append(Text(f"{tr(self.mod.developer_title)} {self.mod.authors}",
                                   no_wrap=False, color=ft.colors.SECONDARY, weight=ft.FontWeight.BOLD))

        mod_info = []
        options_installed = []
        if mod_name != "community_patch":
            for option in self.mod.optional_content:
                variant = install_info[option.name]
                if variant != "skip":
                    if variant != "yes":
                        variant_description = ""
                        for setting in option.install_settings:
                            if setting["name"] == variant:
                                variant_description = setting["description"]
                        options_installed.append(Row([
                            Text(option.display_name,
                                 color=ft.colors.SECONDARY, weight=ft.FontWeight.BOLD),
                            Text(f"[{option.name} / {variant}]", opacity=0.6)]))
                        options_installed.append(Text(option.description + f"\n({variant_description})"))
                    else:
                        options_installed.append(Row([
                            Text(option.display_name,
                                 color=ft.colors.SECONDARY, weight=ft.FontWeight.BOLD),
                            Text(f"[{option.name}]", opacity=0.6)]))
                        options_installed.append(Text(option.description))

        with_opt_label = ""
        if options_installed:
            with_opt_label = tr("with_option").capitalize()
            if len(options_installed) > 1:
                with_opt_label = tr("with_options").capitalize()

            mod_info.append(
                ExpandableContainer(with_opt_label,
                                    with_opt_label,
                                    Column(options_installed),
                                    expanded=False))

        if changes_description:
            mod_info.append(Text(f'{tr("binary_fixes").capitalize()}:'))
            for change in changes_description:
                change = tr(change)
                for splited in change.split("\n"):
                    splited = splited.replace("* ", "").strip()
                    if splited:
                        mod_info.append(Row([
                            ft.Icon(ft.icons.CHECK_CIRCLE_ROUNDED,
                                    color=ft.colors.TERTIARY,
                                    expand=1),
                            Text(splited, expand=15)
                            ]))

        reinstall_warn_container = ft.Container(Row([
            Icon(ft.icons.WARNING_OUTLINED, color=ft.colors.ERROR),
            Text((f'{tr("was_reinstall").capitalize()}!\n'
                  f'{tr("install_from_scratch_if_issues")}'),
                 no_wrap=False, color=ft.colors.ERROR, expand=True),
            ]),
            border_radius=10, padding=10, margin=ft.margin.only(bottom=8),
            bgcolor=ft.colors.ERROR_CONTAINER,
            height=0,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            animate_size=ft.animation.Animation(500, ft.AnimationCurve.DECELERATE),
            visible=self.mod.is_reinstall)

        c1 = ft.Container(
                Column([
                    Icon(ft.icons.CHECK_CIRCLE_ROUNDED if status_ok else ft.icons.WARNING_ROUNDED,
                         size=100,
                         color=info_color),
                    result_text], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                margin=10
                )
        c2 = ft.Container(
                Row([
                    Column([
                        Icon(ft.icons.CHECK_CIRCLE_ROUNDED if status_ok else ft.icons.WARNING_ROUNDED,
                             size=80,
                             color=info_color),
                        Text(tr("installed").capitalize() if status_ok else tr("not_installed").capitalize(),
                             color=ft.colors.TERTIARY if status_ok else ft.colors.ERROR,
                             weight=ft.FontWeight.W_600)],
                           horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=2),
                    Column(mod_basic_info, expand=10) if status_ok else Text(ex, no_wrap=False,
                                                                             color=ft.colors.ERROR,
                                                                             expand=10)
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                margin=ft.margin.symmetric(vertical=10), height=0,
                animate_size=ft.animation.Animation(500, ft.AnimationCurve.DECELERATE))

        mod_status_and_description = ft.AnimatedSwitcher(
            c1,
            transition=ft.AnimatedSwitcherTransition.SCALE,
            duration=500,
            reverse_duration=200,
            switch_in_curve=ft.AnimationCurve.EASE_OUT,
            switch_out_curve=ft.AnimationCurve.EASE_IN)

        mod_info_column = ft.Ref[Column]()
        close_window_btn = ft.Ref[ft.FilledTonalButton]()

        self.screen.current.content = ft.Column([
            ft.Text(tr("install_results").capitalize(),
                    style=ft.TextThemeStyle.HEADLINE_SMALL),
            mod_status_and_description,
            Column(controls=mod_info, height=0,
                   ref=mod_info_column,
                   animate_size=ft.animation.Animation(500, ft.AnimationCurve.DECELERATE)),
            ft.Divider(),
            reinstall_warn_container,
            ft.FilledTonalButton(tr("close_window").capitalize(),
                                 data="close",
                                 ref=close_window_btn,
                                 height=0,
                                 on_click=self.close_wizard)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        for mod in self.app.session.mods.values():
            mod.load_session_compatibility(self.app.game.installed_content,
                                           self.app.game.installed_descriptions)

        await self.screen.current.update_async()
        self.can_close = False
        await asyncio.sleep(1)
        mod_status_and_description.content = c2
        await mod_status_and_description.update_async()
        c2.height = None
        mod_info_column.current.height = None
        reinstall_warn_container.height = None
        close_window_btn.current.height = None
        await c2.update_async()
        await mod_info_column.current.update_async()
        await reinstall_warn_container.update_async()
        await close_window_btn.current.update_async()

        self.close_wizard_btn.current.data = "close"
        self.close_wizard_btn.current.disabled = False
        self.close_wizard_btn.current.selected = False
        await self.close_wizard_btn.current.update_async()

        self.close_wizard_btn_tooltip.current.message = tr("close_window").capitalize()
        await self.close_wizard_btn_tooltip.current.update_async()

        self.can_close = True

    def get_flag_buttons(self):
        flag_buttons = []
        for lang, mod in self.main_mod.translations_loaded.items():
            if mod.known_language:
                flag = get_internal_file_path(LangFlags[lang].value)
            else:
                flag = get_internal_file_path(LangFlags.other.value)

            icon = Image(flag, fit=ft.ImageFit.FILL)

            flag_tooltip = mod.lang_label.capitalize()

            if not mod.can_install:
                icon.opacity = 0.5
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
                if not option_card.complex_selector and value == "skip":
                    value = False
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

        if self.mod.language != "ru":
            disable_compatch_install = True
            disable_compatch_install_tooltip = tr("patch_only_supports_russian")
        elif (self.mod.is_reinstall
              and self.app.game.installed_content.get("community_remaster") is not None):
            disable_compatch_install = True
            disable_compatch_install_tooltip = tr("cant_install_patch_over_remaster")
        else:
            disable_compatch_install = False
            disable_compatch_install_tooltip = None

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
            disabled=disable_compatch_install,
            opacity=0.7 if disable_compatch_install else 1.0,
            tooltip=disable_compatch_install_tooltip,
            on_click=self.show_comrem_welcome,
            width=170, height=60,
            scale=1.0 if is_compatch else 0.95)

        if mod.optional_content:
            self.can_have_custom_install = True
            for option in mod.optional_content:
                if option.install_settings is not None and option.default_option is None:
                    # if any option doesn't have a default, we will ask user to make a choice
                    self.requires_custom_install = True
                    break

        if is_compatch:
            mod_description = tr("compatch_description")
        else:
            mod_description = mod.description

        description = (f"{tr('description')}\n{mod_description}\n\n"
                       f"{tr(mod.developer_title)} {mod.authors}")

        reinstall_warning = mod.reinstall_warning if mod.is_reinstall else ""
        if reinstall_warning:
            reinstall_warning += "\n" + tr("install_from_scratch_if_issues")

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
            welcome_install_prompt = tr("install_mod_ask")

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
                    ]), padding=ft.padding.only(bottom=5),
                             col={"xs": 12, "xl": 11, "xxl": 10})
                ], alignment=ft.MainAxisAlignment.CENTER),
            ft.ResponsiveRow([ft.Container(ft.Divider(height=3), col={"xs": 12, "xl": 11, "xxl": 10})],
                             alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(Column([
                ft.Container(Row([
                        Icon(ft.icons.WARNING_OUTLINED, color=ft.colors.ERROR),
                        Column([
                            Text(tr("check_reinstallability").capitalize(), weight=ft.FontWeight.BOLD,
                                 color=ft.colors.ERROR),
                            Text(reinstall_warning, no_wrap=False, color=ft.colors.ERROR)], spacing=5),
                        ], expand=True, spacing=15),
                        visible=bool(reinstall_warning), border_radius=10, padding=15,
                        margin=ft.margin.only(bottom=10),
                        bgcolor=ft.colors.ERROR_CONTAINER),
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
        await self.update_status_capsules(self.Steps.WELCOME)

    async def keep_track_of_options(self, update=True):
        if not self.mod.optional_content:
            return

        no_options = all([not option.active for option in self.options])
        no_options_no_base = self.mod.no_base_content and no_options
        if no_options:
            self.install_ask.current.value = tr("install_base_mod_ask")
        else:
            self.install_ask.current.value = tr("install_mod_with_options_ask")

        if no_options_no_base:
            self.ok_button.current.disabled = True
            self.no_base_content_mod_warning.current.visible = True
        else:
            self.ok_button.current.disabled = False
            self.no_base_content_mod_warning.current.visible = False
        if update:
            if self.mod.no_base_content:
                await self.ok_button.current.update_async()
                await self.no_base_content_mod_warning.current.update_async()
            await self.install_ask.current.update_async()

    async def show_settings_screen(self, e=None):
        self.options.clear()
        await self.update_status_capsules(self.Steps.SETTING_UP)
        mod = self.mod

        for option in mod.optional_content:
            if mod.is_reinstall and not mod.safe_reinstall_options:
                existing_install = self.app.game.installed_content.get(mod.name)
                if existing_install is not None:
                    existing_content = existing_install.get(option.name)
                    if existing_content is not None:
                        self.options.append(self.ModOption(self, option, existing_content))
                        continue
            self.options.append(self.ModOption(self, option))

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
                              ref=self.ok_button,
                              ),
            ft.FilledTonalButton(tr("no").capitalize(),
                                 width=100,
                                 on_click=self.close_wizard),
        ]

        default_install_btn_row = ft.ResponsiveRow([], alignment=ft.MainAxisAlignment.CENTER)

        forced_options = mod.is_reinstall and not mod.safe_reinstall_options

        default_install_btn_row.controls.append(ft.ElevatedButton(
            content=ft.Container(Row([
                Icon(ft.icons.RECOMMEND_ROUNDED,
                     color=ft.colors.TERTIARY,
                     visible=not forced_options),
                Icon(ft.icons.RULE,
                     color=ft.colors.TERTIARY,
                     visible=forced_options),
                Text(tr("recommended_install_chosen").capitalize(),
                     visible=not forced_options),
                Text(tr("last_settings_chosed").capitalize(),
                     visible=forced_options)
                ], alignment=ft.MainAxisAlignment.CENTER),
                clip_behavior=ft.ClipBehavior.HARD_EDGE),
            col=7 if forced_options else 6,
            on_click=self.set_to_default,
            disabled=True,
            visible=not self.requires_custom_install or mod.is_reinstall,
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
                    Column(controls=self.options,
                           scroll=ft.ScrollMode.AUTO, spacing=5),
                    ]),
                    padding=ft.padding.only(top=5, bottom=10),
                    col={"xs": 12, "xl": 11, "xxl": 10})
                ], alignment=ft.MainAxisAlignment.CENTER),
            ft.ResponsiveRow([ft.Container(ft.Divider(height=3),
                                           col={"xs": 10, "xl": 9, "xxl": 8})],
                             alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(
                Row([
                    Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                         color=ft.colors.ON_TERTIARY_CONTAINER,
                         expand=1),
                    Text(value=tr("no_base_content_mod_requires_options"),
                         weight=ft.FontWeight.BOLD,
                         no_wrap=False,
                         color=ft.colors.ON_TERTIARY_CONTAINER,
                         expand=15)]),
                bgcolor=ft.colors.TERTIARY_CONTAINER,
                padding=10, border_radius=10,
                visible=False,
                ref=self.no_base_content_mod_warning),
            ft.Container(Column([
                # TODO: replace with simpler "install mod?" if no options are selected
                Text(tr("install_mod_with_options_ask"),
                     ref=self.install_ask,
                     text_align=ft.TextAlign.CENTER),
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=5), padding=5),
            Row(controls=user_choice_buttons,
                alignment=ft.MainAxisAlignment.CENTER)
            ],
            spacing=5,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        await self.keep_track_of_options(update=False)
        await self.screen.current.update_async()

    async def set_install_lang(self, e):
        self.mod = self.main_mod.translations_loaded[e.control.data]
        await self.show_welcome_mod_screen()

    async def update_status_capsules(self, step: Steps):
        self.current_screen = step

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
            welcome_clr = deflt_clr
            welcome_cont = deflt_cont

        if welcome:
            setting_up_clr = bg_clr
            setting_up_cont = bg_cont
        elif setting_up:
            setting_up_clr = active_clr
            setting_up_cont = active_cont
        else:
            setting_up_clr = deflt_clr
            setting_up_cont = deflt_cont

        if welcome or setting_up:
            installing_clr = bg_clr
            installing_cont = bg_cont
        elif installing:
            installing_clr = active_clr
            installing_cont = active_cont
        else:
            installing_clr = deflt_clr
            installing_cont = deflt_cont

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
                             color=setting_up_clr,
                             opacity=0.5 if self.mod is None else 1.0),
                        bgcolor=setting_up_cont,
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
                             color=installing_clr,
                             opacity=0.5 if self.mod is None else 1.0),
                        bgcolor=installing_cont,
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
                                ref=self.close_wizard_btn_tooltip,
                                content=ft.IconButton(ft.icons.CLOSE_ROUNDED,
                                                      on_click=self.close_wizard,
                                                      ref=self.close_wizard_btn,
                                                      data="cancel",
                                                      icon_color=ft.colors.RED,
                                                      selected_icon=ft.icons.HOURGLASS_BOTTOM_ROUNDED,
                                                      selected_icon_color=ft.colors.ON_BACKGROUND,
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
        self.tracked_loaded_mods = set()
        self.mods_list_view = ft.Ref[ft.ListView]()
        self.mods_archived_list_view = ft.Ref[ft.ListView]()
        self.add_mods_column = ft.Ref[Column]()
        self.add_mod_card = ft.Ref[ft.Card]()
        self.no_mods_warning = ft.Ref[Text]()
        self.game_info = ft.Ref[ft.Container]()
        self.get_mod_archive_dialog = ft.FilePicker(on_result=self.get_mod_archive_result)
        self.refreshing = False
        self.game_is_running = False

    # TODO: is not working properly when first starting with no distro and then adding it
    # shows no_local_mods_found warning
    async def did_mount_async(self):
        # await self.app.page.floating_action_button.update_async()
        self.game_is_running = self.app.game.check_is_running()
        # self.game_info.current.update_async()
        if self.app.context.distribution_dir:
            self.game_info.current.content = self.get_game_info()
            await self.update_list()
            self.add_mod_card.current.height = None
            # await self.add_mod_card.current.update_async()
            await self.app.page.update_async()

    async def delete_mod(self, mod):
        cont_ref = ft.Ref[ft.Container]()
        bs = ft.BottomSheet(
            ft.Container(
                Row(
                    [
                        ft.ProgressRing(),
                        ft.Text(f'{mod.name} {mod.version} [{mod.build}]: '
                                f'{tr("deleting_mod_from_lib").capitalize()}.')
                    ],
                    tight=True,
                ),
                padding=20, ref=cont_ref
            ),
            open=True,
        )
        self.app.page.overlay.append(bs)
        await self.app.page.update_async()
        await bs.update_async()
        await aiofiles.os.remove(os.path.join(mod.distribution_dir, "manifest.yaml"))

        mod_path = Path(mod.distribution_dir)
        main_distro = Path(self.app.context.distribution_dir, "mods")

        try:
            if main_distro in mod_path.parents:
                # if mod dir is located directly in "mods" - delete just that
                if mod_path.parent == main_distro:
                    await aioshutil.rmtree(mod_path)
                # mod directory is very often nested inside another dir because of zip files structure
                # if we can detect that it's safe, we will delete whole nested structure
                elif mod_path.parent.parent == main_distro:
                    # we only want to delete parent dir if it was automatically created by commod
                    if mod_path.parent.stem == mod.id:
                        await aioshutil.rmtree(mod_path.parent)
                    else:
                        await aioshutil.rmtree(mod_path)
                elif mod_path.parent.parent.parent == main_distro:
                    # same as above
                    if mod_path.parent.parent.stem == mod.id:
                        await aioshutil.rmtree(mod_path.parent.parent)
                    else:
                        await aioshutil.rmtree(mod_path)
        except PermissionError:
            self.app.show_alert(tr("couldnt_delete_mod_permission_err"))

        cont_ref.current.content = Row(
            [
                Icon(ft.icons.CHECK_CIRCLE_ROUNDED, color=ft.colors.TERTIARY, size=37),
                ft.Text(f'{tr("ready").capitalize()}: {mod.name} {mod.version} [{mod.build}] - '
                        f'{tr("deleted_mod_from_lib")}.'),
            ],
            tight=True,
        )
        await bs.update_async()
        await asyncio.sleep(1)
        bs.open = False
        await bs.update_async()
        self.app.page.overlay.remove(bs)
        self.app.logger.debug(f"Deleted mod {mod.name} {mod.version} [{mod.build}]")
        await self.app.refresh_page(index=AppSections.LOCAL_MODS.value)

    async def update_list(self):
        await self.app.load_distro_async()

        mod_items = self.mods_list_view.current.controls
        self.tracked_loaded_mods = set()
        for mod_item in mod_items:
            if isinstance(mod_item, ModItem):
                self.tracked_loaded_mods.add(mod_item.main_mod.id)
            elif isinstance(mod_item, ft.AnimatedSwitcher):
                self.tracked_loaded_mods.add(mod_item.content.main_mod.id)
                for other_version in mod_item.content.other_versions.values():
                    self.tracked_loaded_mods.add(other_version.main_mod.id)

        if self.app.config.current_distro:
            self.app.logger.debug(f"Have current distro {self.app.config.current_distro}")
        else:
            self.app.logger.debug("No current distro")

        if self.app.config.current_game:
            self.app.logger.debug(f"Have current game {self.app.config.current_game}")
        else:
            self.app.logger.debug("No current game")

        no_env = not self.app.config.current_distro
        no_mods = not self.app.session.mods
        no_archives = not self.app.context.archived_mods

        if no_mods and no_archives:
            self.no_mods_warning.current.visible = True
            self.no_mods_warning.current.value = tr("no_local_mods_found").capitalize()
        else:
            self.no_mods_warning.current.visible = False
        # await self.no_mods_warning.current.update_async()

        self.mods_list_view.current.visible = not no_mods and not no_env
        self.mods_archived_list_view.current.visible = not no_archives and not no_env

        session_mods = set()

        mods_to_show = []

        for path, mod in self.app.session.mods.items():
            session_mods.add(mod.id)
            if mod.id not in self.tracked_loaded_mods:
                mods_to_show.append(ModItem(self.app, mod))
                # self.app.logger.debug(f"Adding mod {mod.id} to list")
                self.tracked_loaded_mods.add(mod.id)
            else:
                pass
                # self.app.logger.debug(f"Mod {mod.id} already in list")

        mods_to_show.sort(key=lambda item: item.main_mod.id.lower())

        mods_families = {}
        for mod_item in mods_to_show:
            mod_name = mod_item.main_mod.name
            installment = mod_item.main_mod.installment
            version_string = mod_item.main_mod.version + f" [{mod_item.main_mod.build}]"
            if mods_families.get(installment+mod_name) is None:
                mods_families[installment+mod_name] = [mod_item]
            else:
                for sister_mod in mods_families[installment+mod_name]:
                    sister_version_string = (sister_mod.main_mod.version
                                             + f"[{sister_mod.main_mod.build}]")
                    sister_mod.other_versions[version_string] = mod_item
                    mod_item.other_versions[sister_version_string] = sister_mod
                mods_families[installment+mod_name].append(mod_item)

        for mod_short_id, mod_items in mods_families.items():
            if len(mod_items) == 1:
                self.mods_list_view.current.controls.append(mod_items[0])
            else:
                newest_mod = mod_items[-1]
                version_switcher = ft.AnimatedSwitcher(
                    newest_mod,
                    transition=ft.AnimatedSwitcherTransition.SCALE,
                    duration=0,
                    reverse_duration=0)
                for item in mod_items:
                    item.switcher = version_switcher
                self.mods_list_view.current.controls.append(version_switcher)

        outdated_mods = self.tracked_loaded_mods - session_mods
        if outdated_mods:
            for mod_item in mod_items:
                if mod_item.main_mod.id in outdated_mods:
                    self.app.logger.debug(f"Removing mod {mod_item.main_mod.id} from list")
                    mod_items.remove(mod_item)

        archived_mod_items = self.mods_archived_list_view.current.controls
        tracked_archived_mods = set([mod_item.mod.id for mod_item in archived_mod_items])
        for path, mod_dummy in self.app.context.archived_mods.items():
            if mod_dummy.id in self.tracked_loaded_mods:
                self.mods_archived_list_view.current
                # self.app.logger.info(f"Archived mod id '{mod_dummy.id}' is already tracked in main list")
            elif mod_dummy.id in tracked_archived_mods:
                pass
                # self.app.logger.info(f"Archived mod id '{mod_dummy.id}' is already tracked as a zip")
            else:
                # self.app.logger.info(f"Archived mod id '{mod_dummy.id}' - adding to list")
                self.mods_archived_list_view.current.controls.append(
                    ModArchiveItem(self.app, self, path, mod_dummy)
                )
        for mod_item in archived_mod_items:
            if mod_item.mod.id in self.tracked_loaded_mods:
                archived_mod_items.remove(mod_item)
                # self.app.logger.debug(f"Removed archived {mod_item.mod.id} from list, already tracked")

        # self.app.logger.debug(f"{len(self.mods_list_view.current.controls)} elements in mods list view")
        self.app.logger.debug(f"Tracked mods: {self.tracked_loaded_mods}")

    async def get_mod_archive_result(self, e: ft.FilePickerResultEvent):
        if e.files:
            print(f"path: {e.files}")
            for file in e.files:
                loading_text = await self.app.show_loading(
                    file.path,
                    tr("reading_archive").capitalize())
                await asyncio.sleep(0.1)
                extension = Path(file.path).suffix
                match extension:
                    case ".7z":
                        manifest = await self.app.context.get_7z_manifest_async(
                            file.path, loading_text=loading_text)
                    case ".zip":
                        manifest = await self.app.context.get_zip_manifest_async(
                            file.path, loading_text=loading_text)
                    case _:
                        manifest = ""

                await self.app.close_alert()
                await asyncio.sleep(0.1)
                if not manifest:
                    await self.app.show_alert(
                        file.path,
                        tr("issue_with_archive"))
                else:
                    print(f'Read manifest for: {manifest.get("display_name")}')
                    try:
                        mod_dummy = Mod(manifest, Path(file.path).parent)
                    except Exception as ex:
                        self.app.logger.error("Error on ZIP mod preload", ex)
                        # TODO: remove raise, need to test
                        raise NotImplementedError
                        continue

                    if mod_dummy.id in self.app.session.tracked_mods:
                        self.app.logger.info(f"Archived mod id '{mod_dummy.id}' is already tracked")
                        await self.app.show_alert(
                            f"{mod_dummy.display_name} {mod_dummy.version} [{mod_dummy.build}]",
                            tr("mod_already_in_library").capitalize())
                    else:
                        self.app.logger.info(f"Archived mod id '{mod_dummy.id}' - adding to list")
                        self.mods_archived_list_view.current.controls.append(
                            ModArchiveItem(self.app, self, file.path, mod_dummy)
                        )
                        self.app.context.archived_mods[file.path] = mod_dummy

                        self.mods_archived_list_view.current.visible = True
                        await self.mods_archived_list_view.current.update_async()

    async def get_archive(self, e):
        await self.get_mod_archive_dialog.pick_files_async(
            dialog_title="Choose archive",
            allowed_extensions=["zip", "7z"])

    def get_game_info(self):
        if not self.app.game.game_root_path:
            return ft.Card(
               ft.Container(
                   Row([
                       ft.Icon(ft.icons.ROCKET_LAUNCH_ROUNDED,
                               size=40,
                               color=ft.colors.TERTIARY,
                               expand=1),
                       Column([
                           Text(tr("commod_needs_game"),
                                weight=ft.FontWeight.BOLD,
                                no_wrap=False,
                                ),
                           Row([Text(tr("launch_game_placeholder")),
                                ft.TextButton(tr("settings").capitalize(),
                                              icon=ft.icons.SETTINGS_OUTLINED,
                                              on_click=self.app.show_settings),
                                ], spacing=2)
                            ], expand=8)
                   ], spacing=19),
                   padding=ft.padding.only(left=20, right=35, top=25, bottom=25)
               ), elevation=5, margin=ft.margin.only(left=80, right=80, bottom=10))

        match self.app.game.installment:
            case "exmachina":
                if self.app.game.patched_version:
                    ico_path = get_internal_file_path("assets/icons/hta_comrem.png")
                else:
                    ico_path = get_internal_file_path("assets/icons/original_hta.png")
            case "m113":
                ico_path = get_internal_file_path("assets/icons/original_m113.png")
            case "arcade":
                ico_path = get_internal_file_path("assets/icons/original_arcade.png")

        if self.app.game.installed_descriptions:
            mods_text = "\n\n".join(self.app.game.installed_descriptions.values())
        else:
            mods_text = ""
        return ft.Card(
            ft.Container(
                Row([
                    Image(src=ico_path,
                          fit=ft.ImageFit.CONTAIN, expand=1),
                    Column([
                        Row([
                            Text(tr(self.app.game.installment),
                                 weight=ft.FontWeight.BOLD,
                                 no_wrap=False),
                            Text(f'[{self.app.game.exe_version.replace("Remaster", "Rem")}]',
                                 weight=ft.FontWeight.W_500),
                            ft.Tooltip(
                                message=mods_text,
                                visible=bool(mods_text),
                                content=Row([
                                    Icon(ft.icons.BUILD_ROUNDED, size=14, color=ft.colors.PRIMARY),
                                    Text(tr("has_mods").capitalize(),
                                         weight=ft.FontWeight.W_500,
                                         color=ft.colors.PRIMARY)
                                    ], spacing=5)),
                            ft.Tooltip(
                                message=self.app.game.target_exe,
                                visible=self.game_is_running,
                                content=Row([
                                    Icon(ft.icons.PENDING_ROUNDED, size=14, color=ft.colors.TERTIARY),
                                    Text(tr("game_is_running"),
                                         weight=ft.FontWeight.W_500,
                                         color=ft.colors.TERTIARY)
                                    ], spacing=5))
                            ]),
                        Text(self.app.config.game_names[self.app.config.current_game],
                             tooltip=self.app.game.game_root_path),
                        # ExpandableContainer(
                        #     tr("local_mods").capitalize(),
                        #     tr("local_mods").capitalize(),
                        #     Text("\n\n".join(self.app.game.installed_descriptions.values())),
                        #     expanded=False,
                        #     visible=bool(self.app.game.installed_descriptions))
                        ], expand=12)
                    ]),
                padding=ft.padding.symmetric(horizontal=15, vertical=15)
            ), elevation=5, margin=ft.margin.only(left=20, right=20, bottom=5),
            surface_tint_color=ft.colors.TERTIARY,
            col={"md": 12, "lg": 11, "xxl": 10})

    def build(self):
        if not self.app.context.distribution_dir:
            return Column([
                    Text(tr("mods_library").capitalize(),
                         style=ft.TextThemeStyle.TITLE_MEDIUM),
                    ft.Card(
                       ft.Container(
                           Row([
                               ft.Icon(ft.icons.BOOKMARK_ADD_ROUNDED,
                                       size=40,
                                       color=ft.colors.TERTIARY,
                                       expand=1),
                               Column([
                                   Text(tr("commod_needs_distro"),
                                        weight=ft.FontWeight.BOLD,
                                        no_wrap=False,
                                        ),
                                   Row([Text(tr("local_mods_placeholder")),
                                        ft.TextButton(tr("settings").capitalize(),
                                                      icon=ft.icons.SETTINGS_OUTLINED,
                                                      on_click=self.app.show_settings),
                                        ], spacing=2)
                                    ], expand=8)
                           ], spacing=19),
                           padding=ft.padding.only(left=20, right=35, top=25, bottom=25)
                       ), elevation=5, margin=ft.margin.only(left=80, right=80, bottom=10))
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        return ft.Container(
            Column([
                Row([Text(tr("mods_library").capitalize(),
                          style=ft.TextThemeStyle.TITLE_MEDIUM)],
                    alignment=ft.MainAxisAlignment.CENTER),
                ft.Column([
                    ft.Container(
                        ft.ResponsiveRow([
                            ft.Container(ref=self.game_info,
                                         col={"md": 12, "lg": 11, "xxl": 10}),
                            Text(tr("no_local_mods_found").capitalize(),
                                 visible=False,
                                 ref=self.no_mods_warning,
                                 col={"md": 12, "lg": 11, "xxl": 10}),
                            ft.ListView([], spacing=10, padding=0,
                                        ref=self.mods_list_view,
                                        col={"md": 12, "lg": 11, "xxl": 10}),
                            ft.ListView([], spacing=10, padding=0,
                                        ref=self.mods_archived_list_view,
                                        col={"md": 12, "lg": 11, "xxl": 10}),
                            ft.Card(ft.Container(
                                Column([
                                    Text(tr("archived_mods_explanation"),
                                         weight=ft.FontWeight.W_400,
                                         color=ft.colors.SECONDARY),
                                    Column([],
                                           horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                           ref=self.add_mods_column),
                                    ft.FloatingActionButton(
                                        tr("add_mod").capitalize(),
                                        mini=True,
                                        on_click=self.get_archive,
                                        height=40,
                                        icon=ft.icons.FILE_OPEN)
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                border_radius=10, padding=20),
                                height=10, ref=self.add_mod_card,
                                col={"md": 12, "lg": 11, "xxl": 10})
                            ],
                            alignment=ft.MainAxisAlignment.CENTER),
                        padding=ft.padding.only(right=22), alignment=ft.alignment.top_center),
                    self.get_mod_archive_dialog
                    ],
                    expand=True, scroll=ft.ScrollMode.ALWAYS)
            ]),
            margin=ft.margin.only(bottom=5), expand=True)


class DownloadModsScreen(UserControl):
    def __init__(self, app: App, **kwargs):
        super().__init__(self, **kwargs)
        self.app = app
        self.refreshing = False

    def build(self):
        return Column([
            Text(tr("download").capitalize(),
                 style=ft.TextThemeStyle.TITLE_MEDIUM),
            ft.Card(
                ft.Container(
                    Column([
                        ft.ResponsiveRow([
                            ft.Icon(ft.icons.PUBLIC_OFF_OUTLINED,
                                    size=40,
                                    color=ft.colors.TERTIARY,
                                    col={"xs": 1, "md": 2, "lg": 3, "xxl": 4}),
                            Text(tr("download_mods_screen_placeholder"),
                                 weight=ft.FontWeight.BOLD,
                                 no_wrap=False,
                                 col={"xs": 11, "md": 10, "lg": 9, "xxl": 8})
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Divider(),
                        Text(tr("download_at_dem_gallery")),
                        ft.TextButton(content=ft.Row([
                            Image(src=get_internal_file_path("assets/icons/discord-icon-svgrepo.svg"),
                                  color=ft.colors.PRIMARY,
                                  fit=ft.ImageFit.FILL, height=30),
                            Text(tr("go_to_dem_server"))],
                            alignment=ft.MainAxisAlignment.CENTER,
                            height=38),
                            url=DEM_DISCORD_MODS_DOWNLOAD_SCREEN),
                        ft.TextButton(content=ft.Row([
                            Image(src=get_internal_file_path("assets/icons/github_invertocat.svg"),
                                  color=ft.colors.PRIMARY,
                                  fit=ft.ImageFit.FILL, height=27),
                            Text(tr("our_github"))],
                            alignment=ft.MainAxisAlignment.CENTER,
                            height=38),
                            url=COMPATCH_GITHUB)
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=ft.padding.only(left=30, right=30, top=30, bottom=20)
                ), elevation=5, margin=ft.margin.symmetric(horizontal=80))
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)


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
        self.launch_prog_ring = ft.Ref[ft.ProgressRing]()
        self.checkbox_windowed_game = ft.Ref[ft.PopupMenuItem]()
        self.checkbox_hi_dpi_aware = ft.Ref[ft.PopupMenuItem]()
        self.checkbox_fullsreen_opts = ft.Ref[ft.PopupMenuItem]()
        self.refreshing = False
        self.game_is_running = False

    async def did_mount_async(self):
        self.got_news = False
        self.offline = False

        if self.app.game.target_exe and not self.app.game.exe_version and self.app.config.current_game:
            await self.select_game_from_home(path=self.app.config.current_game)
        elif self.app.game.check_is_running() and not self.game_is_running:
            await self.select_game_from_home(path=self.app.config.current_game)

        # TODO: check why needs to be reloaded after changing the game
        if self.app.game.target_exe:
            create_task(self.get_news())
        else:
            self.app.logger.debug("No game found")
        if self.app.current_game_process is not None:
            await self.synchronise_launch_btn_prompt(started=True)

    async def get_news(self):
        if not self.offline:
            if self.news_text is not None:
                self.markdown_content.current.value = self.news_text
                await self.markdown_content.current.update_async()
                return

            # await asyncio.sleep(1)
            mappings = "https://raw.githubusercontent.com/DeusExMachinaTeam/ComModNews/main/langs.yaml"
            response_map = await request(
                url=mappings,
                protocol="HTTPS",
                protocol_info={
                    "request_type": "GET",
                    "timeout": 5,
                    "circuit_breaker_config": {
                        "maximum_failures": 3,
                        "timeout": 5}
                }
            )
            if response_map["api_response"]["status_code"] == 200:
                lang_mappings = load_yaml(response_map["api_response"]["text"])
                if not isinstance(lang_mappings, dict):
                    self.app.logger.error("Online news loading: Couldn't parse lang mappings as yaml")
                    return

                dem_news_stem = lang_mappings.get(localisation.LANG)
                if dem_news_stem is None:
                    self.app.logger.error("Online news loading: Couldn't get current lang from lang mappings")

                response = await request(
                    url=(f"https://raw.githubusercontent.com/DeusExMachinaTeam/ComModNews/main/"
                         f"{dem_news_stem}"),
                    protocol="HTTPS",
                    protocol_info={
                        "request_type": "GET",
                        "timeout": 5,
                        "circuit_breaker_config": {
                            "maximum_failures": 3,
                            "timeout": 5}
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
        if self.app.game.game_root_path:
            # just an additional safeguard, all actions on game
            # are delayed by 1 second after game_change_time
            self.app.game_change_time = datetime.now()
            await self.app.game.switch_windowed(enable=not self.checkbox_windowed_game.current.checked)

        self.launch_game_btn.current.disabled = False
        await self.launch_game_btn.current.update_async()

    async def switch_to_hidpi_aware(self, e):
        # temporarily disabling game launch
        self.launch_game_btn.current.disabled = True
        await self.launch_game_btn.current.update_async()

        self.checkbox_hi_dpi_aware.current.checked = not self.checkbox_hi_dpi_aware.current.checked
        if self.app.game.game_root_path:
            # just an additional safeguard, all actions on game
            # are delayed by 1 second after game_change_time
            self.app.game_change_time = datetime.now()
            result_ok = self.app.game.switch_hi_dpi_aware(enable=self.checkbox_hi_dpi_aware.current.checked)
            if not result_ok:
                self.checkbox_hi_dpi_aware.current.checked = not self.checkbox_hi_dpi_aware.current.checked
                await self.app.show_alert(tr("no_access_to_registry_cant_set"))

        await self.checkbox_hi_dpi_aware.current.update_async()

        self.launch_game_btn.current.disabled = False
        await self.launch_game_btn.current.update_async()

    async def switch_fullscreen_optimizations(self, e):
        # temporarily disabling game launch
        self.launch_game_btn.current.disabled = True
        await self.launch_game_btn.current.update_async()

        self.checkbox_fullsreen_opts.current.checked = not self.checkbox_fullsreen_opts.current.checked
        if self.app.game.game_root_path:
            # just an additional safeguard, all actions on game
            # are delayed by 1 second after game_change_time
            self.app.game_change_time = datetime.now()
            result_ok = self.app.game.switch_fullscreen_opts(
                disable=self.checkbox_fullsreen_opts.current.checked)
            if not result_ok:
                self.checkbox_fullsreen_opts.current.checked = \
                    not self.checkbox_fullsreen_opts.current.checked
                await self.app.show_alert(tr("no_access_to_registry_cant_set"))

        await self.checkbox_fullsreen_opts.current.update_async()

        self.launch_game_btn.current.disabled = False
        await self.launch_game_btn.current.update_async()

    async def show_launch_opts_instruction(self, e):
        await self.app.show_modal(tr("launch_options_instruction_text"),
                                  title=tr("launch_options_instructions").capitalize())

    async def launch_game(self, e):
        current_time = datetime.now()
        self.launch_prog_ring.current.visible = True
        await self.launch_prog_ring.current.update_async()
        if self.app.game_change_time is not None:
            if (current_time - self.app.game_change_time).seconds < 1:
                # do not try to relaunch game immediately after a change
                self.launch_prog_ring.current.visible = False
                await self.launch_prog_ring.current.update_async()
                return
        if self.app.current_game_process is None:
            if self.app.game.check_is_running():
                await self.app.show_alert(tr('game_is_already_running'))
                self.game_is_running = True
                self.launch_prog_ring.current.visible = False
                await self.launch_prog_ring.current.update_async()
                await self.app.refresh_page(AppSections.LAUNCH.value)
                return
            other_game_running = await self.check_for_game()
            if other_game_running:
                await self.app.show_alert(tr('game_is_already_running'))
                self.launch_prog_ring.current.visible = False
                await self.launch_prog_ring.current.update_async()
                return
            if "Windows" in platform.system():
                self.app.logger.info(f"Launching: {self.app.game.target_exe}")
                self.app.current_game_process = \
                    await create_subprocess_exec(
                        self.app.game.target_exe,
                        '-console' if self.app.config.game_with_console else "",
                        cwd=self.app.game.game_root_path,
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
            else:
                cmd = self.app.config.linux_run_cmd.split(" ");
                self.app.logger.info(f"Launching: {cmd}")
                self.app.current_game_process = await create_subprocess_exec(*cmd,stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


            self.app.game_change_time = datetime.now()
            await self.synchronise_launch_btn_prompt(starting=True)
            asyncio.create_task(self.keep_track_of_game_proc())
            self.game_is_running = True
            await self.app.refresh_page(AppSections.LAUNCH.value)
        else:
            if self.app.current_game_process.returncode is None:
                # stopping game on a next step, needs to be explained with a changing
                # button prompt
                self.app.current_game_process.terminate()
                self.app.current_game_process = None
                await self.synchronise_launch_btn_prompt(starting=False)
            else:
                # game exited (1 - ok exit status, 3 - crash, maybe other options)
                self.app.current_game_process = None
                await self.synchronise_launch_btn_prompt(starting=False)

    async def keep_track_of_game_proc(self):
        while True:
            if self.app.current_game_process is None:
                self.app.local_mods.game_is_running = False
                await self.app.refresh_page(AppSections.LAUNCH.value)
                break
            if self.app.current_game_process.returncode is None:
                pass
            else:
                self.app.current_game_process = None
                self.app.local_mods.game_is_running = False
                await self.app.refresh_page(AppSections.LAUNCH.value)
                await self.synchronise_launch_btn_prompt(starting=False)
                break
            await asyncio.sleep(3)

    async def synchronise_launch_btn_prompt(self, starting=True, started=False):
        if started:
            self.launch_game_btn_text.current.value = tr("stop_game").capitalize()
            await self.launch_game_btn_text.current.update_async()
        elif starting:
            self.launch_game_btn_text.current.value = f"{tr('launching').capitalize()}..."
            await self.launch_game_btn_text.current.update_async()
            await asyncio.sleep(1)
            self.launch_game_btn_text.current.value = tr("stop_game").capitalize()
            await self.launch_game_btn_text.current.update_async()
        else:
            self.launch_game_btn_text.current.value = tr("play").capitalize()
            await self.launch_game_btn_text.current.update_async()
        self.launch_prog_ring.current.visible = False
        await self.launch_prog_ring.current.update_async()

    async def game_console_mode_change(self, e):
        self.app.config.game_with_console = e.data == 'true'

    def get_no_game_placeholder(self):
        return Column([
            Text(tr("launch_full").capitalize(),
                 style=ft.TextThemeStyle.TITLE_MEDIUM),
            ft.Card(
               ft.Container(
                   Row([
                       ft.Icon(ft.icons.ROCKET_LAUNCH_ROUNDED,
                               size=40,
                               color=ft.colors.TERTIARY,
                               expand=1),
                       Column([
                           Text(tr("commod_needs_game"),
                                weight=ft.FontWeight.BOLD,
                                no_wrap=False,
                                ),
                           Row([Text(tr("launch_game_placeholder")),
                                ft.TextButton(tr("settings").capitalize(),
                                              icon=ft.icons.SETTINGS_OUTLINED,
                                              on_click=self.app.show_settings),
                                ], spacing=2)
                            ], expand=8)
                   ], spacing=19),
                   padding=ft.padding.only(left=20, right=35, top=25, bottom=25)
               ), elevation=5, margin=ft.margin.symmetric(horizontal=80))
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER)

    async def open_clicked(self, e):
        # open game directory in Windows Explorer
        if os.path.isdir(self.app.game.game_root_path):
            os.startfile(self.app.game.game_root_path)
        await self.update_async()

    async def select_game_from_home(self, e=None, path: Optional[str] = None):
        if e is not None:
            game_path = e.control.data
        elif path is not None:
            game_path = path
        else:
            return

        try:
            new_game = GameCopy()
            new_game.process_game_install(game_path)
        except PatchedButDoesntHaveManifest:
            pass
        except HasManifestButUnpatched:
            pass
        except ExeIsRunning:
            if not self.game_is_running:
                await self.app.show_alert(tr('game_is_running_cant_select'))
                self.game_is_running = True
            return
        except Exception as ex:
            # TODO: Handle exceptions properly
            await self.app.show_alert(tr('broken_game'), ex)
            self.app.logger.error(f"[Game loading error] {ex}")
            return

        self.app.game = new_game

        self.app.config.current_game = game_path
        self.app.logger.info(f"Game is now: {game_path}")

        if self.app.context.distribution_dir:
            # self.app.context.validated_mod_configs.clear()
            loaded_steam_game_paths = self.app.context.current_session.steam_game_paths
            self.app.context.current_session = InstallationContext.Session()
            self.app.session = self.app.context.current_session
            # TODO: maybe do a full steam path reload?
            # or maybe also copy steam_parsing_error
            self.app.session.steam_game_paths = loaded_steam_game_paths
            # self.app.load_distro()
            await self.app.load_distro_async()
        else:
            self.app.logger.debug("No distro dir found in context")

        await self.app.refresh_page(AppSections.LAUNCH.value)

    def build(self):
        self.app.page.floating_action_button = ft.FloatingActionButton(
            icon=ft.icons.REFRESH_ROUNDED,
            on_click=self.app.upd_pressed,
            mini=True
            # bgcolor=ft.colors.PRIMARY
            )
        with open(get_internal_file_path("assets/placeholder.md"), "r", encoding="utf-8") as fh:
            md1 = fh.read()
            md1 = process_markdown(md1)

            if self.app.game.installment_id == GameInstallments.EXMACHINA.value:
                logo_path = "assets/em_logo.png"
            elif self.app.game.installment_id == GameInstallments.M113.value:
                logo_path = "assets/m113_logo.png"
            elif self.app.game.installment_id == GameInstallments.ARCADE.value:
                logo_path = "assets/arcade_logo.png"
            else:
                logo_path = None

            if logo_path is not None:
                info_msg = Row(visible=False)
                image = Image(src=get_internal_file_path(logo_path),
                              fit=ft.ImageFit.FILL)
            else:
                image = ft.Stack([Image(src=get_internal_file_path("assets/em_logo.png"),
                                        fit=ft.ImageFit.FILL, opacity=0.4),
                                  ft.Container(Column([
                                        Icon(ft.icons.QUESTION_MARK_ROUNDED,
                                             size=90,
                                             color='red')],
                                        horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                        alignment=ft.alignment.center)
                                  ])
            if self.app.game.check_is_running():
                self.game_is_running = True
                info_msg = Row([
                    Icon(ft.icons.PENDING_ROUNDED,
                         size=20,
                         color=ft.colors.TERTIARY),
                    Text(tr("game_is_running"), color=ft.colors.TERTIARY)])
            elif logo_path is None:
                self.game_is_running = False
                info_msg = Row([
                    Icon(ft.icons.WARNING_ROUNDED,
                         size=20,
                         color=ft.colors.ERROR),
                    Text(tr("broken_game_short"), color=ft.colors.ERROR)])

            if not self.app.game.target_exe:
                return self.get_no_game_placeholder()

            mods_info = Column([])
            if self.app.game.installed_descriptions:
                mods_text = "\n\n".join(self.app.game.installed_descriptions.values())
                for value in self.app.game.installed_descriptions.values():
                    if len(mods_info.controls) > 2:
                        mods_info.controls.append(
                            ft.Container(
                                Text(f"... {tr('and_others')}",
                                     size=12,
                                     color=ft.colors.ON_BACKGROUND,
                                     tooltip=mods_text), margin=ft.margin.only(left=25)))
                        break
                    splited = value.split("\n")
                    if len(splited) > 1:
                        mods_info.controls.append(
                            ft.Container(
                                ft.Row([
                                    Icon(ft.icons.INFO_OUTLINE_ROUNDED,
                                         size=12,
                                         color=ft.colors.SECONDARY,
                                         expand=1),
                                    Text(splited[0],
                                         size=12,
                                         overflow=ft.TextOverflow.ELLIPSIS,
                                         expand=10),
                                   ],
                                   tight=True,
                                   spacing=4,
                                   alignment=ft.MainAxisAlignment.START,
                                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
                                tooltip="\n".join(splited)))
                    else:
                        mods_info.controls.append(
                            ft.Row([
                                    Icon(ft.icons.CIRCLE,
                                         size=12,
                                         color=ft.colors.ON_BACKGROUND,
                                         expand=1),
                                    Text(value,
                                         size=12,
                                         overflow=ft.TextOverflow.ELLIPSIS,
                                         expand=10),
                                   ],
                                   tight=True,
                                   spacing=5,
                                   alignment=ft.MainAxisAlignment.START,
                                   vertical_alignment=ft.CrossAxisAlignment.CENTER))
            else:
                mods_text = ""
                mods_info.visible = False

            if len(self.app.config.game_names) == 1:
                game_selector = ft.Container(
                    Icon(ft.icons.BADGE_ROUNDED, color=ft.colors.PRIMARY, size=20),
                    margin=ft.margin.only(left=7, right=8))
            else:
                game_selector = ft.PopupMenuButton(
                                    icon=ft.icons.BADGE_ROUNDED,
                                    # icon_color=ft.colors.PRIMARY,
                                    # icon_size=20,
                                    scale=0.85,
                                    tooltip=tr("select_other_game").capitalize(),
                                    items=[])
                for key, value in self.app.config.game_names.items():
                    game_selector.items.append(
                        ft.PopupMenuItem(content=Text(value), data=key, on_click=self.select_game_from_home)
                    )
                game_selector = ft.Container(game_selector, margin=ft.margin.only(left=-3))

            return ft.Container(
                ft.ResponsiveRow([
                    Column(controls=[
                        ft.Container(Column([
                            ft.Container(
                                Column([image],
                                       horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                margin=ft.margin.only(top=10)),
                            Row([
                                game_selector,
                                ft.Column([
                                    Text(self.app.config.game_names[self.app.config.current_game],
                                         color=ft.colors.PRIMARY,
                                         overflow=ft.TextOverflow.ELLIPSIS,
                                         weight=ft.FontWeight.W_400,
                                         tooltip=self.app.config.game_names[self.app.config.current_game])],
                                    expand=True)
                                ], spacing=0, alignment=ft.MainAxisAlignment.START),
                            ft.Container(Row([
                                Icon(ft.icons.INFO_ROUNDED, color=ft.colors.PRIMARY, size=20),
                                Text(self.app.game.exe_version,
                                     color=ft.colors.PRIMARY,
                                     tooltip=tr("exe_version") + "\n" + self.app.game.target_exe,
                                     weight=ft.FontWeight.W_700),
                                ]), margin=ft.margin.only(left=7),
                                visible=bool(self.app.game.exe_version)),
                            ft.Container(info_msg, margin=ft.margin.only(left=7), visible=info_msg.visible),
                            ft.Tooltip(
                                message=mods_text,
                                wait_duration=100,
                                visible=bool(mods_text),
                                content=ft.Container(Row([
                                    Text(tr("has_mods").upper(),
                                         weight=ft.FontWeight.BOLD,
                                         color=ft.colors.ON_BACKGROUND)
                                    ]), margin=ft.margin.only(top=10))),
                            ft.Container(mods_info, visible=mods_info.visible),
                            ft.Container(Column([
                                Text(tr("actions").upper(),
                                     weight=ft.FontWeight.BOLD),
                                ft.Tooltip(
                                    message=tr("open_in_explorer"),
                                    wait_duration=300,
                                    content=ft.TextButton(
                                        text=tr("open_in_explorer"),
                                        icon=icons.FOLDER_OPEN,
                                        on_click=self.open_clicked))
                            ]), margin=ft.margin.only(top=10))
                        ]), clip_behavior=ft.ClipBehavior.ANTI_ALIAS),
                        # Text(self.app.context.distribution_dir),
                        # Text(self.app.context.commod_version),
                        # Text(self.app.game.game_root_path),
                        # Text(self.app.game.display_name),
                        Column([
                            Row([Text(tr("launch_params").upper(),
                                      weight=ft.FontWeight.BOLD),
                                 ft.PopupMenuButton(items=[
                                    ft.PopupMenuItem(
                                        content=Row([Icon(ft.icons.FULLSCREEN_ROUNDED),
                                                     Text(tr("windowed_mode").capitalize(),
                                                          width=160,
                                                          size=13)]),
                                        checked=not self.app.game.fullscreen_game,
                                        on_click=self.switch_to_windowed,
                                        ref=self.checkbox_windowed_game),
                                    ft.PopupMenuItem(
                                        content=Row([Icon(ft.icons.FOUR_K_ROUNDED),
                                                     Text(tr("hi_dpi_aware"),
                                                          width=160,
                                                          size=13)]),
                                        checked=self.app.game.hi_dpi_aware,
                                        on_click=self.switch_to_hidpi_aware,
                                        ref=self.checkbox_hi_dpi_aware),
                                    ft.PopupMenuItem(
                                        content=Row([Icon(ft.icons.SETTINGS_APPLICATIONS_OUTLINED),
                                                     Text(tr("fullscreen_optimizations"),
                                                          width=160,
                                                          size=13)]),
                                        checked=self.app.game.fullscreen_opts_disabled,
                                        on_click=self.switch_fullscreen_optimizations,
                                        ref=self.checkbox_fullsreen_opts),
                                    ft.PopupMenuItem(),
                                    ft.PopupMenuItem(
                                        content=ft.Container(
                                            Row([Icon(ft.icons.QUESTION_MARK_OUTLINED,
                                                      color=ft.colors.ON_BACKGROUND),
                                                 Text(tr("launch_options_instructions").capitalize(),
                                                      width=190,
                                                      size=13)]),
                                            margin=ft.margin.only(left=15)),
                                        on_click=self.show_launch_opts_instruction)
                                    ],
                                    # TODO: is this working as intended?
                                    disabled=self.app.game.exe_version == "Unknown")
                                 ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                            ft.Container(
                                Row([ft.Switch(
                                        value=self.app.config.game_with_console,
                                        scale=0.7,
                                        on_change=self.game_console_mode_change,
                                        ref=self.game_console_switch),
                                     Text(tr("enable_console").capitalize(),
                                          weight=ft.FontWeight.W_500)
                                     ], spacing=0), margin=ft.margin.only(bottom=10)),
                            ft.FloatingActionButton(
                                content=ft.Row([
                                    ft.ProgressRing(visible=False,
                                                    color=ft.colors.ON_PRIMARY,
                                                    scale=0.7,
                                                    ref=self.launch_prog_ring),
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
                            )], spacing=0)
                        ],
                        col={"xs": 8, "xl": 7, "xxl": 6}, alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Container(Column([
                        Row([ft.ProgressRing(scale=0.5), Text(tr("checking_online_news"))],
                            ref=self.checking_online, visible=self.news_text is None),
                        ft.Container(ft.Markdown(
                            md1,
                            expand=True,
                            code_theme="atom-one-dark",
                            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                            auto_follow_links=True,
                            ref=self.markdown_content,
                        ), padding=ft.padding.only(left=10, right=22)),
                        ],
                        alignment=ft.MainAxisAlignment.START,
                        spacing=20,
                        scroll=ft.ScrollMode.ADAPTIVE), col={"xs": 16, "xl": 17, "xxl": 18})
                    ], vertical_alignment=ft.CrossAxisAlignment.START, spacing=30, columns=24),
                margin=ft.margin.only(bottom=20), expand=True)
