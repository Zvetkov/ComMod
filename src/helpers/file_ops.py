import asyncio
import html
import logging
import math
import os
import shutil
import struct
import sys
import zipfile
from math import ceil
from pathlib import Path
from typing import Any, Coroutine, Optional

import aiofiles
import aioshutil
import markdownify
import psutil
import py7zr
import yaml
from flet import Text
from lxml import etree, objectify

from console import progbar
from game import data, hd_ui

logger = logging.getLogger('dem')

TARGEM_POSITIVE = ["yes", "yeah", "yep", "true"]
TARGEM_NEGATIVE = ["no", "nope", "none", "false"]


def shorten_path(path: str | Path, length: int = 60) -> str:
    path_to_shorten = Path(path)

    final_str = path_to_shorten.as_posix()
    if len(final_str) <= length:
        return final_str

    for i in range(1, len(path_to_shorten.parts)):
        final_str = path_to_shorten.drive + "/../" + Path(*path_to_shorten.parts[i:]).as_posix()
        if len(final_str) <= length:
            return final_str

    if len(path_to_shorten.stem) <= length - 3:
        return "../" + path_to_shorten.stem
    else:
        return "../" + path_to_shorten.stem[:length-4] + "~"
    
def parse_simple_relative_path(path: str | Path):
    parsed_path = str(path).replace("\\","/").strip()
    while parsed_path.endswith("/"):
        parsed_path = parsed_path[:-1].strip()
    while parsed_path.startswith("/") or parsed_path.startswith("."):
        parsed_path = parsed_path[1:].strip()
    return parsed_path
    

def child_from_xml_node(xml_node: objectify.ObjectifiedElement, child_name: str, do_not_warn: bool = False):
    '''Get child from ObjectifiedElement by name'''
    try:
        return xml_node[child_name]
    except AttributeError:
        if not do_not_warn:
            print(f"There is no child with name {child_name} for xml node {xml_node.tag} in {xml_node.base}")
        return None


def machina_xml_beautify(xml_string: str):
    ''' Format and beautify xml string in the style very similar to
    original Ex Machina dynamicscene.xml files.'''
    beautified_string = b""
    previous_line_indent = -1

    # As first line of xml file is XML Declaration, we want to exclude it
    # from Beautifier to get rid of checks for every line down the line
    for i, line in enumerate(xml_string[xml_string.find(b"\n<")
                             + 1:].splitlines()):
        line_stripped = line.lstrip()
        # calculating indent level of parent line to indent attributes
        # lxml use spaces for indents, game use tabs, so indents maps 2:1
        line_indent = (len(line) - len(line_stripped)) // 2

        line = _split_tag_on_attributes(line_stripped, line_indent)
        # manually tabulating lines according to saved indent level
        line = line_indent * b"\t" + line + b"\n"

        # in EM xmls every first and only first tag of its tree level is
        # separated by a new line
        if line_indent == previous_line_indent:
            line = b"\n" + line

        # we need to know indentation of previous tag to decide if tag is
        # first for its tree level, as described above
        previous_line_indent = line_indent

        beautified_string += line
    return beautified_string


def _split_tag_on_attributes(xml_line: str, line_indent: int):
    white_space_index = xml_line.find(b" ")
    quotmark_index = xml_line.find(b'"')

    # true when no tag attribute contained in string
    if white_space_index == -1 or quotmark_index == -1:
        return xml_line

    elif white_space_index < quotmark_index:
        # next tag attribute found, now indent found attribute and
        # recursively start work on a next line part
        return (xml_line[:white_space_index] + b"\n" + b"\t" * (line_indent + 1)
                + _split_tag_on_attributes(xml_line[white_space_index + 1:],
                                           line_indent))
    else:
        # searching where attribute values ends and new attribute starts
        second_quotmark_index = xml_line.find(b'"', quotmark_index + 1) + 1
        return (xml_line[:second_quotmark_index]
                + _split_tag_on_attributes(xml_line[second_quotmark_index:],
                                           line_indent))


def xml_to_objfy(full_path: str) -> objectify.ObjectifiedElement:
    with open(full_path, 'r', encoding=data.ENCODING) as f:
        parser_recovery = objectify.makeparser(recover=True, encoding=data.ENCODING, collect_ids=False)
        objectify.enable_recursive_str()
        objfy = objectify.parse(f, parser_recovery)
    objectify_tree = objfy.getroot()
    return objectify_tree


# def is_xml_node_contains(xml_node: objectify.ObjectifiedElement, attrib_name: str) -> None | bool:
#     attribs = xml_node.attrib
#     if attribs:
#         return attribs.get(attrib_name) is not None
#     else:
#         logger.warning(f"Asking for attributes of node without attributes: {xml_node.base}")


def save_to_file(objectify_tree: objectify.ObjectifiedElement, path,
                 machina_beautify: bool = True) -> None:
    ''' Saves ObjectifiedElement tree to file at path, will format and
    beautify file in the style very similar to original EM dynamicscene.xml
    files by default. Can skip beautifier and save raw
    lxml formated file.
    '''
    xml_string = etree.tostring(objectify_tree,
                                pretty_print=True,
                                doctype='<?xml version="1.0" encoding="windows-1251" standalone="yes" ?>',
                                encoding="windows-1251")
    with open(path, "wb") as fh:
        if machina_beautify:
            fh.write(machina_xml_beautify(xml_string))
        else:
            fh.write(xml_string)


async def save_to_file_async(objectify_tree: objectify.ObjectifiedElement, path,
                             machina_beautify: bool = True) -> None:
    ''' Asynchronously writes (not generates) ObjectifiedElement tree to file at path,will format and
    beautify file in the style very similar to original EM dynamicscene.xml
    files by default. Can skip beautifier and save raw
    lxml formated file.
    '''
    xml_string = etree.tostring(objectify_tree,
                                pretty_print=True,
                                doctype='<?xml version="1.0" encoding="windows-1251" standalone="yes" ?>',
                                encoding="windows-1251")
    async with aiofiles.open(path, "wb") as fh:
        if machina_beautify:
            await fh.write(machina_xml_beautify(xml_string))
        else:
            await fh.write(xml_string)


def count_files(directory: str) -> int:
    files = []

    if os.path.isdir(directory):
        for path, dirs, filenames in os.walk(directory):
            files.extend(filenames)

    return len(files)


def copy_from_to(from_path_list: list[str], to_path: str, console: bool = False) -> None:
    files_count = 0
    for from_path in from_path_list:
        logger.debug(f"Copying files from '{from_path}' to '{to_path}'")
        files_count += count_files(from_path)
    file_num = 1
    for from_path in from_path_list:
        for path, dirs, filenames in os.walk(from_path):
            for directory in dirs:
                destDir = path.replace(from_path, to_path)
                os.makedirs(os.path.join(destDir, directory), exist_ok=True)
        for path, dirs, filenames in os.walk(from_path):
            for sfile in filenames:
                dest_file = os.path.join(path.replace(from_path, to_path), sfile)
                description = (f" - [{file_num} of {files_count}] - name {sfile} - "
                               f"size {round(Path(os.path.join(path, sfile)).stat().st_size / 1024, 2)} KB")
                logger.debug(description)
                shutil.copy2(os.path.join(path, sfile), dest_file)
                if console:
                    progbar.copy_progress(file_num, files_count)
                file_num += 1


async def copy_from_to_async(from_path_list: list[str], to_path: str, callback_progbar: callable) -> None:
    files_count = 0
    for from_path in from_path_list:
        logger.debug(f"Copying files from '{from_path}' to '{to_path}'")
        files_count += count_files(from_path)
    file_num: int = 1
    for from_path in from_path_list:
        for path, dirs, filenames in os.walk(from_path):
            for directory in dirs:
                destDir = path.replace(from_path, to_path)
                os.makedirs(os.path.join(destDir, directory), exist_ok=True)
        for path, dirs, filenames in os.walk(from_path):
            for sfile in filenames:
                dest_file = os.path.join(path.replace(from_path, to_path), sfile)
                file_size = round(Path(os.path.join(path, sfile)).stat().st_size / 1024, 2)
                await aioshutil.copy2(os.path.join(path, sfile), dest_file)
                await callback_progbar(file_num, files_count, sfile, file_size)
                file_num += 1


async def copy_file_and_call_async(path, file_num, sfile, from_path, to_path, files_count, callback_progbar):
    dest_file = os.path.join(path.replace(from_path, to_path), sfile)
    file_size = round(Path(os.path.join(path, sfile)).stat().st_size / 1024, 2)
    await aioshutil.copy2(os.path.join(path, sfile), dest_file)
    await callback_progbar(file_num[0], files_count, sfile, file_size)
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
        for path, dirs, filenames in os.walk(from_path):
            for directory in dirs:
                dest_dir = path.replace(from_path, to_path)
                os.makedirs(os.path.join(dest_dir, directory), exist_ok=True)
        for path, dirs, filenames in os.walk(from_path):
            await asyncio.gather(*[
                copy_file_and_call_async(path, file_num, sfile,
                                         from_path, to_path, files_count,
                                         callback_progbar) for sfile in filenames])


async def extract_files(archive, file_names, path, callback=None, files_num=1):
    '''Extract and save to disk'''
    for file_name in file_names:
        data = archive.read(file_name)
        try:
            file_name.encode('cp437').decode('ascii')
        except UnicodeDecodeError:
            file_name = file_name.encode('cp437').decode('cp866')
        except UnicodeEncodeError:
            pass
        filepath = Path(path, file_name)
        async with aiofiles.open(str(filepath), 'wb') as fd:
            await fd.write(data)
        if callable is not None:
            await callback(files_num)


async def extract_7z_files(archive: py7zr.SevenZipFile, file_names, path,
                           callback=None, files_num=1, chunksize=1):
    '''Extract and save to disk'''
    archive.reset()
    archive.extract(path, targets=file_names)
    if callable is not None:
        await callback(files_num, chunksize)
        await asyncio.sleep(0.01)


async def extract_from_to(archive_path, to_path, callback=None,
                          loading_text: Optional[Text] = None):
    extension = Path(archive_path).suffix
    match extension:
        case ".7z":
            await extract_7z_from_to(archive_path, to_path, callback, loading_text)
        case ".zip":
            await extract_zip_from_to(archive_path, to_path, callback, loading_text)
        case _:
            raise NotImplementedError(f"Unsupported archive type: {archive_path}")


async def extract_zip_from_to(archive_path, to_path,
                              callback: Optional[Coroutine] = None,
                              loading_text: Optional[Text] = None):
    '''Unzip archive to disk asynchronously'''
    os.makedirs(to_path, exist_ok=True)
    with zipfile.ZipFile(archive_path, 'r') as archive:
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
                    file_path.encode('cp437').decode('ascii')
                except UnicodeDecodeError:
                    file_path = file_path.encode('cp437').decode('cp866')
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
            loading_text.value = (f'[{compression_label}] '
                                  f'{total_compressed_size/1024/1024:.1f}MB -> '
                                  f'{total_size/1024/1024:.1f}MB')
            await loading_text.update_async()
            await asyncio.sleep(0.01)

        files_num = len(only_files)
        for i in range(0, files_num, chunksize):
            file_names = only_files[i:(i + chunksize)]
            tasks.append(extract_files(archive, file_names, to_path, callback, files_num))
        await asyncio.gather(*tasks)


async def extract_7z_from_to(archive_path, to_path,
                             callback: Optional[Coroutine] = None,
                             loading_text: Optional[Text] = None):
    os.makedirs(to_path, exist_ok=True)
    with py7zr.SevenZipFile(str(archive_path), 'r') as archive:
        if loading_text is not None:
            info = archive.archiveinfo()
            loading_text.value = (f'[{info.method_names[0]}] '
                                  f'{info.size/1024/1024:.1f}MB -> '
                                  f'{info.uncompressed/1024/1024:.1f}MB')
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

        for dir in dirs:
            os.makedirs(Path(to_path) / dir, exist_ok=True)

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
            await extract_7z_files(archive, file_names, to_path, callback, files_num, chunksize)


def load_yaml(stream) -> Any:
    try:
        yaml_content = yaml.safe_load(stream)
        return yaml_content
    except yaml.YAMLError as exc:
        logger.error(exc)
        return None


def read_yaml(yaml_path: str) -> Any:
    with open(yaml_path, 'r', encoding="utf-8") as stream:
        yaml_loaded = load_yaml(stream)
        return yaml_loaded


def dump_yaml(data, path, sort_keys=True) -> bool:
    with open(path, 'w', encoding="utf-8") as stream:
        try:
            yaml.dump(data, stream, allow_unicode=True, width=1000, sort_keys=sort_keys)
        except yaml.YAMLError as exc:
            logger.error(exc)
            return False
    return True


def get_internal_file_path(file_name: str) -> str:
    return Path(__file__).parent.parent / file_name


def process_markdown(md_raw):
    md_result = html.unescape(md_raw)
    md_result = md_result.replace('<p align="right">(<a href="#top">перейти наверх</a>)</p>', '')
    md_result = markdownify.markdownify(md_result, convert=['a', 'b', 'img'], escape_asterisks=False)
    return md_result


def patch_offsets(f, offsets_dict: dict, enlarge_coeff: float = 1.0, raw_strings=False) -> None:
    for offset in offsets_dict.keys():
        f.seek(offset)
        if type(offsets_dict[offset]) == int:
            if not math.isclose(enlarge_coeff, 1.0):
                new_value = round(offsets_dict[offset] * enlarge_coeff)
            else:
                new_value = offsets_dict[offset]
            f.write(struct.pack("i", new_value))
        elif type(offsets_dict[offset]) == str:
            if raw_strings:  # write as is, binary insert strings
                f.write(bytes.fromhex(offsets_dict[offset]))
            else:  # hex address to convert to pointer
                f.write(struct.pack('<L', int(offsets_dict[offset], base=16)))
        elif type(offsets_dict[offset]) == float:
            if not math.isclose(enlarge_coeff, 1.0):
                new_value = round(offsets_dict[offset] * enlarge_coeff)
            else:
                new_value = offsets_dict[offset]
            f.write(struct.pack("f", new_value))
        elif type(offsets_dict[offset]) == bool:
            f.write(struct.pack("b", offsets_dict[offset]))
        elif type(offsets_dict[offset]) == tuple:
            f.write(struct.pack("b", offsets_dict[offset][0]))


def patch_remaster_icon(f):
    f.seek(data.size_of_rsrc_offset)
    old_rsrc_size = int.from_bytes(f.read(4), byteorder='little')

    if old_rsrc_size == 6632:
        # patching new icon
        icon_raw: bytes
        with open(get_internal_file_path("assets/icons/hta_comrem.ico"), 'rb+') as ficon:
            ficon.seek(data.new_icon_header_ends)
            icon_raw = ficon.read()

        if icon_raw:
            size_of_icon = len(icon_raw)

            block_size_overflow = len(icon_raw) % 0x10
            padding_size = 0x10 - block_size_overflow

            # reading reloc struct to write in at the end of the rsrc latter on
            f.seek(data.offset_of_reloc_offset)
            reloc_offset = int.from_bytes(f.read(4), byteorder='little') - data.rva_offset
            f.seek(data.size_of_reloc_offset)
            reloc_size = int.from_bytes(f.read(4), byteorder='little')

            f.seek(reloc_offset)
            reloc = f.read(reloc_size)

            # writing icon
            f.seek(data.em_102_icon_offset)
            f.write(icon_raw)
            f.write(b"\x00" * padding_size)

            # writing icon group and saving address to write it to table below
            new_icon_group_address = f.tell()
            f.write(bytes.fromhex(data.new_icon_group_info))
            end_rscr_address = f.tell()
            f.write(b"\x00" * 8)  # padding for icon group

            current_size = f.tell() - data.offset_of_rsrc
            block_size_overflow = current_size % 0x1000

            # padding rsrc to 4Kb block size
            padding_size_rsrc = 0x1000 - block_size_overflow
            raw_size_of_rsrc = current_size + padding_size_rsrc
            f.write(b"\x00" * padding_size_rsrc)

            # now writing reloc struct and saving its address to write to table below
            new_reloc_address_raw = f.tell()
            new_reloc_address = new_reloc_address_raw + data.rva_offset

            # padding reloc to 4Kb block size
            block_size_overflow = len(reloc) % 0x1000
            padding_size = 0x1000 - block_size_overflow
            f.write(reloc)
            f.write(b"\x00" * padding_size)
            size_of_image = f.tell()

            # updating pointers in PE header for rsrc struct and reloc struct
            f.seek(data.size_of_rsrc_offset)
            # old_rsrc_size = int.from_bytes(f.read(4), byteorder='little')
            size_of_rscs = end_rscr_address - data.offset_of_rsrc
            f.write(size_of_rscs.to_bytes(4, byteorder='little'))
            f.seek(data.resource_dir_size)
            f.write(size_of_rscs.to_bytes(4, byteorder='little'))

            f.seek(data.raw_size_of_rsrc_offset)
            f.write(raw_size_of_rsrc.to_bytes(4, byteorder='little'))

            f.seek(data.offset_of_reloc_offset)
            f.write(new_reloc_address.to_bytes(4, byteorder='little'))

            # updating size of resource for icon and pointer to icon group resource
            f.seek(data.new_icon_size_offset)
            f.write(size_of_icon.to_bytes(4, byteorder='little'))

            f.seek(data.new_icon_group_offset)
            f.write((new_icon_group_address+data.rva_offset).to_bytes(4, byteorder='little'))

            f.seek(data.offset_of_reloc_raw)
            f.write(new_reloc_address_raw.to_bytes(4, byteorder='little'))

            f.seek(data.size_of_image)
            f.write((size_of_image+data.rva_offset).to_bytes(4, byteorder='little'))


def get_config(root_dir: str) -> objectify.ObjectifiedElement:
    return xml_to_objfy(os.path.join(root_dir, "data", "config.cfg"))


def running_in_venv() -> bool:
    return (hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and
            sys.base_prefix != sys.prefix))


def get_glob_props_path(root_dir: str) -> str:
    config = get_config(root_dir)
    if config.attrib.get("pathToGlobProps") is not None:
        glob_props_path = config.attrib.get("pathToGlobProps")
    return glob_props_path


def get_proc_by_names(proc_names):
    '''Returns one proccess matching given list of names or None'''
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


def patch_memory(target_exe: str):
    '''Applies only two memory related binary exe fixes'''
    with open(target_exe, 'rb+') as f:
        patch_offsets(f, data.minimal_mm_inserts, raw_strings=True)

        offsets_text = data.get_text_offsets("minimal")
        for offset in offsets_text.keys():
            text_fin = offsets_text[offset][0]
            text_str = bytes(text_fin, 'utf-8')
            allowed_len = offsets_text[offset][1]
            f.seek(offset)
            f.write(struct.pack(f'{allowed_len}s', text_str))

    return ["mm_inserts_patched"]


def patch_game_exe(target_exe: str, version_choice: str, build_id: str,
                   monitor_res: tuple, exe_options: dict = {},
                   under_windows: bool = True) -> list[str]:
    '''Applies binary exe fixes, makes related changes to config and global properties
       and returns list with a localised description of applied changes'''
    changes_description = []
    with open(target_exe, 'rb+') as f:
        game_root_path = Path(target_exe).parent
        width, height = monitor_res

        if version_choice == "remaster":
            patch_offsets(f, data.offsets_comrem_relative, data.ENLARGE_UI_COEF)
            patch_offsets(f, data.offsets_comrem_absolute)

            hd_ui.toggle_16_9_UI_xmls(game_root_path, width, height, enable=True)
            hd_ui.toggle_16_9_glob_prop(game_root_path, enable=True)
            changes_description.append("widescreen_interface_patched")

        patch_offsets(f, data.binary_inserts, raw_strings=True)
        changes_description.append("binary_inserts_patched")
        changes_description.append("spawn_freezes_fix")
        changes_description.append("camera_patched")

        patch_offsets(f, data.minimal_mm_inserts, raw_strings=True)
        patch_offsets(f, data.additional_mm_inserts, raw_strings=True)
        changes_description.append("mm_inserts_patched")

        patch_offsets(f, data.offsets_exe_fixes)

        changes_description.append("numeric_fixes_patched")

        patch_offsets(f, data.offsets_draw_dist, raw_strings=True)
        patch_offsets(f, data.offset_draw_dist_numerics)
        changes_description.append("draw_distance_patched")

        if version_choice == "remaster":
            patch_remaster_icon(f)

            if under_windows:
                if exe_options.get("game_font") is not None:
                    font_alias = exe_options.get("game_font")
                else:
                    font_alias = ""
                fonts_scaled = hd_ui.scale_fonts(game_root_path, data.OS_SCALE_FACTOR, font_alias)
                if fonts_scaled:
                    logger.info("fonts corrected")
                else:
                    logger.info("cant correct fonts")
            else:
                logger.warning("Font scaling is unsupported under OS other then Windows")

            width_list = []
            if width in data.PREFERED_RESOLUTIONS.keys():
                width_list = data.PREFERED_RESOLUTIONS[width]
            else:
                width_possible = reversed(list(data.possible_resolutions.keys()))
                for width_candidate in width_possible:
                    if width_candidate <= width:
                        width_list.append(width_candidate)
                if len(width_list) >= 5:
                    if width not in width_list:
                        width_list.insert(0, width)
                        data.possible_resolutions[width] = height
                    width_list = width_list[:5]
                    width_list.reverse()
                else:
                    width_list = data.DEFAULT_RESOLUTIONS

            for i in range(5):
                width_to_change = data.offsets_resolution_list[i][0]
                height_to_change = data.offsets_resolution_list[i][1]
                f.seek(width_to_change)
                f.write(struct.pack("i", width_list[i]))
                f.seek(height_to_change)
                f.write(struct.pack("i", data.possible_resolutions[width_list[i]]))
            logger.info("ui fixes patched")

        offsets_text = data.get_text_offsets(version_choice)
        for offset in offsets_text.keys():
            text_fin = offsets_text[offset][0]
            if "ExMachina - " in offsets_text[offset][0]:
                text_fin += f' [{build_id}]'
            text_str = bytes(text_fin, 'utf-8')
            allowed_len = offsets_text[offset][1]
            f.seek(offset)
            f.write(struct.pack(f'{allowed_len}s', text_str))

        correct_damage_coeffs(game_root_path, data.DEFAULT_COMREM_GRAVITY)
        # increase_phys_step might not have an intended effect, need to verify
        # increase_phys_step(game_root_path)
        logger.info("damage coeff patched")

    patch_configurables(target_exe, exe_options)
    return changes_description


def patch_configurables(target_exe: str, exe_options: dict = {}) -> None:
    '''Applies binary exe fixes which support configuration'''
    with open(target_exe, 'rb+') as f:
        configurable_values = {"gravity": data.DEFAULT_COMREM_GRAVITY,
                               "skins_in_shop_0": (8,),
                               "skins_in_shop_1": (8,),
                               "skins_in_shop_2": (8,),
                               "blast_damage_friendly_fire": False
                               }

        if exe_options.get("gravity") is not None:
            configurable_values["gravity"] = float(exe_options.get("gravity"))

        if exe_options.get("skins_in_shop") is not None:
            configurable_values["skins_in_shop_0"] = (int(exe_options.get("skins_in_shop")),)
            configurable_values["skins_in_shop_1"] = (int(exe_options.get("skins_in_shop")),)
            configurable_values["skins_in_shop_2"] = (int(exe_options.get("skins_in_shop")),)

        if exe_options.get("blast_damage_friendly_fire") is not None:
            blast_config = exe_options.get("blast_damage_friendly_fire")
            if not isinstance(blast_config, bool):
                blast_config = str(blast_config)
                if blast_config.lower() == "true":
                    blast_config = True
                else:
                    blast_config = False
            configurable_values["blast_damage_friendly_fire"] = blast_config

        configured_offesets = {}
        for key in data.configurable_offsets.keys():
            configured_offesets[data.configurable_offsets.get(key)] = configurable_values[key]

        if exe_options.get("game_font") is not None:
            font_alias = exe_options.get("game_font")
            hd_ui.scale_fonts(Path(target_exe).parent, data.OS_SCALE_FACTOR, font_alias)

        patch_offsets(f, configured_offesets)


def patch_render_dll(target_dll: str) -> None:
    with open(target_dll, 'rb+') as f:
        for offset in data.offsets_dll.keys():
            f.seek(offset)
            if type(data.offsets_dll[offset]) == str:  # hex address
                f.write(struct.pack('<Q', int(data.offsets_dll[offset], base=16))[:4])
            elif type(data.offsets_dll[offset]) == float:
                f.write(struct.pack("f", data.offsets_dll[offset]))


def rename_effects_bps(game_root_path: str) -> None:
    '''Without packed bps file game will use individual effects, which allows making edits to them'''
    bps_path = os.path.join(game_root_path, "data", "models", "effects.bps")
    new_bps_path = os.path.join(game_root_path, "data", "models", "stock_effects.bps")
    if os.path.exists(bps_path):
        if os.path.exists(new_bps_path):
            os.remove(bps_path)
            logger.info(f"Deleted effects.bps in path '{bps_path}' as renamed backup already exists")
        else:
            os.rename(bps_path, new_bps_path)
            logger.info(f"Renamed effects.bps in path '{bps_path}'")
    elif not os.path.exists(new_bps_path):
        logger.warning(f"Can't find effects.bps not in normal path '{bps_path}', "
                       "nor in renamed form, probably was deleted by user")


def correct_damage_coeffs(root_dir: str, gravity: float | int) -> None:
    config = get_config(root_dir)
    if config.attrib.get("ai_clash_coeff") is not None:
        ai_clash_coeff = 0.001 / ((gravity / -9.8))
        config.attrib["ai_clash_coeff"] = f"{ai_clash_coeff:.4f}"
        save_to_file(config, os.path.join(root_dir, "data", "config.cfg"))


def increase_phys_step(root_dir: str, enable: bool = True) -> None:
    glob_props_full_path = os.path.join(root_dir, get_glob_props_path(root_dir))
    glob_props = xml_to_objfy(glob_props_full_path)
    physics = child_from_xml_node(glob_props, "Physics")
    if physics is not None:
        if enable:
            physics.attrib["PhysicStepTime"] = "0.0166"
        else:
            physics.attrib["PhysicStepTime"] = "0.033"
    save_to_file(glob_props, glob_props_full_path)
