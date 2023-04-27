
import logging
import os
import sys

import qtawesome as qta

from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets
from file_ops import get_internal_file_path
# from __feature__ import true_property

from qtmodern import styles, windows, resources  # resources are being used implicitly
from data import get_title
from environment import InstallationContext, GameCopy

from localisation import tr
from color import br, fcss, css

from errors import ExeIsRunning, ExeNotFound, ExeNotSupported, HasManifestButUnpatched, InvalidGameDirectory,\
                   PatchedButDoesntHaveManifest, WrongGameDirectoryPath,\
                   DistributionNotFound, FileLoggingSetupError, InvalidExistingManifest, ModsDirMissing,\
                   NoModsFound, CorruptedRemasterFiles, DXRenderDllNotFound


def main(options):
    app = QtWidgets.QApplication(sys.argv)
    std_font = QtGui.QFont("Roboto", 10)
    app.setFont(std_font)
    window = MainWindow(app)
    app.window = window
    mw = windows.ModernWindow(window)

    palette = QtWidgets.QApplication.instance().palette()

    qta.set_defaults(color="red",
                     color_active="red",
                     color_on="red")

    mw.resize(1024, 720)
    mw.setMinimumHeight(600)
    mw.setMinimumWidth(800)
    mw.move(QtGui.QGuiApplication.primaryScreen().availableGeometry().center() - mw.rect().center())

    app.dev = options.dev

    # creating dummy objects to fill latter
    app.context = InstallationContext(dev_mode=app.dev, can_skip_adding_distro=True)
    app.context.setup_loggers(stream_only=True)
    app.known_distros = set()

    app.session = app.context.current_session
    app.game = GameCopy()
    app.known_games = set()

    # if nothing else is known, we expect commod to launch inside the game folder
    # with distibution files (ComRem files and optional "mods" directory) around
    distribution_dir = InstallationContext.get_local_path()
    target_dir = distribution_dir

    # console params can override this early
    if options.distribution_dir:
        distribution_dir = options.distribution_dir
    if options.target_dir:
        target_dir = options.target_dir

    # at the end of each operation, commod tries to create aconfig near itself
    # if we can load it - we will use the data from it, except when overriden from console args
    config = InstallationContext.get_config()
    if config is not None:
        if not distribution_dir:
            distribution_dir = config.get_current_distribution()
        if not target_dir:
            target_dir = config.get_current_target()

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

    need_quick_start = (config is None
                        and app.context.distribution_dir is None
                        and app.game.game_root_path is None
                        and not options.skip_wizard)

    if need_quick_start:
        app.context.current_session.load_steam_game_paths()
        window.show_guick_start_wizard()
        window.wizard.destroyed.connect(mw.show)
        window.wizard.destroyed.connect(window.proccess_game_and_distro_setup)
    else:
        mw.show()
        window.proccess_game_and_distro_setup()

    app.exec()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, app) -> None:
        super(MainWindow, self).__init__()

        # setting up application skin and display properties
        self.app = app
        self.setWindowTitle(get_title())

        styles._apply_base_theme(self.app.instance())
        styles.dark(self.app.instance())
        self.create_icons()

        self.logger = logging.getLogger("dem")
        self.logger.debug("Setting up MainTabWidget")

        self.create_actions()

        self.setup_main_tab_widget()
        self.setCentralWidget(self.main_tab_widget)
        self.setup_status_bar()

        self.setup_top_menu()
        self.setup_tool_bar()

        # self.setup_quick_look()

    # def choose_from_steam(self):
    #     steam_game_selector = QuickStart(self.app.context.current_session.steam_game_paths)
    #     steam_game_selector.show()

    # def show_distro_start_wizard(self):
    #     msg_box = QtWidgets.QMessageBox()
    #     msg_box.setWindowTitle(tr("path_to_comrem"))
    #     msg_box.setIconPixmap(self.icons["dir"].pixmap(32, 32))

    #     info = fcss(tr("welcome"), p=True) + br(tr("commod_needs_remaster"))
    #     msg_box.setText(info)

    #     msg_box.setInformativeText(tr("show_path_to"))

    #     choose_dir_btn = msg_box.addButton(tr("choose_path"), QtWidgets.QMessageBox.ActionRole)
    #     discard_btn = msg_box.addButton(tr("later"), QtWidgets.QMessageBox.RejectRole)
    #     msg_box.setDefaultButton(choose_dir_btn)
    #     choose_dir_btn.clicked.connect(self.openDistributionFolder)

    #     msg_box.exec()

    #     if msg_box.clickedButton() == discard_btn:
    #         return None

    def show_guick_start_wizard(self):
        wizard = QuickStart(self.app)
        self.wizard = wizard
        wizard.show()
        # msg_box.setIconPixmap(self.fileDirIconLight.pixmap(32, 32))

        # info = (f'{fcss(tr("welcome"), True)}' + br(tr("commod_needs_game")))

        # discard_btn = msg_box.addButton(tr("later"), QtWidgets.QMessageBox.RejectRole)

        # if self.app.context.current_session.steam_game_paths:
        #     info += fcss(tr("steam_game_found"), css.GREEN, p=True)
        #     choose_from_steam = msg_box.addButton(tr("choose_from_found"), QtWidgets.QMessageBox.ActionRole)
        #     choose_dir_btn = msg_box.addButton(tr("choose_path_manually"), QtWidgets.QMessageBox.ActionRole)
        #     choose_from_steam.clicked.connect(self.choose_from_steam)
        #     msg_box.setDefaultButton(choose_from_steam)
        # else:
        #     choose_dir_btn = msg_box.addButton(tr("choose_path"), QtWidgets.QMessageBox.ActionRole)
        #     msg_box.setInformativeText(tr("show_path_to"))
        #     msg_box.setDefaultButton(choose_dir_btn)
        # choose_dir_btn.clicked.connect(self.openGameFolder)
        # msg_box.setText(info)

        # msg_box.exec()

        # if msg_box.clickedButton() == discard_btn:
        #     return None

    def setup_top_menu(self):
        self.fileMenu = QtWidgets.QMenu("&File", self)
        self.fileMenu.addAction(self.openGameFolderAction)
        self.fileMenu.addAction(self.openDistributionAction)
        self.fileMenu.addSeparator()
        self.fileMenu.addAction(self.quitAction)

        self.viewMenu = QtWidgets.QMenu("&View", self)

        self.settingsMenu = QtWidgets.QMenu("&Settings", self)
        self.settingsMenu.addAction(self.propertiesAction)

        self.aboutMenu = QtWidgets.QMenu("&About", self)
        self.aboutMenu.addAction(self.aboutAction)
        self.aboutMenu.addAction(self.aboutQtAction)

        self.menuBar().addMenu(self.fileMenu)
        self.menuBar().addMenu(self.viewMenu)
        self.menuBar().addMenu(self.settingsMenu)
        self.menuBar().addMenu(self.aboutMenu)

    def create_actions(self):
        self.openGameFolderAction = QtGui.QAction(QtGui.QIcon.fromTheme("folder-open", qta.icon("fa5s.folder-plus")),
                                                  "&Open Game Folder...", self, shortcut="Ctrl+O",
                                                  statusTip="Open folder where Ex Machina is installed",
                                                  triggered=self.openGameFolder)
        self.openDistributionAction = QtGui.QAction(QtGui.QIcon.fromTheme("folder-open", qta.icon("fa5s.folder-plus")),
                                                    "&Open Distribution Folder...", self, shortcut="Ctrl+Shift+O",
                                                    statusTip="Open folder where ComRem and mods are located",
                                                    triggered=self.openDistributionFolder)

        self.quitAction = QtGui.QAction("&Quit", self, shortcut="Ctrl+Q", statusTip="Quit the application",
                                        triggered=self.close_application)

        self.propertiesAction = QtGui.QAction(QtGui.QIcon.fromTheme("application-properties",
                                              qta.icon("fa5s.cog")),
                                              "&Properties", self, shortcut="Ctrl+P",
                                              statusTip="Application properties", triggered=self.properties)

        self.aboutAction = QtGui.QAction("&About ComMod", self, statusTip="Show the ComMod About box",
                                         triggered=self.about)

        self.aboutQtAction = QtGui.QAction("About &Qt", self, statusTip="Show the Qt library's About box",
                                           triggered=QtWidgets.QApplication.instance().aboutQt)

    def openGameFolder(self, known_game: str = ""):
        self.update_status("openGameFolder placeholder", logging.DEBUG)
        if known_game:
            directory_name = known_game
        else:
            dir_dialogue = QtWidgets.QFileDialog(self)
            dir_dialogue.setFileMode(QtWidgets.QFileDialog.Directory)
            directory_name = dir_dialogue.getExistingDirectory(self, tr("path_to_game"))
            if not directory_name:
                return
        validated, _ = GameCopy.validate_game_dir(directory_name)
        if validated:
            err_msg = ""
            err_detailed = ""
            info_msg = ""
            info_detailed = ""

            try:
                exe_name = GameCopy.get_exe_name(directory_name)
                exe_version = GameCopy.get_exe_version(exe_name)

                if exe_version is not None:
                    validated_exe = GameCopy.is_compatch_compatible_exe(exe_version)
                    if validated_exe:
                        # TODO: handle "patched but doesn't have manifest"
                        if self.app.game.target_exe is not None:
                            self.app.game = GameCopy()
                        self.app.game.process_game_install(directory_name)
                    else:
                        err_msg = fcss(f'{tr("unsupported_exe_version")}: {exe_version}',
                                       [css.RED, css.BOLD], p=True)
                else:
                    err_msg = fcss(f'{tr("exe_is_running")}: {Path(exe_name).name}',
                                   [css.RED, css.BOLD], p=True)
            except PatchedButDoesntHaveManifest as ex:
                info_msg = fcss(f'{tr("install_leftovers")}',
                                [css.YELLOW, css.BOLD], p=True)
                info_detailed = f"{ex!r}"
            except HasManifestButUnpatched as ex:
                info_msg = fcss(f'{tr("install_leftovers")}',
                                [css.YELLOW, css.BOLD], p=True)
                info_detailed = f"{ex!r}"
            except Exception as ex:
                err_detailed = f"{ex!r}"

            if err_msg or err_detailed:
                error_box = QtWidgets.QMessageBox()
                error_box.setIcon(QtWidgets.QMessageBox.Critical)
                error_box.setWindowTitle(tr("path_to_game"))

                if not err_msg:
                    err_msg = fcss(tr("failed_and_cleaned"), [css.RED, css.BOLD], p=True)

                err_msg += f"{tr('commod_needs_game')}"
                error_box.setText(err_msg)
                if err_detailed:
                    error_box.setDetailedText(err_detailed)
                error_box.exec()
            if info_msg:
                info_box = QtWidgets.QMessageBox()
                info_box.setIcon(QtWidgets.QMessageBox.Information)
                info_box.setWindowTitle(tr("path_to_game"))

                info_msg += f"{tr('commod_needs_game')}"
                info_box.setText(info_msg)
                info_box.setDetailedText(info_detailed)
                info_box.exec()
        else:
            error_box = QtWidgets.QMessageBox()
            error_box.setIcon(QtWidgets.QMessageBox.Critical)
            error_box.setWindowTitle(tr("path_to_game"))
            err_msg = fcss(tr("target_dir_missing_files"), [css.RED, css.BOLD], p=True)
            err_msg += f"{tr('commod_needs_game')}"
            error_box.setText(err_msg)
            error_box.exec()

        self.proccess_game_and_distro_setup()

    def openDistributionFolder(self, known_distro: str = ""):
        self.update_status("openGameFolder placeholder", logging.DEBUG)
        if known_distro:
            directory_name = known_distro
        else:
            dir_dialogue = QtWidgets.QFileDialog(self)
            dir_dialogue.setFileMode(QtWidgets.QFileDialog.Directory)
            directory_name = dir_dialogue.getExistingDirectory(self, tr("path_to_comrem"))
            if not directory_name:
                return

        validated = InstallationContext.validate_distribution_dir(directory_name)
        if validated:
            try:
                self.app.context.add_distribution_dir(directory_name)
            except Exception as ex:
                error_box = QtWidgets.QMessageBox()
                error_box.setIcon(QtWidgets.QMessageBox.Critical)
                error_box.setWindowTitle(tr("path_to_comrem"))
                err_msg = fcss(tr("failed_and_cleaned"), [css.RED, css.BOLD], p=True)
                err_msg += f"{br(tr('commod_needs_remaster'))}"
                error_box.setText(err_msg)
                error_box.setDetailedText(str(ex))
                error_box.exec()
        else:
            error_box = QtWidgets.QMessageBox()
            error_box.setIcon(QtWidgets.QMessageBox.Critical)
            error_box.setWindowTitle(tr("path_to_comrem"))
            err_msg = fcss(tr("target_dir_missing_files"), [css.RED, css.BOLD], p=True)
            err_msg += f"{br(tr('commod_needs_remaster'))}"
            error_box.setText(err_msg)
            error_box.exec()

        self.proccess_game_and_distro_setup()

    def close_application(self):
        self.app.quit()

    def properties(self):
        self.update_status("properties placeholder", logging.DEBUG)

    def about(self):
        QtWidgets.QMessageBox.about(self, "About ComMod",
                                    "Placeholder <b>ComMod</b> description "
                                    "something something")

    def setup_tool_bar(self):
        self.fileToolBar = self.addToolBar("File&Edit")
        self.fileToolBar.addAction(self.openGameFolderAction)
        self.game_selector = QtWidgets.QComboBox()
        self.game_selector.setMinimumWidth(300)
        self.game_selector.addItem(f"{tr('path_to_game')} [{tr('havent_been_chosen')}]", 'dummy')
        self.game_selector.setDisabled(True)
        self.game_selector.currentIndexChanged.connect(self.game_selector_changed_game)
        self.fileToolBar.addWidget(self.game_selector)
        self.fileToolBar.addSeparator()

        self.fileToolBar.addAction(self.openDistributionAction)
        self.distro_selector = QtWidgets.QComboBox()
        self.distro_selector.setMinimumWidth(300)
        self.distro_selector.addItem(f"{tr('path_to_comrem')} [{tr('havent_been_chosen')}]", 'dummy')
        self.distro_selector.setDisabled(True)
        self.distro_selector.currentIndexChanged.connect(self.distro_selector_changed_distro)
        self.fileToolBar.addWidget(self.distro_selector)
        self.fileToolBar.addSeparator()
        spacer = QtWidgets.QWidget()
        spacer.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.fileToolBar.addWidget(spacer)
        self.fileToolBar.addAction(self.propertiesAction)

    def game_selector_changed_game(self):
        current_game = self.game_selector.currentData()
        if current_game != self.app.game.game_root_path:
            previous_game = self.app.game
            self.app.game = GameCopy()
            self.openGameFolder(current_game)
            if self.app.game.game_root_path is None:
                self.app.game = previous_game
                previous_index = self.game_selector.findData(self.app.game.game_root_path)
                self.game_selector.setCurrentIndex(previous_index)
                # TODO: handler case when all game copies are broken inside the session
                self.setup_notice.update_view()
            else:
                self.app.context.new_session()
            previous_game = None

    def distro_selector_changed_distro(self):
        current_distro = self.distro_selector.currentData()
        if current_distro != self.app.context.distribution_dir:
            previous_context = self.app.context
            self.app.context = InstallationContext(dev_mode=self.app.dev, can_skip_adding_distro=True)
            self.openDistributionFolder(current_distro)
            if self.app.context.distribution_dir is None:
                self.app.context = previous_context
                previous_index = self.distro_selector.findData(self.app.context.distribution_dir)
                self.distro_selector.setCurrentIndex(previous_index)
                self.setup_notice.update_view()
            previous_context = None

    def setup_status_bar(self):
        self.statusBar().showMessage("Ready")

    def update_status(self, msg: str, log_level: int = None):
        if log_level is None:
            log_level = logging.INFO
        self.statusBar().showMessage(msg)
        self.logger.log(log_level, msg)

    def setup_quick_look(self):
        self.objectViewDock = QtWidgets.QDockWidget(tr("QuickLook"))
        self.objectViewDock.setMinimumSize(205, 210)
        self.objectViewDock.setAllowedAreas(QtCore.Qt.LeftDockWidgetArea | QtCore.Qt.RightDockWidgetArea)
        self.prot_grid = QtWidgets.QVBoxLayout()

        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)

        inner_frame = QtWidgets.QFrame(scroll_area)
        inner_frame.setLayout(self.prot_grid)

        scroll_area.setWidget(inner_frame)

        quicklook_promt = QtWidgets.QLabel(tr("QuickLookPromt"))
        self.prot_grid.addWidget(quicklook_promt)
        spacer = QtWidgets.QSpacerItem(20, 40, QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Expanding)
        self.prot_grid.addItem(spacer)

        self.objectViewDock.setWidget(scroll_area)

        self.addDockWidget(QtCore.Qt.RightDockWidgetArea, self.objectViewDock)
        self.viewMenu.addAction(self.objectViewDock.toggleViewAction())

    def create_icons(self):
        module_path = Path(os.path.abspath(__file__))
        ui_path = os.path.join(module_path.parent, "ui")
        self.icons = {}
        self.icons["dir"] = QtGui.QIcon(os.path.join(ui_path, "icons/filedir_white.svg"))
        self.icons["gear"] = QtGui.QIcon(os.path.join(ui_path, "icons/gear_white.svg"))
        self.icons["undo"] = QtGui.QIcon(os.path.join(ui_path, "icons/undo_white.svg"))
        self.icons["redo"] = QtGui.QIcon(os.path.join(ui_path, "icons/redo_white.svg"))
        self.icons["save"] = QtGui.QIcon(os.path.join(ui_path, "icons/save_white.svg"))
        self.icons["check"] = self.app.style().standardIcon(QtWidgets.QStyle.SP_DialogApplyButton)
        self.icons["cross"] = self.app.style().standardIcon(QtWidgets.QStyle.SP_MessageBoxCritical)

    def setup_main_tab_widget(self):
        self.main_tab_widget = QtWidgets.QTabWidget()
        self.main_tab_widget.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)

        # filtering and sorting model
        # self.proxy_model = QtCore.QSortFilterProxyModel()
        # self.proxy_model.setDynamicSortFilter(True)
        # self.proxy_model.setRecursiveFilteringEnabled(True)

        # self.load_prototypes_to_source_model()

        # tree view to display in tab
        # tab_mod_explorer = QtWidgets.QWidget()
        # self.tree_mod_explorer = QtWidgets.QTreeView()
        # self.tree_mod_explorer.setModel(self.proxy_model)
        # self.tree_mod_explorer.setSortingEnabled(True)
        # self.tree_mod_explorer.setColumnWidth(0, 180)
        # self.tree_mod_explorer.setColumnWidth(1, 150)

        # self.main_tab_widget.addTab(tab_mod_explorer, "&Mod Explorer")
        self.setup_notice = SetupStateInfoNotice(self)
        self.main_tab_widget.addTab(self.setup_notice, f'&{tr("finish_setup")}')
        index_setup_notice = self.main_tab_widget.indexOf(self.setup_notice)
        self.main_tab_widget.setTabVisible(index_setup_notice, False)

        # self.comrem_wizard = LocalModsWidget(self)
        # self.main_tab_widget.addTab(self.comrem_wizard, f'&Community Remaster / Patch')
        # index_comrem_wizard = self.main_tab_widget.indexOf(self.comrem_wizard)
        # self.main_tab_widget.setTabVisible(index_comrem_wizard, False)

        self.game_home_screen = GameHomeScreen(self)
        self.main_tab_widget.addTab(self.game_home_screen, f'&{tr("game_info")}')
        index_game_home = self.main_tab_widget.indexOf(self.game_home_screen)
        self.main_tab_widget.setTabVisible(index_game_home, False)

    def proccess_game_and_distro_setup(self):
        if self.app.game.game_root_path is not None:
            index_of_game = self.game_selector.findData(self.app.game.game_root_path)
            if index_of_game == -1:
                self.game_selector.addItem(self.app.game.display_name, self.app.game.game_root_path)
                index_of_game = self.game_selector.findData(self.app.game.game_root_path)
            self.game_selector.setCurrentIndex(index_of_game)
            self.app.known_games.add(self.app.game.game_root_path)
            # enabling dropdown if we have multiple managed game distros
            have_multiple_games = len(self.app.known_games) > 1
            self.game_selector.setEnabled(have_multiple_games)

            dummy_index = self.game_selector.findData("dummy")
            if dummy_index != -1:
                self.game_selector.removeItem(dummy_index)

        if self.app.context.distribution_dir is not None:
            index_of_distro = self.distro_selector.findData(self.app.context.distribution_dir)
            if index_of_distro == -1:
                self.distro_selector.addItem(self.app.context.short_path, self.app.context.distribution_dir)
                index_of_distro = self.distro_selector.count()
                index_of_distro = self.distro_selector.findData(self.app.context.distribution_dir)
            self.distro_selector.setCurrentIndex(index_of_distro)
            self.app.known_distros.add(self.app.context.distribution_dir)
            have_multiple_distros = len(self.app.known_distros) > 1
            self.distro_selector.setEnabled(have_multiple_distros)

            dummy_index = self.distro_selector.findData("dummy")
            if dummy_index != -1:
                self.distro_selector.removeItem(dummy_index)

        if self.app.game.game_root_path is None or self.app.context.distribution_dir is None:
            index = self.main_tab_widget.indexOf(self.setup_notice)
            self.main_tab_widget.setTabVisible(index, True)
        else:
            index = self.main_tab_widget.indexOf(self.setup_notice)
            self.main_tab_widget.setTabVisible(index, False)

            game_home_screen_index = self.main_tab_widget.indexOf(self.game_home_screen)
            self.game_home_screen.update_game(self.app.game, self.app.context)
            self.main_tab_widget.setTabVisible(game_home_screen_index, True)

        self.setup_notice.update_view()


class SetupStateInfoNotice(QtWidgets.QWidget):
    def __init__(self, parent: MainWindow):
        QtWidgets.QWidget.__init__(self)
        self.app = parent.app
        self.icons = parent.icons

        layout = QtWidgets.QVBoxLayout(self)

        self.need_game = QtWidgets.QWidget()
        layout_need_game = QtWidgets.QVBoxLayout(self.need_game)
        need_game_intro = QtWidgets.QLabel(fcss(tr("commod_needs_game"), [css.BLUE, css.BOLD]))
        # need_game_intro.setStyleSheet(f'"{css.ORANGE};"')
        need_game_hyper = ClickableIconLabel(text=fcss(tr("add_game_using_btn")),
                                             icon=qta.icon("fa5s.folder-open"))
        need_game_hyper.clicked.connect(parent.openGameFolder)
        layout_need_game.addWidget(need_game_intro)
        layout_need_game.addWidget(need_game_hyper)

        self.need_distro = QtWidgets.QWidget()
        layout_need_distro = QtWidgets.QVBoxLayout(self.need_distro)
        need_distro_intro = QtWidgets.QLabel(fcss(tr("commod_needs_remaster"), [css.BLUE, css.BOLD]))

        need_distro_hyper = ClickableIconLabel(text=fcss(tr("add_distro_using_btn")),
                                               icon=qta.icon("fa5s.folder-open"))
        need_distro_hyper.clicked.connect(parent.openDistributionFolder)
        layout_need_distro.addWidget(need_distro_intro)
        layout_need_distro.addWidget(need_distro_hyper)

        layout.addWidget(self.need_game)
        layout.addWidget(self.need_distro)
        layout.addStretch()

    def update_view(self):
        self.need_game.setVisible(self.app.game.game_root_path is None)
        self.need_distro.setVisible(self.app.context.distribution_dir is None)


class GameHomeScreen(QtWidgets.QWidget):
    def __init__(self, parent: MainWindow):
        QtWidgets.QWidget.__init__(self)
        game_home_layout = QtWidgets.QVBoxLayout(self)
        icon_and_info_layout = QtWidgets.QHBoxLayout()
        icon_layout = QtWidgets.QVBoxLayout()
        info_layout = QtWidgets.QVBoxLayout()
        info_layout.setSpacing(15)
        info_layout.setContentsMargins(15, 0, 128, 0)
        bottom_bar_layout = QtWidgets.QHBoxLayout()
        bottom_bar_widget = QtWidgets.QWidget()

        icon_and_info_widget = QtWidgets.QWidget()
        left_stretch = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        left_stretch.setHorizontalStretch(1)
        right_stretch = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)
        right_stretch.setHorizontalStretch(6)

        game_icon_widget = QtWidgets.QWidget()
        game_icon_widget.setSizePolicy(left_stretch)
        game_icon_widget.setLayout(icon_layout)
        game_icon = ResizableIconLabel()
        game_icon.setScaledContents(1)
        game_icon.setMinimumSize(1, 1)
        game_icon_widget.setMaximumWidth(256)
        game_icon_pixmap = QtGui.QPixmap(get_internal_file_path("icons/hta_comrem.png"))
        game_icon.setPixmap(game_icon_pixmap)  # .scaled(64, 64, QtCore.Qt.KeepAspectRatio, QtCore.Qt.FastTransformation)
        # game_icon_widget.setMaximumWidth(100)
        # game_icon.setAlignment(QtCore.Qt.AlignTop)
        game_icon.setAlignment(QtCore.Qt.AlignHCenter)
        icon_layout.addWidget(game_icon)
        icon_layout.addStretch()

        game_info_widget = QtWidgets.QWidget()
        game_info_widget.setSizePolicy(right_stretch)

        game_home_layout.addWidget(icon_and_info_widget)
        game_home_layout.addWidget(bottom_bar_widget)

        icon_and_info_widget.setLayout(icon_and_info_layout)
        icon_and_info_layout.addWidget(game_icon_widget)
        icon_and_info_layout.addWidget(game_info_widget)

        game_info_widget.setLayout(info_layout)
        label_name = QtWidgets.QLabel("Game Name")
        header_font = QtGui.QFont()
        header_font.setPointSize(22)
        header_font.setBold(True)
        label_name.setFont(header_font)

        label_version = QtWidgets.QLabel(fcss(tr("Some additional info about the game"), [css.ORANGE, css.BOLD]))
        version_font = QtGui.QFont()
        version_font.setPointSize(10)
        label_version.setFont(version_font)

        label_opt_content = QtWidgets.QLabel(fcss(tr("* Optional content: some_thing, and_other_thing"), [css.BLUE, css.BOLD]))
        label_opt_content.setFont(version_font)

        mods_label = QtWidgets.QLabel(fcss(tr("Other mod"), [css.BLUE, css.BOLD]))
        mods_label.setFont(version_font)

        hor_line = QHLine()
        hor_line.setMinimumHeight(30)

        link_install_mods = ClickableIconLabel(text=fcss(tr("install_mods")),
                                               icon=qta.icon("fa5s.wrench"))

        link_download_mods = ClickableIconLabel(text=fcss(tr("download_mods")),
                                                icon=qta.icon("fa5s.download"))

        link_backup_game = ClickableIconLabel(text=fcss(tr("backup_game")),
                                              icon=qta.icon("mdi6.backup-restore"))

        button_launch_game = QtWidgets.QPushButton(tr("launch_game_button"))
        # button_launch_game = QtWidgets.QToolButton()
        # self.openGameFolderAction
        # button_launch_game.setMenu(parent.fileToolBar)
        # button_launch_game.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        # button_launch_game.setDefaultAction(parent.openGameFolderAction)
        button_launch_game.setMinimumSize(160, 80)
        button_launch_game.setMaximumSize(320, 160)
        button_launch_game.setFont(header_font)

        info_layout.addWidget(label_name)
        info_layout.addWidget(label_version)
        info_layout.addWidget(label_opt_content)
        info_layout.addWidget(mods_label)
        info_layout.addWidget(hor_line)
        info_layout.addWidget(link_install_mods)
        info_layout.addWidget(link_download_mods)
        info_layout.addWidget(link_backup_game)
        info_layout.addStretch()
        info_layout.addWidget(button_launch_game)
        info_layout.addStretch()

        bottom_bar_widget.setLayout(bottom_bar_layout)
        our_discord_label = ClickableIconLabel(text=fcss(tr("our_discord")),
                                               icon=qta.icon("fa5b.discord"),
                                               icon_size=24)
        our_discord_label.setMinimumWidth(100)
        our_discord_label.setContentsMargins(50, 0, 0, 0)
        our_discord_label.setAlignment(QtCore.Qt.AlignCenter)
        our_github_label = ClickableIconLabel(text=fcss(tr("our_github")),
                                              icon=qta.icon("fa5b.github"),
                                              icon_size=24)
        our_github_label.setMinimumWidth(100)
        our_github_label.setAlignment(QtCore.Qt.AlignCenter)
        bottom_bar_layout.addWidget(our_discord_label)
        bottom_bar_layout.addWidget(our_github_label)
        bottom_bar_layout.addStretch()

        self.game_icon_label = game_icon
        self.game_name_label = label_name
        self.game_version_label = label_version
        self.additional_content_label = label_opt_content
        self.mods_label = mods_label
        self.install_mods_label = link_install_mods
        self.download_mods_label = link_download_mods
        self.backup_game_label = link_backup_game
        self.start_game_btn = button_launch_game

    def update_game(self, game: GameCopy, context: InstallationContext):
        if game.installment == "exmachina":
            if "ComRemaster" in game.exe_version:
                game_icon = get_internal_file_path("icons/hta_comrem.png")
            else:
                game_icon = get_internal_file_path("icons/original_hta.png")
        elif game.installment == "m113":
            game_icon = get_internal_file_path("icons/original_m113.png")
        elif game.installment == "arcade":
            game_icon = get_internal_file_path("icons/original_arcade.png")
        else:
            game_icon = None

        if game_icon is None:
            game_icon = qta.icon("fa5s.question")
        else:
            game_icon = QtGui.QPixmap(game_icon)

        self.game_icon_label.setVisible(False)  # to prevent flicker on icon change 
        self.game_icon_label.setPixmap(game_icon)
        self.game_icon_label.setVisible(True)

        self.game_name_label.setText(game.installment)

        game_version_text = ""
        game_optional_content = ""
        self.mods_label.clear()
        self.mods_label.setVisible(False)

        game.load_installed_descriptions(context.validated_mod_configs)
        if game.installed_descriptions:
            mods = set(game.installed_content)
            standard_mods = set(("community_patch", "community_remaster"))

            comrem_desc = game.installed_descriptions.get("community_remaster")
            compatch_desc = game.installed_descriptions.get("community_patch")

            if comrem_desc is not None:
                comrem_desc = comrem_desc.split("\n")
                game_version_text = comrem_desc[0]
                game_optional_content = comrem_desc[1]
            elif compatch_desc is not None:
                compatch_desc = compatch_desc.split("\n")
                game_version_text = compatch_desc[0]

            custom_mods = mods.difference(standard_mods)
            if custom_mods:
                mods_text = ""
                for mod_desc in custom_mods:
                    mod_desc_split = game.installed_descriptions[mod_desc].split("\n")
                    mod_version = mod_desc_split[0]
                    mod_optional_content = mod_desc_split[1]
                    mods_text += fcss(mod_version, [css.ORANGE, css.BOLD]) + "<br>"
                    mods_text += fcss(mod_optional_content, [css.BLUE, css.BOLD])
                    mods_text += "<br>"
                self.mods_label.setVisible(True)
                self.mods_label.setText(mods_text)
            else:
                self.mods_label.clear()
                self.mods_label.setVisible(False)
        else:
            if game.exe_version == "Clean 1.02":
                game_version_text = game.exe_version
            elif game.leftovers:
                game_version_text = game.exe_version + " exe"
                game_optional_content = fcss(tr("install_leftovers"), css.RED)
            else:
                raise NotImplementedError("Not implemented version handler on game home screen")

        if game_version_text:
            self.game_version_label.setVisible(True)
            self.game_version_label.setText(fcss(game_version_text, [css.ORANGE, css.BOLD]))
        else:
            self.game_version_label.setVisible(False)

        if game_optional_content:
            self.additional_content_label.setVisible(True)
            self.additional_content_label.setText(fcss(game_optional_content, [css.BLUE, css.BOLD]))
        else:
            self.additional_content_label.setVisible(False)

# class LocalModsWidget(QtWidgets.QWidget):
#     def __init__(self, parent: MainWindow):
#         QtWidgets.QWidget.__init__(self)
#         self.app = parent.app
#         self.icons = parent.icons

#         layout = QtWidgets.QVBoxLayout(self)

#         self.mods_table = QtWidgets.QTableWidget(columns=8)
#         comrem_name = QtWidgets.QLabel(fcss(tr("comrem_name"), [css.BLUE, css.BOLD]))
#         # need_game_intro.setStyleSheet(f'"{css.ORANGE};"')
#         need_game_hyper = ClickableIconLabel(text=fcss(tr("add_game_using_btn")),
#                                              icon=qta.icon("fa5s.folder-open"))
#         need_game_hyper.clicked.connect(parent.openGameFolder)
#         # layout_need_game.addWidget(need_game_intro)
#         # layout_need_game.addWidget(need_game_hyper)

#         self.need_distro = QtWidgets.QWidget()
#         layout_need_distro = QtWidgets.QVBoxLayout(self.need_distro)
#         need_distro_intro = QtWidgets.QLabel(fcss(tr("commod_needs_remaster"), [css.BLUE, css.BOLD]))

#         need_distro_hyper = ClickableIconLabel(text=fcss(tr("add_distro_using_btn")),
#                                                icon=qta.icon("fa5s.folder-open"))
#         need_distro_hyper.clicked.connect(parent.openDistributionFolder)
#         layout_need_distro.addWidget(need_distro_intro)
#         layout_need_distro.addWidget(need_distro_hyper)

#         layout.addWidget(self.need_game)
#         layout.addWidget(self.need_distro)
#         layout.addStretch()


class ClickableLabel(QtWidgets.QLabel):
    clicked = QtCore.Signal()

    def __init__(self, text: str = "", parent: QtWidgets.QWidget | None = None) -> None:
        QtWidgets.QLabel.__init__(self, text, parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover)
        # self.setStyleSheet("QLabel:hover {color: MediumPurple; text-decoration: underline;}")

    def mousePressEvent(self, ev: QtGui.QMouseEvent) -> None:
        self.clicked.emit()


class ClickableIcon(qta.IconWidget):
    clicked = QtCore.Signal()

    def __init__(self, *args, **kwargs) -> None:
        qta.IconWidget.__init__(self, *args, **kwargs)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover)
        # self.setStyleSheet("QLabel:hover {color: MediumPurple; text-decoration: underline;}")

    def mousePressEvent(self, ev: QtGui.QMouseEvent) -> None:
        self.clicked.emit()


class ClickableIconLabel(QtWidgets.QWidget):
    clicked = QtCore.Signal()

    def __init__(self, icon: QtGui.QIcon = None,
                 text="", final_stretch=True, icon_size=16):
        QtWidgets.QWidget.__init__(self)
        self.icon_size = QtCore.QSize(icon_size, icon_size)
        hor_spacing = 2
        # self.setMinimumHeight(icon_size)

        layout = QtWidgets.QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)

        self.icon_label = ClickableIcon()
        if icon is not None:
            self.set_icon(icon)
            # self.icon_label.setMinimumSize(self.icon_size)

        self.text_label = ClickableLabel(text)
        # self.text_label.setMinimumHeight(icon_size)

        layout.addWidget(self.icon_label)
        layout.addSpacing(hor_spacing)
        layout.addWidget(self.text_label)

        self.icon_label.clicked.connect(self.clicked_parts)
        self.text_label.clicked.connect(self.clicked_parts)

        if final_stretch:
            layout.addStretch()

    def clicked_parts(self):
        self.clicked.emit()

    def set_icon(self, icon):
        self.icon_label.setIconSize(self.icon_size)
        self.icon_label.setIcon(icon)

    def setAlignment(self, alignment_flag):
        self.text_label.setAlignment(alignment_flag)


class QuickStart(QtWidgets.QWidget):
    def __init__(self, app: QtWidgets.QApplication):
        QtWidgets.QWidget.__init__(self)
        self.icons = app.window.icons
        self.logger = logging.getLogger("dem")
        self.app = app
        self.mw = windows.ModernWindow(self, disable_maximization=True)
        self.mw.setWindowTitle(tr("quick_start"))
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)

        self.game_dir = None
        self.distro_dir = None

        box_layout = QtWidgets.QVBoxLayout(self)

        info_widget = QtWidgets.QWidget()
        info_layout = QtWidgets.QHBoxLayout(info_widget)
        info_icon = qta.IconWidget()
        info_icon.setIcon(qta.icon("fa5s.folder-open"))
        info_label = QtWidgets.QLabel(fcss(tr("welcome")))

        info_layout.addWidget(info_icon, 30, QtCore.Qt.AlignCenter)
        info_layout.addWidget(info_label, 70)

        distro_widget = QtWidgets.QWidget()
        distro_layout = QtWidgets.QGridLayout(distro_widget)
        distro_label = QtWidgets.QLabel(tr("commod_needs_remaster"))
        distro_button = QtWidgets.QPushButton(tr("choose_path"), self)
        distro_button.setMinimumWidth(130)
        distro_button.clicked.connect(self.add_distro_folder)
        distro_status_icon = qta.IconWidget()
        self.distro_status_icon = distro_status_icon
        distro_status_icon.setIcon(qta.icon("fa5s.folder-open"))

        distro_edit = QtWidgets.QLineEdit()
        self.distro_edit = distro_edit
        distro_edit.editingFinished.connect(self.distro_edit_entered)
        distro_edit.returnPressed.connect(self.distro_edit_on_enter)
        # distro_edit.c.lostFocus.connect(self.distro_edit_entered)
        distro_edit.setPlaceholderText(tr("ask_to_choose_path"))

        distro_layout.addWidget(distro_label, 0, 0, 1, 3)
        distro_layout.addWidget(distro_status_icon, 1, 0)
        distro_layout.addWidget(distro_edit, 1, 1)
        distro_layout.addWidget(distro_button, 1, 2, 1, 2)

        game_widget = QtWidgets.QWidget()
        game_layout = QtWidgets.QGridLayout(game_widget)

        game_label = QtWidgets.QLabel(tr("commod_needs_game"))
        game_label.setContentsMargins(10, 0, 0, 0)

        steam_widget = QtWidgets.QWidget()
        steam_layout = QtWidgets.QGridLayout(steam_widget)

        steam_label = QtWidgets.QLabel(tr("steam_game_found"))
        steam_label.setFixedHeight(20)

        steam_dirs_list = QtWidgets.QComboBox()
        steam_dirs_list.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        steam_dirs_list.setContentsMargins(10, 0, 0, 0)
        self.steam_dirs_list = steam_dirs_list
        steam_dirs_list.addItems(self.app.context.current_session.steam_game_paths)
        # TODO: potential bug if now steam game copies found in the system?
        steam_dirs_list.setCurrentIndex(steam_dirs_list.findText(self.app.context.current_session.steam_game_paths[0]))

        steam_btn_agree = QtWidgets.QPushButton(tr("choose_found"), self)
        steam_btn_agree.setMinimumWidth(130)
        steam_btn_agree.clicked.connect(self.steam_choosen)

        steam_layout.addWidget(steam_label, 0, 0, 1, 3)
        steam_layout.addWidget(steam_dirs_list, 1, 0)
        steam_layout.addWidget(steam_btn_agree, 1, 2, 1, 1)
        # steam_layout.setAlignment(steam_btn_agree, QtCore.Qt.AlignHCenter)

        game_status_icon = qta.IconWidget()
        self.game_status_icon = game_status_icon
        game_status_icon.setIcon(qta.icon("fa5s.folder-open"))

        game_edit = QtWidgets.QLineEdit()
        self.game_edit = game_edit
        game_edit.editingFinished.connect(self.game_edit_entered)
        game_edit.returnPressed.connect(self.game_edit_on_enter)
        game_edit.setPlaceholderText(tr("ask_to_choose_path"))

        game_button = QtWidgets.QPushButton(tr("choose_path_manually"), self)
        game_button.setMinimumWidth(130)
        game_button.clicked.connect(self.add_game_folder)

        game_layout.addWidget(game_status_icon, 0, 0)
        game_layout.addWidget(game_edit, 0, 1)
        game_layout.addWidget(game_button, 0, 2, 1, 2)

        question_widget = QtWidgets.QLabel(fcss(tr("you_can_postpone_but"), css.GOLD))
        question_widget.setContentsMargins(0, -40, 0, 0)
        question_widget.setAlignment(QtCore.Qt.AlignCenter)

        buttons_widget = QtWidgets.QWidget()
        buttons_layout = QtWidgets.QHBoxLayout(buttons_widget)
        button_agree = QtWidgets.QPushButton(tr("confirm_choice"), self)
        # button_agree.setStyleSheet('QPushButton {color: lightgreen;}')
        self.button_agree = button_agree
        button_agree.setDisabled(True)
        button_agree.clicked.connect(self.load_env_from_wizard)
        button_reject = QtWidgets.QPushButton(tr("later"), self)
        buttons_layout.addWidget(button_agree)
        buttons_layout.addWidget(button_reject)

        button_reject.clicked.connect(self.close)

        spacer1 = QtWidgets.QSpacerItem(0, 20,
                                        QtWidgets.QSizePolicy.Expanding,
                                        QtWidgets.QSizePolicy.Fixed)
        spacer2 = QtWidgets.QSpacerItem(0, 0,
                                        QtWidgets.QSizePolicy.Expanding,
                                        QtWidgets.QSizePolicy.Expanding)

        box_layout.setSpacing(0)
        box_layout.addWidget(info_widget)
        box_layout.addWidget(distro_widget)
        box_layout.addItem(spacer1)
        box_layout.addWidget(game_label)
        box_layout.addWidget(steam_widget)
        box_layout.addWidget(game_widget)
        box_layout.addItem(spacer2)
        box_layout.addWidget(question_widget)
        box_layout.addWidget(buttons_widget)

    def show(self):
        if not self.isVisible():
            self.mw.setMaximumSize(900, 440)
            self.mw.move(QtGui.QGuiApplication.primaryScreen().availableGeometry().center() - self.rect().center())
            self.mw.show()
        else:
            self.logger.debug("Already visible")

    def add_game_folder(self):
        dir_dialogue = QtWidgets.QFileDialog(self)
        dir_dialogue.setFileMode(QtWidgets.QFileDialog.Directory)
        directory_name = dir_dialogue.getExistingDirectory(self, tr("path_to_game"))
        if directory_name:
            self.update_game_edit(str(Path(directory_name)))

    def add_distro_folder(self):
        dir_dialogue = QtWidgets.QFileDialog(self)
        dir_dialogue.setFileMode(QtWidgets.QFileDialog.Directory)
        directory_name = dir_dialogue.getExistingDirectory(self, tr("path_to_comrem"))
        if directory_name:
            self.update_distro_edit(str(Path(directory_name)))

    def update_game_edit(self, directory_name, set_text: bool = False):
        validated, _ = GameCopy.validate_game_dir(directory_name)
        if validated:
            exe_name = GameCopy.get_exe_name(directory_name)
            exe_version = GameCopy.get_exe_version(exe_name)
            validated_exe = ""
            if exe_version is not None:
                validated_exe = GameCopy.is_compatch_compatible_exe(exe_version)
            if validated_exe:
                self.game_edit.setStyleSheet("font-weight: bold;")
                self.game_edit.setText(directory_name)
                self.game_edit.setPlaceholderText(tr("ask_to_choose_path"))
                self.game_status_icon.setIcon(qta.icon("fa5s.check-circle", color="green"))
                self.game_dir = directory_name
            else:
                self.game_edit.setStyleSheet("border: 1px solid rgba(255, 0, 0, 60%); border-radius: 2px")
                if exe_version is not None:
                    self.game_edit.setPlaceholderText(f'{tr("unsupported_exe_version")}: {exe_version}')
                else:
                    self.game_edit.setPlaceholderText(f'{tr("exe_is_running")}: {Path(exe_name).name}')
                self.game_status_icon.setIcon(qta.icon("fa5s.exclamation-circle", color="red"))
                self.game_edit.setText('')
                self.game_dir = None
        elif directory_name:
            self.game_edit.setStyleSheet("border: 1px solid rgba(255, 0, 0, 60%); border-radius: 2px")
            self.game_edit.setPlaceholderText(tr("target_dir_missing_files"))
            self.game_status_icon.setIcon(qta.icon("fa5s.exclamation-circle", color="red"))
            self.game_dir = None
            if set_text:
                self.game_edit.setText(directory_name)
            else:
                self.game_edit.setText('')
        self.check_if_env_is_ready()

    def update_distro_edit(self, directory_name, set_text: bool = False):
        validated = InstallationContext.validate_distribution_dir(directory_name)
        if validated:
            self.distro_edit.setStyleSheet("font-weight: bold;")
            self.distro_edit.setText(directory_name)
            self.distro_edit.setPlaceholderText(tr("ask_to_choose_path"))
            self.distro_status_icon.setIcon(qta.icon("fa5s.check-circle", color="green"))
            self.distro_dir = directory_name
        elif directory_name:
            self.distro_edit.setStyleSheet("border: 1px solid rgba(255, 0, 0, 60%); border-radius: 2px")
            self.distro_edit.setPlaceholderText(tr("target_dir_missing_files"))
            self.distro_status_icon.setIcon(qta.icon("fa5s.exclamation-circle", color="red"))
            self.distro_dir = None
            if set_text:
                self.distro_edit.setText(directory_name)
            else:
                self.distro_edit.setText('')
        self.check_if_env_is_ready()

    def game_edit_entered(self):
        directory_name = self.game_edit.text()
        if directory_name:
            self.update_game_edit(directory_name, set_text=True)
        else:
            self.game_edit.setStyleSheet("")
            self.game_edit.setPlaceholderText(tr("ask_to_choose_path"))
            self.game_status_icon.setIcon(qta.icon("fa5s.folder-open"))
            self.game_dir = None
            self.check_if_env_is_ready()

    def distro_edit_entered(self):
        directory_name = self.distro_edit.text()
        if directory_name:
            self.update_distro_edit(directory_name, set_text=True)
        else:
            self.distro_edit.setStyleSheet("")
            self.distro_edit.setPlaceholderText(tr("ask_to_choose_path"))
            self.distro_status_icon.setIcon(qta.icon("fa5s.folder-open"))
            self.distro_dir = None
            self.check_if_env_is_ready()

    def game_edit_on_enter(self):
        self.game_edit.deselect()
        self.game_edit.clearFocus()

    def distro_edit_on_enter(self):
        self.distro_edit.deselect()
        self.distro_edit.clearFocus()

    def steam_choosen(self):
        directory_name = self.steam_dirs_list.currentText()
        if directory_name:
            self.update_game_edit(directory_name, set_text=True)

    def check_if_env_is_ready(self):
        if self.game_dir is not None and self.distro_dir is not None:
            self.button_agree.setEnabled(True)
        elif self.button_agree.isEnabled():
            self.button_agree.setDisabled(True)

    def load_env_from_wizard(self):
        if self.game_dir:
            try:
                self.app.game.process_game_install(self.game_dir)
            except Exception as ex:
                # TODO: Handle exceptions properly
                print(f"[Game loading error] {ex}")

        if self.distro_dir:
            try:
                self.app.context.add_distribution_dir(self.distro_dir)
            except Exception as ex:
                # TODO: Handle exceptions properly
                print(f"[Distro loading error] {ex}")

        self.close()
        self.mw.show()


class QHLine(QtWidgets.QFrame):
    def __init__(self):
        super(QHLine, self).__init__()
        self.setFrameShape(QtWidgets.QFrame.HLine)
        self.setLineWidth(2)
        self.setStyleSheet("color: #848484")
        # self.setFrameShadow(QtWidgets.QFrame.Sunken)


class QVLine(QtWidgets.QFrame):
    def __init__(self):
        super(QVLine, self).__init__()
        self.setFrameShape(QtWidgets.QFrame.VLine)
        self.setLineWidth(2)
        self.setStyleSheet("color: #848484")
        # self.setFrameShadow(QtWidgets.QFrame.Sunken)


class ResizableIconLabel(QtWidgets.QLabel):
    def __init__(self, parent: QtWidgets.QWidget | None = None):
        super().__init__(parent)
        self.setMinimumSize(1, 1)
        self.setScaledContents(False)
        self._pixmap: QtGui.QPixmap | None = None

    def heightForWidth(self, width: int) -> int:
        if self._pixmap is None:
            return self.height()
        else:
            return self._pixmap.height() * width / self._pixmap.width()

    def scaledPixmap(self) -> QtGui.QPixmap:
        scaled = self._pixmap.scaled(
            self.size() * self.devicePixelRatioF(),
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        scaled.setDevicePixelRatio(self.devicePixelRatioF())
        return scaled

    def setPixmap(self, pixmap: QtGui.QPixmap) -> None:
        self._pixmap = pixmap
        super().setPixmap(pixmap)

    def sizeHint(self) -> QtCore.QSize:
        width = self.width()
        return QtCore.QSize(width, self.heightForWidth(width))

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        if self._pixmap is not None:
            super().setPixmap(self.scaledPixmap())
            self.setAlignment(QtCore.Qt.AlignTop)


if __name__ == "__main__":
    sys.exit(main())
