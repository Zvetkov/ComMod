# ruff: noqa: SIM108

import logging
import os
from pathlib import Path

import commod.game.mod_auxiliary
from commod.game import data
from commod.helpers import file_ops, parse_ops
from commod.helpers.get_system_fonts import get_fonts

logger = logging.getLogger("dem")


def scale_fonts(root_dir: str | Path, scale_factor: float, custom_font: str = "",
                under_windows: bool = True) -> bool:
    config = file_ops.get_config(root_dir)

    config_path_parts = config.attrib.get("ui_pathToSchema")
    if config_path_parts is None:
        logger.debug("Unable to read 'ui_pathToSchema' for config!")
        return False
    config_path = Path(*config_path_parts.split("\\"))
    ui_schema_path = Path(root_dir, config_path)
    ui_schema = parse_ops.xml_to_objfy(str(ui_schema_path).lower())

    font_alias = custom_font if custom_font else "Arial"

    listed_system_fonts = []
    fonts_path = Path(Path.home().drive + "/", "Windows", "fonts")

    # code by github.com/CMiSSioN
    if not under_windows:
        test_dir = root_dir
        while True:
            temp_dir = os.path.dirname(test_dir)
            if temp_dir == test_dir:
                break
            test_dir = temp_dir
            fonts_path = Path(test_dir, "Windows", "fonts")
            if fonts_path.exists():
                break

    if fonts_path.exists():
        listed_system_fonts = [font.lower() for font in os.listdir(fonts_path)]

    font_available = f"{font_alias.lower().replace(' ', '')}.ttf" in listed_system_fonts

    if not font_available:
        system_fonts = get_fonts()
        font_available = font_alias in system_fonts

    if not font_available:
        return False

    large_font_size = str(round(12 / scale_factor * data.ENLARGE_UI_COEF, 1))
    sml_font_size = str(round(10 / scale_factor * data.ENLARGE_UI_COEF, 1))

    if ui_schema["schema"].attrib.get("titleFontSize") is not None and font_available:
        ui_schema["schema"].attrib["titleFontFace"] = font_alias
        ui_schema["schema"].attrib["titleFontSize"] = large_font_size
        ui_schema["schema"].attrib["titleFontType"] = "0"
    if ui_schema["schema"].attrib.get("wndFontSize") is not None and font_available:
        ui_schema["schema"].attrib["wndFontFace"] = font_alias
        ui_schema["schema"].attrib["wndFontSize"] = sml_font_size
        ui_schema["schema"].attrib["wndFontType"] = "0"
    if ui_schema["schema"].attrib.get("tooltipFontSize") is not None and font_available:
        ui_schema["schema"].attrib["tooltipFontFace"] = font_alias
        ui_schema["schema"].attrib["tooltipFontSize"] = large_font_size
        ui_schema["schema"].attrib["tooltipFontType"] = "0"
    if ui_schema["schema"].attrib.get("miscFontSize") is not None and font_available:
        ui_schema["schema"].attrib["miscFontFace"] = font_alias
        ui_schema["schema"].attrib["miscFontSize"] = sml_font_size
        ui_schema["schema"].attrib["miscFontType"] = "0"
    file_ops.write_xml_to_file(ui_schema, ui_schema_path)

    return True

# TODO: better to have two functions without bool flag
def toggle_16_9_UI_xmls(root_dir: str | Path, screen_width: int, screen_height: int, enable: bool = True) -> None:  # noqa: N802
    config = file_ops.get_config(root_dir)
    if config.attrib.get("pathToUiWindows") is not None:
        if enable:
            new_value = r"data\if\dialogs_16_9\uiwindows.xml"
        else:
            new_value = r"data\if\dialogs\uiwindows.xml"
        config.attrib["pathToUiWindows"] = new_value

    if config.attrib.get("pathToCredits") is not None:
        if enable:
            new_value = r"data\if\dialogs_16_9\credits.xml"
        else:
            new_value = r"data\if\dialogs\credits.xml"
        config.attrib["pathToCredits"] = new_value

    if config.attrib.get("ui_pathToFrames") is not None:
        if enable:
            new_value = r"data\if\frames\frames_hd.xml"
        else:
            new_value = r"data\if\frames\frames.xml"
        config.attrib["ui_pathToFrames"] = new_value

    if config.attrib.get("pathToSplashes") is not None:
        if enable:
            new_value = r"data\if\ico_hd\splashes.xml"
        else:
            new_value = r"data\if\ico\splashes.xml"
        config.attrib["pathToSplashes"] = new_value

    if config.attrib.get("pathToUiIcons") is not None:
        if enable:
            new_value = r"data\if\ico_hd\uiicons.xml"
        else:
            new_value = r"data\if\ico\uiicons.xml"
        config.attrib["pathToUiIcons"] = new_value

    if config.attrib.get("pathToLevelInfo") is not None:
        if enable:
            new_value = r"data\if\diz\levelinfo_hd.xml"
        else:
            new_value = r"data\if\diz\levelinfo.xml"
        config.attrib["pathToLevelInfo"] = new_value

    if config.attrib.get("g_impostorThreshold") is not None:
        new_value = "1000" if enable else "500"
        config.attrib["g_impostorThreshold"] = new_value

    width = config.attrib.get("r_width")
    height = config.attrib.get("r_height")
    if width is not None and height is not None:
        if enable:
            good_width = screen_width in list(data.KNOWN_RESOLUTIONS.keys())
            good_heigth = data.KNOWN_RESOLUTIONS.get(screen_width) == screen_height
            if good_width and good_heigth:
                new_width = str(screen_width)
                new_height = str(screen_height)
            else:
                new_width = "1280"
                new_height = "720"
        else:  # noqa: PLR5501
            if width == "1280" and height == "720":
                new_width = "1024"
                new_height = "768"
            else:
                new_width = False
                new_height = False
        if width not in ("1920", "2560", "3840") and new_width and new_height:
            config.attrib["r_width"] = new_width
            config.attrib["r_height"] = new_height

    file_ops.write_xml_to_file(config, Path(root_dir, "data", "config.cfg"))


def toggle_16_9_glob_prop(root_dir: str | Path, enable: bool = True) -> None:
    config_path = os.path.join(*(commod.game.mod_auxiliary.get_glob_props_path(root_dir).split("\\")))
    glob_props_full_path = os.path.join(root_dir, config_path)
    glob_props = parse_ops.xml_to_objfy(glob_props_full_path)
    ground_repository = parse_ops.find_element(glob_props, "GroundRepository")
    smart_cursor = parse_ops.find_element(glob_props, "SmartCursor")
    if ground_repository is not None:
        if enable:
            ground_repository.attrib["Size"] = "18 300"
        else:
            ground_repository.attrib["Size"] = "13 10000"
    if smart_cursor is not None:
        if enable:
            smart_cursor.attrib["InfoAreaRadius"] = "70"
            smart_cursor.attrib["UnlockRegion"] = "422 422"
            smart_cursor.attrib["InfoObjUpdateTimeout"] = "0.2"
        else:
            smart_cursor.attrib["InfoAreaRadius"] = "50"
            smart_cursor.attrib["UnlockRegion"] = "300 300"
            smart_cursor.attrib["InfoObjUpdateTimeout"] = "0.5"
    file_ops.write_xml_to_file(glob_props, glob_props_full_path)
