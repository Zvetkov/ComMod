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
import hd_ui

logger = logging.getLogger('dem')


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
        logger.warning(f"Asking for attributes of node without attributes: {xml_node.base}")


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


def copy_from_to(from_path_list: list[str], to_path: str, console: bool = False):
    files_count = 0
    for from_path in from_path_list:
        logger.debug(f"Copying files from '{from_path}' to '{to_path}'")
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
                logger.debug(description)
                shutil.copy2(os.path.join(path, sfile), destFile)
                if console:
                    progbar.copy_progress(file_num, files_count)
                file_num += 1


def read_yaml(yaml_path):
    yaml_config = None
    with open(yaml_path, 'r', encoding="utf-8") as stream:
        try:
            yaml_config = yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            logger.debug(exc)
    return yaml_config


def dump_yaml(data, path):
    with open(path, 'w', encoding="utf-8") as stream:
        try:
            yaml.dump(data, stream)
        except yaml.YAMLError as exc:
            logger.debug(exc)
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


def patch_game_exe(target_exe, version_choice: str, build_id: str, exe_options: dict = {}):
    changes_description = []
    with open(target_exe, 'rb+') as f:
        game_root_path = Path(target_exe).parent
        offsets_exe = data.offsets_exe_fixes
        width, height = hd_ui.get_monitor_resolution()

        if version_choice == "remaster":
            for offset in data.offsets_abs_sizes.keys():
                f.seek(offset)
                if type(data.offsets_abs_sizes[offset]) == int:
                    f.write(struct.pack("i", round(data.offsets_abs_sizes[offset] * data.ENLARGE_UI_COEF)))
                elif type(data.offsets_abs_sizes[offset]) == str:  # hex address
                    f.write(struct.pack('<L', int(data.offsets_abs_sizes[offset], base=16)))
                elif type(data.offsets_abs_sizes[offset]) == float:
                    f.write(struct.pack("f", round(data.offsets_abs_sizes[offset] * data.ENLARGE_UI_COEF)))
            for offset in data.offsets_abs_move_x.keys():
                original_x = data.offsets_abs_move_x[offset]
                f.seek(offset)
                f.write(struct.pack("f", round((original_x * data.ENLARGE_UI_COEF * data.PARTIAL_STRETCH)
                                               + (data.PARTIAL_STRETCH_OFFSET * data.TARGET_RES_X))))

            offsets_exe = data.offsets_exe_fixes
            offsets_exe.update(data.offsets_exe_ui)

            hd_ui.toggle_16_9_UI_xmls(game_root_path, width, height, enable=True)
            hd_ui.toggle_16_9_glob_prop(game_root_path, enable=True)
            changes_description.append("widescreen_interface_patched")

        for offset in data.binary_inserts.keys():
            f.seek(offset)
            f.write(bytes.fromhex(data.binary_inserts[offset]))
        changes_description.append("binary_inserts_patched")

        for offset in data.mm_inserts.keys():
            f.seek(offset)
            f.write(bytes.fromhex(data.mm_inserts[offset]))
        changes_description.append("mm_inserts_patched")

        patch_offsets(f, offsets_exe)

        changes_description.append("numeric_fixes_patched")
        changes_description.append("general_compatch_fixes")
        if version_choice == "remaster":
            logger.debug("ui_fixes_patched")
            hd_ui.scale_fonts(game_root_path, data.OS_SCALE_FACTOR)

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

        offsets_text = data.get_text_offsets(version_choice)
        for offset in offsets_text.keys():
            text_fin = offsets_text[offset][0]
            if "ExMachina - " in offsets_text[offset][0]:
                text_fin += f' [{build_id}]'
            text_str = bytes(text_fin, 'utf-8')
            allowed_len = offsets_text[offset][1]
            f.seek(offset)
            f.write(struct.pack(f'{allowed_len}s', text_str))

        correct_damage_coeffs(game_root_path, data.GRAVITY)
        increase_phys_step(game_root_path)
        logger.debug("damage_coeff_patched")

    patch_configurables(target_exe, exe_options)
    return changes_description


def patch_configurables(target_exe, exe_options={}):
    with open(target_exe, 'rb+') as f:
        configurable_values = {"gravity": data.GRAVITY,
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

        patch_offsets(f, configured_offesets)


def patch_render_dll(target_dll):
    with open(target_dll, 'rb+') as f:
        for offset in data.offsets_dll.keys():
            f.seek(offset)
            if type(data.offsets_dll[offset]) == str:  # hex address
                f.write(struct.pack('<Q', int(data.offsets_dll[offset], base=16))[:4])
            elif type(data.offsets_dll[offset]) == float:
                f.write(struct.pack("f", data.offsets_dll[offset]))


def rename_effects_bps(game_root_path):
    bps_path = os.path.join(game_root_path, "data", "models", "effects.bps")
    new_bps_path = os.path.join(game_root_path, "data", "models", "stock_effects.bps")
    if os.path.exists(bps_path):
        os.rename(bps_path, new_bps_path)
        logger.debug(f"Renamed effects.bps in path '{bps_path}'")
    elif not os.path.exists(new_bps_path):
        logger.warning(f"Can't find effects.bps not in normal path '{bps_path}', "
                       "nor in renamed form, probably was deleted by user")


def correct_damage_coeffs(root_dir: str, gravity):
    config = get_config(root_dir)
    if config.attrib.get("ai_clash_coeff") is not None:
        ai_clash_coeff = 0.001 / ((gravity / -9.8))
        config.attrib["ai_clash_coeff"] = f"{ai_clash_coeff:.4f}"
        save_to_file(config, os.path.join(root_dir, "data", "config.cfg"))


def increase_phys_step(root_dir: str, enable=True):
    glob_props_full_path = os.path.join(root_dir, get_glob_props_path(root_dir))
    glob_props = xml_to_objfy(glob_props_full_path)
    physics = child_from_xml_node(glob_props, "Physics")
    if physics is not None:
        if enable:
            physics.attrib["PhysicStepTime"] = "0.0166"
        else:
            physics.attrib["PhysicStepTime"] = "0.033"
    save_to_file(glob_props, glob_props_full_path)
