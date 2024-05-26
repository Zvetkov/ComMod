import os
import tempfile

import flet as ft
from flet import IconButton, Image, Page, Theme, ThemeVisualDensity

from commod.game.data import get_title
from commod.game.environment import GameCopy, InstallationContext
from commod.gui.app_widgets import App
from commod.gui.common_widgets import title_btn_style
from commod.gui.config import AppSections, Config
from commod.helpers.file_ops import get_internal_file_path
from commod.helpers.parse_ops import init_input_parser
from commod.localisation.service import tr


async def main(page: Page) -> None:
    options = init_input_parser().parse_args()

    page.window_title_bar_hidden = True
    page.title = "ComMod"
    page.scroll = None
    page.window_min_width = 900
    page.window_min_height = 600
    page.padding = 0

    page.theme_mode = ft.ThemeMode.SYSTEM
    page.theme = Theme(color_scheme_seed="#FFA500", visual_density=ThemeVisualDensity.COMPACT)
    page.dark_theme = Theme(color_scheme_seed="#FFA500", visual_density=ThemeVisualDensity.COMPACT)

    conf = Config(page)
    # at the end of execution, commod tries to create config near itself
    # if we can load it - we will use the data from it, except when overriden from console args
    conf.load_from_file()

    # loading distibution context
    # console params can override distribution_dir and target_dir early
    if options.distribution_dir:  # noqa: SIM108
        distribution_dir = options.distribution_dir
    else:
        distribution_dir = conf.current_distro

    if distribution_dir:
        try:
            install_context = InstallationContext(
                distribution_dir=distribution_dir,
                dev_mode=options.dev)
            install_context.setup_logging_folder()
            install_context.setup_loggers()
        except Exception:
            # TODO: handle individuals exceptions properly if they are not caught lower
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
        # TODO: rework for this default to work as expected, should detect the game and add to the list as current
        # target_dir = InstallationContext.get_local_path()


    # we checked everywhere, so we can try to properly load game
    if target_dir:
        try:
            game = GameCopy()
            game.process_game_install(target_dir)
        except Exception as ex:
            # TODO: Handle exceptions properly
            install_context.logger.error(f"[Game loading error] {ex}")

            game = GameCopy()
    else:
        game = GameCopy()

    # TODO: pass 'dev' options further, it's needed in case of changing the context
    app = App(context=install_context,
              game=game,
              config=conf,
              page=page)

    page.on_window_event = app.wrap_on_window_event
    page.window_width = app.config.init_width
    page.window_height = app.config.init_height
    page.window_left = app.config.init_pos_x
    page.window_top = app.config.init_pos_y

    page.theme_mode = app.config.init_theme

    app.logger.info(f"Current lang: {app.config.lang}")

    need_quick_start = (not app.config.game_names
                        and not app.context.distribution_dir
                        and not app.game.game_root_path)

    app.create_sections()

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
                                      on_click=app.change_theme_mode,
                                      ref=page.theme_icon_btn,
                                      selected_icon_color=ft.colors.ON_SURFACE_VARIANT)),
        on_change=app.change_page,
    )
    app.rail = rail

    page.minimize_btn = ft.Ref[IconButton]()
    page.maximize_btn = ft.Ref[IconButton]()
    # title bar to replace system one
    page.add(
        ft.Row(
            [ft.WindowDragArea(ft.Container(
                 ft.Row([
                     Image(src=get_internal_file_path("assets/icons/dem_logo.svg"),
                           width=20,
                           height=20,
                           fit=ft.ImageFit.COVER),
                     ft.Text(get_title(), size=13, weight=ft.FontWeight.W_500)]), padding=6),
                     expand=True),
             ft.IconButton(ft.icons.MINIMIZE_ROUNDED,
                           on_click=app.minimize, icon_size=20,
                           style=title_btn_style(),
                           ref=page.minimize_btn),
             ft.IconButton(ft.icons.CHECK_BOX_OUTLINE_BLANK_ROUNDED,
                           on_click=app.maximize, icon_size=17,
                           style=title_btn_style(),
                           ref=page.maximize_btn),
             ft.IconButton(ft.icons.CLOSE_ROUNDED, on_click=app.finalize, icon_size=22,
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
    page.add(
        ft.Container(ft.Row([rail, app.content_column]),
                     expand=True,
                     padding=ft.padding.only(left=10, right=10, bottom=10)
                     )
    )

    app.context.current_session.load_steam_game_paths()
    if need_quick_start:
        app.logger.debug("showing quick start")
        # modern settings screen has a built-in flow for quick start
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
        # select_game_from_home
        await app.change_page(index=app.config.current_section)

    if "NUITKA_ONEFILE_PARENT" in os.environ:
        splash_filename = os.path.join(
            tempfile.gettempdir(),
            "onefile_%d_splash_feedback.tmp" % int(os.environ["NUITKA_ONEFILE_PARENT"]),
        )

        if os.path.exists(splash_filename):
            os.unlink(splash_filename)
    page.update()


def start() -> None:
    ft.app(target=main)
