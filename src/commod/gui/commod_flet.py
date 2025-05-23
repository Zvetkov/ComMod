import asyncio
import os
import tempfile
from pathlib import Path

import flet as ft

from commod.game.data import get_title
from commod.game.environment import GameCopy, InstallationContext
from commod.gui import common_widgets as cw
from commod.gui.app_widgets import App, PageHelper
from commod.gui.config import AppSections, Config
from commod.helpers.file_ops import get_internal_file_path
from commod.helpers.parse_ops import init_input_parser
from commod.localisation.service import tr


async def main(page: ft.Page) -> None:
    options = init_input_parser().parse_args()

    page.fonts = {
        "Fira Code": str(get_internal_file_path("assets/fonts/FiraCode-Regular.ttf"))
    }

    page.window.title_bar_hidden = True
    page.title = "ComMod"
    page.scroll = None
    page.window.min_width = 900
    page.window.min_height = 600
    page.padding = 0

    page.theme_mode = ft.ThemeMode.SYSTEM
    page.theme = ft.Theme(color_scheme_seed="#FFA500", visual_density=ft.VisualDensity.COMPACT)
    page.dark_theme = ft.Theme(color_scheme_seed="#FFA500", visual_density=ft.VisualDensity.COMPACT)

    conf = Config(page)
    # at the end of execution, commod tries to create config near itself
    # if we can load it - we will use the data from it, except when overriden from console args
    conf.load_from_file()

    page.window.width = conf.init_width
    page.window.height = conf.init_height
    page.window.left = conf.init_pos_x
    page.window.top = conf.init_pos_y
    page.window.visible = True

    loading_ring = ft.Container(
        ft.ProgressRing(width=300, height=300, color=ft.Colors.PRIMARY_CONTAINER),
        expand=True,
        alignment=ft.alignment.center)

    page.add(loading_ring)
    page.update()
    await asyncio.sleep(0.01)

    # loading distibution context
    # console params can override distribution_dir and target_dir early
    if options.distribution_dir:  # noqa: SIM108
        distribution_dir = options.distribution_dir
    else:
        distribution_dir = conf.current_distro

    install_context: InstallationContext | None = None
    if distribution_dir:
        try:
            install_context = InstallationContext(
                distribution_dir=distribution_dir,
                dev_mode=options.dev)
            install_context.setup_logging_folder()
            install_context.setup_loggers()
        except Exception:
            # TODO: handle individuals exceptions properly if they are not caught lower
            if install_context is not None:
                install_context.logger.exception("[Distro loading error]")

            install_context = InstallationContext(dev_mode=options.dev)
            install_context.setup_loggers(stream_only=True)
    else:
        install_context = InstallationContext(dev_mode=options.dev)
        install_context.setup_loggers(stream_only=True)

    install_context.load_system_info()

    # loading game
    if options.target_dir:  # noqa: SIM108
        target_dir = options.target_dir
    else:
        # if app.config.known_games:
        target_dir = conf.current_game
        # else:
        # TODO: rework this default to work as expected:
        # should detect the game and add to the list as current
        # target_dir = InstallationContext.get_local_config_path()


    # we checked everywhere, so we can try to properly load game
    if target_dir:
        try:
            game = GameCopy()
            game.process_game_install(target_dir)
        except Exception:
            # TODO: Handle exceptions properly
            install_context.logger.exception("[Game loading error]")

            game = GameCopy()
    else:
        game = GameCopy()

    page_helper = PageHelper()

    # TODO: pass 'dev' options further, it's needed in case of changing the context
    app = App(context=install_context,
              game=game,
              config=conf,
              page=page,
              page_helper=page_helper)

    page.window.on_event = app.wrapped_on_window_event
    page.theme_mode = conf.init_theme


    app.logger.info(f"Current lang: {app.config.lang}")

    need_quick_start = (not app.config.game_names
                        and not app.context.distribution_dir
                        and not app.game.game_root_path)

    app.create_sections()

    theme_icon = ft.Icons.BRIGHTNESS_AUTO
    match page.theme_mode:
        case ft.ThemeMode.SYSTEM:
            theme_icon = ft.Icons.BRIGHTNESS_AUTO
        case ft.ThemeMode.DARK:
            theme_icon = ft.Icons.WB_SUNNY_OUTLINED
        case ft.ThemeMode.LIGHT:
            theme_icon = ft.Icons.NIGHTLIGHT_OUTLINED

    rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.SELECTED,
        min_extended_width=160,
        animate_size=ft.animation.Animation(200, ft.AnimationCurve.DECELERATE),
        destinations=[
            ft.NavigationRailDestination(
                icon=ft.Icons.ROCKET_LAUNCH_OUTLINED,
                selected_icon=ft.Icons.ROCKET_LAUNCH,
                label=tr("launch").capitalize()
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.BOOKMARK_BORDER,
                selected_icon=ft.Icons.BOOKMARK,
                label=tr("local_mods").capitalize(),
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.DOWNLOAD_OUTLINED,
                selected_icon=ft.Icons.DOWNLOAD,
                label=tr("download").capitalize()
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.SETTINGS_OUTLINED,
                selected_icon=ft.Icons.SETTINGS,
                label=tr("settings").capitalize()
            ),
            ft.NavigationRailDestination(
                icon=ft.Icons.CONSTRUCTION_OUTLINED,
                selected_icon=ft.Icons.CONSTRUCTION,
                label=tr("modding_tools").capitalize(),
                visible=app.config.modder_mode
            ),
        ],
        trailing=ft.IconButton(
            icon=theme_icon,
            on_click=app.change_theme_mode,
            ref=page_helper.theme_icon_btn,
            selected_icon_color=ft.Colors.ON_SURFACE_VARIANT,
            tooltip=ft.Tooltip(
                message=tr("theme_mode"),
                wait_duration=500)),
        on_change=app.change_page,
    )
    app.rail = rail

    page.remove(loading_ring)

    page.add(
        ft.Row(
            [ft.WindowDragArea(ft.Container(
                 ft.Row([
                     ft.Image(src=str(get_internal_file_path("assets/icons/dem_logo.svg")),
                           width=20,
                           height=20,
                           fit=ft.ImageFit.COVER),
                     ft.Text(get_title(), size=13, weight=ft.FontWeight.W_500),
                     ft.Text("[dev]", size=13, color=ft.Colors.ERROR, weight=ft.FontWeight.BOLD,
                             visible=install_context.dev_mode),
                     ]), padding=6),
                     expand=True),
             cw.TitleButton(ft.Icons.MINIMIZE_ROUNDED,
                            on_click=app.minimize,
                            icon_size=20,
                            ref=page_helper.minimize_btn),
             cw.TitleButton(ft.Icons.CHECK_BOX_OUTLINE_BLANK_ROUNDED,
                            on_click=app.maximize,
                            icon_size=17,
                            ref=page_helper.maximize_btn),
             cw.TitleButton(ft.Icons.CLOSE_ROUNDED,
                            on_click=app.finalize,
                            icon_size=22,
                            hover_color=ft.Colors.RED),
             ],
            spacing=0,
            height=31
        )
    )

    app.content_container.content = loading_ring
    app.content_container.expand = True
    app.content_container.alignment = ft.alignment.top_center
    app.content_container.margin = ft.margin.only(left=0, right=0)

    # add application's root control to the page
    page.add(
        ft.Container(ft.Row([rail, app.content_container]),
                     expand=True,
                     padding=ft.padding.only(left=10, right=10, bottom=10)
                     )
    )
    page.update()
    await asyncio.sleep(0.01)

    if app.context.under_windows:
        app.context.current_session.load_steam_game_paths()
        if app.context.current_session.steam_parsing_error:
            app.logger.debug(app.context.current_session.steam_parsing_error)

    if need_quick_start:
        app.logger.debug("showing quick start")
        # modern settings screen has a built-in flow for quick start
        app.content_container.content = None
        app.content_container.update()
        await app.show_settings()
    else:
        await app.load_distro_async()
        if app.context.distribution_dir and not app.config.current_distro:
            app.logger.debug(f"Added distro to empty config: {app.context.distribution_dir}")
            app.config.add_distro_to_config(app.context.distribution_dir)
        if app.game.game_root_path and not app.config.current_game:
            app.logger.debug(f"Added game to empty config: {app.game.game_root_path}")
            app.config.add_game_to_config(app.game.game_root_path)
            if app.config.current_distro and app.config.current_game:
                app.logger.debug("Automatically switched to local mods page as running with generated config")
                app.config.current_section = AppSections.LOCAL_MODS.value
        elif app.game.game_root_path and app.config.current_game != app.game.game_root_path:
            app.logger.debug(f"Added game to empty config: {app.game.game_root_path}")
            app.config.add_game_to_config(app.game.game_root_path, Path(app.game.game_root_path).stem)
            app.logger.debug(f"Added game passed to args to the config: {app.game.game_root_path}")
        # select_game_from_home
        app.content_container.content = None
        app.content_container.update()
        await app.change_page(index=app.config.current_section)

    if "NUITKA_ONEFILE_PARENT" in os.environ:
        splash_filename = os.path.join(
            tempfile.gettempdir(),
            "onefile_%d_splash_feedback.tmp" % int(os.environ["NUITKA_ONEFILE_PARENT"]),  # noqa: UP031
        )

        if os.path.exists(splash_filename):
          os.unlink(splash_filename)

    page.update()


def start() -> None:
    ft.app(target=main, view=ft.AppView.FLET_APP_HIDDEN)
