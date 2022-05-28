from typing import overload
import data
import os
import sys
import shutil

# import winreg
import logging
import yaml
import struct
from pathlib import Path

from lxml import etree, objectify

import progbar


class bcolors:
    HEADER = '\033[95m'   # Bright Magenta
    OKBLUE = '\033[94m'   # Bright Blue
    OKCYAN = '\033[96m'   # Bright Cyan
    OKGREEN = '\033[92m'  # Bright Green
    WARNING = '\033[93m'  # Bright Yellow
    RED = '\033[91m'      # Bright Red
    GRAY = '\033[90m'     # Bright Black (Gray)
    ENDC = '\033[0m'      # closing code 'tag'
    BOLD = '\033[1m'
    FAINT = '\033[2m'     # decreased intensity or dim
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'


class DistributionNotFound(Exception):
    def __init__(self, path: str, message: str = "Invalid distibution path") -> None:
        self.path = path
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"{self.message}: '{self.path}'"


class FileLoggingSetupError(Exception):
    def __init__(self, path: str, message: str = "Couldn't setup file logging") -> None:
        self.path = path
        self.message = message
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"{self.message}: '{self.path}'"


class WrongGameDirectoryPath(Exception):
    pass


class ExeNotFound(Exception):
    pass


class ExeNotSupported(Exception):
    def __init__(self, exe_version: str) -> None:
        self.exe_version = exe_version
        super().__init__(self.exe_version)


class ExeIsRunning(Exception):
    pass


class ModsDirMissing(Exception):
    pass


class NoModsFound(Exception):
    pass


class InvalidGameDirectory(Exception):
    def __init__(self, missing_path: str) -> None:
        self.missing_path = missing_path
        super().__init__(self.missing_path)

class InvalidExistingManifest(Exception):
    def __init__(self, manifest_path: str) -> None:
        self.manifest_path = manifest_path
        super().__init__(self.manifest_path)


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


def loc_string(str_name: str):
    loc_str = data.strings_loc.get(str_name)
    if loc_str is not None:
        return loc_str[data.LANG]
    else:
        logging.warning(f"Localized string '{str_name}' not found!")
        return f"Unlocalised string '{str_name}'"


def xml_to_objfy(full_path: str):
    with open(full_path, 'r', encoding=data.ENCODING) as f:
        parser_recovery = objectify.makeparser(recover=True, encoding=data.ENCODING, collect_ids=False)
        objectify.enable_recursive_str()
        objfy = objectify.parse(f, parser_recovery)
    objectify_tree = objfy.getroot()
    return objectify_tree


def is_xml_node_contains(xml_node: objectify.ObjectifiedElement, attrib_name: str):
    attribs = xml_node.attrib
    if attribs:
        return attribs.get(attrib_name) is not None
    else:
        logging.warning(f"Asking for attributes of node without attributes: {xml_node.base}")


def save_to_file(objectify_tree: objectify.ObjectifiedElement, path,
                 machina_beautify: bool = True):
    ''' Saves ObjectifiedElement tree to file at path, will format and
    beautify file in the style very similar to original Ex Machina
    dynamicscene.xml files by default. Can skip beautifier and save raw
    lxml formated file.
    '''
    xml_string = etree.tostring(objectify_tree,
                                pretty_print=True,
                                doctype='<?xml version="1.0" encoding="windows-1251" standalone="yes" ?>',
                                encoding="windows-1251")
    with open(path, "wb") as writer:
        if machina_beautify:
            writer.write(machina_xml_beautify(xml_string))
        else:
            writer.write(xml_string)


def makedirs(dest):
    if not os.path.exists(dest):
        os.makedirs(dest)


def countFiles(directory):
    files = []

    if os.path.isdir(directory):
        for path, dirs, filenames in os.walk(directory):
            files.extend(filenames)

    return len(files)


def copy_from_to(from_path_list, to_path):
    files_count = 0
    for from_path in from_path_list:
        logging.debug(f"Copying files from '{from_path}' to '{to_path}'")
        files_count += countFiles(from_path)
    file_num = 1
    for from_path in from_path_list:
        for path, dirs, filenames in os.walk(from_path):
            for directory in dirs:
                destDir = path.replace(from_path, to_path)
                makedirs(os.path.join(destDir, directory))
        for path, dirs, filenames in os.walk(from_path):
            for sfile in filenames:
                destFile = os.path.join(path.replace(from_path, to_path), sfile)
                description = (f" - [{file_num} of {files_count}] - name {sfile} - "
                               f"size {round(Path(os.path.join(path, sfile)).stat().st_size / 1024, 2)} KB")
                logging.debug(description)
                shutil.copy2(os.path.join(path, sfile), destFile)
                progbar.copy_progress(file_num, files_count)
                file_num += 1


def read_yaml(yaml_path):
    yaml_config = None
    with open(yaml_path, 'r', encoding="utf-8") as stream:
        try:
            yaml_config = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            logging.debug(exc)
    return yaml_config


def dump_yaml(data, path):
    with open(path, 'w', encoding="utf-8") as stream:
        try:
            yaml.dump(data, stream)
        except yaml.YAMLError as exc:
            logging.debug(exc)
            return False
    return True


def patch_offsets(f, offsets_dict):
    for offset in offsets_dict.keys():
        f.seek(offset)
        if type(offsets_dict[offset]) == int:
            f.write(struct.pack("i", offsets_dict[offset]))
        elif type(offsets_dict[offset]) == str:  # hex address
            f.write(struct.pack('<L', int(offsets_dict[offset], base=16)))
        elif type(offsets_dict[offset]) == float:
            f.write(struct.pack("f", offsets_dict[offset]))
        elif type(offsets_dict[offset]) == bool:
            f.write(struct.pack("b", offsets_dict[offset]))
        elif type(offsets_dict[offset]) == tuple:
            f.write(struct.pack("b", offsets_dict[offset][0]))


def get_config(root_dir: str):
    return xml_to_objfy(os.path.join(root_dir, "data", "config.cfg"))


def running_in_venv():
    return (hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and
            sys.base_prefix != sys.prefix))


def get_glob_props_path(root_dir: str):
    config = get_config(root_dir)
    if config.attrib.get("pathToGlobProps") is not None:
        glob_props_path = config.attrib.get("pathToGlobProps")
    return glob_props_path


def format_text(string: str, style: bcolors = bcolors.BOLD):
    return f"{style}{string}{bcolors.ENDC}"
