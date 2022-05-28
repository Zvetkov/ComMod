import datetime
import logging
import os
import sys

from pathlib import Path
from mod import Mod
from utils import ExeIsRunning, ExeNotFound, ExeNotSupported, InvalidGameDirectory, WrongGameDirectoryPath,\
                  DistributionNotFound, FileLoggingSetupError, InvalidExistingManifest, ModsDirMissing,\
                  NoModsFound, loc_string, running_in_venv, read_yaml
from data import VERSION_BYTES_102_NOCD


class InstallationContext:
    '''
    Contains all the data about the current distribution directory
    (dir where installation files are located)
    '''
    def __init__(self, distribution_dir: str | None = None,
                 developer_mode: bool = False) -> None:
        self.developer_mode = developer_mode
        self.target_game_copy = None

        if distribution_dir is not None:
            try:
                self.add_distribution_dir(distribution_dir)
            except EnvironmentError:
                logging.error(f"Couldn't add '{distribution_dir = }'")
        else:
            self.distribution_dir = None

        self.current_session = self.Session()

    @staticmethod
    def validate_distribution_dir(distribution_dir: str) -> bool:
        '''Distribution dir is a location of files to install, need to have at
        least files of ComPatch and ComRem'''
        if not os.path.isdir(distribution_dir):
            return False

        paths_to_check = [os.path.join(distribution_dir, "patch"),
                          os.path.join(distribution_dir, "remaster"),
                          os.path.join(distribution_dir, "remaster", "data"),
                          os.path.join(distribution_dir, "remaster", "manifest.yaml"),
                          os.path.join(distribution_dir, "libs", "library.dll"),
                          os.path.join(distribution_dir, "libs", "library.pdb")]

        for path in paths_to_check:
            if not os.path.exists(path):
                return False
        return True

    @classmethod
    def add_distribution_dir(self, distribution_dir: str) -> None:
        '''
        Distribution dir is a location of files available for installation
        By default it's ComPatch and ComRemaster files, but can also contain mods
        '''

        if self.validate_distribution_dir(distribution_dir):
            self.distribution_dir = os.path.normpath(distribution_dir)
        else:
            raise DistributionNotFound(distribution_dir, "Couldn't validate given distribuion dir")

    @classmethod
    def add_default_distribution_dir(self) -> None:
        '''Looks for distribution files arround exe and sets as distribution dir if its validated'''
        sys_exe = str(Path(sys.executable).resolve())
        # check if we are running as py script, compiled exe, or in venv
        if ".exe" in sys_exe and not running_in_venv():
            # Nuitka way
            exe_path = Path(sys.argv[0]).resolve().parent
            # PyInstaller compatible way
            # distribution_dir = Path(sys.executable).resolve().parent
        elif running_in_venv():
            # probably running in venv
            exe_path = Path(__file__).resolve().parent
        else:
            raise EnvironmentError

        if self.validate_distribution_dir(exe_path):
            self.distribution_dir = exe_path
        else:
            raise DistributionNotFound(exe_path, "Distribution not found around patcher exe")

    @staticmethod
    def exe_is_compatible(version: str) -> bool:
        return ("Clean" in version) or ("ComRemaster" in version) or ("ComPatch" in version)

    @classmethod
    def load_mods(self):
        mod_loading_errors = self.current_session.mod_loading_errors
        mods_path = os.path.join(self.distribution_dir, "mods")
        if not os.path.isdir(mods_path):
            raise ModsDirMissing
        mod_configs_paths = self.get_existing_mods(mods_path)
        if not mod_configs_paths:
            raise NoModsFound
        self.validated_mod_configs = {}
        for mod_config_path in mod_configs_paths:
            yaml_config = read_yaml(mod_config_path)
            if yaml_config is None:
                self.logger.debug(f"Couldn't read mod manifest: {mod_config_path}")
                mod_loading_errors.append(f"\n{loc_string('empty_mod_manifest')}: "
                                          f"{Path(mod_config_path).parent.name} - "
                                          f"{Path(mod_config_path).name}")
                continue
            config_validated = Mod.validate_install_config(yaml_config, mod_config_path)
            if config_validated:
                self.validated_mod_configs[mod_config_path] = yaml_config
            else:
                self.logger.debug(f"Couldn't validate Mod manifest: {mod_config_path}")
                mod_loading_errors.append(f"\n{loc_string('not_validated_mod_manifest')}: "
                                          f"{Path(mod_config_path).parent.name} - "
                                          f"{Path(mod_config_path).name}")

    @staticmethod
    def get_existing_mods(mods_dir: str) -> list[str]:
        mod_list = []
        for entry in os.scandir(mods_dir):
            if entry.is_dir():
                manifest_path = os.path.join(entry, "manifest.yaml")
                if os.path.exists(manifest_path):
                    mod_list.append(manifest_path)
        return mod_list

    @classmethod
    def setup_logging_folder(self):
        if self.distribution_dir is not None:
            log_path = os.path.join(self.distribution_dir, 'patcher_logs')
            if not os.path.exists(log_path):
                os.mkdir(log_path)
            self.log_path = log_path
        else:
            raise FileLoggingSetupError("", "Distribution not found when setting up file logging")

    @classmethod
    def setup_console_loggers(self):
        self.logger = logging.getLogger('dem')
        if self.logger.handlers:
            self.logger.debug("Logger already exists, will use it with existing settings")
        else:
            self.logger.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s: %(levelname)s - '
                                          '%(module)s - line %(lineno)d - %(message)s')

            file_handler = logging.FileHandler(
                                os.path.join(self.log_path,
                                             f'debug_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.log'),
                                encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(formatter)

            stream_handler = logging.StreamHandler()
            if self.developer_mode:
                stream_handler.setLevel(logging.DEBUG)
            else:
                stream_handler.setLevel(logging.INFO)

            stream_handler.setFormatter(formatter)

            self.logger.addHandler(file_handler)
            self.logger.addHandler(stream_handler)
            self.logger.debug("Loggers initialised")

    class Session:
        '''Session stores information about the course of install and errors encountered'''
        def __init__(self) -> None:
            self.installed_mods = []
            self.mod_loading_errors = []
            self.mod_installation_errors = []
            self.error_messages = []


class GameCopy:
    def __init__(self) -> None:
        self.installed_content = {}
        self.patched_version = False
        self.existing_install_manifest = None

    @staticmethod
    def validate_game_dir(game_root_path: str) -> tuple[bool, str]:
        '''Checks existence of expected basic file structure in given game directory'''
        if not os.path.isdir(game_root_path):
            return False, game_root_path
        paths_to_check = [os.path.join(game_root_path, "dxrender9.dll"),
                          os.path.join(game_root_path, "data"),
                          os.path.join(game_root_path, "data", "effects"),
                          os.path.join(game_root_path, "data", "gamedata"),
                          os.path.join(game_root_path, "data", "if"),
                          os.path.join(game_root_path, "data", "maps"),
                          os.path.join(game_root_path, "data", "models"),
                          os.path.join(game_root_path, "data", "music"),
                          os.path.join(game_root_path, "data", "scripts"),
                          os.path.join(game_root_path, "data", "shaders"),
                          os.path.join(game_root_path, "data", "sounds"),
                          os.path.join(game_root_path, "data", "textures"),
                          os.path.join(game_root_path, "data", "weather.xml"),
                          os.path.join(game_root_path, "data", "config.cfg")]

        for path in paths_to_check:
            if not os.path.exists(path):
                return False, path
        return True, ''

    @staticmethod
    def validate_install_manifest(install_config):
        compatch = install_config.get("community_patch")
        if compatch is not None:
            base = compatch.get("base")
            version = compatch.get("version")
            if base is None or version is None:
                return False
        else:
            return False
        comrem = install_config.get("community_remaster")
        if comrem is not None:
            base = comrem.get("base")
            version = compatch.get("version")
            if base is None or version is None:
                return False
        return True

    @classmethod
    def process_game_install(self, target_dir: str) -> None:
        '''Parse game install to know the version and current state of it'''
        if not os.path.exists(target_dir):
            raise WrongGameDirectoryPath
        else:
            valid_base_dir, missing_path = self.validate_game_dir(target_dir)
            if not valid_base_dir:
                raise InvalidGameDirectory(missing_path)
        possible_exe_paths = [os.path.join(target_dir, "hta.exe"),
                              os.path.join(target_dir, "game.exe"),
                              os.path.join(target_dir, "ExMachina.exe")]
        for exe_path in possible_exe_paths:
            if os.path.exists(exe_path):
                self.target_exe = exe_path

        if self.target_exe is None:
            raise ExeNotFound

        self.exe_version = self.get_exe_version(self.target_exe)
        if self.exe_version is None:
            raise ExeIsRunning

        if not self.exe_is_compatible(self.exe_version):
            raise ExeNotSupported(self.exe_version)

        self.game_root_path = target_dir
        self.data_path = os.path.join(self.game_root_path, "data")
        self.installed_manifest_path = os.path.join(self.data_path, "mod_manifest.yaml")
        if os.path.exists(self.installed_manifest_path):
            install_manifest = read_yaml(self.installed_manifest_path)
            patched_version = ("ComRemaster" in self.exe_version) or ("ComPatch" in self.exe_version)
            valid_manifest = self.validate_install_manifest(install_manifest) and patched_version
            if valid_manifest:
                self.existing_install_manifest = install_manifest
                self.patched_version = True
            else:
                raise InvalidExistingManifest(self.installed_manifest_path)

    @staticmethod
    def get_exe_version(target_exe: str) -> str:
        try:
            with open(target_exe, 'rb+') as f:
                f.seek(VERSION_BYTES_102_NOCD)
                version_identifier = f.read(15)
            if version_identifier[8:12] == b'1.02':
                return "Clean 1.02"
            elif version_identifier[3:7] == b'1.10':
                return "ComRemaster 1.10"
            elif version_identifier[:4] == b'1.10':
                return "ComPatch 1.10"
            elif version_identifier[3:7] == b'1.11':
                return "ComRemaster 1.11"
            elif version_identifier[:4] == b'1.11':
                return "ComPatch 1.11"
            else:
                return "Unknown"
        except PermissionError:
            return None
