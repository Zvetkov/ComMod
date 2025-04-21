import locale
import logging
from dataclasses import dataclass
from enum import Enum, StrEnum, auto

from commod.game.data import OWN_VERSION
from commod.helpers.file_ops import get_internal_file_path, read_yaml

logger = logging.getLogger("dem")

@dataclass
class LocalizationService:
    language: str
    strings: dict[str, dict[str, str]]

class KnownLangFlags(Enum):
    eng = "assets\\flags\\openmoji_uk.svg"
    ru = "assets\\flags\\openmoji_ru.svg"
    ua = "assets\\flags\\openmoji_ua.svg"
    de = "assets\\flags\\openmoji_de.svg"
    tr = "assets\\flags\\openmoji_tr.svg"
    pl = "assets\\flags\\openmoji_pl.svg"
    kz = "assets\\flags\\openmoji_kz.svg"
    by = "assets\\flags\\openmoji_by.svg"
    jp = "assets\\flags\\openmoji_jp.svg"
    other = "assets\\flags\\openmoji_orange.svg"

    @classmethod
    def list_values(cls) -> list[str]:
        return [c.value for c in cls]

    @classmethod
    def list_names(cls) -> list[str]:
        return [c.name for c in cls]

class SupportedLanguages(StrEnum):
    ENG = auto()
    RU = auto()
    UA = auto()

    @classmethod
    def list_values(cls) -> list[str]:
        return [c.value for c in cls]

    @classmethod
    def list_names(cls) -> list[str]:
        return [c.name for c in cls]

    @classmethod
    def _missing_(cls, value: str) -> str | None:
        value = value.lower()
        for member in cls:
            if member == value:
                return member
        return None

# Fallback for new lines that are added in development,
# before they can be translated to all supported langs
local_dict: dict[str, str] = {
    "info": "Информация",
    "modding_tools": "Моддинг",
    "merge_mod_creation": "Создание merge-мода",
    "open_in_editor": "Открыть в редакторе",
    "diffed_files_are_equal": "Сравниваемые файлы эквивалентны",
    "command_generation_error": "Ошибка генерации команд",
    "saving_commands_error": "Ошибка сохранения команд",
    "unable_to_apply_commands": "Не удалось применить команды к файлу",
    "cant_load_files_for_diffing": "Не удалось загрузить файлы для сравнения",
    "unsupported_file_or_encoding": "Неподдерживаемый тип файлов, или файлы в неподдерживаемой кодировке",
    "need_two_paths_for_comparison": "Нужно указать два пути для сравнения",
    "enter_path_to_source": "Укажите путь к исходному файлу для сравнения",
    "source_path_doesnt_exist": "Исходный файл не существует",
    "enter_path_to_moddified": "Укажите путь к модифицированному файлу для сравнения",
    "modded_path_doesnt_exist": "Модифицированный файл не существует",
    "incorrect_commands_for_source": "Эти команды невозможно применить к исходному файлу: {cmd_path}",
    "enter_path_to_output": "Укажите путь к финальному файлу для сохранения команд",
    "preload_existing_commands": "Подгрузите существующие команды для поиска только новых изменений",
    "select_all": "Выбрать все",
    "deselect_all": "Отменить выбор",
    "invert_selection": "Инвертировать выбор",
    "save_selected": "Сохранить выбранные",
    "save_all": "Сохранить все",
    "no_selected": "Нет выбранных команд",
    "calculate_diff": "Рассчитать разницу",
    "num_commands_saved": "Сохранено: {num_cmds} команд(а)",
    "parsed_commands": "Новых команд",
    "nodes_processed": "Обработано нодов",
    "preloaded_commands": "Подгруженных команд",
    "command_list": "Список команд",
    "command_preview": "Просмотр команды",
    "source_node": "Исходный нод",
    "moddified_node": "Модифицированный нод",
    "using_fallback_differ": "Неизвестная схема xml файлов, результат будет проблемным",
    "overwrite_file_are_you_sure": "Данный файл уже существует, вы уверены что хотите перезаписать его?",
    "choose_file": "Выберите файл",
    "choose_files": "Выберите файлы",
    "go_to_dem_forum": "Перейти на DEM форум"

}

def get_strings_dict() -> dict[str, dict[str, str]]:
    eng = read_yaml(get_internal_file_path("localisation/strings_eng.yaml"))
    rus = read_yaml(get_internal_file_path("localisation/strings_rus.yaml"))
    ukr = read_yaml(get_internal_file_path("localisation/strings_ukr.yaml"))

    if (eng.keys() != rus.keys() or eng.keys() != ukr.keys()) and not local_dict:
        raise ValueError("Localisation string for one of the languages is missing")

    loc_dict = {key: {SupportedLanguages.ENG.value: value} for key, value in eng.items()}

    for key in rus:
        loc_dict[key][SupportedLanguages.RU.value] = rus[key]

    for key in ukr:
        loc_dict[key][SupportedLanguages.UA.value] = ukr[key]

    return loc_dict


def tr_lang(str_name: str, lang: SupportedLanguages) -> str:
    """Return localised string in specific supported language."""
    loc_str = stored.strings.get(str_name)
    if loc_str is not None:
        return loc_str[lang]
    return f"Unlocalised string '{str_name}'"

def tr(str_name: str, **kwargs: str) -> str:
    # return "SomeString"
    """Return localised string based on the current locale language.

    Uses localisation files for each supported language
    """
    loc_str = stored.strings.get(str_name)
    if loc_str is not None:
        final_string = loc_str[stored.language]
        if "{OWN_VERSION}" in final_string:
            final_string = final_string.replace("{OWN_VERSION}", OWN_VERSION)
        if kwargs:
            final_string = final_string.format(**kwargs)
        return final_string

    # development fallback
    if local_dict.get(str_name):
        return local_dict[str_name].format(**kwargs) if kwargs else local_dict[str_name]

    logger.warning(f"Localized string '{str_name}' not found!")
    return f"Unlocalised string '{str_name}'"

def get_default_lang() -> str:
    def_locale_tuple = locale.getlocale()
    if isinstance(def_locale_tuple[0], str):
        def_locale = def_locale_tuple[0].replace("-", "_")
    else:
        return SupportedLanguages.ENG.value

    if def_locale.startswith("Russian_"):
        return SupportedLanguages.RU.value
    if def_locale.startswith("Ukrainian_"):
        return SupportedLanguages.UA.value

    return SupportedLanguages.ENG.value

stored = LocalizationService(get_default_lang(), get_strings_dict())

def get_current_lang() -> SupportedLanguages:
    return stored.language

def is_known_lang(lang: str) -> bool:
    return lang in KnownLangFlags.list_names()

def get_known_mod_display_name(
        service_name: str, library_mods_info: dict[str, dict[str, str]] | None = None) -> str | None:
    current_lang = get_current_lang()
    lang_dict = library_mods_info[service_name]
    if library_mods_info and lang_dict:
        if translated := lang_dict.get(current_lang):
            return translated
        if lang_dict.values():
            return next(iter(lang_dict.values()))
    known_names = {"community_patch": "Community Patch",
                   "community_remaster": "Community Remaster"}
    return known_names.get(service_name)
