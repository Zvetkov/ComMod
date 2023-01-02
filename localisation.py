import os
import locale
import logging

from file_ops import read_yaml
from data import VERSION

logger = logging.getLogger('dem')

DEM_DISCORD = "https://discord.gg/jZHxYdF"
COMPATCH_GITHUB = "https://github.com/DeusExMachinaTeam/EM-CommunityPatch"
WIKI_COMPATCH = "https://deuswiki.com/w/Community_Patch"


def get_strings_dict() -> dict:
    eng = read_yaml(load_internal_file("localisation/strings_eng.yaml"))
    rus = read_yaml(load_internal_file("localisation/strings_rus.yaml"))
    ukr = read_yaml(load_internal_file("localisation/strings_ukr.yaml"))

    if eng.keys() != rus.keys() or eng.keys() != ukr.keys():
        raise Exception("Localisation string for one of the languages is missing")

    loc_dict = {key: {"eng": value} for key, value in eng.items()}

    for key in rus:
        loc_dict[key]["rus"] = rus[key]

    for key in ukr:
        loc_dict[key]["ukr"] = ukr[key]

    return loc_dict


def loc_string(str_name: str, **kwargs) -> str:
    loc_str = STRINGS.get(str_name)
    if loc_str is not None:
        final_string = loc_str[LANG]
        if "{VERSION}" in final_string:
            final_string = final_string.replace("{VERSION}", VERSION)
        if kwargs:
            final_string = final_string.format(**kwargs)
        return final_string

    else:
        logger.warning(f"Localized string '{str_name}' not found!")
        return f"Unlocalised string '{str_name}'"


def load_internal_file(file_name: str) -> str:
    # sys_exe = str(Path(sys.executable).resolve())
    # if ".exe" in sys_exe and not running_in_venv():
    #     # Nuitka way
    #     return Path(sys.argv[0]).resolve().parent + file_name
    # elif running_in_venv():
    #     # probably running in venv
    #     exe_path = Path(__file__).resolve().parent + file_name
    return os.path.join(os.path.dirname(__file__), file_name)


def_locale = locale.getdefaultlocale()[0].replace("_", "-")

if def_locale[-3:] == '-RU':
    LANG = "rus"
elif def_locale[:2] == "uk" or def_locale[-3:] == '-UA':
    LANG = "ukr"
elif def_locale[:3] == "ru-":
    LANG = "rus"
else:
    LANG = "eng"

STRINGS = get_strings_dict()
