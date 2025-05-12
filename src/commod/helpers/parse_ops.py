import argparse
import html
import re
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


def beautify_machina_xml(xml_string: bytes) -> bytes:
    """Format and beautify XML string in the style similar to original Ex Machina dynamicscene.xml files."""
    never_split_tags = {b"event", b"Point", b"Wheel"}
    xml_declaration_prefix = b"<?xml"
    xml_delcaration_suffix = b"?>"
    script_start_tag = b"<script>"
    script_end_tag = b"</script>"
    indent_symbol = b"    "

    beautified_parts = []
    previous_line_indent = -1
    inside_plaintext_block = False
    plaintext_tag_indent = 0
    plaintext_block_offset = None

    for raw_line in xml_string.splitlines():
        line_stripped = raw_line.lstrip()

        if (line_stripped.startswith(xml_declaration_prefix)
           and line_stripped.endswith(xml_delcaration_suffix)):
            beautified_parts.append(raw_line + b"\n\n")
            continue

        # calculating indent level of parent line to indent attributes
        # We use 4 spaces for indents
        line_indent = (len(raw_line.expandtabs(4)) - len(line_stripped)) // 4

        # Content in plain text blocks (scripts in triggers) will not be treated as xml,
        # but we still need to indent it correctly.
        # We will make sure that script is always indented once, not more or less
        if inside_plaintext_block:
            if line_stripped.startswith(script_end_tag):
                inside_plaintext_block = False
                line_indent = plaintext_tag_indent
                previous_line_indent = 0
                plaintext_tag_indent = 0
                plaintext_block_offset = None
            else:
                if plaintext_block_offset is None:
                    plaintext_block_offset = previous_line_indent - line_indent + 1

                detabbed_line = raw_line.expandtabs(4) + b"\n"
                if detabbed_line.isspace():
                    beautified_parts.append(b"\n")
                    continue

                if plaintext_block_offset < 0:
                    detabbed_line = detabbed_line[len(indent_symbol) * abs(plaintext_block_offset):]
                else:
                    detabbed_line = indent_symbol * plaintext_block_offset + detabbed_line
                beautified_parts.append(detabbed_line)

                continue

        # Format line based on tag type \ node being comment
        formatted_line = None

        tag_prefix = _extract_tag_prefix(line_stripped)
        if line_stripped.startswith(b"<!--") or tag_prefix in never_split_tags:
            formatted_line = line_indent * indent_symbol + line_stripped + b"\n"
        else:
            formatted_line = _split_tag_on_attributes(line_stripped, line_indent)
            formatted_line = line_indent * indent_symbol + formatted_line + b"\n"

        # Add blank line before tags at the same level (first tag of its tree level)
        if line_indent == previous_line_indent:
            formatted_line = b"\n" + formatted_line

        beautified_parts.append(formatted_line)
        previous_line_indent = line_indent

        if line_stripped.startswith(script_start_tag):
            inside_plaintext_block = True
            plaintext_tag_indent = line_indent

    return b"".join(beautified_parts)

def _extract_tag_prefix(tag_line: bytes) -> bytes:
    """
    Extract the tag name from an XML tag line.

    Example: b"<Point x=10>" -> b"Point".
    """
    if not tag_line.startswith(b"<"):
        return b""

    # Find end of tag name (space or closing bracket)
    end_pos = tag_line.find(b" ")
    if end_pos == -1:
        end_pos = tag_line.find(b">")
    if end_pos == -1:
        return b""

    # Extract just the tag name
    tag_name = tag_line[1:end_pos]

    # Remove any namespace prefix if present
    colon_pos = tag_name.find(b":")
    if colon_pos != -1:
        tag_name = tag_name[colon_pos+1:]

    return tag_name

def _split_tag_on_attributes(xml_line: bytes, line_indent: int) -> bytes:
    # Skip processing for comments
    indent_symbol = b"    "
    if xml_line.startswith(b"<!--") and b"-->" in xml_line:
        return xml_line

    if b" " not in xml_line or b'"' not in xml_line:
        return xml_line

    # Find tag name first
    tag_match = re.match(rb"[^\s]+", xml_line)
    if not tag_match:
        return xml_line

    tag_name = tag_match.group(0)
    remainder = xml_line[len(tag_name):]

    # Pattern to match: space followed by attr="value"
    # Using positive lookahead to find spaces that are followed by an attribute
    attr_pattern = rb'(?=\s+[^\s="]+="[^"]*")'

    parts = map(bytes.strip, re.split(attr_pattern, remainder))

    indent = b"\n" + indent_symbol * (line_indent + 1)
    return tag_name + indent.join(parts)


def xml_to_objfy(full_path: str | Path) -> objectify.ObjectifiedElement:
    with Path(full_path).open("rb") as fh:
        byte_string = fh.read()
        try:
            encoding = "utf-8"
            byte_string.decode(encoding)
        except UnicodeDecodeError:
            encoding = data.ENCODING
            byte_string.decode(data.ENCODING)

        parser_recovery = objectify.makeparser(recover=True, encoding=encoding, collect_ids=False)
        objectify.enable_recursive_str(True)

        # objectify.parse(f, parser_recovery)
        return objectify.fromstring(byte_string, parser_recovery)
