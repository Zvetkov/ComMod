import math

from os import system
from ctypes import windll

DATE = "(Jan 13 2023)"
VERSION = "1.13"

COMPATCH_VER = f"ExMachina - Community Patch build v{VERSION} {DATE}"
COMPATCH_VER_SHRT = f"ExMachina - ComPatch v{VERSION} {DATE}"
COMREM_VER = f"ExMachina - Community Remaster build v{VERSION} {DATE}"
COMREM_VER_SHRT = f"ExMachina - ComRem v{VERSION} {DATE}"

VERSION_BYTES_102_NOCD = 0x005906A3
VERSION_BYTES_102_STAR = 0x00000241

VERSION_BYTES_103_NOCD = 0x005917D2
VERSION_BYTES_103_STAR = 0x00000309


ENCODING = 'windows-1251'

TARGET_RES_X = 1920.0
TARGET_RES_Y = 1080.0
ORIG_RES_X = 1024.0
ORIG_RES_Y = 768.0

GRAVITY = -19.62

OS_SCALE_FACTOR = windll.shcore.GetScaleFactorForDevice(0) / 100

PARTIAL_STRETCH_OFFSET = 0.07
PARTIAL_STRETCH = 1 / (1 - 2 * PARTIAL_STRETCH_OFFSET)

ASPECT_RATIO = TARGET_RES_X / TARGET_RES_Y

TARGET_FOV_X_DEG = 90.0
TARGET_FOV_X_RADS = math.radians(TARGET_FOV_X_DEG)
TARGET_FOV_Y_RADS = 2 * math.atan(math.tan(TARGET_FOV_X_RADS / 2) * (1 / ASPECT_RATIO))
TARGET_FOV_Y_DEG = math.degrees(TARGET_FOV_Y_RADS)
COEFF_FOV_X_FROM_Y = TARGET_FOV_X_RADS / TARGET_FOV_Y_RADS
COEFF_FOV_Y_FROM_X = TARGET_FOV_Y_RADS / TARGET_FOV_X_RADS

ENLARGE_UI_COEF = TARGET_RES_Y / ORIG_RES_Y

OFFSET_UI_X = round((TARGET_RES_X - ORIG_RES_X * ENLARGE_UI_COEF) / 2)
OFFSET_UI_Y = round((TARGET_RES_Y - ORIG_RES_Y * ENLARGE_UI_COEF) / 2)


# 0x5E2BCB
# 0x5E300C
# 0x5E306C
# 0x5E3204
# 0x5E3C61
# 0x5E41EA
# 0x5E4133 # ware InfoItem max String width
# 0x5E4179 # important msg font size
# 0x5E4264 # max damage resistance coeff
# 0x5E44D1 # GameMenuWnd logo y size
# 0x5E485C # MapSellItem icon size
# 0x5E48D1 # MapSellItem item height
# 0x5E497C # hacked "aspect_ratio" coeff to calc fov_y
# 0x5E4A4C # cabinFirstGunOrigin Y
# 0x5E4B0B # SaleWnd tab btn.space
# 0x5E4D94 # Radar camera sight X
# 0x5E5102 # Speedometer pointer size X
# 0x5E5332 # Speedometer pointer size Y
# 0x5E562C # target capturing texCaptureSzBig.x and .y
# 0x5E576C # radar turret ico size redirect
# 0x5E59DC # target capturing texCaptureSzSml
# 0x5E5A14 # for UI bounds on X axis
# 0x5E5A74 # aspect ratio camera correction Y/X
# 0x5E5AAC # target capturing texCapturingSizeY
# 0x5E5B0C # target capturing texCapturingSizeX
# 0x5E5BDC # target capturing texCaptureSzBig


PREFERED_RESOLUTIONS = {1920: [960, 1280, 1366, 1600, 1920],
                        2560: [960, 1280, 1600, 1920, 2560],
                        3840: [1280, 1366, 1920, 2560, 3840]}

DEFAULT_RESOLUTIONS = PREFERED_RESOLUTIONS[1920]

possible_resolutions = {426: 240,
                        640: 360,
                        854: 480,
                        960: 540,
                        1024: 576,
                        1280: 720,
                        1366: 768,
                        1600: 900,
                        1920: 1080,
                        2560: 1440,
                        3200: 1800,
                        3840: 2160,
                        5120: 2880,
                        7680: 4320}


offsets_dll = {
               # to keep 1/1024 intact for other uses, redirect aspect ratio correction
               0x006E35: "0x1016E6F3",

               # and use this value instead of the original one
               0x16E6F3: 1/TARGET_RES_X,
               0x16E618: 1/TARGET_RES_Y,
               0x16E624: TARGET_RES_Y,
               0x16E628: TARGET_RES_X
               }

binary_inserts = {
                  # proper projection matrix correction
                  0x1D770: "D94020D8701CD94020D80D68599E00D80DE8599E00D9F2DDD8D83D7C599E00D9C057B91000000089D7F30F1005545A9E0031C0F3AB5F0F28D0F30F5CD1F30F5EC2F30F114228F30F59C10F57C9F30F5CC8F30F10057C599E00F30F114A38F30F11422CD91AD8F1D95A14DDD8C3",
                  # disabling blast damage friendly fire
                  0x3DFADC: "00",
                  # removing player death count from stats screen
                  0x108E3A: "EB0F",
                  # Treecollisionfix
                  # ai::BreakableObjectPrototypeInfo::RefreshFromXml
                  0x453B57: "5E83C418C20800CCCCCCCCCCCCCCCCCC",
                  # ai::BreakableObjectPrototypeInfo::LoadFromXML
                  0x452D6C: "6A06",
                  # near plane fix 1.0 -> 0.1
                  0x3AB7FB: "68CDCCCC3D"
                  }

mm_inserts = {
              # MemoryManager::MemoryManager
              # 0x3487A0-0x348820
              0x3487A0: "5689CEC70162519600C74104685196006863ED9F00FF158CE1980089460885C07504CC9090906A0190909050FF1590E1980085C07501CC89F1FFD089460C8B480C894E108B4810894E148B401489461889F05EC3CCCCCCCCCCCCCCCCCCCCCCCC",
              # MemoryManager::~MemoryManager
              # 0x348820-0x348A30
              0x348820: "575689CE837908007501CC837E0C007501CC8D7E0C6A02FF7608FF1590E1980085C07501CC8B560C89F1FFD00F57C00F1107FF7608FF15A0E19800C74608000000005E5FC3CCCCCCCCCCCCCCCCCCCCCC",
              # MemoryManager::Malloc
              # 0x348A30-0x348B50
              0x348A30: "575683790C007501CC8B7424148B4424108B54240C8B791085FF7504CC8B79108B490C5650FFD75E5FC20C00CCCCCCCC",
              # MemoryManager::Realloc
              # 0x348C10-0x348CE0
              0x348C10: "53575683790C007501CC8B7C241C8B7424188B4424148B5424108B591485DB7504CC8B59148B490C575650FFD35E5F5BC21000CCCCCCCCCCCCCCCCCCCCCCCCCC",
              # MemoryManager::Free
              # 0x348B50-0x348C10
              0x348B50: "83790C007501CC8B5424048B411885C07504CC8B41188B490CFFD0C20400CCCC",
              # SgNode::CheckNodeValidity
              # 0x2368C0-0x236D50
              0x2368C0: "C3CCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
              # ConstantDLLName
              0x5FED63: "6C6962726172792E646C6C00",
              # 4GB patch
              0x00015E: "2E",
              # stack size - 4 Mb
              0x1A8: "00004000"
              }

offsets_exe_fixes = {
               # aspect ratio hack for Frustum Culling
               0x3A6128: TARGET_FOV_X_RADS,   # fov_x passed to CClipper::CreateScreenFrustums
               0x5E497C: COEFF_FOV_X_FROM_Y,  # hacked "aspect_ratio" coeff to calc fov_y

               # back sliding vehicle throttle lock coeff
               0x1DABEE: "0x009E59EC",

               # max_resistance_for_damage
               0x2D72A5: "0x009E4264",
               0x5E4264: 100.0,

               # reflection experiment to fix fov
               # 0x001C19B7: "0x009E4133",
               # 0x5E4133: 0.56
               }

offsets_resolution_list = [
               # game video options resolutions
               [0x60948C,  # 800
                0x609490],  # 600
               [0x609494,  # 1024
                0x609498],  # 768
               [0x60949C,  # 1152
                0x6094A0],  # 864
               [0x6094A4,  # 1280
                0x6094A8],  # 960
               [0x6094AC,  # 1600
                0x6094B0],  # 1200
               ]

offsets_exe_ui = {
               # base UI resolution without aspect ratio correction
               0x5E5A3C: TARGET_RES_X,  # 1024.0 CMiracle3D:Render
               0x5E5A38: TARGET_RES_Y,  # 768.0 CMiracle3D:Render
               0x19786: TARGET_RES_X,   # 1024.0 CMiracle3d::DrawBackground - can't find result
               0x1977E: TARGET_RES_Y,   # 768.0 CMiracle3d::DrawBackground - can't find result
               # autoScrollPixelSpeed maxWidth - can't find result
               0xA5B58: TARGET_RES_X,

               # mouse cursor coordinates - OnGameMouse and CaptureMouse
               0x1203: int(TARGET_RES_X) / 2,
               0x18053: int(TARGET_RES_X) / 2,
               0x120B: int(TARGET_RES_Y) / 2,
               0x1805B: int(TARGET_RES_Y) / 2,

               # move 1024.0 to another address for use in m3d::Landscape::BuildSolidLandscape
               0x5E5A14: 1024.0,  # 009E5A14
               # start to use it
               0x3A6B9B: "0x009E5A14",  # m3d::Landscape::BuildSolidLandscape

               0x30808B: 2048,  # model rendering
               0x308092: 2048,  # same as previous

               # aspect ratio camera correction
               # 0x5E5A74: 0.5, # 009E5A74
               # camera projection matrix coeff redirect
               # 0x1D7DD: "0x009E5A74",

               # text adjustment
               0x590248: 1 / TARGET_RES_X,  # 1/1024

               # save screenshot resolution
               0x17BCA8: 512,
               0x17BCAF: 256,

               # PostEffectManager
               0x26B416: TARGET_RES_X,
               0x26B49D: TARGET_RES_X,
               0x26B495: TARGET_RES_Y,
               0x26B40E: (25.0 * ENLARGE_UI_COEF),
               0x26B4A5: (TARGET_RES_Y - (25.0 * ENLARGE_UI_COEF)),

               # target capturing cursor
               0x12864C: 12,  # 12, numCapturingSectors

               # moving FOV_Y in degrees
               # 0x1AA393: "0x0098FCCA", # m3d::Application::Application
               # 0x19ED6C: "0x0098FCCA", # CCamera::CCamera
               # 0x58FCCA: TARGET_FOV_Y_DEG
               # FOV_X in degrees can be replaced in place
               # 0x58FE0C: TARGET_FOV_X_DEG,

               # water
               # 0x1C58F0: "0x009E59B8", # 4.0 -> 2.0 - cell size
               # 0x1C59A6: "0x009E5A08" # 32.0 -> 64.0
               # 0x1C5508: "0x009E5A08", # 32.0 -> 64.0
               # 0x1C5617: "0x009E5A08", # 32.0 -> 64.0
               # 0x1C5627: "0x009E5A08", # 32.0 -> 64.0
               # 0x1C5630: "0x009E5A08", # 32.0 -> 64.0
               # 0x1C5641: "0x009E5A08", # 32.0 -> 64.0,
               # 0x1C5376: 8

               # radar turret ico size redirect
               0x5E576C: 14.0,
               0x12C3D1: "0x009E576C",

               # NpcList spacing
               0x5E59C8: 8.0,

               # SaveSellList spacing (def - 5.0)
               0x103829: "0x009E5A80",

               # GameMenuWnd (pause menu)
               # 0xB626B: "0x009E5AF0",  # logo offset
               0x5C3B0C: 420.0,  # menu size X
               0xB627C: "0x009E44D1",  # logo y size
               0x5E44D1: 72.0,
               0xB626B: "0x009E41EA",  # logo x size
               0x5E41EA: 295.0,
               0x5E5AEC: 118.0,  # logo x offset
               0xB642F: "0x009E4264",  # button height
               0x5E4264: 42.0,

               # ware InfoItem max String width
               0x5E4133: 500.0,
               0x4E30E: "0x009E4133",

               # console character X
               0x004D85ED: int(10 * 1.3 * OS_SCALE_FACTOR),  # 1440 / 768 * OS_SCALE_FACTOR
               # console character Y
               0x004D85F7: int(14 * 1.4 * OS_SCALE_FACTOR),
               # console font size
               0x0054FDA4: int(9 * 0.9 / OS_SCALE_FACTOR),

               # important msg font size
               0x00121B24: "0x009E4179",
               0x5E4179: 16 / OS_SCALE_FACTOR,
               }

offsets_abs_sizes = {
                     # credits pointer
                     0x5E5AE8: 256.0,  # texSz.y
                     0x5E5AF4: 186.0,  # rotationScreenCenter.x
                     0x5E5AF8: 129.0,  # rotationCenter.y
                     0x5E5AF0: 290.0,  # rotationScreenCenter.y

                     0xB127B: "0x009E5B0C",  # 32.0 texSz.x
                     0xB129A: "0x009E5AAC",  # 16.0 rotationCenter.x

                     # target capturing cursor
                     0x5E5AC4: 58.0,  # 58.0 - capturingRadius, used once
                     # texCapturingSizeX - 32.0
                     0x5E5B0C: 32.0,
                     0x128626: "0x009E5B0C",  # texCapturingSizeX - 32.0
                     0xA5CEE: "0x009E5B0C",  # bindKeysWnd item X - 32.0
                     # texCapturingSizeY - 16.0
                     0x5E5AAC: 16.0,
                     0x128633: "0x009E5AAC",

                     # checklist ico size (journal check-lists)
                     0xD16C6: "0x009E5AAC",

                     # texCaptureSzBig - 140.0
                     0x5E5BDC: 140.0,
                     0x134376: "0x009E5BDC",
                     # texCaptureSzSml - 36.0
                     0x5E59DC: 36.0,
                     0x134388: "0x009E59DC",
                     # texCaptureSzBig.x and .y
                     0x5E562C: 64.0,
                     0x134D66: "0x009E562C",

                     # speedometer pointer
                     0x5E5102: 7.0,  # 8.0 - original
                     0x13307E: "0x009E5102",  # Speedometer pointer size X (8.0) 009E5978
                     0x5E5332: 73.0,  # 64.0
                     0x13308B: "0x009E5332",  # Speedometer pointer size Y (64.0) 009E5A08
                     # radar and speedometer
                     0x5E5ABC: 56.0,  # Radar inner/outer Radius
                     0x5E5AA4: 74.0,  # RotationCenter for Speedometer(Y) and Radar(X,Y)
                     0x5E5AA8: 71.0,  # RotationCenter for Speedometer(X)
                     0x5E5A9C: 31.0,  # Speedometer(X) pointer radius
                     0x5E5AB8: 150.0,  # Radar hightlight width/height
                     0x12C592: "0x009E59D8",  # Radar higlight origin (5.0->8.0)
                     # radar camera sight X
                     0x5E4D94: 146.0,
                     0x12C4F2: "0x009E4D94",
                     # radar camera sight Y
                     0x12C502: "0x009E5332",   # same as speedometer pointer size Y

                     # salewnd tabs
                     # tabBtnSz.x - 96.0
                     0x5E5B1C: 106.0,
                     # tabBtnSz.y - 48.0
                     0x5E5B18: 50.0,
                     # tabBtnSpace - 10.0, used elsewhere
                     0x5E4B0B: 12.0,
                     0x6FBE9: "0x009E4B0B",

                     # cabin SecondGunOrigin
                     # y - 70.0
                     0x5E4A4C: 70.0,
                     0x38B5A: "0x009E4A4C",

                     # cabinFirstGunOrigin
                     # y - 112.0
                     0x5E5B30: 112.0,

                     # scrollpane (bar width, thumbSize, btnSize)
                     #   0x5E497C: 20.0,
                     #   0x2F9A74: "0x009E497C",

                     # GeomSlot (bar width, thumbSize, btnSize)
                     #  0x5E497C: 15.0,
                     #  0x4464E: "0x009E497C",
                     0x6A6DA: "0x009E5B0C",  # bindKeysWnd item X - 32.0

                     # max resistance for damage - 25 -> 100
                     0x2D72A5: "0x009E5A28",

                     # ReputationList spacing, x,y=2.0 -> 4.0
                     0x1025EB: "0x009E5ADC",
                     0x1025C4: "0x009E5ADC",
                     0x1003D3: "0x009E5ADC",
                     0x102573: "0x009E5ADC",
                     0x10265B: "0x009E5ADC",

                     # MapSellItem item height
                     0xF1715: "0x009E48D1",
                     0x5E48D1: 40.0,
                     # MapSellItem icon size
                     0xF16B4: "0x009E485C",
                     0x5E485C: 38.0,

                     # GameMenuWnd (pause menu) size Y
                     0x5C3B10: 448.0
                    }

offsets_abs_move_x = {
                      # cabin SecondGunOrigin
                      # x - 144.0
                      0x5E5B34: 144.0,
                      # cabinFirstGunOrigin
                      # x - 368.0
                      0x5E5B3C: 368.0
                      }

configurable_offsets = {"gravity": 0x202D25,
                        "skins_in_shop_0": 0x181DCA,
                        "skins_in_shop_1": 0x181C95,
                        "skins_in_shop_2": 0x181E75,
                        "blast_damage_friendly_fire": 0x3DFADC
                        }

hidden_values = {"low_fuel_threshold": [0.25, 0x124CCD, "pointer", "used_elsewhere"],
                 "low_fuel_blinking_period": [300, 0x124CF3, "direct", "single_use"],
                 "min_resistance_for_damage": [-25.1, 0x2D7295, "pointer", "single_use"],  # ai::VehiclePartPrototypeInfo::LoadFromXML
                 "max_resistance_for_damage": [25.0, 0x2D72A5, "pointer", "used_elsewhere"],
                 "blast_damage_friendly_fire": [0x01, 0x3DFADC, "direct", "single_use"]}  # bool

# strings_loc = {"installation_title": {"eng": f"Community Remaster & Community Patch installation - installer version {VERSION}",
#                                       "rus": f"Установка Community Remaster & Community Patch - версия установщика {VERSION}",
#                                       "ua": f"Інсталяція Community Remaster & Community Patch - версія інсталятора {VERSION}"},
#                "patch_title": {"rus": f"Установка Community Patch - версия установщика {VERSION}",
#                                       "eng": f"Community Patch installation - installer version {VERSION}"},
#                "remaster_title": {"rus": f"Установка Community Remaster - версия установщика {VERSION}",
#                                   "eng": f"Community Remaster installation - installer version {VERSION}"},
#                "mod_manager_title": {"rus": f"Mod Manager {VERSION} - установка модов для ComPatch/ComRem",
#                                      "eng": f"Mod Manager {VERSION} - installation of mods for ComPatch/ComRem"},
#                "advanced": {"rus": "Расширенная",
#                             "eng": "Advanced"},
#                "installation": {"rus": "Установка",
#                                 "eng": "Installation"},
#                "cant_be_installed": {"rus": "Установка невозможна",
#                                      "eng": "Installation is not possible"},
#                "version": {"rus": "Версия",
#                            "eng": "Version"},
#                "or": {"rus": "или",
#                       "eng": "or"},
#                "and": {"rus": "и",
#                       "eng": "and"},
#                "simple_intro": {"rus": ("Установка по умолчанию включает в себя все возможные улучшения, такие как:\n"
#                                         "* HD 16:9 интерфейс\n* новые HD модели для некоторой техники и оружия\n* ремастер саундтрека\n"
#                                         "* все доступные фиксы движка\n* исправления ошибок квестов и кат-сцен\n"
#                                         "* улучшения игровых локаций\n* улучшения низкокачественных моделей\n"
#                                         "... и многое другое - полный список изменений в readme."),
#                                 "eng": ("Default installation includes all the available improvements, such as:\n"
#                                         "* HD 16:9 interface\n* new HD models for some trucks and guns\n"
#                                         "* sountrack remaster\n* many changes and fixes for quests, maps, models\n"
#                                         "... find full list of changes in readme.")},
#                "install_mods": {"rus": "Найдены доступные для установки моды. Хотите запустить установку модов?",
#                                 "eng": "Mods available for installation found. Do you want to start installation for mods?"},
#                "just_enter": {"rus": "Чтобы установить всё - просто нажмите 'Enter'",
#                               "eng": "To install everything - just press 'Enter'"},
#                "or_options": {"rus": "Для выбора опций - наберите 'options' и нажмите 'Enter'",
#                               "eng": "To choose install options - input 'options' and press 'Enter'"},
#                "first_choose_base_option": {"rus": "Сперва выберите основную версию:",
#                                             "eng": "First choose base installation version."},
#                "intro_version_choice": {"rus": ("\033[95mCommunity Remaster\033[0m - расширенная версия, 16:9 HD интерфейс, "
#                                                 "возможность установить новые HD модели, ремастер саундтрека. "
#                                                 "Включает все исправления Community Patch."
#                                                 "\n\n\033[95mCommunity Patch\033[0m - базовая версия, исправления ошибок, квестов, кат-сцен, "
#                                                 "улучшения игровых механик, интерфейс для старых 4:3 мониторов."),
#                                         "eng": ("\033[95mCommunity Remaster\033[0m - extended version, 16:9 HD interface, "
#                                                 "optional choice of new HD models, remastered soundtrack. "
#                                                 "Includes all fixes from Community Patch.\n\n\033[95mCommunity Patch\033[0m - base version, "
#                                                 "fixes bugs and quest issues, interface for old 4:3 monitors.")},
#                "exe_not_supported": {"rus": "Найдена неподдерживаемая версия игры, установка будет прервана.\nПоддерживается установка только на распакованную игру версии 1.02.\nИгру можно приобрести в Steam: https://store.steampowered.com/app/285500\nДля установки поместите менеджер модов и папки 'patch', 'remaster', 'libs' в корневую папку игры.",
#                                      "eng": "Unsupported game version is found, will not be able to apply patch.\nOnly unpacked version 1.02 is supported.\nGame can be purchased on Steam: https://store.steampowered.com/app/285500\nTo install put mod manager and folders 'patch', 'remaster', 'libs' inside the root folder of the game."},
#                "exe_is_running": {"rus": "Отказано в доступе к игровому exe, возможно игра уже запущена. Если игра запущена - сперва закройте её полностью, а потом запустите менеджер модов.",
#                                   "eng": "Game exe access denied, game is probably already running. If game is running - first close the game, then start the mod manager."},
#                "dll_not_found": {"rus": "dxrender9.dll не найден, невозможно продолжить патчинг",
#                                  "eng": "dxrender9.dll is not found, will not be able to apply patch"},
#                "exe_not_found": {"rus": "Исполняемый файл игры(exe) не найден, невозможно продолжить патчинг.\nПоместите менеджер модов и папки 'patch', 'remaster', 'libs' в корневую папку игры.\nПоддерживается установка только на распакованную игру версии 1.02.\nИгру можно приобрести в Steam: https://store.steampowered.com/app/285500",
#                                  "eng": "Game`s executable is not found, will not be able to apply patch.\nPut mod manager and folders 'patch', 'remaster', 'libs' inside the root folder of the game.\nOnly unpacked version 1.02 is supported.\nGame can be purchased on Steam: https://store.steampowered.com/app/285500"},
#                "patching_exe": {"rus": "Работаем над exe",
#                                 "eng": "Patching exe"},
#                "copying_patch_files_please_wait": {"rus": "Копируем базовые файлы патча, это может занять некоторое время, пожалуйста не закрывайте установщик",
#                                                    "eng": "Copying base patch files, this can take a bit, please don't close installer"},
#                "copying_base_files_please_wait": {"rus": "Копируем дополнительный контент, это может занять некоторое время, пожалуйста не закрывайте установщик",
#                                                   "eng": "Copying additional content, this can take a bit, please don't close installer"},
#                "copying_options_please_wait": {"rus": "Копируем выбранные опции, это может занять некоторое время, пожалуйста не закрывайте установщик",
#                                                "eng": "Copying optional content, this can take a bit, please don't close installer"},
#                "copy_done": {"rus": "Копирование завершено",
#                              "eng": "Finished copying"},
#                "cant_find_distribution_files": {"rus": "Не получается найти другие файлы патча.\nУстановщик и другие файлы патча должны находиться в одной папке",
#                                                 "eng": "Can't find game files.\nInstaller and other patch files should be located in the same folder"},
#                "installation_error": {"rus": "При установке возникла ошибка, установка не была закончена",
#                                       "eng": "Installation error has occured, installation hasn't been finished"},
#                "requirements_not_met": {"rus": "Требования мода к игровой копии не удовлетворены, установка была прервана.",
#                                         "eng": "Mod requirements for installation are not met, installation is interrupted."},
#                "version_requirement_not_met": {"rus": "! Не выполнены требования к версии базового мода",
#                                                "eng": "! Version requirement is not met for base mod"},
#                "content_requirement_not_met": {"rus": "! Не все нужные аддоны базовых модов установлены.\nПеред тем как начинать установку, сперва поставьте базовый мод с следующими аддонами",
#                                                "eng": "! Not all required content of base mods were installed.\nYou need to install additional content for the base mods before installing this one"},
#                "technical_name": {"rus": "техническое имя",
#                                   "eng": "technical name"},
#                "for_mod": {"rus": "для мода",
#                            "eng": "for mod"},
#                "of_version": {"rus": "версии",
#                               "eng": "of version"},
#                "mod_url": {"rus": "Домашняя страница:",
#                            "eng": "Home page:"},
#                "version_needed": {"rus": "Совместимые версии",
#                                   "eng": "Compatible versions"},
#                "version_available": {"rus": "установленная версия",
#                                      "eng": "installed version"},
#                "check_for_a_new_version": {"rus": "Проверьте доступны ли новые версии для устанавливаемых модов и все ли зависимости соблюдены.",
#                                            "eng": "Check if newer versions are available for mods and if all the required dependencies are fulfilled."},
#                "usupported_patcher_version": {"rus": "Установка контента {content_name} запрашивает другую версию мод менеджера: {required_version}, сейчас используется: {current_version}\n"
#                                                      "Скачать новую версию мод менеджера можно на: {github_url}",
#                                               "eng": "Content {content_name} installation required other mod manager version: {required_version}, now used: {current_version}\n"
#                                                      "You can download a new mod manager version from: {github_url}"},
#                "including_options": {"rus": "Включая опции",
#                                      "eng": "Including options"},
#                "base_prompt": {"rus": "Введите доступный вариант и нажмите ENTER",
#                                "eng": "Input available option and press ENTER"},
#                "enter_accepted_prompt": {"rus": "Нажмите ENTER или сперва введите один из вариантов",
#                                          "eng": "Press ENTER or first input one of the options"},
#                "install_setting_ask": {"rus": "Установить опцию?",
#                                        "eng": "Install option?"},
#                "install_mod_ask": {"rus": "Установить мод?",
#                                    "eng": "Install mod?"},
#                "yes_no": {"rus": "'yes' - да, 'no' - нет",
#                           "eng": "yes, no"},
#                "skip": {"rus": "'skip' - пропустить опцию",
#                         "eng": "'skip' - skip option"},
#                "description": {"rus": "Описание:",
#                                "eng": "Description:"},
#                "author": {"rus": "Автор:",
#                           "eng": "Author:"},
#                "authors": {"rus": "Авторы:",
#                            "eng": "Authors:"},
#                "install_setting_title": {"rus": "Способ установки",
#                                          "eng": "Installation setting"},
#                "compatch_mod_incompatible_with_comrem": {"rus": "Мод сделанный специально под Community Patch нельзя устанавливать поверх Community Remaster",
#                                                          "eng": "Mod created specifically for Community Patch can't be install over Community Remaster"},   
#                "required_mod_not_found": {"rus": "Не установлен требуемый базовый мод(ы)",
#                                           "eng": "Required base mod(s) is not installed"},
#                "required_base": {"rus": "Требуемая база",
#                                  "eng": "Required base"},
#                "found_incompatible": {"rus": "На игру установлен несовместимый мод",
#                                       "eng": "Game installation has an incompatible mod"},
#                "install_settings": {"rus": "Доступные варианты установки:",
#                                     "eng": "Available install variants:"},
#                "optional_content": {"rus": "опциональный контент",
#                                     "eng": "optional content"},
#                "install_leftovers": {"rus": "Предупреждение: установка поверх грязной копии игры.\nНа эту копию игры ранее уже происходила установка модов или ComPatch, не завершившаяся успешно.\nМы можем попробовать повторно установить ComPatch/ComRemaster, установка модов будет отключена.\nВ случае ошибок, попробуйте установку на чистую копию игры.",
#                                      "eng": "Warning: installation in the dirty environment.\nThis game copy previously experienced unsuccessfull installation of some mod or ComPatch.\nWe can try to reinstall ComPatch/ComRemaster, but mod installation will be unavailable.\nIn case of errors, try again with a clean game copy."},
#                "cant_install_patch_over_remaster": {"rus": "Community Patch не поддерживает установку поверх Community Remaster, опция отключена",
#                                                     "eng": "Community Patch doesn't support installation over Community Remaster, options is disabled"},
#                "reinstalling_intro_no_mods": {"rus": ("Установщик обнаружил, что Community Patch или Remaster уже установлены на эту копию игры.\n"
#                                                       "Доступные для установки совместимые моды не найдены.\n"
#                                                       "Поддерживаются только моды совместимые c ComPatch/ComRem.\n"
#                                                       "Чтобы установить такой мод, поместите распакованный мод в папку 'mods' рядом с менеджером модов и запустите его снова.\n\n"
#                                                       "Чтобы закрыть инсталлятор - введите 'exit'\n"
#                                                       "Для повторной установки Patch/Remaster поверх существующей инсталляции - введите 'reinstall'"
#                                                       ),
#                                               "eng": ("Installer detected that Community Patch or Community Remaster is already installed on this game copy.\n"
#                                                       "No available for installation compatible mods found.\n"
#                                                       "Only specific mods compatible with ComPatch/ComRem are supported.\n"
#                                                       "To install such mod, place mod folder into folder 'mods' near mod manager executable and launch it again.\n\n"
#                                                       "If you want to exit installation - enter 'exit'\n"
#                                                       "If you want to overwrite existing installation of Community Patch/Remaster and install it again - enter 'reinstall'"
#                                                       )
#                                               },
#                "reinstalling_intro": {"rus": ("Установщик обнаружил, что Community Patch или Community Remaster уже установлены на эту копию игры.\n"
#                                               "Если вы хотите перейти к установке модов - введите 'mods'\n"
#                                               "Если хотите повторно установить Community Patch/Remaster поверх существующей инсталляции - введите 'reinstall'"),
#                                       "eng": ("Installer detected that Community Patch or Community Remaster is already installed on this game copy.\n"
#                                               "If you want to continue installation of mods - enter 'mods'\n"
#                                               "If you want to overwrite existing installation of Community Patch/Remaster and install it again - enter 'reinstall'")
#                                       },
#                "intro_modded_game": {"rus": ("Установщик обнаружил, что на эту копию игры с Community Patch или Community Remaster уже установлен мод.\n"
#                                              "Повторная установка ComPatch/Remaster на эту копию отключена.\n"
#                                              "Если вы хотите перейти к установке модов - введите 'mods'\n"
#                                              "Чтобы закрыть инсталлятор - введите 'exit'"
#                                              ),
#                                      "eng": ("Installer detected that mods was already installed on this game copy with Community Patch or Community Remaster.\n"
#                                              "Reinstallation of ComPatch/ComRem is disabled.'\n"
#                                              "If you want to continue installation of mods - enter 'mods'\n"
#                                              "If you want to exit installation - enter 'exit'"
#                                              )
#                                      },
#                "intro_modded_no_available_mods": {"rus": ("Установщик обнаружил, что на эту копию игры с Community Patch или Community Remaster уже установлен мод.\n"
#                                                           "Повторная установка ComPatch/Remaster на эту копию отключена.\n"
#                                                           "Доступные для установки моды не найдены.\n"
#                                                           "Чтобы установить мод, поместите распакованный мод в папку 'mods' рядом с менеджером модов и запустите его снова."
#                                                           ),
#                                                   "eng": ("Installer detected that mods was already installed on this game copy with Community Patch or Community Remaster.\n"
#                                                           "Reinstallation of ComPatch/ComRem is disabled.'\n"
#                                                           "No available for installation mods found.\n"
#                                                           "To install mod, place unpacked mod into folder 'mods' near mod manager executable and launch it again."
#                                                           )
#                                                   },
#                "reinstalling_intro_mods": {"rus": ("Установщик обнаружил, что данный мод уже установлен на эту копию игры.\n"
#                                                    "Если вы хотите пропустить установку  - введите 'skip'\n"
#                                                    "Если хотите повторно установить мод поверх существующей инсталляции - введите 'reinstall'"),
#                                            "eng": ("Installer detected that this mod is already installed on this game copy.\n"
#                                                    "If you want to skip its installation - enter 'skip'\n"
#                                                    "If you want to overwrite the existing installation of the mod and install it again - enter 'reinstall'")
#                                            },
#                "warn_reinstall": {"rus": "ВАЖНО: повторная установка ComPatch/ComRemaster нежелательна.\nМы всегда рекомендуем ставить ComPatch/ComRemaster на чистую распакованную версию игры версии 1.02",
#                                   "eng": "IMPORTANT: overwriting existing installation of Patch/Remaster is undesirable.\nWe always recommend installing ComPatch/ComRemaster on the clean unpacked 1.02 version of the game"},
#                "warn_reinstall_mods": {"rus": "ВАЖНО: повторная установка модов нежелательна.\nМы всегда рекомендуем ставить совместимые моды на свежую копию игры с ComPatch/ComRemaster",
#                                        "eng": "IMPORTANT: overwriting existing installation of mods is undesirable.\nWe always recommend installing compatible mods on a clean copy of the game with ComPatch/ComRemaster"},
#                "default_options": {"rus": "[Установка опционального контента]\nМожно установить всё по-умолчанию или выбрать опции.",
#                                    "eng": "[Optional content installation]\nCan be installed with default settings or you can change them."},
#                "default_options_prompt": {"rus": "Настройка по-умолчанию включает:",
#                                           "eng": "Default settings include:"},
#                "incorrect_prompt_answer": {"rus": "ответ не поддерживается, выберите один из перечисленных.",
#                                            "eng": "answer is unsupported, choose one of the listed options."},
#                "installed_listing": {"rus": "Установлено:",
#                                      "eng": "Installed:"},
#                "already_installed": {"rus": "Уже установлены",
#                                      "eng": "Already installed"},
#                "base_version": {"rus": "Базовая версия",
#                                 "eng": "Base version"},
#                "made_dpi_aware": {"rus": "+ Exe установлен флаг DPI Aware для лучшего масштабирования в оконном режиме",
#                                   "eng": "+ Exe made DPI Aware for better scaling in windowed mode"},
#                "widescreen_interface_patched": {"rus": "* Применён патч на широкоформатный 16:9 интерфейс",
#                                                 "eng": "* Widescreen 16:9 interface patch applied"},
#                "binary_inserts_patched": {"rus": "* Правки ошибок движка",
#                                           "eng": "* Game engine fixes"},
#                "mm_inserts_patched": {"rus": "* Замена менеджера памяти, 4GB патч",
#                                       "eng": "* Memory manager replacement, 4GB patch"},
#                "numeric_fixes_patched": {"rus": ("* Улучшения физики и поведения авто"
#                                                  "\n* Улучшения работы игровой камеры"),
#                                          "eng": ("* Vehicle physics and handling improvements"
#                                                  "\n* Game camera improvements")},
#                "general_compatch_fixes": {"rus": ("* Исправления ошибок квестов и кат-сцен\n"
#                                                   "* Улучшения игровых локаций и низкокачественных моделей\n"
#                                                   "... и многое другое - полный список изменений доступен в ченжлисте"),
#                                           "eng": ("* Fixes for quests and cutscenes\n"
#                                                   "* Improvements of many game maps and low quality models\n"
#                                                   "... and many other changes - see change list for full description")},
#                "ui_fixes_patched": {"rus": ("* 16:9 опции разрешения экрана в настройках\n"
#                                             "* Улучшения отображения шрифтов в консоли"),
#                                     "eng": ("* 16:9 resolution options in options menu\n"
#                                             "* Console font size fix")},
#                "fonts_corrected": {"rus": "* Шрифты скорректированы согласно системному масштабированию",
#                                    "eng": "* Fonts are corrected according to system`s scaling"},
#                "cant_correct_fonts": {"rus": "Невозможно скорректировать шрифты, Arial недоступен в системе",
#                                       "eng": "Can't correct fonts as Arial is not installed in the system"},
#                "damage_coeff_patched": {"rus": "* Урон от столкновений скорректирован в соответствии с новой физикой",
#                                         "eng": "* Vehicle crash damage is corrected to match new physics"},
#                "failed_and_cleaned": {"rus": "При работе возникла ошибка, обратитесь к разработчику с информацией о проблеме.",
#                                       "eng": "Patching failed, contact developer with information about the issue."},
#                "installation_finished": {"rus": "Установка завершена!",
#                                          "eng": "Installation is complete!"},
#                "demteam_links": {"rus": "Discord команды Комьюнити Патча: {discord_url}\n"
#                                         "Больше информации про проект: {deuswiki_url} (может быть нужен VPN)\n"
#                                         "Свежие релизы патча на GitHub: {github_url}",
#                                  "eng": "Discord of Community Patch team: {discord_url}\n"
#                                         "More info about the project: {deuswiki_url}\n"
#                                         "Latest releases on GitHub: {github_url}"},
#                "press_enter_to_exit": {"rus": "Нажмите Enter чтобы закрыть окно.",
#                                        "eng": "Press Enter to close the window."},
#                "press_enter_to_continue": {"rus": "Нажмите Enter чтобы продолжить.",
#                                            "eng": "Press Enter to continue."},
#                "manifest_exists_game_unpatched": {"rus": "В указанную папку игры уже ранее пытались установить ComPatch/ComRemaster, но установка не была полностью успешной.\nУдалите игру и установите её заново перед установкой ComPatch.",
#                                                   "eng": "Targeted game directory previously was a target on unsuccessful ComPatch installation.\nDelete game and reinstall it from scratch before the new attempt to install ComPatch."},
#                "invalid_existing_manifest": {"rus": "Манифест предыдущей установки модов или ComPatch для выбранной папки с игрой повреждён или имеет неподдерживаемый формат.\nУдалите игру и установите её заново перед установкой ComPatch.",
#                                              "eng": "Installation manifest of mods or ComPatch for the target game installation is corrupted or has an unknown format.\nDelete game and reinstall it from scratch before the new attempt to install ComPatch."},
#                "stopping_patching": {"rus": "Патчинг остановлен, нажмите Enter, чтобы закрыть окно.",
#                                      "eng": "Stopping patching, press Enter to close the window."},
#                "target_game_dir_doesnt_exist": {"rus": "Указанная папка игры не существует.",
#                                                 "eng": "Targeted game directory doesn't exist."},
#                "not_validated_mod_manifest": {"rus": "Не удалось начать установку для мода, возможно файлы повреждены или манифест установки имеет некорректный формат",
#                                               "eng": "Couldn't start installation for mod, files might be corrupted or mod install manifest is of incorrect format"},
#                "folder": {"rus": "папка",
#                           "eng": "folder"},
#                "empty_mod_manifest": {"rus": "Не удалось начать установку для мода, возможно файлы повреждены - манифест установки пуст или сломан",
#                                       "eng": "Couldn't start installation for mod, files might be corrupted - install manifest is empty or broken"},
#                "cant_find_game_data": {"rus": "Не получается найти файлы игры.\nСкопируйте все файлы и папки патча в папку с игрой, рядом с exe файлом игры",
#                                        "eng": "Can't find game files.\nCopy all files and folders of patch to the folder where game is located, on the same level as a game executable"},
#                "corrupted_installation": {"rus": "Файлы игры или Community Patch / Remaster повреждены или не все файлы корректно скопированы.\nПереустановите игру заново и снова скопируйте файлы патча в корень перед установкой.",
#                                           "eng": "Game or Community Patch / Remaster files are corrupted or not all the patch files are present in the game directory.\nReinstall the game and copy all the files of the patch to the root folder of the game before installing."},
#                "missing_distribution": {"rus": "Файлы Community Patch / Remaster не найдены рядом с установщиком.\nПоместите установщик в одну папку с остальными файлами ComPatch.",
#                                         "eng": "Community Patch / Remaster files were not found near the installer.\nPut the installer in the same folder where other Compatch distribution files are located"},
#                "error_logging_setup": {"rus": "Ошибка во время настройки логирования",
#                                        "eng": "Error occured when trying to setup logging"},
#                "installation_aborted": {"rus": "Установка прервана по желанию пользователя.",
#                                         "eng": "Installation aborted by the user."},
#                "nothing_to_install": {"rus": "Нечего устанавливать, работа закончена.",
#                                       "eng": "Nothing to install, work finished."}
#                }


def set_title() -> None:
    system("title " + f"DEM Community Mod Manager - v{VERSION} {DATE}")


def get_text_offsets(version: str) -> dict:
    if version == "patch":
        version_text = COMPATCH_VER
    elif version == "remaster":
        version_text = COMREM_VER
    else:
        raise NameError(f"Unsupported version '{version}'!")

    offsets_text = {
                    # version line in log and main menu
                    0x590680: [version_text, 70],
                    # version line in short log
                    0x5A85C8: [version_text, 70],
                    # log category: Loaded models info (AnimModels server log)
                    0x5A96D8: [version_text, 70],
                    # log category: Generic export description (SaveExportDescToFile)
                    0x5BA3C8: [version_text, 70],
                    # console version line
                    0x5BDCE8: [version_text, 70],
                    0x598DCC: ["169", 3]}
    return offsets_text

