from ctypes import windll
import logging
import os
import platform
import subprocess
import sys

from pathlib import Path
from datetime import datetime
import winreg
from color import bcolors, fconsole
from mod import Mod
from errors import ExeIsRunning, ExeNotFound, ExeNotSupported, HasManifestButUnpatched, InvalidGameDirectory,\
                  DistributionNotFound, FileLoggingSetupError, InvalidExistingManifest, ModsDirMissing,\
                  NoModsFound, CorruptedRemasterFiles, PatchedButDoesntHaveManifest, WrongGameDirectoryPath
from data import VERSION, VERSION_BYTES_102_NOCD, VERSION_BYTES_102_STAR,\
                 VERSION_BYTES_103_NOCD, VERSION_BYTES_103_STAR, OS_SCALE_FACTOR, VERSION_BYTES_DEM_LNCH
from localisation import tr
from file_ops import running_in_venv, read_yaml, makedirs


class InstallationContext:
    '''
    Contains all the data about the current distribution directory
    (dir where installation files are located) and some details about ComMod
    '''
    def __init__(self, distribution_dir: str | None = None,
                 dev_mode: bool = False, can_skip_adding_distro: bool = False) -> None:
        self.developer_mode = dev_mode
        self.distribution_dir = None
        self.validated_mod_configs = {}
        self.commod_version = VERSION
        self.os = platform.system()
        self.os_version = platform.release()

        if distribution_dir is not None:
            try:
                self.add_distribution_dir(distribution_dir)
            except EnvironmentError:
                logging.error(f"Couldn't add '{distribution_dir = }'")
        elif not can_skip_adding_distro:
            self.add_default_distribution_dir()

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

    @staticmethod
    def get_config():
        config_path = os.path.join(InstallationContext.get_local_path(), "commod.yaml")
        if os.path.exists(config_path):
            config = read_yaml(config_path)
            return config
        return None

    def add_distribution_dir(self, distribution_dir: str, ignore_invalid: bool = False) -> None:
        '''
        Distribution dir is a location of files available for installation
        By default it's ComPatch and ComRemaster files, but can also contain mods
        '''
        if self.validate_distribution_dir(distribution_dir):
            self.distribution_dir = os.path.normpath(distribution_dir)
        elif not ignore_invalid:
            raise DistributionNotFound(distribution_dir,
                                       "Couldn't find all required files in given distribuion dir")

    def load_system_info(self):
        self.os = platform.system()
        self.os_version = platform.release()

        self.under_windows = "Windows" in self.os
        self.monitor_res = self.get_monitor_resolution()

        self.logger.info(f"Running on {self.os}: {self.os_version}")

    def get_monitor_resolution(self) -> tuple[int, int]:
        if "Windows" in platform.system():
            success = False
            retry_count = 10
            for retry in range(retry_count):
                res_x = windll.user32.GetSystemMetrics(0)
                res_y = windll.user32.GetSystemMetrics(1)
                if res_x != 0 and res_y != 0:
                    success = True
                    break
            if not success:
                res_x = 1920
                res_y = 1080
                self.logger.warning("GetSystemMetrics failed, can't determine resolution "
                                    "using FullHD as a fallback")
        else:
            cmd = ['xrandr']
            cmd2 = ['grep', '*']
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            p2 = subprocess.Popen(cmd2, stdin=p.stdout, stdout=subprocess.PIPE)
            p.stdout.close()
            resolution_string, junk = p2.communicate()
            resolution = resolution_string.split()[0]
            res_x, res_y = resolution.split('x')

        monitor_res = int(res_x), int(res_y)
        self.logger.info(f"reported res X:Y: {res_x}:{res_y}")

        if self.under_windows:
            self.logger.info(f"os scale factor: {OS_SCALE_FACTOR}")
        return monitor_res

    def validate_remaster(self):
        yaml_path = os.path.join(self.distribution_dir, "remaster", "manifest.yaml")
        yaml_config = read_yaml(yaml_path)
        if yaml_config is None:
            raise CorruptedRemasterFiles(yaml_path, "Couldn't read ComRemaster manifest")
        if not Mod.validate_install_config(yaml_config, yaml_path):
            raise CorruptedRemasterFiles(yaml_path, "Couldn't validate ComRemaster manifes or files")
        else:
            self.remaster_config = yaml_config
            self.remaster_path = os.path.join(self.distribution_dir, "remaster")

    @staticmethod
    def get_local_path():
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

        return str(exe_path)

    def add_default_distribution_dir(self) -> None:
        '''Looks for distribution files arround exe and sets as distribution dir if its validated'''
        exe_path = self.get_local_path()

        if self.validate_distribution_dir(exe_path):
            self.distribution_dir = exe_path
        else:
            raise DistributionNotFound(exe_path, "Distribution not found around mod manager exe")

    def load_mods(self) -> None:
        mod_loading_errors = self.current_session.mod_loading_errors
        mods_path = os.path.join(self.distribution_dir, "mods")
        if not os.path.isdir(mods_path):
            makedirs(mods_path)
            raise ModsDirMissing
        mod_configs_paths = self.get_existing_mods(mods_path)
        if not mod_configs_paths:
            raise NoModsFound

        for mod_config_path in mod_configs_paths:
            yaml_config = read_yaml(mod_config_path)
            if yaml_config is None:
                self.logger.warning(f"Couldn't read mod manifest: {mod_config_path}")
                mod_loading_errors.append(f"\n{tr('empty_mod_manifest')}: "
                                          f"{Path(mod_config_path).parent.name} - "
                                          f"{Path(mod_config_path).name}")
                continue
            config_validated = Mod.validate_install_config(yaml_config, mod_config_path)
            if config_validated:
                self.validated_mod_configs[mod_config_path] = yaml_config
            else:
                self.logger.warning(f"Couldn't validate Mod manifest: {mod_config_path}")
                mod_loading_errors.append(f"\n{tr('not_validated_mod_manifest')}.\n"
                                          f"{tr('folder').capitalize()}: "
                                          f"/{Path(mod_config_path).parent.parent.name}"
                                          f"/{Path(mod_config_path).parent.name}"
                                          f"/{Path(mod_config_path).name}")

        if mod_loading_errors:
            self.logger.info("***")
            self.logger.debug(f"Mod loading errors: {mod_loading_errors}")

    @staticmethod
    def get_existing_mods(mods_dir: str) -> list[str]:
        mod_list = []
        for entry in os.scandir(mods_dir):
            if entry.is_dir():
                manifest_path = os.path.join(entry, "manifest.yaml")
                if os.path.exists(manifest_path):
                    mod_list.append(manifest_path)
                else:
                    for internal_entry in os.scandir(entry):
                        if internal_entry.is_dir():
                            internal_manifest_path = os.path.join(internal_entry, "manifest.yaml")
                            if os.path.exists(internal_manifest_path):
                                mod_list.append(internal_manifest_path)
        return mod_list

    def setup_loggers(self, stream_only: bool = False) -> None:
        self.logger = logging.getLogger('dem')
        if self.logger.handlers:
            self.logger.debug("Logger already exists, will use it with existing settings")
        else:
            self.logger.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s: %(levelname)-7s - '
                                          '%(module)-11s - line %(lineno)-3d: %(message)s')
            stream_formatter = logging.Formatter('%(levelname)-7s - %(module)-11s'
                                                 ' - line %(lineno)-3d: %(message)s')

            if self.developer_mode:
                stream_handler = logging.StreamHandler()
                stream_handler.setLevel(logging.DEBUG)
                stream_handler.setFormatter(stream_formatter)
                self.logger.addHandler(stream_handler)

                file_handler_level = logging.DEBUG
            else:
                # stream_handler.setLevel(logging.WARNING)
                file_handler_level = logging.INFO

            if not stream_only:
                file_handler = logging.FileHandler(
                                    os.path.join(self.log_path,
                                                 f'debug_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.log'),
                                    encoding='utf-8')
                file_handler.setLevel(file_handler_level)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

            self.logger.info("Loggers initialised")

    def setup_logging_folder(self) -> None:
        if self.distribution_dir is not None:
            log_path = os.path.join(self.distribution_dir, 'logs_commod')
            if os.path.exists(log_path) and not os.path.isdir(log_path):
                os.remove(log_path)

            if not os.path.exists(log_path):
                os.mkdir(log_path)
            self.log_path = log_path
        else:
            raise FileLoggingSetupError("", "Distribution not found when setting up file logging")

    class Session:
        '''Session stores information about the course of install and errors encountered'''
        def __init__(self) -> None:
            self.mod_loading_errors = []
            self.mod_installation_errors = []
            self.steam_parsing_error = None

            self.content_in_processing = {}
            self.installed_content_description = []
            self.steam_game_paths = None

        def load_steam_game_paths(self) -> tuple[str, str]:
            '''Tries to find the game in default Steam folder, returns path and error message'''
            steam_install_reg_path = r"SOFTWARE\WOW6432Node\Valve\Steam"
            hklm = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
            validated_dirs = []
            try:
                # getting Steam installation folder from Reg
                steam_install_reg_value = winreg.OpenKey(hklm, steam_install_reg_path)
                steam_install_path = winreg.QueryValueEx(steam_install_reg_value, 'InstallPath')[0]

                # game can be installed in main Steam dir or in any of the libraries specified in config
                library_folders_config = os.path.join(steam_install_path, "SteamApps", "libraryfolders.vdf")
                library_folders = [steam_install_path]
                game_folders = []

                with open(library_folders_config, 'r') as f:
                    lines = f.readlines()
                    if '"libraryfolders"\n' in lines:
                        library_folders = [line for line in lines if '"path"' in line]

                    for lib in library_folders:
                        striped_lib = lib.replace('path', "").replace('"', '').strip()
                        if striped_lib:
                            path = Path(striped_lib)
                            if path.is_dir():
                                games_path = path / "SteamApps" / "common"
                                if games_path.is_dir():
                                    game_folders.append(games_path)

                if not library_folders:
                    self.steam_parsing_error = "NoLibraryFolders"
                    return False

                if not game_folders:
                    self.steam_parsing_error = "NoGameFolders"
                    return False

                for folder in game_folders:
                    # checking that game install exist for this library
                    # and that data folder and exe exists as well
                    expected_game_path = folder / "Hard Truck Apocalypse"
                    if expected_game_path.is_dir():
                        validated, _ = GameCopy.validate_game_dir(expected_game_path)
                        if validated:
                            validated_dirs.append(str(expected_game_path))

                    for entry in folder.glob("*"):
                        if entry.is_dir() and entry != expected_game_path:
                            validated, _ = GameCopy.validate_game_dir(str(entry))
                            if validated:
                                validated_dirs.append(str(entry))
            except FileNotFoundError:
                self.steam_parsing_error = "FileNotFound/RegistryNotFound"
                return False

            self.steam_game_paths = validated_dirs
            return True


class GameCopy:
    '''Stores info about a processed HTA/EM game copy'''
    def __init__(self) -> None:
        self.installed_content = {}
        self.installed_descriptions = {}
        self.patched_version = False
        self.leftovers = False
        self.target_exe = None
        self.label = ""

    @staticmethod
    def validate_game_dir(game_root_path: str) -> tuple[bool, str]:
        '''Checks existence of expected basic file structure in given game directory'''
        if not os.path.isdir(game_root_path):
            return False, game_root_path

        possible_exe_paths = [os.path.join(game_root_path, "hta.exe"),
                              os.path.join(game_root_path, "game.exe"),
                              os.path.join(game_root_path, "start.exe"),
                              os.path.join(game_root_path, "ExMachina.exe")]

        if not any([os.path.exists(exepath) for exepath in possible_exe_paths]):
            return False, os.path.join(game_root_path, "hta.exe")

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
    def validate_install_manifest(install_config: dict) -> bool:
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

        for config_name in install_config:
            if install_config[config_name] in ["community_patch", "community_remaster"]:
                continue
            else:
                base = install_config[config_name].get("base")
                version = install_config[config_name].get("version")
                if base is None or version is None:
                    return False
        return True

    def process_game_install(self, target_dir: str) -> None:
        '''Parse game install to know the version and current state of it'''
        if not os.path.isdir(target_dir):
            raise WrongGameDirectoryPath
        else:
            valid_base_dir, missing_path = self.validate_game_dir(target_dir)
            if not valid_base_dir:
                raise InvalidGameDirectory(missing_path)

        exe_path = self.get_exe_name(target_dir)

        if exe_path is not None:
            self.target_exe = exe_path
        else:
            raise ExeNotFound

        self.exe_version = self.get_exe_version(self.target_exe)
        if self.exe_version is None:
            raise ExeIsRunning

        if not self.is_compatch_compatible_exe(self.exe_version):
            raise ExeNotSupported(self.exe_version)

        self.game_root_path = target_dir
        self.data_path = os.path.join(self.game_root_path, "data")
        self.installed_manifest_path = os.path.join(self.data_path, "mod_manifest.yaml")

        patched_version = ("ComRemaster" in self.exe_version) or ("ComPatch" in self.exe_version)

        if os.path.exists(self.installed_manifest_path):
            install_manifest = read_yaml(self.installed_manifest_path)
            valid_manifest = self.validate_install_manifest(install_manifest)
            if valid_manifest and patched_version:
                self.installed_content = install_manifest
                self.patched_version = True
                return
            elif patched_version and not valid_manifest:
                raise InvalidExistingManifest(self.installed_manifest_path)
            else:
                raise HasManifestButUnpatched(self.exe_version, install_manifest)

        if patched_version:
            self.patched_version = True
            self.installed_content = None
            raise PatchedButDoesntHaveManifest(self.exe_version)

    def is_modded(self) -> bool:
        if self.installed_content is None:
            return False

        if "community_remaster" in self.installed_content.keys():
            if len(self.installed_content) > 2:
                return True
        elif "community_patch" in self.installed_content.keys():
            if len(self.installed_content) > 1:
                return True

        return False

    def load_installed_descriptions(self, additional_manifests: list = [], colourise=False) -> list[str]:
        '''Constructs dict of pretty description strings for list of installed content
           based on existing manifest inside the game and optionall list of full mod manifests'''
        available_external_manifests = []

        if additional_manifests:
            available_external_manifests = [manifest['name'] for manifest in additional_manifests.values()]

        if self.installed_content is None:
            return

        for content_piece in self.installed_content:
            install_manifest = self.installed_content[content_piece]
            name = content_piece

            if name == "community_patch":
                if "community_remaster" in self.installed_content.keys():
                    continue
                name = "Community Patch"
            elif name == "community_remaster":
                name = "Community Remaster"
            elif install_manifest.get("display_name") is not None:
                name = install_manifest["display_name"]
            elif content_piece in available_external_manifests:
                external_manifest = [manifest for manifest in additional_manifests.values()
                                     if (manifest["name"] == content_piece and
                                         str(manifest["version"]) == install_manifest["version"])]
                if external_manifest:
                    name = external_manifest[0]["display_name"]

            optional_content_keys = (install_manifest.keys()
                                     - set(["base", "version", "display_name", "build"]))
            unskipped_content = {key: value for key, value in install_manifest.items() if value != "skip"}
            installed_optional_content = (unskipped_content.keys()
                                          - set(["base", "version", "display_name", "build"]))

            build = ''
            if install_manifest.get("build") is not None:
                build = f" [{install_manifest['build']}]"

            if colourise:
                description = fconsole(f'{name} ({tr("version")} '
                                          f'{install_manifest["version"]}){build}\n',
                                          bcolors.OKBLUE)
            else:
                description = f'{name} ({tr("version")} {install_manifest["version"]})\n'

            if installed_optional_content:
                if colourise:
                    description += fconsole("*", bcolors.OKCYAN)
                description += (f' {tr("optional_content").capitalize()}: '
                                f'{", ".join(sorted(list(installed_optional_content)))}\n')
            elif optional_content_keys:
                description += f'{fconsole("*", bcolors.OKCYAN)} {tr("base_version")}\n'

            # description += "\n"
            self.installed_descriptions[content_piece] = description

    @staticmethod
    def is_compatch_compatible_exe(version: str) -> bool:
        return ("Clean" in version) or ("ComRemaster" in version) or ("ComPatch" in version)

    @staticmethod
    def get_exe_name(target_dir: str):
        possible_exe_paths = [os.path.join(target_dir, "hta.exe"),
                              os.path.join(target_dir, "game.exe"),
                              os.path.join(target_dir, "start.exe"),
                              os.path.join(target_dir, "ExMachina.exe")]
        for exe_path in possible_exe_paths:
            if os.path.exists(exe_path):
                return os.path.normpath(exe_path)

        return None

    @staticmethod
    def get_exe_version(target_exe: str) -> str:
        try:
            with open(target_exe, 'rb+') as f:
                f.seek(VERSION_BYTES_102_NOCD)
                version_identifier = f.read(15)
                f.seek(VERSION_BYTES_103_NOCD)
                version_identifier_103_nocd = f.read(15)
                f.seek(VERSION_BYTES_103_STAR)
                version_identifier_103_star = f.read(15)
                f.seek(VERSION_BYTES_102_STAR)
                version_identifier_102_star = f.read(15)
                f.seek(VERSION_BYTES_DEM_LNCH)
                version_identifier_dem_lnch = f.read(15) 

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
            elif version_identifier[3:7] == b'1.12':
                return "ComRemaster 1.12"
            elif version_identifier[:4] == b'1.12':
                return "ComPatch 1.12"
            elif version_identifier[3:7] == b'1.13':
                return "ComRemaster 1.13"
            elif version_identifier[:4] == b'1.13':
                return "ComPatch 1.13"
            elif version_identifier[8:12] == b'1.04':
                return "KRBDZSKL 1.04"
            elif version_identifier_103_nocd[1:5] == b'1.03':
                return "DRM Free 1.03"
            elif version_identifier_103_star[:9] == b'\xbf\xcf\x966\xf1\x97\xf2\xc5\x11':
                return "1.03 Starforce"
            elif version_identifier_102_star[:9] == b'O0\x87\xfa%\xbc\x9f\x86Q':
                return "1.02 Starforce"
            elif version_identifier_dem_lnch[:9] == b'\x00\x8dU\x98R\xe8)\x07\x00':
                return "Old DEM launcher"
            else:
                return "Unknown"
        except PermissionError:
            return None
