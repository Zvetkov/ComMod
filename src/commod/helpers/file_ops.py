# ruff: noqa: E721

import asyncio
import logging
import math
import os
import struct
import sys
import typing
import zipfile
from collections.abc import Coroutine
from math import ceil
from pathlib import Path
from typing import Any

import aiofiles
import aioshutil
import psutil
import py7zr
import yaml
from flet import Text
from lxml import etree, objectify

from commod.helpers.parse_ops import beautify_machina_xml, xml_to_objfy

logger = logging.getLogger("dem")

SUPPORTED_IMG_TYPES = (".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp")
RESOLUTION_OPTION_LIST_SIZE = 5

def write_xml_to_file(objectify_tree: objectify.ObjectifiedElement, path: str,
                 machina_beautify: bool = True) -> None:
    """Write ObjectifiedElement tree to file at path.

    Will format and beautify file in the style very similar to original EM dynamicscene.xml
    files by default. Can skip beautifier and save raw lxml formated file.
    """
    xml_string = etree.tostring(
        objectify_tree,
        pretty_print=True,
        doctype='<?xml version="1.0" encoding="windows-1251" standalone="yes" ?>',
        encoding="windows-1251")
    with open(path, "wb") as fh:
        if machina_beautify:
            fh.write(beautify_machina_xml(xml_string))
        else:
            fh.write(xml_string)


async def write_xml_to_file_async(objectify_tree: objectify.ObjectifiedElement, path: str,
                             machina_beautify: bool = True) -> None:
    """Asynchronously write ObjectifiedElement tree to file at path.

    Will format and beautify file in the style very similar to original EM
    dynamicscene.xml files by default. Can skip beautifier and save raw lxml
    formated file.
    """
    xml_string = etree.tostring(
        objectify_tree,
        pretty_print=True,
        doctype='<?xml version="1.0" encoding="windows-1251" standalone="yes" ?>',
        encoding="windows-1251")
    async with aiofiles.open(path, "wb") as fh:
        if machina_beautify:
            await fh.write(beautify_machina_xml(xml_string))
        else:
            await fh.write(xml_string)


def count_files(directory: str) -> int:
    files = []

    if os.path.isdir(directory):
        for _, _, filenames in os.walk(directory):
            files.extend(filenames)

    return len(files)


async def copy_from_to_async(from_path_list: list[str],
                             to_path: str, callback_progbar: callable) -> None:
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
                await aioshutil.copy2(os.path.join(path, sfile), dest_file)
                await callback_progbar(file_num, files_count, sfile, file_size)
                file_num += 1


async def copy_file_and_call_async(path: str, file_num: list[int],
                                   single_file: str,
                                   from_path: str, to_path: str,
                                   files_count: int,
                                   callback_progbar: Coroutine) -> None:
    # TODO: rethink if something this ugly is really required \/
    # Note: file num is a dirty hack to pass pointer to mutable int value (index of current file)
    dest_file = os.path.join(path.replace(from_path, to_path), single_file)
    file_size = round(Path(os.path.join(path, single_file)).stat().st_size / 1024, 2)
    await aioshutil.copy2(os.path.join(path, single_file), dest_file)
    # TODO: describe interface for this type of callback
    await callback_progbar(file_num[0], files_count, single_file, file_size)
    await asyncio.sleep(0.001)
    file_num[0] += 1


async def copy_from_to_async_fast(from_path_list: list[str | Path],
                                  to_path: str | Path,
                                  callback_progbar: callable) -> None:
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
                                         callback_progbar) for single_file in filenames])


async def extract_files_from_zip(
        archive: zipfile.ZipFile,
        file_names: list[str],
        path: str | Path,
        callback: Coroutine | None = None,
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
        async with aiofiles.open(str(filepath), "wb") as fd:
            await fd.write(data)
        if callable is not None:
            await callback(files_num)


async def extract_files_from_7z(
        archive: py7zr.SevenZipFile,
        file_names: list[str],
        path: str | Path,
        callback: Coroutine | None = None,
        files_num: int = 1, chunksize: int = 1) -> None:
    archive.reset()
    archive.extract(path, targets=file_names)
    if callable is not None:
        await callback(files_num, chunksize)
        await asyncio.sleep(0.01)


async def extract_archive_from_to(archive_path: str, to_path: str, callback: Coroutine | None = None,
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
                              callback: Coroutine | None = None,
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
            await loading_text.update_async()
            await asyncio.sleep(0.01)

        files_num = len(only_files)
        for i in range(0, files_num, chunksize):
            file_names = only_files[i:(i + chunksize)]
            tasks.append(extract_files_from_zip(archive, file_names, to_path, callback, files_num))
        await asyncio.gather(*tasks)


async def extract_7z_from_to(archive_path: str | Path, to_path: str | Path,
                             callback: Coroutine | None = None,
                             loading_text: Text | None = None) -> None:
    os.makedirs(to_path, exist_ok=True)
    with py7zr.SevenZipFile(str(archive_path), "r") as archive:
        if loading_text is not None:
            info = archive.archiveinfo()
            loading_text.value = (f"[{info.method_names[0]}] "
                                  f"{info.size/1024/1024:.1f}MB -> "
                                  f"{info.uncompressed/1024/1024:.1f}MB")
            await loading_text.update_async()
            await asyncio.sleep(0.01)
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
        chunk_file_size = archive_size / 5
        default_chunk_file_size = 1024 * 1024 * 32

        if chunk_file_size > default_chunk_file_size:
            workers = round(archive_size / chunk_file_size)
        else:
            workers = round(archive_size / default_chunk_file_size)

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


def get_internal_file_path(file_name: str) -> Path:
    return Path(__file__).parent.parent / file_name


def patch_offsets(f: typing.BinaryIO,
                  offsets_dict: dict, enlarge_coeff: float = 1.0,
                  raw_strings: bool = False) -> None:
    for offset in offsets_dict:
        new_value = offsets_dict[offset]
        f.seek(offset)

        # type equality used instead of isinstance because isinstance(True, int) is True, it's an error here
        if type(new_value) == int:
            if not math.isclose(enlarge_coeff, 1.0):
                new_value = round(new_value * enlarge_coeff)
            f.write(struct.pack("i", new_value))
        elif type(new_value) == str:
            if raw_strings:  # write as is, binary insert strings
                f.write(bytes.fromhex(new_value))
            else:  # hex address to convert to pointer
                f.write(struct.pack("<L", int(new_value, base=16)))
        elif type(new_value) == float:
            if not math.isclose(enlarge_coeff, 1.0):
                new_value = round(new_value * enlarge_coeff)
            f.write(struct.pack("f", new_value))
        elif type(new_value) == bool:
            f.write(struct.pack("b", new_value))
        elif type(new_value) == tuple:
            f.write(struct.pack("b", new_value[0]))
        else:
            raise TypeError("Unsuported type given")


def get_config(root_dir: str) -> objectify.ObjectifiedElement:
    return xml_to_objfy(os.path.join(root_dir, "data", "config.cfg"))


def running_in_venv() -> bool:
    return (hasattr(sys, "real_prefix") or (hasattr(sys, "base_prefix") and
            sys.base_prefix != sys.prefix))


def get_proc_by_names(proc_names: list[str]) -> psutil.Process | None:
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


