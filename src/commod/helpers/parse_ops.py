import argparse
import html
import xml.etree.ElementTree as ET

from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import markdownify
from lxml import objectify

from commod.game import data

DOMAIN_SAFELIST = {"youtube.com", "youtu.be", "github.com",
                   "deuswiki.com", "forum.deuswiki.com", "dem.org.ua"}

def init_input_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DEM Community Mod Manager")
    parser.add_argument("-target_dir", help="path to game directory", required=False)
    parser.add_argument("-distribution_dir",
                        help=('path to folder where "mods" library is located'), required=False)
    parser.add_argument("-dev", help="developer mode",
                        action="store_true", default=False, required=False)
    parser.add_argument("-console", help="legacy flag, support removed",
                        action="store_true", default=False, required=False)

    return parser

@cache
def is_url_safe(url: str) -> bool:
    if url:
        return urlparse(url).netloc.removeprefix("www.") in DOMAIN_SAFELIST
    return True

def parse_str_from_dict(dictionary: dict[str, Any], key: str, default: str) -> str:
    value = dictionary.get(key)
    if isinstance(value, str):
        return value.strip()
    return default

def parse_bool_from_dict(dictionary: dict[str, Any], key: str, default: bool) -> bool:
    value = dictionary.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        if value.lower() == "true":
            return True
        if value.lower() == "false":
            return False
    return default

def remove_substrings(string: str, substrings: Iterable[str]) -> str:
    for substring in substrings:
        string = string.replace(substring, "")
    return string


def process_markdown(md_raw: str) -> str:
    md_result = html.unescape(md_raw)
    md_result = md_result.replace('<p align="right">(<a href="#top">перейти наверх</a>)</p>', "")
    return markdownify.markdownify(md_result, convert=["a", "b", "img"], escape_asterisks=False)


def str_to_md_format(md_str: str) -> str:
    return "\n\n".join(
        [" ".join([
            word if ("https://" not in word) else f"[{word}]({word})"
                 for word in line.split()])
                     for line in md_str.splitlines()])


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
    return "../" + path_to_shorten.stem[:length-4] + "~"


def parse_simple_relative_path(path: str | Path) -> str:
    parsed_path = str(path).replace("\\", "/").strip()
    while parsed_path.endswith("/"):
        parsed_path = parsed_path[:-1].strip()
    while parsed_path.startswith(("/", ".")):
        parsed_path = parsed_path[1:].strip()
    return parsed_path


def find_element(
        xml_node: objectify.ObjectifiedElement | None,
        child_name: str, do_not_warn: bool = False) -> objectify.ObjectifiedElement | None:
    """Get child from ObjectifiedElement by name."""
    if not isinstance(xml_node, objectify.ObjectifiedElement):
        if not do_not_warn:
            print(f"Can't find child node, as parent element is invalid: '{xml_node}'")
        return None
    try:
        return xml_node[child_name]
    except AttributeError:
        if not do_not_warn:
            print(f"No child with name '{child_name}' for xml node "
                  f"'{xml_node.tag}' in '{xml_node.base}'")
        return None

def find_node(
        xml_node: ET.Element | None,
        child_name: str, do_not_warn: bool = False) -> ET.Element | None:
    """Get the first child from ElementTree by the name."""
    if not isinstance(xml_node, ET.Element):
        if not do_not_warn:
            print(f"Can't find child node, as parent element is invalid: '{xml_node}'")
        return None
    child = xml_node.find(child_name)
    if child is None and not do_not_warn:
        print(f"No child with name '{child_name}' for xml node '{xml_node.tag}'")
    return child

def find_nodes(
        xml_node: ET.Element | None,
        children_name: str, do_not_warn: bool = False) -> list[ET.Element]:
    """Get all matching children from ElementTree by their name."""
    if not isinstance(xml_node, ET.Element):
        if not do_not_warn:
            print(f"Can't find child node, as parent element is invalid: '{xml_node}'")
        return []
    childs = xml_node.findall(children_name)
    if not childs and not do_not_warn:
        print(f"No children with name '{children_name}' for xml node '{xml_node.tag}'")
    return childs

def get_attrib(
        xml_node: ET.Element | None,
        attrib_name: str, do_not_warn: bool = False) -> str | None:
    if not isinstance(xml_node, ET.Element):
        if not do_not_warn:
            print(f"Can't get attribute '{attrib_name}', node is invalid: '{xml_node}'")
        return None
    attrib = xml_node.get(attrib_name)
    if attrib is None and not do_not_warn:
        print(f"No attribute with name '{attrib_name}' for xml node '{xml_node.tag}'")
    return attrib

def beautify_machina_xml(xml_string: bytes) -> bytes:
    """Format and beautify xml string in the style similar to original Ex Machina dynamicscene.xml files."""
    beautified_string = b""
    previous_line_indent = -1

    # As first line of xml file is XML Declaration, we want to exclude it
    # from Beautifier to get rid of checks for every line down the line
    inside_plaintext_block = False
    plaintext_tag_indent = 0

    never_split_tags = [b"event", b"Point", b"Wheel"] # b"Folder"

    for raw_line in xml_string.splitlines():
        line = raw_line

        line_stripped = line.lstrip()

        # calculating indent level of parent line to indent attributes
        # lxml use spaces for indents, game use tabs, so indents maps 2:1
        line_indent = (len(line) - len(line_stripped)) // 2

        if line_stripped.startswith(b"</script>"):
            inside_plaintext_block = False
            line_indent = plaintext_tag_indent
            previous_line_indent = 0
            plaintext_tag_indent = 0

        if line_stripped.startswith(b"<?xml") and line_stripped.endswith(b"?>"):
            beautified_string += line + b"\n\n"
            continue

        if inside_plaintext_block:
            beautified_string += line + b"\n"
            continue


        # beautified_string += line_indent * b"\t" + line + b"\n"

        if any(line_stripped.startswith(b"<"+prefix) for prefix in never_split_tags):
            line = line_indent * b"\t" + line_stripped + b"\n"
        else:
            # manually tabulating lines according to saved indent level
            line = _split_tag_on_attributes(line_stripped, line_indent)
            line = line_indent * b"\t" + line + b"\n"

        # in EM xmls every first and only first tag of its tree level is
        # separated by a new line
        if line_indent == previous_line_indent:
            line = b"\n" + line

        # we need to know indentation of previous tag to decide if tag is
        # first for its tree level, as described above
        previous_line_indent = line_indent

        beautified_string += line

        if line_stripped.startswith(b"<script>"):
            inside_plaintext_block = True
            plaintext_tag_indent = line_indent

    return beautified_string


def _split_tag_on_attributes(xml_line: bytes, line_indent: int) -> bytes:
    white_space_index = xml_line.find(b" ")
    quotmark_index = xml_line.find(b'"')

    # true when no tag attribute contained in string
    if white_space_index == -1 or quotmark_index == -1:
        return xml_line

    if white_space_index < quotmark_index:
        # next tag attribute found, now indent found attribute and
        # recursively start work on a next line part
        return (xml_line[:white_space_index] + b"\n" + b"\t" * (line_indent + 1)
                + _split_tag_on_attributes(xml_line[white_space_index + 1:],
                                           line_indent))

    # searching where attribute values ends and new attribute starts
    second_quotmark_index = xml_line.find(b'"', quotmark_index + 1) + 1
    return (xml_line[:second_quotmark_index]
            + _split_tag_on_attributes(xml_line[second_quotmark_index:],
                                       line_indent))


def xml_to_objfy(full_path: str | Path) -> objectify.ObjectifiedElement:
    with Path(full_path).open("rb") as fh:
        byte_string = fh.read()
        try:
            encoding = "utf-8"
            file_data = byte_string.decode(encoding)
        except UnicodeDecodeError:
            encoding = data.ENCODING
            file_data = byte_string.decode(data.ENCODING)

        parser_recovery = objectify.makeparser(recover=True, encoding=encoding, collect_ids=False)
        objectify.enable_recursive_str(True)
        # objectify.parse(f, parser_recovery)
        objfy = objectify.fromstring(byte_string, parser_recovery)
    return objfy

def xml_to_etree(full_path: str | Path) -> ET.Element:
    tree = ET.parse(full_path)
    return tree.getroot()
