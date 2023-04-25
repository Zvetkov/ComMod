from enum import Enum
import locale
import logging

from file_ops import read_yaml, get_internal_file_path
from data import VERSION

logger = logging.getLogger('dem')

DEM_DISCORD = "https://discord.gg/jZHxYdF"
COMPATCH_GITHUB = "https://github.com/DeusExMachinaTeam/EM-CommunityPatch"
WIKI_COMPATCH = "https://deuswiki.com/w/Community_Patch"


class SupportedLanguages(Enum):
    SYS = 0
    ENG = 1
    RUS = 2
    UKR = 3


local_dict = {
    "yes": "да",
    "no": "нет",
    "settings": "настройки",
    "setting_up": "настройка",
    "launch": "запуск",
    "local_mods": "моды",
    "no_local_mods_found": "Доступные для установки моды не найдены",
    "download": "скачать",
    "open": "открыть",
    "but": "но",
    "mod_name": "название мода",
    "about_mod": "о моде",
    "hide_menu": "свернуть меню",
    "main_info": "основная информация",
    "screenshots": "скриншоты",
    "language": "язык",
    "mod_install_language": "язык установки мода",
    "close_window": "закрыть окно",
    "change_log": "список изменений",
    "other_info": "другая информация",
    "reinstall_mod_ask": "Попробовать установить мод повторно?",
    "mod_already_installed": "мод уже установлен",
    "can_reinstall": "Мод может быть повторно установлен на эту копию игру",
    "cant_reinstall": "Мод нельзя повторно установить на эту копию игру",
    "cant_reinstall_over_other_mods": "Простая переустановка невозможна когда уже установлены другие моды",
    "complex_safe_reinstall": "Повторная установка безопасна в случае выбора одинаковых опций.",
    "safe_reinstall": "Повторная установка безопасна.",
    "complex_unsafe_reinstall": "Установка поверх старой версии мода может вызывать ошибки, для повышения совместимости установка будет включать те же опции.",
    "unsafe_reinstall": "Установка поверх старой версии мода может вызывать ошибки.",
    "cant_reinstall_over_newer_build": "Установка поверх более новой версии того же мода невозможна.",
    "cant_reinstall_over_other_version": "Установка поверх другой версии того же мода невозможна.",
    "setup_mod_ask": "Перейти к выбору опций?",
    "trailer_watch": "смотреть трейлер",
    "error": "Ошибка",
    "of_any_version": "любой версии",
    "click_screen_to_compare": "Нажмите на скриншот для сравнения",
    "play": "играть",
    "warn_external_address": "Осторожно! Внешняя ссылка от автора модификации!",
    "install": "установить",
    "installed": "установлен",
    "release": "релиз",
    "eng": "английский",
    "us": "английский",
    "ru": "русский",
    "ua": "украинский",
    "de": "немецкий",
    "tr": "турецкий",
    "pl": "польский",
    "recommended_install_chosen": "выбраны рекомендованные опции",
    "choose_recommended_install": "выбрать рекомендованные опции",
    "choose_one_of_the_options": "выберите один из вариантов",
    "will_not_be_installed": "не будет установлена",
    "setup_install": "настроить установку",
    "cancel_install": "отменить установку",
    "install_steps": "шаги установки",
    "welcoming": "вступление",
    "install_mod_with_options_ask": "Установить мод с выбранными опциями?",
    "install_results": "финал установки",
    "exe_version": "Версия exe игры",
    "add_to_list": "добавить в список",
    "all_versions": "все версии",
    "launch_params": "параметры запуска",
    "windowed_mode": "оконный режим",
    "incompatible_base": "несовместимые моды",
    "enable_console": "включить консоль",
    "broken_game": "Ранее добавленная копия игры не прошла проверку на целостность, сейчас её невозможно использовать для работы",
    "where_is_game": "Где находится игра?",
    "where_is_distro": "Где должны храниться моды и Community Remaster?",
    "welcome": "Добро пожаловать в менеджер модов!",
    "control_game_copies": "управление копиями игры",
    "control_mod_folders": "управление хранилищем модов",
    "quick_start": "Быстрый старт",
    "dirty_copy": "Грязная копия",
    "requirements_met": "Требования мода к игровой копии удовлетворены",
    "use_this_game": "Использовать эту игру",
    "theme_mode": "Цветовая тема: системная, тёмная, светлая",
    "commod_needs_game": "Для работы ComMod нужна установленная распакованная Ex Machina версии 1.02.",
    "commod_needs_remaster": "Для работы ComMod нужны файлы Community Remaster\n(папки 'patch', 'remaster', 'libs').",
    "steam_game_found": "Найдена копия игры установленная в Steam, использовать её?",
    "steam_add_hint": "Выберите путь и нажмите кнопку чтобы добавить игру в список",
    "game_is_running": "Найдена уже запущенная игра",
    "choose_from_steam": "Выбрать из установленных в Steam",
    "choose_found": "выбрать найденную",
    "show_path_to": "Указать путь к файлам сейчас?",
    "path_to_game": "Путь к игре",
    "path_to_comrem": "Путь к файлам Community Remaster",
    "open_in_explorer": "Открыть в проводнике",
    "already_in_list": "Уже в списке",
    "remove_from_list": "Убрать из списка",
    "already_chosen": "Уже выбран",
    "choose_path": "Указать путь",
    "ask_to_choose_path": "Укажите путь",
    "choose_path": "Указать путь",
    "choose_game_path_manually": "Указать путь к игре вручную",
    "choose_distro_path": "Указать путь к хранилищу",
    "later": "Позже",
    "new_name": "Новое имя",
    "edit_name": "Редактировать имя",
    "confirm_choice": "Подтвердить выбор",
    "finish_setup": "Завершите настройку",
    "add_game_using_btn": "Указать путь к игре можно кнопкой выше или нажав сюда",
    "add_distro_using_btn": "Указать путь к файлам Community Remaster можно кнопкой выше или нажав сюда",
    "you_can_postpone_but": "Вы можете выбрать папки позднее, но без них ComMod не сможет полноценно работать.",
    "not_a_valid_path": "Указанный путь не существует",
    "target_dir_missing_files": "Указанная папка не содержит все необходимые файлы.",
    "unsupported_exe_version": "Указанная папка содержит не поддерживаемую версию игры",
    "havent_been_chosen": "не указан",
    "launch_game_button": "Запустить игру",
    "download_mods": "Скачать моды",
    "backup_game": "Сделать резервную копию / Восстановить из копии",
    "our_discord": "Наш Discord",
    "our_github": "Github проекта",
    "game_info": "Информация об игре",
    "bugfix": "багфикс",
    "gameplay": "геймплейный",
    "story": "сюжетный",
    "visual": "визуальный",
    "audio": "аудио",
    "weapons": "оружие",
    "vehicles": "транспорт",
    "ui": "интерфейс",
    "balance": "баланс",
    "humor": "юмор",
    "uncategorized": "без категории",
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
        loc_dict[key]["rus"] = rus[key]

    for key in ukr:
        loc_dict[key]["ukr"] = ukr[key]

    return loc_dict


def tr(str_name: str, **kwargs) -> str:
    # return "SomeString"
    '''Returns localised string based on the current locale language,
       uses localisation files for each supported language'''
    loc_str = STRINGS.get(str_name)
    if loc_str is not None:
        final_string = loc_str[LANG]
        if "{VERSION}" in final_string:
            final_string = final_string.replace("{VERSION}", VERSION)
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
    LANG = "rus"
elif def_locale[:2] == "uk" or def_locale[-3:] == '-UA':
    LANG = "ukr"
elif def_locale[:3] == "ru-":
    LANG = "rus"
else:
    LANG = "eng"

STRINGS = get_strings_dict()
