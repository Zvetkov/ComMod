from typing import Iterable
import markdownify
import html
from pathlib import Path
from lxml import objectify
from game import data


def remove_substrings(string: str, substrings: Iterable[str]) -> str:
    for substring in substrings:
        string.replace(substring, "")
    return string


def process_markdown(md_raw):
    md_result = html.unescape(md_raw)
    md_result = md_result.replace('<p align="right">(<a href="#top">перейти наверх</a>)</p>', '')
    md_result = markdownify.markdownify(md_result, convert=['a', 'b', 'img'], escape_asterisks=False)
    return md_result


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
    parsed_path = str(path).replace("\\", "/").strip()
    while parsed_path.endswith("/"):
        parsed_path = parsed_path[:-1].strip()
    while parsed_path.startswith("/") or parsed_path.startswith("."):
        parsed_path = parsed_path[1:].strip()
    return parsed_path


def get_child_from_xml_node(xml_node: objectify.ObjectifiedElement,
                            child_name: str, do_not_warn: bool = False):
    '''Get child from ObjectifiedElement by name'''
    try:
        return xml_node[child_name]
    except AttributeError:
        if not do_not_warn:
            print(f"There is no child with name {child_name} for xml node "
                  f"{xml_node.tag} in {xml_node.base}")
        return None


def beautify_machina_xml(xml_string: str):
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
