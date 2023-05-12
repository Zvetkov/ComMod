from enum import Enum
import locale
import logging

from file_ops import read_yaml, get_internal_file_path
from data import OWN_VERSION

logger = logging.getLogger('dem')

DEM_DISCORD = "https://discord.gg/jZHxYdF"
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
    "exmachina": "Ex Machina",
    "m113": "Ex Machina: M113",
    "arcade": "EM: Arcade",
    "game": "игра",
    "yes": "да",
    "no": "нет",
    "settings": "настройки",
    "setting_up": "настройка",
    "launch": "запуск",
    "launch_full": "запуск игры",
    "has_mods": "установлены моды",
    "ready": "готово",
    "no_game_selected": "игра не выбрана",
    "game_compatibility": "совместимость с игрой",
    "incompatible_game_installment": "Несовместимая часть игры",
    "mod_for_game": "мод для игры",
    "local_mods": "моды",
    "mods_library": "библиотека модов",
    "issue_with_archive": "Проблема с архивом: мод не запакован совместимым с ComMod образом или архив повреждён.",
    "no_local_mods_found": "Доступные для установки моды не найдены",
    "mod_already_in_library": "данный мод уже есть в библиотеке",
    "download": "скачать",
    "open": "открыть",
    "delete_mod_short": "удалить файлы",
    "delete_mod_from_library": "удалить мод из библиотеки (удалит файлы мода с диска)",
    "this_will_delete_mod": "мод будет удалён из библиотеки, а все файлы мода удалены с диска",
    "ask_confirm_deletion": "подтверждаете удаление?",
    "deleted_mod_from_lib": "мод удалён из библиотеки",
    "deleting_mod_from_lib": "мод удаляется из библиотеки",
    "install_results": "итоги установки",
    "but": "но",
    "attention": "внимание!",
    "one_of_many": "из",
    "mod_name": "название мода",
    "mod_version_and_build": "версия и билд мода",
    "about_mod": "о моде",
    "hide_menu": "свернуть меню",
    "was_reinstall": "была прозведена переустановка",
    "main_info": "основная информация",
    "screenshots": "скриншоты",
    "language": "язык",
    "install_in_progress": "идёт установка",
    "successfully": "успешно",
    "error_occurred": "возникла ошибка",
    "mod_install_language": "язык установки мода",
    "copying_file": "копируется файл",
    "download_mods_screen_placeholder": "Скачивание модов внутри ComMod будет доступно в следующих версиях",
    "launch_game_placeholder": "Добавить игру можно в разделе",
    "local_mods_placeholder": "Добавить папку хранилища модов можно в разделе",
    "close_window": "закрыть окно",
    "app_lang": "язык приложения",
    "developers": "разработчики",
    "restart_to_change_lang": "Полное переключение языка требует перезапуска ComMod",
    "change_log": "список изменений",
    "other_info": "другая информация",
    "patch_only_supports_russian": "ComPatch не поддерживает переводы, попробуйте ComRemaster",
    "reinstall_mod_ask": "Попробовать установить мод повторно?",
    "check_reinstallability": "проверка возможности переустановки",
    "can_reinstall": "Переустановка на выбранную копию игры возможна, но может вызывать ошибки.",
    "cant_reinstall": "Переустановка на выбранную копию игры отключена.",
    "cant_reinstall_with_different_options": "Набор опции установленной и этой версии мода отличаются, установка поверх невозможна.",
    "cant_reinstall_different_lang": "Мод нельзя переустановить поверх при выборе языка отличного от уже установленного.",
    "cant_reinstall_over_other_mods": "Простая переустановка невозможна когда уже установлены другие моды",
    "cant_reinstall_over_newer_version": "Установка поверх более новой версии того же мода невозможна.",
    "cant_reinstall_over_newer_build": "Установка поверх более нового билда того же мода невозможна.",
    "cant_reinstall_over_other_version": "Установка поверх другой версии того же мода невозможна.",
    "to_increase_compat_options_are_limited": "Для повышения совместимости выбор опций будет ограничен.",
    "install_from_scratch_if_issues": "В случае проблем, переустановите моды с нуля на чистую игру.",
    "install_from_scratch": "При необходимости переустановите моды с нуля на чистую игру.",
    "setup_mod_ask": "Перейти к выбору опций?",
    "trailer_watch": "смотреть трейлер",
    "install_please_wait": "Установка может занять некоторое время, пожалуйста не закрывайте установщик",
    "error": "Ошибка",
    "of_any_version": "любой версии",
    "click_screen_to_compare": "Нажмите на скриншот для сравнения",
    "play": "играть",
    "launching": "запускается",
    "stop_game": "закрыть игру",
    "warn_external_address": "Осторожно! Внешняя ссылка от автора модификации!",
    "install": "установить",
    "installed": "установлен",
    "not_installed": "не установлен",
    "release": "релиз",
    "not_specified": "не указан",
    "eng": "английский",
    "us": "английский",
    "ru": "русский",
    "ua": "украинский",
    "de": "немецкий",
    "tr": "турецкий",
    "pl": "польский",
    "binary_fixes": "бинарные правки",
    "spawn_freezes_fix": "Убран фриз при спавне машин",
    "recommended_install_chosen": "выбраны рекомендованные опции",
    "choose_recommended_install": "выбрать рекомендованные опции",
    "last_settings_chosed": "выбраны опции предыдущей установки",
    "choose_one_of_the_options": "выберите один из вариантов",
    "will_not_be_installed": "не будет установлена",
    "setup_install": "настроить установку",
    "cancel_install": "отменить установку",
    "with_option": "с опцией",
    "with_options": "с опциями",
    "install_steps": "шаги установки",
    "welcoming": "вступление",
    "cant_change_choice": "нельзя изменить выбор",
    "install_base_mod_ask": "Установить мод без опций?",
    "install_mod_with_options_ask": "Установить мод с выбранными опциями?",
    "exe_version": "Версия exe игры",
    "extract": "распаковать",
    "extract_mod": "распаковать мод",
    "mod_in_archive": "Для установки требуется распаковка",
    "archived_mods_explanation": "Здесь можно добавить в библиотеку архив с модом который вы сами ранее скачали",
    "add_to_list": "добавить в список",
    "all_versions": "все версии",
    "add_mod": "добавить мод",
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
    "other_settings": "другие настройки",
    "quick_start": "Быстрый старт",
    "dirty_copy": "Грязная копия",
    "requirements_met": "Требования мода к игровой копии удовлетворены",
    "use_this_game": "Использовать эту игру",
    "theme_mode": "Цветовая тема: системная, тёмная, светлая",
    "commod_needs_game": "Для полноценной работы ComMod нужно указать путь к распакованной копии Ex Machina версии 1.02.",
    "commod_needs_distro": "Для полноценной работы ComMod нужно указать папку для хранения модов и других связанных файлов.",
    "steam_game_found": "Найдена копия игры установленная в Steam, использовать её?",
    "steam_add_hint": "Выберите путь и нажмите кнопку чтобы добавить игру в список",
    "game_is_running": "Игра запущенна",
    "choose_from_steam": "Выбрать из установленных в Steam",
    "choose_found": "выбрать найденную",
    "path_to_game": "Путь к игре",
    "path_to_comrem": "Путь к файлам Community Remaster",
    "open_in_explorer": "Открыть в проводнике",
    "already_in_list": "Уже в списке",
    "remove_from_list": "Убрать из списка",
    "already_chosen": "Уже выбран",
    "choose_path": "Указать путь",
    "ask_to_choose_path": "Укажите путь",
    "choose_game_path_manually": "Указать путь к игре вручную",
    "choose_distro_path": "Указать путь к хранилищу",
    "new_name": "Новое имя",
    "edit_name": "Редактировать имя",
    "confirm_choice": "Подтвердить выбор",
    "not_yet_added_games_of_type": "Вы пока не добавили подходящие копии игр\n(поддержка M113 и Arcade появится в следующих версиях)",
    "not_a_valid_path": "Указанный путь не существует",
    "target_dir_missing_files": "Указанная папка не содержит все необходимые файлы.",
    "unsupported_exe_version": "Указанная папка содержит не поддерживаемую версию игры",
    "no_base_content_mod_requires_options": "Данный мод состоит из отдельных опций, нужно выбрать хотя бы одну",
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
