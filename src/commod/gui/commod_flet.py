import os
import tempfile

import flet as ft
from commod import _init_input_parser
from flet import IconButton, Image, Page, Theme, ThemeVisualDensity
from game.data import get_title
from game.environment import GameCopy, InstallationContext
from helpers.file_ops import get_internal_file_path
from localisation.service import tr

from .app_widgets import App, DownloadModsScreen, HomeScreen, LocalModsScreen, SettingsScreen
from .config import Config


async def main(page: Page):
    async def maximize(e: ft.ControlEvent) -> None:
        page.window_maximized = not page.window_maximized
        await page.update_async()

    async def minimize(e: ft.ControlEvent) -> None:
        page.window_minimized = True
        await page.update_async()

    async def change_theme_mode(e: ft.ControlEvent) -> None:
        theme = page.theme_mode
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

    def title_btn_style(hover_color: str | None = None) -> ft.ButtonStyle:
        color_dict = {ft.MaterialState.DEFAULT: ft.colors.ON_BACKGROUND}
        if hover_color is not None:
            color_dict[ft.MaterialState.HOVERED] = ft.colors.RED
        return ft.ButtonStyle(
            color=color_dict,
            padding={ft.MaterialState.DEFAULT: 0},
            shape={ft.MaterialState.DEFAULT: ft.RoundedRectangleBorder(radius=2)}
        )

    def create_sections(app: App) -> None:
        app.page.floating_action_button = ft.FloatingActionButton(
            icon=ft.icons.REFRESH_ROUNDED,
            on_click=app.upd_pressed,
            mini=True
            )
        app.home = HomeScreen(app)
        app.local_mods = LocalModsScreen(app)
        app.download_mods = DownloadModsScreen(app)
        app.settings_page = SettingsScreen(app)

        app.content_pages = [app.home, app.local_mods, app.download_mods, app.settings_page]

    async def wrap_on_window_event(e: ft.ControlEvent) -> None:
        if e.data == "close":
            await finalize(e)
        elif e.data in ("unmaximize", "maximize"):
            if page.window_maximized:
                page.icon_maximize.current.icon = ft.icons.FILTER_NONE
                page.icon_maximize.current.icon_size = 15
            else:
                page.icon_maximize.current.icon = ft.icons.CHECK_BOX_OUTLINE_BLANK_ROUNDED
                page.icon_maximize.current.icon_size = 17
            await page.icon_maximize.current.update_async()

    async def finalize(e: ft.ControlEvent) -> None:
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
    page.padding = 0

    page.theme_mode = ft.ThemeMode.SYSTEM
    page.theme = Theme(color_scheme_seed="#FFA500", visual_density=ThemeVisualDensity.COMPACT)
    page.dark_theme = Theme(color_scheme_seed="#FFA500", visual_density=ThemeVisualDensity.COMPACT)

    app = App(context=InstallationContext(dev_mode=options.dev, can_skip_adding_distro=True),
              game=GameCopy(),
              config=Config(page),
              page=page)

    # page.app = app
    # TODO: pass 'dev' options further, it's needed in case of changing the context

    # at the end of each operation, commod tries to create config near itself
    # if we can load it - we will use the data from it, except when overriden from console args

    # TODO: remove if is really duplicate
    # app.config = Config(page
    app.config.load_from_file()

    app.context.setup_loggers(stream_only=True)
    app.context.load_system_info()

    page.window_width = app.config.init_width
    page.window_height = app.config.init_height
    page.window_left = app.config.init_pos_x
    page.window_top = app.config.init_pos_y

    page.theme_mode = app.config.init_theme

    app.logger.info(f"Current lang: {app.config.lang}")

    # if app.config.known_games:
    target_dir = app.config.current_game
    # else:
    # TODO: rework for this default to work as expected, should detect the game and add to the list as current
    # target_dir = InstallationContext.get_local_path()

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

    # TODO: do we want to check env arround binary to detect that we are running in distro directory?
    # local_path = InstallationContext.get_local_path()
    # if (app.context.get_config() is None
    #    and not distribution_dir
    #    and Path(Path(local_path) / "remaster").is_dir()
    #    and Path(Path(local_path) / "patch").is_dir()):
    #     distribution_dir = local_path

    if distribution_dir:
        try:
            # TODO: all distribution validation needs to be async in case of many distro folders present
            app.context.add_distribution_dir(distribution_dir)
            # await app.load_distro_async()
        except Exception as ex:
            # TODO: handle individuals exceptions properly if they are not caught lower
            app.logger.error("[Distro loading error]", exc_info=ex)

    if app.context.distribution_dir:
        app.context.setup_logging_folder()
        app.context.setup_loggers()

    need_quick_start = (not app.config.game_names
                        and not app.context.distribution_dir
                        and not app.game.game_root_path)

    create_sections(app)

    page.theme_icon_btn: ft.Ref[IconButton] = ft.Ref[IconButton]()
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
    app.rail = rail

    page.icon_maximize: ft.Ref[IconButton] = ft.Ref[IconButton]()
    # title bar to replace system one
    await page.add_async(
        ft.Row(
            [ft.WindowDragArea(ft.Container(
                 ft.Row([
                     Image(src=get_internal_file_path("assets/icons/dem_logo.svg"),
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
        # modern settings screen has a built-in flow for quick start
        await app.show_settings()
    else:
        # app.load_distro()
        await app.load_distro_async()
        await app.change_page(index=app.config.current_section)

    if "NUITKA_ONEFILE_PARENT" in os.environ:
        splash_filename = os.path.join(
            tempfile.gettempdir(),
            "onefile_%d_splash_feedback.tmp" % int(os.environ["NUITKA_ONEFILE_PARENT"]),
        )

        if os.path.exists(splash_filename):
            os.unlink(splash_filename)
    await page.update_async()


def start() -> None:
    ft.app(target=main)
