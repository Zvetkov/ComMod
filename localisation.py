import os
import locale
import logging

from file_ops import read_yaml
from data import VERSION

logger = logging.getLogger('dem')

DEM_DISCORD = "https://discord.gg/jZHxYdF"
COMPATCH_GITHUB = "https://github.com/DeusExMachinaTeam/EM-CommunityPatch"
WIKI_COMPATCH = "https://deuswiki.com/w/Community_Patch"

local_dict = {
    "welcome": "Добро пожаловать в менеджер модов!",
    "quick_start": "Быстрый старт",
    "commod_needs_game": "Для работы ComMod нужна установленная распакованная Ex Machina версии 1.02.",
    "commod_needs_remaster": "Для работы ComMod нужны файлы Community Remaster\n(папки 'patch', 'remaster', 'libs').",
    "steam_game_found": "Найдена копия игры установленная в Steam, использовать её?",
    "choose_found": "Выбрать найденную",
    "show_path_to": "Указать путь к файлам сейчас?",
    "path_to_game": "Путь к игре",
    "path_to_comrem": "Путь к файлам Community Remaster",
    "choose_path": "Указать путь",
    "ask_to_choose_path": "Укажите путь",
    "choose_path_manually": "Указать путь вручную",
    "later": "Позже",
    "confirm_choice": "Подтвердить выбор",
    "you_can_postpone_but": "Вы можете выбрать папки позднее, но без них ComMod не сможет полноценно работать.",
    "target_dir_missing_files": "Указанная папка не содержит все необходимые файлы.",
    "unsupported_exe_version": "Указанная папка содержит не поддерживаемую версию игры"
}


def get_strings_dict() -> dict:
    eng = read_yaml(load_internal_file("localisation/strings_eng.yaml"))
    rus = read_yaml(load_internal_file("localisation/strings_rus.yaml"))
    ukr = read_yaml(load_internal_file("localisation/strings_ukr.yaml"))

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
