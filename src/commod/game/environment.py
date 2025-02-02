# ruff: noqa: S603

import asyncio
import hashlib
import logging
import os
import platform
import pprint
import subprocess
import sys
import zipfile
from asyncio import gather
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from aiopath import AsyncPath
from flet import Text

# import aiofiles
from py7zr import py7zr
from pydantic import DirectoryPath, ValidationError

from commod.game.data import (
    DATE,
    KNOWN_RESOLUTIONS,
    OS_SCALE_FACTOR,
    OWN_VERSION,
    TARGEM_NEGATIVE,
    TARGEM_POSITIVE,
    VERSION_BYTES_100_STAR,
    VERSION_BYTES_102_NOCD,
    VERSION_BYTES_102_STAR,
    VERSION_BYTES_103_NOCD,
    VERSION_BYTES_103_STAR,
    VERSION_BYTES_ARCD_100,
    VERSION_BYTES_DEM_LNCH,
    VERSION_BYTES_M113_101,
)
from commod.game.mod import Mod
from commod.game.mod_auxiliary import RESERVED_CONTENT_NAMES, ConfigOptions, Version
from commod.helpers.errors import (
    DistributionNotFoundError,
    ExeIsRunningError,
    ExeNotFoundError,
    ExeNotSupportedError,
    FileLoggingSetupError,
    HasManifestButUnpatchedError,
    InvalidExistingManifestError,
    InvalidGameDirectoryError,
    ModsDirMissingError,
    NoModsFoundError,
    PatchedButDoesntHaveManifestError,
    WrongGameDirectoryPathError,
)
from commod.helpers.file_ops import get_config, load_yaml, read_yaml, running_in_venv, write_xml_to_file_async
from commod.localisation.service import SupportedLanguages, tr


class GameStatus(Enum):
    COMPATIBLE = ""
    NOT_EXISTS = "not_a_valid_path"
    BAD_EXE = "exe_not_supported"
    EXE_RUNNING = "exe_is_running"
    MISSING_FILES = "target_dir_missing_files"
    LEFTOVERS = "install_leftovers"
    ALREADY_ADDED = "already_in_list"
    NOT_DIRECTORY = "not_directory"
    GENERAL_ERROR = "error"


class DistroStatus(Enum):
    COMPATIBLE = ""
    NOT_EXISTS = "not_a_valid_path"
    MISSING_FILES = "target_dir_missing_files"
    ALREADY_ADDED = "already_chosen"
    NOT_DIRECTORY = "not_directory"
    GENERAL_ERROR = "error"

# TODO: maybe implement a hashable description of installed Mod
@dataclass(frozen=True)
class ModDescription:
    base: Literal["yes", "no"]
    build: str
    display_name: str
    installment: str

LOG_FILES_TO_KEEP = 30

class InstallationContext:
    """
    Contains all the data about the current distribution directory and ComMod.

    Distribution dir is a storage location for mods.
    """

    def __init__(self, distribution_dir: str = "",
                 dev_mode: bool = False) -> None:
        self.dev_mode = dev_mode
        self.distribution_dir: str = ""
        self.validated_mods: dict[str, Mod] = {}
        self.hashed_mod_manifests: dict[Path, str] = {}
        self.archived_mods: dict[str, Mod] = {}
        self.archived_mods_cache: dict[str, Mod] = {}
        self.archived_mod_manifests_cache: dict[str, tuple[Any, Path]] = {}
        self.commod_version = OWN_VERSION
        self.os = platform.system()
        self.os_version = platform.release()

        self.log_path = None

        if distribution_dir:
            try:
                self.add_distribution_dir(distribution_dir)
            except OSError:
                logging.error(f"Couldn't add '{distribution_dir = }'")

        self.current_session = self.Session()

    @property
    def library_mods_info(self) -> dict[str, dict[str, str]] | None:
        """Return dict of known display info (names) for mods in session."""
        if not self.validated_mods:
            return None
        mod_info_dict = defaultdict(dict)
        for mod in self.validated_mods.values():
            for variant in mod.variants_loaded.values():
                mod_info_dict[variant.name][variant.language] = variant.display_name

        return mod_info_dict

    def new_session(self) -> None:
        self.current_session = self.Session()

    @staticmethod
    def validate_distribution_dir(distribution_dir: str) -> bool:
        """Validate distribution dir - storage location for mods."""
        return bool(distribution_dir) and os.path.isdir(distribution_dir)

    @staticmethod
    def get_commod_config() -> dict | None:
        config_path = os.path.join(InstallationContext.get_local_config_path(), "commod.yaml")
        if os.path.exists(config_path):
            # Invalid yaml config will be returned as None, no need to handle as special case
            return read_yaml(config_path)
        return None

    def add_distribution_dir(self, distribution_dir: str) -> None:
        """
        Distribution dir is a storage location for mods.

        By default it's ComPatch and ComRemaster files, but can also contain mods
        """
        if self.validate_distribution_dir(distribution_dir):
            self.distribution_dir = os.path.normpath(distribution_dir)
        else:
            raise DistributionNotFoundError(
                distribution_dir,
                "Couldn't find all required files in given distribuion dir")

    def load_system_info(self) -> None:
        self.under_windows = "Windows" in self.os
        self.monitor_res = self.get_monitor_resolution()

        self.logger.info(f"Running on {self.os} {self.os_version} OS family")

    def get_monitor_resolution(self) -> tuple[int, int]:
        if "Windows" in platform.system():
            success = False
            retry_count = 10
            # sometimes can randomly fail, blame windll for need to retry
            try:
                for _ in range(retry_count):
                    from ctypes import windll
                    res_x = windll.user32.GetSystemMetrics(0)
                    res_y = windll.user32.GetSystemMetrics(1)
                    if res_x != 0 and res_y != 0:
                        success = True
                        break
            except (ImportError, NameError):
                pass

            if not success:
                res_x = 1920
                res_y = 1080
                self.logger.warning("GetSystemMetrics failed, can't determine resolution "
                                    "using FullHD as a fallback")
        else:
            cmd = ["xrandr"]
            cmd2 = ["grep", "*"]
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
            p2 = subprocess.Popen(cmd2, stdin=p.stdout, stdout=subprocess.PIPE)
            p.stdout.close()
            resolution_byte, junk = p2.communicate()
            resolution_string = resolution_byte.decode("utf-8")
            resolution = resolution_string.split()[0]
            self.logger.debug(f"Detected resolution: {resolution}")
            res_x, res_y = resolution.split("x")
            if int(res_y) > int(res_x):
                res_x, res_y = res_y, res_x

        monitor_res = int(res_x), int(res_y)
        self.logger.info(f"Reported resolution (X:Y): {res_x}:{res_y}")

        if self.under_windows:
            self.logger.info(f"OS scale factor: {OS_SCALE_FACTOR}")
        return monitor_res

    @staticmethod
    def get_local_config_path() -> str:
        sys_exe = str(Path(sys.executable).resolve())
        # check if we are running as py script, compiled exe, or in venv
        if "Windows" in platform.system():
            if ".exe" in sys_exe and not running_in_venv():
                # Windows Nuitka way
                config_path = Path(sys.argv[0]).resolve().parent
                # old PyInstaller compatible way
                # exe_path = Path(sys.executable).resolve().parent
            elif running_in_venv():
                # *probably* running in venv
                config_path = Path(__file__).parent.parent
            else:
                # Let's default to something instead of raising
                config_path = Path(sys.argv[0]).resolve().parent
        else:
            # for Linux storing local portable config around binary is undesirable, will use XDG Base Dir Spec
            config_root = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.environ.get("HOME"), ".config")
            if config_root == "/.config": # valid for "nobody"
                config_path = Path(sys.argv[0]).resolve().parent
            else:
                config_path = Path(config_root, "commod")
                os.makedirs(config_path, exist_ok=True)
        return str(config_path)

    async def load_mods_async(self) -> None:
        all_config_paths = []
        # TODO: deprecate all code related to legacy comrem file structure
        legacy_comrem = os.path.join(self.distribution_dir, "remaster", "manifest.yaml")
        root_mod = os.path.join(self.distribution_dir, "manifest.yaml")
        if os.path.exists(legacy_comrem):
            all_config_paths.append(legacy_comrem)
        elif os.path.exists(root_mod):
            all_config_paths.append(root_mod)

        self.current_session.mod_loading_errors.clear()
        mod_loading_errors = self.current_session.mod_loading_errors
        mods_path = os.path.join(self.distribution_dir, "mods")
        if not os.path.isdir(mods_path):
            os.makedirs(mods_path, exist_ok=True)
            raise ModsDirMissingError
        # self.logger.debug("get_existing_mods_async call")
        mod_configs_paths, archived_mods = await self.get_existing_mods_async(mods_path)
        self.logger.debug("-- Got existing mods --")
        all_config_paths.extend(mod_configs_paths)
        if not all_config_paths and not archived_mods:
            raise NoModsFoundError

        # TODO: maybe use ThreadPool to speedup
        start = datetime.now()
        for mod_config_path in all_config_paths:
            with open(mod_config_path, "rb") as f:
                digest = hashlib.file_digest(f, "md5").hexdigest()

            # TODO: check AnyIO approach, as this is not faster than sync implementation
            # https://anyio.readthedocs.io/en/stable/fileio.html
            # md5 = hashlib.md5()
            # async with aiofiles.open(mod_config_path, "rb") as f:
            #     digest = hashlib.file_digest(f, "md5").hexdigest()
            #     while chunk := await f.read(8192):
            #         md5.update(chunk)
            # digest = md5.hexdigest()

            validated = False

            if mod_config_path in self.hashed_mod_manifests:
                if digest == self.hashed_mod_manifests[mod_config_path]:
                    validated = True
                    continue
                self.validated_mods.pop(mod_config_path, None)

            self.logger.info(f"--- Loading {mod_config_path} ---")
            yaml_config = read_yaml(mod_config_path)
            if yaml_config is None:
                self.logger.warning(f"Couldn't read mod manifest or it's empty: {mod_config_path}")
                mod_loading_errors.append(f"\n{tr('empty_mod_manifest')}: "
                                          f"{Path(mod_config_path).parent.name} - "
                                          f"{Path(mod_config_path).name}")
                if mod_config_path in self.validated_mods:
                    self.validated_mods.pop(mod_config_path, None)
                continue
            try:
                mod = Mod(**yaml_config, manifest_root=Path(mod_config_path).parent)
                self.validated_mods[mod_config_path] = mod
                validated = True
                self.hashed_mod_manifests[mod_config_path] = digest
                self.logger.debug(f"Validated mod manifest and loaded mod: '{mod.id_str}'")
            except (ValueError, AssertionError, ValidationError) as ex:
                self.logger.warning(f"Couldn't load mod install manifest: {mod_config_path}")
                self.logger.error(f"Validation error: {ex}")
                mod_loading_errors.append(f"\n{tr('not_validated_mod_manifest')}.\n"
                          f"{tr('folder').capitalize()}: "
                          f"/{Path(mod_config_path).parent.parent.name}"
                          f"/{Path(mod_config_path).parent.name} ->"
                          f"{Path(mod_config_path).name}: \n\n"
                          f"**{tr('error')}:**\n\n{ex}")
            except Exception as ex:
                self.logger.exception("General error:")
                mod_loading_errors.append(f"\n{tr('error_occurred').capitalize()}.\n"
                      f"{tr('folder').capitalize()}: "
                      f"/{Path(mod_config_path).parent.parent.name}"
                      f"/{Path(mod_config_path).parent.name} ->"
                      f"{Path(mod_config_path).name}: \n\n"
                      f"**{tr('error')}:**\n\n{ex}")
            finally:
                if not validated and (mod_config_path in self.validated_mods):
                    self.validated_mods.pop(mod_config_path, None)

        end = datetime.now()
        self.logger.debug(f"{(end - start).microseconds / 1000000} seconds took mods loading")

        outdated_mods = set(self.validated_mods.keys()) - set(all_config_paths)
        if outdated_mods:
            for mod in outdated_mods:
                self.logger.debug(f"Removed missing {mod} from rotation")
                self.validated_mods.pop(mod, None)
                self.hashed_mod_manifests.pop(mod, None)

        if archived_mods:
            for path, manifest in archived_mods.items():
                try:
                    mod_dummy = Mod(**manifest, manifest_root=Path(path).parent)
                    self.archived_mods[path] = mod_dummy
                except Exception as ex:
                    self.logger.exception("Error on archived mod preload")
                    # TODO: remove raise, need to test
                    raise NotImplementedError from ex
                    continue

        if mod_loading_errors:
            self.logger.error("-- Errors occurred when loading mods! --")

    def get_dir_manifests(self, directory: str, nesting_levels: int = 3, top_level: bool = True) -> list[str]:
        found_manifests = []
        levels_left = nesting_levels - 1
        for entry in os.scandir(directory):
            if entry.is_dir():
                manifest_path = os.path.join(entry, "manifest.yaml")
                if os.path.exists(manifest_path):
                    found_manifests.append(manifest_path)
                    if not top_level:
                        break
                elif levels_left != 0:
                    found_manifests.extend(self.get_dir_manifests(entry, levels_left, top_level=False))
        return found_manifests

    async def find_manifest_in_dir(self, target_dir: AsyncPath, nesting_levels: int = 3) -> list:
        self.logger.debug(f"{datetime.now()} looking for manifest in {target_dir.name}")
        levels_left = nesting_levels - 1
        manifests_path = AsyncPath(target_dir, "manifest.yaml")
        if await manifests_path.exists():
            return manifests_path

        if levels_left == 0:
            return None

        nested_dirs = [path async for path in target_dir.glob("*") if await path.is_dir()]

        num_dirs = len(nested_dirs)
        if num_dirs == 0:
            return None

        if num_dirs > 1:
            dir_names = {nested_dir.name for nested_dir in nested_dirs}
            if {"patch", "remaster"}.issubset(dir_names):
                return await self.find_manifest_in_dir(AsyncPath(target_dir, "remaster"))
            return None

        return await self.find_manifest_in_dir(nested_dirs[0])

    async def get_dir_manifest_async(self, target_dir: str) -> str:
        top_level_dirs = [path async for path in AsyncPath(target_dir).glob("*") if await path.is_dir()]

        search_results = await gather(*[self.find_manifest_in_dir(top_dir) for top_dir in top_level_dirs])

        return [result for result in search_results if result is not None]

    async def get_existing_mods_async(self, mods_dir: str) -> list[str]:
        # TODO: review this commented out code
        # self.logger.debug("Inside get_existing_mods async")
        # mod_list = await self.get_dir_manifest_async(mods_dir)
        mod_list = self.get_dir_manifests(mods_dir)
        # self.logger.debug("Finished get_dir_manifest")
        archive_dict = {}
        # async for entry in AsyncPath(mods_dir).glob("*.zip"):
        #     self.logger.debug(f"Working on zip {entry}")
        #     if entry.suffix == ".zip":
        #         self.logger.debug(f"Getting zip manifest for {entry}")
        #         manifest = await self.get_zip_manifest_async(entry)
        #         if manifest:
        #             archive_dict[entry] = manifest
        #     self.logger.debug("Added zip manifest to list")

        # async for entry in AsyncPath(mods_dir).glob("*.7z"):
        #     self.logger.debug(f"Working on 7z {entry}")
        #     if entry.suffix == ".7z":
        #         self.logger.debug(f"Getting 7z manifest for {entry}")
        #         manifest = await self.get_7z_manifest_async(entry)
        #         if manifest:
        #             archive_dict[entry] = manifest
        #     self.logger.debug("Added 7z manifest to list")

        # self.logger.debug("Finished get_archived_manifests")
        return mod_list, archive_dict

    async def get_zip_mod_manifest_async(
            self, archive_path: str | AsyncPath, ignore_cache: bool = False,
            loading_text: Text | None = None
            ) -> tuple[
                str | None,
                Path | None,
                list[zipfile.ZipInfo] | None,
                Exception | None]:
        if isinstance(archive_path, str):
            archive_path = AsyncPath(archive_path)
        if not ignore_cache:
            cached_info = self.archived_mod_manifests_cache.get(archive_path)
            if cached_info is not None:
                cached, root_path, file_list = cached_info
                if cached is not None:
                    return cached, root_path, file_list, None
        try:
            await asyncio.sleep(0)
            with zipfile.ZipFile(archive_path, "r") as archive:
                if loading_text is not None:
                    uncompressed = sum([file.file_size for file in archive.filelist])
                    compressed = sum([file.compress_size for file in archive.filelist])
                    loading_text.value = (f"[ZIP] "
                                          f"{compressed/1024/1024:.1f} MB -> "
                                          f"{uncompressed/1024/1024:.1f} MB")
                    loading_text.update()
                    await asyncio.sleep(0)
                file_list = archive.filelist
                manifests = [file for file in file_list
                             if "manifest.yaml" in file.filename]
                if manifests:
                    manifest_b = archive.read(manifests[0])
                    if manifest_b:
                        manifest_root_dir = Path(manifests[0].filename).parent
                        manifest = load_yaml(manifest_b)
                        if manifest is None:
                            raise yaml.YAMLError("Invalid yaml found in archive")

                        self.archived_mod_manifests_cache[archive_path] = (
                            manifest, manifest_root_dir, file_list)
                        return manifest, manifest_root_dir, file_list, None

                return None, None, None, ValueError("Manifest not found in archive or broken")
        except Exception as ex:
            self.logger.exception("Error on ZIP manifest check")
            self.archived_mod_manifests_cache[archive_path] = (None, None, None)
            return None, None, None, ex

    async def get_7z_mod_manifest_async(
            self, archive_path: str | AsyncPath, ignore_cache: bool = False,
            loading_text: Text | None = None
            ) -> tuple[
                str | None,
                Path | None,
                py7zr.ArchiveFileList | None,
                Exception | None]:
        if isinstance(archive_path, str):
            archive_path = AsyncPath(archive_path)
        if not ignore_cache:
            cached_info = self.archived_mod_manifests_cache.get(archive_path)
            if cached_info is not None:
                cached, root_path, file_list = cached_info
                if cached is not None:
                    return cached, root_path, file_list, None
        try:
            await asyncio.sleep(0)
            with py7zr.SevenZipFile(str(archive_path), "r") as archive:
                if loading_text is not None:
                    info = archive.archiveinfo()
                    loading_text.value = (f"[{info.method_names[0]}] "
                                          f"{info.size/1024/1024:.1f} MB -> "
                                          f"{info.uncompressed/1024/1024:.1f} MB")
                    loading_text.update()
                    await asyncio.sleep(0)
                file_list = archive.files
                manifests = [file for file in file_list
                             if "manifest.yaml" in file.filename]
                if manifests:
                    manifests_read_dict = archive.read(targets=[manifests[0].filename])
                    if manifests_read_dict.values():
                        manifest_b = list(manifests_read_dict.values())[0]  # noqa: RUF015
                    if manifest_b:
                        manifest_root_dir = Path(manifests[0].filename).parent
                        manifest = load_yaml(manifest_b)
                        if manifest is None:
                            raise yaml.YAMLError("Invalid yaml found in archive")

                        self.archived_mod_manifests_cache[archive_path] = (
                            manifest, manifest_root_dir, file_list)
                        return manifest, manifest_root_dir, file_list, None

                return None, None, None, ValueError("Manifest not found in archive or broken")
        except Exception as ex:
            self.logger.exception("Error on 7z manifest check")
            self.archived_mod_manifests_cache[archive_path] = (None, None, None)
            return None, None, None, ex

    async def get_archive_manifest(
            self, archive_path: str | AsyncPath, ignore_cache: bool = False,
            loading_text: Text | None = None) -> tuple[dict | None, Exception | None]:
        extension = Path(archive_path).suffix
        match extension:
            case ".7z":
                manifest, manifest_root_dir, file_list, exception = await self.get_7z_mod_manifest_async(
                    archive_path, loading_text=loading_text)
            case ".zip":
                manifest, manifest_root_dir, file_list, exception = await self.get_zip_mod_manifest_async(
                    archive_path, loading_text=loading_text)
            case _:
                manifest, manifest_root_dir, file_list, exception = \
                    None, None, None, TypeError("Unsuported archive type")
        return manifest, manifest_root_dir, file_list, exception

    async def get_archived_mod(
            self, archive_path: str | AsyncPath,
            manifest: Any, manifest_root_dir: DirectoryPath,  # noqa: ANN401
            file_list: list[zipfile.ZipInfo] | py7zr.ArchiveFileList | None,
            ignore_cache: bool = False
            ) -> tuple[Mod | None, Exception | None]:
        if not ignore_cache:
            cached = self.archived_mods_cache.get(archive_path)
            if cached is not None:
                return cached, None
        try:
            mod = Mod(
                **manifest, manifest_root=manifest_root_dir,
                archive_file_list=file_list)
        except (ValueError, AssertionError, ValidationError) as ex:
            self.archived_mods_cache[archive_path] = None
            return None, ex
        else:
            self.archived_mods_cache[archive_path] = mod
            return mod, None

    def setup_loggers(self, stream_only: bool = False) -> None:
        self.logger = logging.getLogger("dem")
        self.logger.propagate = False
        if self.logger.handlers and len(self.logger.handlers) > 1:
            self.logger.debug("Logger already exists, will use it with existing settings")
        else:
            self.logger.handlers.clear()
            self.logger.setLevel(logging.DEBUG)
            formatter = logging.Formatter("%(asctime)s: %(levelname)-7s - "
                                          "%(module)-11s - line %(lineno)-4d: %(message)s")
            stream_formatter = logging.Formatter("%(asctime)s: %(levelname)-7s - %(module)-11s"
                                                 " - line %(lineno)-4d: %(message)s")

            if self.dev_mode or (stream_only and "NUITKA_ONEFILE_PARENT" not in os.environ):
                stream_handler = logging.StreamHandler()
                stream_handler.setLevel(logging.DEBUG)
                stream_handler.setFormatter(stream_formatter)
                self.logger.addHandler(stream_handler)

            file_handler_level = logging.DEBUG

            if not stream_only:
                file_handler = logging.FileHandler(
                    os.path.join(self.log_path, f'debug_{datetime.now().strftime("%Y-%m-%d_%H-%M-%S")}.log'),
                    encoding="utf-8")
                file_handler.setLevel(file_handler_level)
                file_handler.setFormatter(formatter)
                self.logger.addHandler(file_handler)

            self.logger.info(f"ComMod {OWN_VERSION} {DATE} is running, loggers initialised")

    def setup_logging_folder(self) -> None:
        if self.distribution_dir:
            log_path = os.path.join(self.distribution_dir, "logs_commod")
            if os.path.exists(log_path):
                if not os.path.isdir(log_path):
                    os.remove(log_path)
                else:
                    log_files = list(Path(log_path).glob("debug_*.log"))
                    if len(log_files) >= LOG_FILES_TO_KEEP:
                        limit_logs_remove_at_once = 10
                        remove_num = len(log_files) - LOG_FILES_TO_KEEP
                        if remove_num > limit_logs_remove_at_once:
                            remove_num = limit_logs_remove_at_once
                        for _ in range(remove_num + 1):
                            try:
                                oldest_file = min(log_files, key=lambda f: f.stat().st_ctime)
                                oldest_file.unlink()
                                log_files.remove(oldest_file)
                            except PermissionError:
                                pass

            if not os.path.exists(log_path):
                os.mkdir(log_path)
            self.log_path = log_path
        else:
            raise FileLoggingSetupError("", "Distribution not found when setting up file logging")

    class Session:
        """Session stores information about the course of install and errors encountered."""

        def __init__(self) -> None:
            self.mod_loading_errors: list[str] = []
            self.steam_parsing_error: str | None = None

            self.content_in_processing: dict[str, str] = {}
            self.steam_game_paths: list[str] = []
            self.tracked_mods_hashes: dict[str, str] = {}
            self.mods: dict[str, Mod] = {}
            self.variants: dict[str, Mod] = {}

        @property
        def tracked_mods(self) -> set[str]:
            return {mod.id_str for mod in self.mods.values()}

        def load_steam_game_paths(self) -> tuple[str, str]:
            """Try to find the game(s) in default Steam folder, return path and error message."""
            steam_install_reg_path = r"SOFTWARE\WOW6432Node\Valve\Steam"
            validated_dirs = []
            try:
                import winreg
                hklm = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
                # getting Steam installation folder from Reg
                steam_install_reg_value = winreg.OpenKey(hklm, steam_install_reg_path)
                steam_install_path = winreg.QueryValueEx(steam_install_reg_value, "InstallPath")[0]

                # game can be installed in main Steam dir or in any of the libraries specified in config
                library_folders_config = os.path.join(steam_install_path, "config", "libraryfolders.vdf")
                library_folders_config_steamapps = os.path.join(steam_install_path, "SteamApps",
                                                                "libraryfolders.vdf")
                library_folder_config_steamapps = os.path.join(steam_install_path, "SteamApps",
                                                               "libraryfolder.vdf")
                library_folders = [steam_install_path] if os.path.isdir(steam_install_path) else []
                game_folders = []
                if os.path.exists(library_folders_config):
                    library_config_path = library_folders_config
                elif os.path.exists(library_folders_config_steamapps):
                    library_config_path = library_folders_config_steamapps
                elif os.path.exists(library_folder_config_steamapps):
                    library_config_path = library_folder_config_steamapps
                else:
                    return False

                if not os.path.exists(library_config_path):
                    return False

                with open(library_config_path, encoding="utf-8") as f:
                    lines = f.readlines()
                    if '"libraryfolders"\n' in lines:
                        library_folders = [line for line in lines if '"path"' in line]
                    elif '"libraryfolder"\n' in lines:
                        pass

                    for lib in library_folders:
                        striped_lib = lib.replace("path", "").replace('"', "").strip()
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
            except (ImportError, NameError):
                self.steam_parsing_error = "WinRegUnavailable/OSNotSupportedForSteamAutodetect"
                return False
            except FileNotFoundError:
                self.steam_parsing_error = "FileNotFound/RegistryNotFound"
                return False
            except Exception as ex:  # noqa: BLE001
                self.steam_parsing_error = f"General error when parsing Steam paths: {ex}"
                return False

            self.steam_game_paths = validated_dirs
            return True


class GameInstallment(Enum):
    ALL = 0
    EXMACHINA = 1
    M113 = 2
    ARCADE = 3
    UNKNOWN = 4

    @classmethod
    def list_values(cls) -> list[int]:
        return [c.value for c in cls]


class GameCopy:
    """Stores info about a processed HTA/EM game copy."""

    def __init__(self) -> None:
        self.logger = logging.getLogger("dem")
        self.installed_content = {}
        self.installed_descriptions = {}
        self.patched_version = False
        self.leftovers = False
        self.target_exe = ""
        self.fullscreen_game = True
        self.hi_dpi_aware = False
        self.fullscreen_opts_disabled = False
        self.game_root_path = ""
        self.exe_version = "unknown"
        self.installment = None
        self.installment_id = 4
        self.cached_warning = ""

    @property
    def exe_version_tr(self) -> str:
        if self.exe_version == "unknown":
            return tr(self.exe_version)
        if not self.exe_version:
            return " ... "
        return self.exe_version.replace("Remaster", "Rem")

    @staticmethod
    def validate_game_dir(game_root_path: str) -> tuple[bool, str]:
        """Check existence of expected basic file structure in a given game directory."""
        if not game_root_path or not os.path.isdir(game_root_path):
            return False, game_root_path

        exe_path = GameCopy.get_exe_name(game_root_path)

        if exe_path is None:
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
        return True, ""

    @staticmethod
    def validate_install_manifest(install_config: dict) -> bool:
        for config_name in install_config:
            base = install_config[config_name].get("base")
            version = install_config[config_name].get("version")
            if base is None or version is None:
                return False
        return True

    def check_is_running(self) -> bool:
        if not Path(self.target_exe).exists():
            raise ExeNotFoundError

        if self.target_exe:
            return self.get_exe_version(self.target_exe) is None

        return False

    def refresh_game_launch_params(self, exclude_registry_params: bool = False) -> None:
        if self.exe_version != "unknown" and self.game_root_path:
            self.fullscreen_game = self.get_is_fullscreen()
            if self.fullscreen_game is None:
                # TODO: is not actually InvalidGameDirectory but more like BrokenGameConfig exception
                raise InvalidGameDirectoryError(os.path.join(self.game_root_path, "data", "config.cfg"))
            if not exclude_registry_params:
                self.hi_dpi_aware = self.get_is_hidpi_aware()
                self.logger.debug(f"HiDPI awareness status: {self.hi_dpi_aware}")
                self.fullscreen_opts_disabled = self.get_is_fullscreen_opts_disabled()
                self.logger.debug(f"Fullscreen optimisations disabled status: {self.fullscreen_opts_disabled}")

    def process_game_install(self, target_dir: str) -> None:
        """Parse game install to know the version and current state of it."""
        self.logger.debug(f"Checking that '{target_dir}' is dir")
        if not os.path.isdir(target_dir):
            raise WrongGameDirectoryPathError

        self.logger.debug(f"Starting game files validation for '{target_dir}'")
        valid_base_dir, missing_path = self.validate_game_dir(target_dir)
        self.logger.debug(f"Game dir 'is valid' status: {valid_base_dir}")

        if missing_path:
            self.logger.debug(f"Missing path: '{missing_path}'")
        if not valid_base_dir:
            raise InvalidGameDirectoryError(missing_path)

        self.logger.debug("Getting exe name from target dir")
        exe_path = self.get_exe_name(target_dir)
        self.logger.debug(f"Exe path: '{exe_path}'")

        if exe_path is not None:
            self.target_exe = exe_path
        else:
            raise ExeNotFoundError

        self.logger.debug("Getting exe version")
        exe_version = self.get_exe_version(self.target_exe)
        if exe_version is None:
            if self.exe_version == "unknown":
                self.exe_version = ""
            raise ExeIsRunningError

        self.exe_version = exe_version
        self.logger.debug(f"Exe version: {self.exe_version}")

        if self.exe_version == "unknown":
            self.installment = None
            self.installment_id = 4
        elif "M113" in self.exe_version:
            self.installment = "m113"
            self.installment_id = 2
        elif "Arcade" in self.exe_version:
            self.installment = "arcade"
            self.installment_id = 3
        else:
            self.installment = "exmachina"
            self.installment_id = 1

        if not self.is_commod_compatible_exe(self.exe_version):
            raise ExeNotSupportedError(self.exe_version_tr)

        self.logger.debug("Is ComPatch compatible")
        self.game_root_path = target_dir
        self.data_path = os.path.join(self.game_root_path, "data")
        self.installed_manifest_path = os.path.join(self.data_path, "mod_manifest.yaml")

        patched_version = (self.exe_version.startswith("ComRemaster")
                           or self.exe_version.startswith("ComPatch"))

        self.refresh_game_launch_params()

        # self.display_name = f"[{self.exe_version_tr}] {shorten_path(self.game_root_path, 45)}"

        self.logger.debug(f"Checking mod_manifest for game copy: {self.installed_manifest_path}")
        if os.path.exists(self.installed_manifest_path):
            install_manifest = read_yaml(self.installed_manifest_path)
            if install_manifest is None:
                raise InvalidExistingManifestError(self.installed_manifest_path)
            valid_manifest = self.validate_install_manifest(install_manifest)
            if valid_manifest and patched_version:
                self.logger.debug("mod_manifest is valid")
                for manifest in install_manifest.values():
                    if manifest.get("language") is None:
                        manifest["language"] = "not_specified"
                    if manifest.get("installment") is None:
                        manifest["installment"] = GameInstallment.EXMACHINA.value
                self.installed_content = install_manifest
                self.patched_version = True
                return

            if patched_version and not valid_manifest:
                raise InvalidExistingManifestError(self.installed_manifest_path)

            self.leftovers = True
            raise HasManifestButUnpatchedError(self.exe_version_tr, install_manifest)

        if patched_version:
            self.patched_version = True
            self.installed_content = {}
            self.leftovers = True
            raise PatchedButDoesntHaveManifestError(self.exe_version_tr)

        self.logger.debug("Finished process_game_install")

    def is_modded(self) -> bool:
        # TODO: deprecate this or add logic not dependent on ComRem/Patch existance
        if not self.installed_content:
            return False

        if "community_remaster" in self.installed_content and len(self.installed_content) > 2:
            return True
        if "community_patch" in self.installed_content and len(self.installed_content) > 1:
            return True

        return False

    def load_installed_descriptions(self, known_mods: list[Mod] | None = None) -> list[str]:
        """Construct dict of pretty description strings for list of installed content.

        Does so based on existing short mod manifest of the game and optional list of full mod objects.
        """
        known_mod_names = []

        if known_mods:
            known_mod_names = {mod.name for mod in known_mods.values()}

        if not self.installed_content:
            return

        for content_piece in self.installed_content:
            install_manifest = self.installed_content[content_piece]
            name = content_piece

            content_version_str = repr(Version.parse_from_str(str(install_manifest["version"])))

            if name == "community_patch" and "community_remaster" in self.installed_content:
                continue

            if install_manifest.get("display_name") is not None:
                name = install_manifest["display_name"]
            elif known_mod_names and content_piece in known_mod_names:
                content_lang = install_manifest.get("language") or SupportedLanguages.RU.value
                known_mod_entries = [
                    mod for mod in known_mods.values()
                    if (mod.name == content_piece
                        and repr(mod.version) == content_version_str
                        and mod.language == content_lang)]
                if known_mod_entries:
                    name = known_mod_entries[0].display_name

            optional_content_keys = install_manifest.keys() - RESERVED_CONTENT_NAMES
            unskipped_content = {key: value for key, value in install_manifest.items() if value != "skip"}
            installed_optional_content = unskipped_content.keys() - RESERVED_CONTENT_NAMES

            build = ""
            if install_manifest.get("build") is not None:
                build = f" [{install_manifest['build']}]"

            description = f'{name} ({tr("version")} {content_version_str}){build}\n'

            if installed_optional_content:
                description += (f'{tr("optional_content").capitalize()}: '
                                f'{", ".join(sorted(installed_optional_content))}\n')
            elif optional_content_keys:
                description += f'* {tr("base_version")}\n'

            self.installed_descriptions[content_piece] = description.strip()

    async def change_config_values(self, config_options: ConfigOptions) -> None:
        config = get_config(self.game_root_path)

        key_value_pairs = config_options.model_dump()

        for key, value in key_value_pairs.items():
            if value is None:
                continue
            current_value = config.attrib.get(key)
            if current_value is not None:
                config.attrib[key] = str(value)
        await write_xml_to_file_async(
            config, os.path.join(self.game_root_path, "data", "config.cfg"))

    async def switch_windowed(self, monitor_res: tuple[int, int],
                              enable: bool = True) -> None:
        config = get_config(self.game_root_path)
        current_value = config.attrib.get("r_fullScreen")
        if current_value is not None:
            if enable:
                if current_value in TARGEM_POSITIVE:
                    return
                config.attrib["r_fullScreen"] = "true"
                # TODO: maybe also check for existance of "r_width", "r_height" in case of broken config
                cur_width = int(config.attrib["r_width"])
                cur_height = int(config.attrib["r_height"])
                known_height = KNOWN_RESOLUTIONS.get(cur_width)
                if (known_height is not None and cur_height != known_height):
                    self.logger.debug("Fixed broken fullscreen res in config")
                    config.attrib["r_height"] = str(known_height)
                    self.fullscreen_game = True
                elif known_height is None:
                    new_res = [(w, h) for w, h in KNOWN_RESOLUTIONS.items() if h == monitor_res[1]]
                    if new_res:
                        config.attrib["r_width"] = str(new_res[0][0])
                        config.attrib["r_height"] = str(new_res[0][1])          
                        self.fullscreen_game = True
                    else:
                        self.logger.debug(
                            "Was unable to find appropriate fullscreen game res: "
                            f"current window res: ({config.attrib['r_height']}, {config.attrib['r_width']}), "
                            f"monitor res: ({monitor_res})")
                        return
            else:
                if current_value in TARGEM_NEGATIVE:
                    return
                config.attrib["r_fullScreen"] = "false"
                self.fullscreen_game = False
            await write_xml_to_file_async(config,
                                     os.path.join(self.game_root_path, "data", "config.cfg"))

    def get_is_fullscreen(self) -> bool:
        config = get_config(self.game_root_path)
        current_value = config.attrib.get("r_fullScreen")
        if current_value in TARGEM_POSITIVE:
            return True
        if current_value in TARGEM_NEGATIVE:
            return False

        return None

    # TODO: maybe split to two functions without bool flag
    def switch_hi_dpi_aware(self, enable: bool = True) -> None:
        self.logger.debug("Setting hidpi awareness")
        compat_settings_reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
        try:
            import winreg
            hkcu = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            compat_settings_reg_value_hkcu = winreg.OpenKey(
                hkcu, compat_settings_reg_path, 0, winreg.KEY_WRITE)
        except (ImportError, NameError):
            self.logger.debug("Unable to use WinReg, might be running under another OS")
            return False
        except PermissionError:
            self.logger.debug("Unable to open registry - no access")
            return False
        except OSError:
            self.logger.debug("OS error, key probably doesn't exist", exc_info=True)

        if enable:
            try:
                if self.fullscreen_opts_disabled:
                    new_value = "~ DISABLEDXMAXIMIZEDWINDOWEDMODE HIGHDPIAWARE"
                else:
                    new_value = "~ HIGHDPIAWARE"
                winreg.SetValueEx(compat_settings_reg_value_hkcu,
                                  self.target_exe, 0, winreg.REG_SZ,
                                  new_value)
                self.hi_dpi_aware = True
            except PermissionError:
                self.logger.debug("Unable to set hi_dpi_aware/disable_fullscreen_optimisations - no access")
                return False
            else:
                return True
        else:
            try:
                if not self.fullscreen_opts_disabled:
                    winreg.DeleteValue(compat_settings_reg_value_hkcu,
                                       self.target_exe)
                else:
                    winreg.SetValueEx(compat_settings_reg_value_hkcu,
                                      self.target_exe, 0, winreg.REG_SZ,
                                      "~ DISABLEDXMAXIMIZEDWINDOWEDMODE")
            except FileNotFoundError:
                pass
            except (PermissionError, OSError):
                return False

            success = not self.get_is_hidpi_aware()

            if success:
                self.hi_dpi_aware = False
                return True
            return False

    def get_is_hidpi_aware(self) -> bool:
        try:
            self.logger.debug("Checking hidpi awareness status")
            compat_settings_reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
            try:
                import winreg
                hklm = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
                compat_settings_reg_value = winreg.OpenKey(hklm, compat_settings_reg_path, 0, winreg.KEY_READ)
                value = winreg.QueryValueEx(compat_settings_reg_value, self.target_exe)
                if "HIGHDPIAWARE" in value[0]:
                    self.logger.debug("Found key in HKLM")
                    return True
                value = None
            except (ImportError, NameError):
                self.logger.debug("Unable to use WinReg, might be running under another OS")
                return False
            except FileNotFoundError:
                value = None
                self.logger.debug("Key not found in HKLM")
            except OSError:
                self.logger.debug("General os error", exc_info=True)
                value = None
            except IndexError:
                value = None

            hkcu = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            try:
                compat_settings_reg_value = winreg.OpenKey(hkcu, compat_settings_reg_path, 0, winreg.KEY_READ)
                value = winreg.QueryValueEx(compat_settings_reg_value, self.target_exe)
                if "HIGHDPIAWARE" in value[0]:
                    self.logger.debug("Found key in HKCU")
                    return True
                value = None
            except FileNotFoundError:
                value = None
                self.logger.debug("Key not found in HKCU")
            except OSError:
                value = None
                self.logger.debug("General os error", exc_info=True)
            except IndexError:
                value = None

            if value is None:
                return False
        except Exception:
            self.logger.exception("General error when trying to get hidpi status")
            return False

    # TODO: split to two functions without bool flag
    def switch_fullscreen_opts(self, disable: bool = True) -> bool:
        compat_settings_reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
        try:
            import winreg
            hkcu = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            compat_settings_reg_value_hkcu = winreg.OpenKey(
                hkcu, compat_settings_reg_path, 0, winreg.KEY_WRITE)
        except (ImportError, NameError):
            self.logger.debug("Unable to use WinReg, might be running under another OS")
            return False
        except PermissionError:
            self.logger.debug("Unable to open registry - no access")
            return False

        if disable:
            try:
                if self.hi_dpi_aware:
                    new_value = "~ DISABLEDXMAXIMIZEDWINDOWEDMODE HIGHDPIAWARE"
                else:
                    new_value = "~ DISABLEDXMAXIMIZEDWINDOWEDMODE"
                winreg.SetValueEx(compat_settings_reg_value_hkcu,
                                  self.target_exe, 0, winreg.REG_SZ,
                                  new_value)

                self.fullscreen_opts_disabled = True
            except PermissionError:
                self.logger.debug("Unable to set hi_dpi_aware/disable_fullscreen_optimisations - no access")
                return False
            else:
                return True
        else:
            try:
                if not self.hi_dpi_aware:
                    winreg.DeleteValue(compat_settings_reg_value_hkcu,
                                       self.target_exe)
                else:
                    winreg.SetValueEx(compat_settings_reg_value_hkcu,
                                      self.target_exe, 0, winreg.REG_SZ,
                                      "~ HIGHDPIAWARE")
            except FileNotFoundError:
                pass
            except (PermissionError, OSError):
                return False

            success = not self.get_is_fullscreen_opts_disabled()

            if success:
                self.fullscreen_opts_disabled = False
                return True
            return False

    def get_is_fullscreen_opts_disabled(self) -> bool:
        try:
            self.logger.debug("Checking fullscreen optimisations status")
            compat_settings_reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
            try:
                import winreg
                hklm = winreg.ConnectRegistry(None, winreg.HKEY_LOCAL_MACHINE)
                compat_settings_reg_value = winreg.OpenKey(hklm, compat_settings_reg_path, 0, winreg.KEY_READ)
                value = winreg.QueryValueEx(compat_settings_reg_value, self.target_exe)
                if "DISABLEDXMAXIMIZEDWINDOWEDMODE" in value[0]:
                    self.logger.debug("Found key in HKLM")
                    return True
                value = None
            except (ImportError, NameError):
                self.logger.debug("Unable to use WinReg, might be running under another OS")
                return False
            except FileNotFoundError:
                value = None
                self.logger.debug("Key not found in HKLM")
            except OSError:
                value = None
                self.logger.debug("General os error", exc_info=True)
            except IndexError:
                value = None

            hkcu = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            try:
                compat_settings_reg_value = winreg.OpenKey(hkcu, compat_settings_reg_path, 0, winreg.KEY_READ)
                value = winreg.QueryValueEx(compat_settings_reg_value, self.target_exe)
                if "DISABLEDXMAXIMIZEDWINDOWEDMODE" in value[0]:
                    self.logger.debug("Found key in HKCU")
                    return True
                value = None
            except FileNotFoundError:
                value = None
                self.logger.debug("Key not found in HKCU")
            except OSError:
                value = None
                self.logger.debug("General os error", exc_info=True)
            except IndexError:
                value = None

            if value is None:
                return False
        except Exception:
            self.logger.exception("General error when gettings fullscreen optimisations status")
            return False

    @staticmethod
    def is_commod_compatible_exe(version: str) -> bool:
        return ("Clean" in version) or ("ComRemaster" in version) or ("ComPatch" in version)

    @staticmethod
    def get_exe_name(target_dir: str) -> str:
        possible_exe_paths = ["hta.exe",
                              "game.exe",
                              "start.exe",
                              "ExMachina.exe",
                              "Meridian113.exe",
                              "emarcade.exe"]
        for exe_name in possible_exe_paths:
            full_path = os.path.join(target_dir, exe_name)
            if os.path.exists(full_path):
                return os.path.normpath(full_path)
        return None

    @staticmethod
    def get_exe_version(target_exe: str) -> str:
        try:
            with open(target_exe, "rb+") as f:
                f.seek(VERSION_BYTES_102_NOCD)
                main_version_identifier = f.read(15)

                vanilla_version_id = main_version_identifier[8:12]
                if vanilla_version_id == b"1.02":
                    return "Clean 1.02"
                if vanilla_version_id == b"1.04":
                    return "KRBDZSKL 1.04"

                compatch_version_id = main_version_identifier[:4]
                match compatch_version_id:
                    case b"1.10":
                        return "ComPatch 1.10"
                    case b"1.11":
                        return "ComPatch 1.11"
                    case b"1.12":
                        return "ComPatch 1.12"
                    case b"1.13":
                        return "ComPatch 1.13"
                    case b"1.14":
                        return "ComPatch 1.14"
                    case b"1.02":
                        return "ComPatch Mini"

                comrem_version_id = main_version_identifier[3:7]
                match comrem_version_id:
                    case b"1.10":
                        return "ComRemaster 1.10"
                    case b"1.11":
                        return "ComRemaster 1.11"
                    case b"1.12":
                        return "ComRemaster 1.12"
                    case b"1.13":
                        return "ComRemaster 1.13"
                    case b"1.14":
                        return "ComRemaster 1.14"

                f.seek(VERSION_BYTES_103_NOCD)
                version_identifier_103_nocd = f.read(15)
                if version_identifier_103_nocd[1:5] == b"1.03":
                    return "DRM-free 1.03"

                f.seek(VERSION_BYTES_M113_101)
                version_identifier_m113 = f.read(4)
                if version_identifier_m113 == b"1.01":
                    return "Meridian 113/RoC 1.01 (unsupported)"

                f.seek(VERSION_BYTES_ARCD_100)
                version_identifier_arcade = f.read(3)
                if version_identifier_arcade == b"1.0":
                    return "Arcade 1.0 (unsupported)"

                f.seek(VERSION_BYTES_100_STAR)
                version_identifier_100_star = f.read(15)
                if version_identifier_100_star[1:5] == b"1.0 ":
                    return "1.0 Starforce"

                f.seek(VERSION_BYTES_102_STAR)
                version_identifier_102_star = f.read(15)
                if version_identifier_102_star[:9] == b"O0\x87\xfa%\xbc\x9f\x86Q":
                    return "1.02 Starforce"

                f.seek(VERSION_BYTES_103_STAR)
                version_identifier_103_star = f.read(15)
                if version_identifier_103_star[:9] == b"\xbf\xcf\x966\xf1\x97\xf2\xc5\x11":
                    return "1.03 Starforce"

                f.seek(VERSION_BYTES_DEM_LNCH)
                version_identifier_dem_lnch = f.read(15)
                if version_identifier_dem_lnch[:9] == b"\x00\x8dU\x98R\xe8)\x07\x00":
                    return "Old DEM launcher"

        except PermissionError:
            return None
        else:
            return "unknown"

    def check_compatible_game(self, game_path: str) -> tuple[bool, bool]:
        can_be_added = True
        warning = ""

        game_is_running = False
        try:
            self.process_game_install(game_path)
        except WrongGameDirectoryPathError:
            can_be_added = False
            warning = f"{tr('not_a_valid_path')}: {game_path}"
        except ExeIsRunningError:
            can_be_added = False
            warning = f"{tr('game_is_running_cant_select')}"
            game_is_running = True
        except PatchedButDoesntHaveManifestError as ex:
            warning += (f"{tr('install_leftovers')}\n\n"
                        f"**{tr('error')}:**\n\n"
                        f"{tr('dirty_copy_warning')} (PatchedButDoesntHaveManifestError)\n"
                        f"**{tr('exe_version')}:** {ex.exe_version}\n\n")
        except HasManifestButUnpatchedError as ex:
            warning = (f"{tr('install_leftovers')}\n\n"
                       f"**{tr('error')}:**\n\n"
                       f"{tr('dirty_copy_warning')} (HasManifestButUnpatchedError)\n\n"
                       f"**{tr('exe_version')}:** {ex.exe_version}\n\n"
                       f"**{tr('description')}:**\n{pprint.pformat(ex.manifest_content)}\n\n")
        except ExeNotSupportedError as ex:
            can_be_added = False
            warning = (f'{tr("broken_game")}\n\n'
                       f'**{tr("exe_version")}:** {ex.exe_version}\n\n'
                       f'**{tr("error")}:**\n\n{tr("exe_not_supported")}\n\n')
        except InvalidGameDirectoryError as ex:
            can_be_added = False
            warning = (f'{tr("broken_game")}\n\n**{tr("error")}**:\n\n'
                       f'{tr("target_dir_missing_files")}\n\n{ex}')
        except InvalidExistingManifestError as ex:
            can_be_added = False
            warning = (f'{tr("broken_game")}\n\n**{tr("error")}**:\n\n'
                       f'{tr("invalid_existing_manifest")}\n\n{ex}')
        except Exception as ex:
            can_be_added = False
            warning = (f'{tr("broken_game")}\n\n{tr("path_to_game")}: {game_path}\n\n'
                       f'**{tr("error")}**:\n{ex} ({ex!r})')
            self.logger.exception("Error when processing game install")
        self.cached_warning = warning

        return can_be_added, game_is_running

