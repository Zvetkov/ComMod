from enum import Enum
import locale
import logging

from file_ops import read_yaml, get_internal_file_path
from data import OWN_VERSION

logger = logging.getLogger('dem')

DEM_DISCORD = "https://discord.gg/jZHxYdF"
DEM_DISCORD_MODS_DOWNLOAD_SCREEN = "https://discord.gg/deus-ex-machina-522817939616038912"
COMPATCH_GITHUB = "https://github.com/DeusExMachinaTeam/EM-CommunityPatch"
WIKI_COMPATCH = "https://deuswiki.com/w/Community_Patch"


class LangFlags(Enum):
    eng = "assets\\flags\\openmoji_uk.svg"
    ru = "assets\\flags\\openmoji_ru.svg"
    ua = "assets\\flags\\openmoji_ua.svg"
    de = "assets\\flags\\openmoji_de.svg"
    tr = "assets\\flags\\openmoji_tr.svg"
    pl = "assets\\flags\\openmoji_pl.svg"
    other = "assets\\flags\\openmoji_orange.svg"


class SupportedLanguages(Enum):
    ENG = "eng"
    RU = "ru"
    UA = "ua"

    @classmethod
    def list_values(cls):
        return list(map(lambda c: c.value, cls))

    @classmethod
    def list_names(cls):
        return list(map(lambda c: c.name, cls))


local_dict = {
}


def get_strings_dict() -> dict:
    eng = read_yaml(get_internal_file_path("localisation/strings_eng.yaml"))
    rus = read_yaml(get_internal_file_path("localisation/strings_rus.yaml"))
    ukr = read_yaml(get_internal_file_path("localisation/strings_ukr.yaml"))

    if eng.keys() != rus.keys() or eng.keys() != ukr.keys():
        if not local_dict:
            raise Exception("Localisation string for one of the languages is missing")

    loc_dict = {key: {"eng": value} for key, value in eng.items()}

    for key in rus:
        loc_dict[key]["ru"] = rus[key]

    for key in ukr:
        loc_dict[key]["ua"] = ukr[key]

    return loc_dict


def tr(str_name: str, **kwargs) -> str:
    # return "SomeString"
    '''Returns localised string based on the current locale language,
       uses localisation files for each supported language'''
    loc_str = STRINGS.get(str_name)
    if loc_str is not None:
        final_string = loc_str[LANG]
        if "{OWN_VERSION}" in final_string:
            final_string = final_string.replace("{OWN_VERSION}", OWN_VERSION)
        if kwargs:
            final_string = final_string.format(**kwargs)
        return final_string
    # developer fallback
    elif local_dict.get(str_name):
        return local_dict[str_name]
    else:
        logger.warning(f"Localized string '{str_name}' not found!")
        return f"Unlocalised string '{str_name}'"


def_locale = locale.getdefaultlocale()[0].replace("_", "-")

if def_locale[-3:] == '-RU':
    LANG = "ru"
elif def_locale[:2] == "uk" or def_locale[-3:] == '-UA':
    LANG = "ua"
elif def_locale[:3] == "ru-":
    LANG = "ru"
else:
    LANG = "eng"

STRINGS = get_strings_dict()
