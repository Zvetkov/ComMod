import locale
import logging
from dataclasses import dataclass
from enum import Enum

from game.data import OWN_VERSION
from helpers.file_ops import get_internal_file_path, read_yaml

logger = logging.getLogger("dem")

@dataclass
class LocalizationService:
    current_language: str
    strings: dict[str, dict[str, str]]

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
    def list_values(cls) -> list[str]:
        return [c.value for c in cls]

    @classmethod
    def list_names(cls) -> list[str]:
        return [c.name for c in cls]

# Fallback for new lines that are added in development,
# before they can be translated to all supported langs
local_dict: dict[str, str] = {
}

def get_strings_dict() -> dict[str, dict[str, str]]:
    eng = read_yaml(get_internal_file_path("localisation/strings_eng.yaml"))
    rus = read_yaml(get_internal_file_path("localisation/strings_rus.yaml"))
    ukr = read_yaml(get_internal_file_path("localisation/strings_ukr.yaml"))

    if (eng.keys() != rus.keys() or eng.keys() != ukr.keys()) and not local_dict:
        raise ValueError("Localisation string for one of the languages is missing")

    loc_dict = {key: {"eng": value} for key, value in eng.items()}

    for key in rus:
        loc_dict[key]["ru"] = rus[key]

    for key in ukr:
        loc_dict[key]["ua"] = ukr[key]

    return loc_dict


def tr(str_name: str, **kwargs: str) -> str:
    # return "SomeString"
    """Return localised string based on the current locale language.

    Uses localisation files for each supported language
    """
    loc_str = localization_service.strings.get(str_name)
    if loc_str is not None:
        final_string = loc_str[localization_service.current_language]
        if "{OWN_VERSION}" in final_string:
            final_string = final_string.replace("{OWN_VERSION}", OWN_VERSION)
        if kwargs:
            final_string = final_string.format(**kwargs)
        return final_string

    # development fallback
    if local_dict.get(str_name):
        return local_dict[str_name]

    logger.warning(f"Localized string '{str_name}' not found!")
    return f"Unlocalised string '{str_name}'"

def get_default_lang() -> str:
    def_locale_tuple = locale.getdefaultlocale()
    if isinstance(def_locale_tuple[0], str):
        def_locale = def_locale_tuple[0].replace("_", "-")
    else:
        return "eng"

    if def_locale[-3:] == "-RU":
        return "ru"
    if def_locale[:2] == "uk" or def_locale[-3:] == "-UA":
        return "ua"
    if def_locale[:3] == "ru-":
        return "ru"

    return "eng"

localization_service = LocalizationService(get_default_lang(), get_strings_dict())


def is_known_lang(lang: str) -> bool:
    return lang in ("eng", "ru", "ua", "de", "pl", "tr")
