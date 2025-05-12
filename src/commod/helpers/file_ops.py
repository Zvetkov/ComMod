# ruff: noqa: E721

import asyncio
import json
import logging
import math
import os
import platform
import shutil
import struct
import subprocess
import sys
import typing
import zipfile
from collections.abc import Awaitable, Callable, Iterable, Sequence
from math import ceil
from pathlib import Path
from typing import Any

import aiofiles
import psutil
import py7zr
import yaml
from flet import Text
from lxml import etree, objectify

from commod.game.data import ENCODING
from commod.helpers.parse_ops import beautify_machina_xml, xml_to_objfy

logger = logging.getLogger("dem")

SUPPORTED_IMG_TYPES = (".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
RESOLUTION_OPTION_LIST_SIZE = 5

def process_xml_tree(objectify_tree: objectify.ObjectifiedElement,
                     machina_beautify: bool = True,
                     use_utf: bool = False) -> bytes:
    if use_utf:
        doctype = ""
        encoding = "utf-8"
    else:
        doctype = f'<?xml version="1.0" encoding="{ENCODING}" standalone="yes" ?>'
        encoding = ENCODING

    etree.indent(objectify_tree, space="    ")
    xml_string = etree.tostring(
        objectify_tree,
        pretty_print=True,
        xml_declaration=False,
        doctype=doctype,
        encoding=encoding)

    return beautify_machina_xml(xml_string) if machina_beautify else xml_string

def write_xml_to_file(
    objectify_tree: objectify.ObjectifiedElement,
    path: str | Path, machina_beautify: bool = True,
    use_utf: bool = False) -> None:
    """Write ObjectifiedElement tree to file at path.

    Will format and beautify file in the style very similar to original EM dynamicscene.xml
    files by default. Can skip beautifier and save raw lxml formated file.
    """
    with Path(path).open("wb") as fh:
        fh.write(process_xml_tree(
            objectify_tree,
            machina_beautify=machina_beautify,
            use_utf=use_utf))


async def write_xml_to_file_async(
        objectify_tree: objectify.ObjectifiedElement,
        path: str | Path,
        machina_beautify: bool = True,
        use_utf: bool = False) -> None:
    """Asynchronously write ObjectifiedElement tree to file at path.

    Will format and beautify file in the style very similar to original EM
    dynamicscene.xml files by default. Can skip beautifier and save raw lxml
    formated file.
    """
    async with aiofiles.open(path, mode="wb") as fh:
        await fh.write(process_xml_tree(
            objectify_tree,
            machina_beautify=machina_beautify,
            use_utf=use_utf))

def open_dir_in_os(directory_path: str | Path) -> None:
    """Open directory in Windows Explorer or OS specific equiavalents."""
    directory_path = Path(directory_path)
    if directory_path.is_dir():
        sysplat = platform.system()
        if "Windows" in sysplat:
            os.startfile(directory_path)  # noqa: S606
            return
        opener = "open" if "Darwin" in sysplat else "xdg-open"
        subprocess.call([opener, directory_path])  # noqa: S603

def open_file_in_editor(file_path: str | Path, editor: str, line: int = 1) -> None:
    """Open file in VSCode or other configurated editor."""
    file_path = Path(file_path)
    if file_path.exists():
        final_cmd = [editor]
        try:
            if editor == "code" or "code.exe" in editor.lower():
                if line != 1:
                    final_cmd.extend(["-g", f"{file_path}:{line}"])
                else:
                    final_cmd.append(str(file_path))
            elif "notepad++" in editor.lower():
                if line != 1:
                    final_cmd.extend([str(file_path), f"-n{line}"])
                else:
                    final_cmd.append(str(file_path))
            elif Path(editor).exists():
                final_cmd.append(str(file_path))
            else:
                return

            # looks bad but isn't, we validate both parts of shell invocation to disallow arbitrary execution
            subprocess.run(final_cmd, shell=True, check=False)  # noqa: S602
        except Exception:
            logger.exception("Unable to open file in editor")

def count_files(directory: str) -> int:
    files = []

    if os.path.isdir(directory):
        for _, _, filenames in os.walk(directory):
            files.extend(filename for filename in filenames if not filename.startswith("_"))

    return len(files)

async def copy_from_to_async(from_path_list: list[str],
                             to_path: str, callback_progbar: Callable) -> None:
    files_count = 0
    for from_path in from_path_list:
        logger.debug(f"Copying files from '{from_path}' to '{to_path}'")
        files_count += count_files(from_path)
    file_num: int = 1
    for from_path in from_path_list:
        for path, dirs, _ in os.walk(from_path):
            for directory in dirs:
                dest_dir = path.replace(from_path, to_path)
                os.makedirs(os.path.join(dest_dir, directory), exist_ok=True)
        for path, _, filenames in os.walk(from_path):
            for sfile in filenames:
                dest_file = os.path.join(path.replace(from_path, to_path), sfile)
                file_size = round(Path(os.path.join(path, sfile)).stat().st_size / 1024, 2)
                await asyncio.to_thread(shutil.copy2, os.path.join(path, sfile), dest_file)
                await callback_progbar(file_num, files_count, sfile, file_size)
                file_num += 1

async def copy_relative_paths_and_call_async(
        relative_path: Path,
        file_num: list[int],
        base_from_path: str | Path, base_to_path: str | Path,
        files_count: int,
        callback_progbar: Callable[[int, int, str, float], Awaitable[None]]) -> None:
    from_path = Path(base_from_path, relative_path)
    to_path = Path(base_to_path, relative_path)
    # TODO: rethink if something this ugly is really required \/
    # Note: file num is a dirty hack to pass pointer to mutable int value (index of current file)
    file_size = round(from_path.stat().st_size / 1024, 2)
    try:
        await asyncio.to_thread(shutil.copy2, from_path, to_path)
    except PermissionError:
        msg = f"Can't overwrite path '{to_path}', this file is blocked by something, possibly opened"
        raise PermissionError(msg)  # noqa: B904
    await callback_progbar(file_num[0], files_count, from_path.name, file_size)
    await asyncio.sleep(0)
    file_num[0] += 1

async def copy_file_and_call_async(
        path: str, file_num: list[int],
        single_file: str,
        from_path: str, to_path: str,
        files_count: int,
        callback_progbar: Callable[[int, int, str, float], Awaitable[None]]) -> None:
    # TODO: rethink if something this ugly is really required \/
    # Note: file num is a dirty hack to pass pointer to mutable int value (index of current file)
    dest_file = os.path.join(path.replace(from_path, to_path), single_file)
    file_size = round(Path(os.path.join(path, single_file)).stat().st_size / 1024, 2)
    await asyncio.to_thread(shutil.copy2, os.path.join(path, single_file), dest_file)
    await callback_progbar(file_num[0], files_count, single_file, file_size)
    await asyncio.sleep(0)
    file_num[0] += 1


async def copy_targets_from_to_async(
        targets_list: Sequence[Path],
        from_base_path: str | Path,
        to_base_path: str | Path,
        callback_progbar: Callable[[int, int, str, float], Awaitable[None]]) -> None:

    from_base_path = Path(from_base_path)
    to_base_path = Path(to_base_path)
    files_count = len(targets_list)
    file_num = []
    file_num.append(1)
    for target in targets_list:
        file_parent = (to_base_path / target).parent
        file_parent.mkdir(parents=True, exist_ok=True)

    await asyncio.gather(*[
        copy_relative_paths_and_call_async(
            target, file_num,
            from_base_path, to_base_path,
            files_count,
            callback_progbar) for target in targets_list])

async def copy_from_to_async_fast(
        from_path_list: Sequence[str | Path],
        to_path: str | Path,
        callback_progbar: Callable[[int, int, str, float], Awaitable[None]]) -> None:
    from_path_list = [str(path_entry) for path_entry in from_path_list]
    to_path = str(to_path)

    files_count = 0
    for from_path in from_path_list:
        logger.debug(f"Copying files from '{from_path}' to '{to_path}'")
        files_count += count_files(from_path)
    file_num = []
    file_num.append(1)
    for from_path in from_path_list:
        for path, dirs, _ in os.walk(from_path):
            for directory in dirs:
                dest_dir = path.replace(from_path, to_path)
                os.makedirs(os.path.join(dest_dir, directory), exist_ok=True)
        for path, _, filenames in os.walk(from_path):
            await asyncio.gather(*[
                copy_file_and_call_async(path, file_num, single_file,
                                         from_path, to_path, files_count,
                                         callback_progbar) for single_file in filenames
                                         if not single_file.startswith("_")])


async def extract_files_from_zip(
        archive: zipfile.ZipFile,
        file_names: list[str],
        path: str | Path,
        callback: Callable | None = None,
        files_num: int = 1) -> None:
    for file_name_raw in file_names:
        file_name = file_name_raw
        data = archive.read(file_name)
        try:
            file_name.encode("cp437").decode("ascii")
        except UnicodeDecodeError:
            file_name = file_name.encode("cp437").decode("cp866")
        except UnicodeEncodeError:
            pass
        filepath = Path(path, file_name)
        if not filepath.parent.is_dir():
            os.makedirs(filepath.parent, exist_ok=True)

        async with aiofiles.open(str(filepath), "wb") as fd:
            await fd.write(data)
        if callback is not None:
            await callback(files_num)


async def extract_files_from_7z(
        archive: py7zr.SevenZipFile,
        file_names: list[str],
        path: str | Path,
        callback: Callable | None = None,
        files_num: int = 1, chunksize: int = 1) -> None:
    archive.reset()
    archive.extract(path, targets=file_names)
    if callback is not None:
        await callback(files_num, chunksize)
        await asyncio.sleep(0)


async def extract_archive_from_to(archive_path: str, to_path: str, callback: Callable | None = None,
                          loading_text: Text | None = None) -> None:
    extension = Path(archive_path).suffix
    match extension:
        case ".7z":
            await extract_7z_from_to(archive_path, to_path, callback, loading_text)
        case ".zip":
            await extract_zip_from_to(archive_path, to_path, callback, loading_text)
        case _:
            raise NotImplementedError(f"Unsupported archive type: {archive_path}")


async def extract_zip_from_to(archive_path: str | Path, to_path: str | Path,
                              callback: Callable | None = None,
                              loading_text: Text | None = None) -> None:
    os.makedirs(to_path, exist_ok=True)
    with zipfile.ZipFile(archive_path, "r") as archive:
        only_files = []

        total_size = 0
        total_compressed_size = 0
        compression_label = "ZIP"

        namelist = archive.namelist()
        workers = 100
        chunksize = ceil(len(namelist) / workers)
        if chunksize == 0:
            chunksize = 1
        tasks = []

        for file in archive.filelist:
            file_path = file.filename
            if file.is_dir():
                try:
                    file_path.encode("cp437").decode("ascii")
                except UnicodeDecodeError:
                    file_path = file_path.encode("cp437").decode("cp866")
                except UnicodeEncodeError:
                    pass
                os.makedirs(Path(to_path) / file_path, exist_ok=True)
            else:
                only_files.append(file_path)
                if loading_text is not None:
                    total_size += file.file_size
                    total_compressed_size += file.compress_size
                    if compression_label == "ZIP":
                        match file.compress_type:
                            case 8:
                                compression_label = "DEFLATE"
                            case 12:
                                compression_label = "BZIP2"
                            case 14:
                                compression_label = "LZMA"
                            case _:
                                pass

        if loading_text is not None:
            loading_text.value = (f"[{compression_label}] "
                                  f"{total_compressed_size/1024/1024:.1f}MB -> "
                                  f"{total_size/1024/1024:.1f}MB")
            loading_text.update()
            await asyncio.sleep(0)

        files_num = len(only_files)
        for i in range(0, files_num, chunksize):
            file_names = only_files[i:(i + chunksize)]
            tasks.append(extract_files_from_zip(archive, file_names, to_path, callback, files_num))
        await asyncio.gather(*tasks)


async def extract_7z_from_to(archive_path: str | Path, to_path: str | Path,
                             callback: Callable | None = None,
                             loading_text: Text | None = None) -> None:
    os.makedirs(to_path, exist_ok=True)
    with py7zr.SevenZipFile(str(archive_path), "r") as archive:
        if loading_text is not None:
            info = archive.archiveinfo()
            loading_text.value = (f"[{info.method_names[0]}] "
                                  f"{info.size/1024/1024:.1f}MB -> "
                                  f"{info.uncompressed/1024/1024:.1f}MB") # type: ignore (is actually int)
            loading_text.update()
            await asyncio.sleep(0)
        all_files = archive.files
        dirs = []
        files = []
        for file in all_files:
            if file.emptystream:
                dirs.append(file.filename)
            else:
                files.append(file.filename)

        for one_dir in dirs:
            os.makedirs(Path(to_path) / one_dir, exist_ok=True)

        archive_size = archive.archiveinfo().uncompressed
        # chunk extraction for every 32MB of internal data to show some kind of progress
        # if file is big, extract it in 5 chunks
        chunk_file_size = archive_size / 5 # type: ignore (is actually int)
        default_chunk_file_size = 1024 * 1024 * 32

        if chunk_file_size > default_chunk_file_size:
            workers = round(archive_size / chunk_file_size)
        else:
            workers = round(archive_size / default_chunk_file_size) # type: ignore (is actually int)

        if workers == 0:
            workers = 1

        chunksize = ceil(len(files) / workers)
        if chunksize == 0:
            chunksize = 1

        files_num = len(files)
        for i in range(0, files_num, chunksize):
            file_names = files[i:(i + chunksize)]
            await extract_files_from_7z(archive, file_names, to_path, callback, files_num, chunksize)


def load_yaml(stream: typing.IO) -> Any:  # noqa: ANN401
    try:
        return yaml.safe_load(stream)
    except yaml.YAMLError:
        logger.exception("Unable to load yaml")
        return None

def read_json(json_path: str | Path) -> Any: # noqa: ANN401
    with Path(json_path).open(encoding="utf-8") as fh:
        try:
            loaded = json.load(fh)
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.exception("Unable to decode json")
            loaded = None

        if loaded is None:
            logger.error(f"Couln't read json at: '{json_path}")
        return loaded

def read_yaml(yaml_path: str | Path) -> Any:  # noqa: ANN401
    with open(yaml_path, encoding="utf-8") as stream:
        loaded = load_yaml(stream)
        if loaded is None:
            logger.error(f"Couldn't read yaml at: '{yaml_path}'")
        return loaded



def dump_yaml(data: Any, path: str | Path, sort_keys: bool = True) -> bool:  # noqa: ANN401
    with open(path, "w", encoding="utf-8") as stream:
        try:
            yaml.dump(data, stream, allow_unicode=True, width=1000, sort_keys=sort_keys)
        except yaml.YAMLError as exc:
            logger.error(exc)
            return False
    return True


def get_internal_file_path(file_name: str | Path) -> Path:
    return Path(__file__).parent.parent / file_name


def patch_offsets(f: typing.BinaryIO,
                  offsets_dict: dict, enlarge_coeff: float = 1.0,
                  raw_strings: bool = False) -> None:
    for offset, new_value in offsets_dict.items():
        f.seek(offset)

        # type equality used instead of isinstance because isinstance(True, int) is True, it's an error here
        if type(new_value) == int:
            if not math.isclose(enlarge_coeff, 1.0):
                final_value = round(new_value * enlarge_coeff)
            else:
                final_value = new_value
            f.write(struct.pack("i", final_value))
        elif type(new_value) == str:
            if raw_strings:  # write as is, binary insert strings
                f.write(bytes.fromhex(new_value))
            else:  # hex address to convert to pointer
                f.write(struct.pack("<L", int(new_value, base=16)))
        elif type(new_value) == float:
            if not math.isclose(enlarge_coeff, 1.0):
                final_value = round(new_value * enlarge_coeff)
            else:
                final_value = new_value
            f.write(struct.pack("f", final_value))
        elif type(new_value) == bool:
            f.write(struct.pack("b", new_value))
        elif type(new_value) == tuple:
            f.write(struct.pack("b", new_value[0]))
        else:
            raise TypeError("Unsuported type given")


def get_config(root_dir: str | Path) -> objectify.ObjectifiedElement:
    return xml_to_objfy(Path(root_dir, "data", "config.cfg"))


def running_in_venv() -> bool:
    return (hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and
            sys.base_prefix != sys.prefix))


def get_proc_by_names(proc_names: Iterable[str]) -> psutil.Process | None:
    """Return one proccess matching given list of names or None."""
    for p in psutil.process_iter():
        name = ""
        try:
            name = p.name()
        except (psutil.AccessDenied, psutil.ZombieProcess):
            pass
        except psutil.NoSuchProcess:
            continue
        if name in proc_names:
            return p
    return None


