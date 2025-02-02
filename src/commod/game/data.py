# flake8: noqa
from dataclasses import dataclass
from enum import StrEnum
from os import system
import platform

from commod import __version__

OWN_VERSION = __version__

DATE = "(Oct 04 2024)"
# version of binary fixes
# corresponds with the latest major.minor ComPatch/Rem release at the time of ComMod compilation
VERSION = "1.14"

# main version of exe is dependent on binary fixes, not on ComMod
# but version string will include ComPatch/Rem build id at the end of the string
COMPATCH_VER = f"ExMachina - Community Patch fixes v{VERSION} {DATE}"
COMPATCH_MIN = f"ExMachina - Minimal ComPatch build 1.02 {DATE}"
COMREM_VER = f"ExMachina - Community Remaster fixes v{VERSION} {DATE}"


DEM_DISCORD = "https://discord.gg/jZHxYdF"
DEM_DISCORD_MODS_DOWNLOAD_SCREEN = "https://discord.gg/deus-ex-machina-522817939616038912"
COMPATCH_GITHUB = "https://github.com/DeusExMachinaTeam/EM-CommunityPatch"
WIKI_COMREM = "https://deuswiki.com/w/Community_Remaster"

COMMOD_USES = (
    "[flet](https://github.com/flet-dev/flet/blob/main/LICENSE), "
    "[pydantic](https://github.com/pydantic/pydantic/blob/main/LICENSE), "
    "[nuitka](https://github.com/Nuitka/Nuitka/blob/develop/LICENSE.txt), "
    "[pyyaml](https://github.com/yaml/pyyaml/blob/main/LICENSE), "
    "[lxml](https://lxml.de/index.html#license), "
    "[py7zr](https://github.com/miurahr/py7zr/blob/master/LICENSE), "
    "[httpx](https://github.com/encode/httpx/blob/master/LICENSE.md), "
    "[pathvalidate](https://github.com/thombashi/pathvalidate/blob/master/LICENSE), "
    "[python-markdownify](https://github.com/matthewwithanm/python-markdownify/blob/develop/LICENSE), "
    "[aiofiles](https://github.com/Tinche/aiofiles/blob/main/LICENSE), "
    "[aiopath](https://github.com/alexdelorenzo/aiopath/blob/main/LICENSE), "
    "[aioshutil](https://github.com/kumaraditya303/aioshutil/blob/master/LICENSE.md)")

VERSION_BYTES_100_STAR = 0x005A69C2
VERSION_BYTES_102_NOCD = 0x005906A3
VERSION_BYTES_102_STAR = 0x000102CD
VERSION_BYTES_103_NOCD = 0x005917D2
VERSION_BYTES_103_STAR = 0x000103CD
VERSION_BYTES_DEM_LNCH = 0x0000DEAD

VERSION_BYTES_M113_101 = 0x007BED2B
VERSION_BYTES_ARCD_100 = 0x0072F9FC

ENCODING = 'windows-1251'

TARGET_RES_X = 1920.0
TARGET_RES_Y = 1080.0
ORIG_RES_X = 1024.0
ORIG_RES_Y = 768.0

DEFAULT_COMREM_GRAVITY = -19.62


ENLARGE_UI_COEF = TARGET_RES_Y / ORIG_RES_Y

TARGEM_POSITIVE = ("yes", "yeah", "yep", "true")
TARGEM_NEGATIVE = ("no", "nope", "none", "false")

PREFERED_RESOLUTIONS = {1920: [960, 1280, 1366, 1600, 1920],
                        2560: [960, 1280, 1600, 1920, 2560],
                        3840: [1280, 1366, 1920, 2560, 3840]}

DEFAULT_RESOLUTIONS = PREFERED_RESOLUTIONS[1920]

KNOWN_RESOLUTIONS = {426: 240,
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

DEFAULT_SCALE_FACTOR = 1.0
DEFAULT_LINUX_SCALE_FACTOR = 2.0

def get_system_os_scale():
    if "Windows" in platform.system():
        try:
            from ctypes import windll
            return windll.shcore.GetScaleFactorForDevice(0) / 100
        except (ImportError, NameError):
            return DEFAULT_SCALE_FACTOR
    else:
        return DEFAULT_LINUX_SCALE_FACTOR

OS_SCALE_FACTOR = get_system_os_scale()

@dataclass
class BinaryPatch:
    offset: int
    enable_value: str
    disable_value: str
    comment: str = ""
    value_is_offset: bool = False

projection_matrix_patches = [
    BinaryPatch(
        offset=0x1D770,
        enable_value="D94020D8701CD94020D80D68599E00D80DE8599E00D9F2DDD8D83D7C599E00D9C057B91000000089D7F30F1005545A9E0031C0F3AB5F0F28D0F30F5CD1F30F5EC2F30F114228F30F59C10F57C9F30F5CC8F30F10057C599E00F30F114A38F30F11422CD91AD8F1D95A14DDD8C3",
        disable_value="D9402057D80D68599E00B9100000008BFAF30F1005545A9E00D80DE8599E00D9401C0F28D0D8702033C0F3ABF30F5CD1F30F5EC2F30F114228F30F59C10F57C9F30F5CC8F30F10057C599E00F30F114A38F30F11422C5FD8C9D80D68599E00D9F2DDD8D83D7C599E00D91AD80D"
        )]

draw_distance_patches = [
    BinaryPatch(
        offset=0x1BF494,
        enable_value="83F8207E05B820000000",
        disable_value="83F80C7E05B80C000000",
        comment="m3d::Landscape::Load"
    ),
    BinaryPatch(
        offset=0x23A682,
        enable_value="83F8207E05B820000000",
        disable_value="83F80C7E05B80C000000",
        comment="m3d::SceneGraph::UpdateVis"
    ),
    BinaryPatch(
        offset=0x3A54B5,
        enable_value="83F8207E05B820000000",
        disable_value="83F80C7E05B80C000000",
        comment="m3d::Landscape::GetFogStartAndEnd"
    ),
    BinaryPatch(
        offset=0x3AB185,
        enable_value="83FB207E09BB20000000",
        disable_value="83FB0C7E09BB0C000000",
        comment="m3d::Landscape::Render"
    ),
    BinaryPatch(
        offset=0x3B61F3,
        enable_value="83FE207E05BE20000000",
        disable_value="83FE0C7E05BE0C000000",
        comment="m3d::RoadManager::UpdateVis"
    ),
    BinaryPatch(
        offset=0x3EC1DD,
        enable_value="83F8207E05B820000000",
        disable_value="83F80C7E05B80C000000",
        comment="ai::InfoCone::GetInfoObjId"
    ),
    BinaryPatch(
        offset=0x4FBEC2,
        enable_value="83F8207E05B820000000",
        disable_value="83F80C7E05B80C000000",
        comment="m3d::WeatherThunderstorm::Render"
    ),
    BinaryPatch(
        offset=0x5E3204, enable_value=19.0, disable_value=0.0,
        comment="max drawDistance with lsViewDivider = 1.0 before min offset (+ 4.0 = 23.0)"
    ),
    BinaryPatch(
        offset=0x1BF478, enable_value="0x009E3204", disable_value="0x00990944",
        comment="m3d::Landscape::Load",
        value_is_offset=True
    ),
    BinaryPatch(
        offset=0x23A666, enable_value="0x009E3204", disable_value="0x009E5978",
        comment="m3d::SceneGraph::UpdateVis",
        value_is_offset=True
    ),
    BinaryPatch(
        offset=0x3A5499, enable_value="0x009E3204", disable_value="0x009AB264",
        comment="m3d::Landscape::GetFogStartAndEnd",
        value_is_offset=True
    ),
    BinaryPatch(
        offset=0x3AB165, enable_value="0x009E3204", disable_value="0x009AB264",
        comment="m3d::Landscape::Render",
        value_is_offset=True
    ),
    BinaryPatch(
        offset=0x3B61D6, enable_value="0x009E3204", disable_value="0x009E5978",
        comment="m3d::RoadManager::UpdateVis",
        value_is_offset=True
    ),
    BinaryPatch(
        offset=0x3EC1C9, enable_value="0x009E3204", disable_value="0x009E5ADC",
        comment="ai::InfoCone::GetInfoObjId",
        value_is_offset=True
    ),
    BinaryPatch(
        offset=0x4FBEAE, enable_value="0x009E3204", disable_value="0x009E5ADC",
        comment="m3d::WeatherThunderstorm::Render",
        value_is_offset=True
    )
]

slow_brake_patches = [
    BinaryPatch(
        offset=0x1DAC06, enable_value="0x009E59E8", disable_value="0x009E597C",
        comment="keep / auto throttle (7C 59 9E 00) -> (E8 59 9E 00) (1.0 -> 0.01)",
        value_is_offset=True
    ),
    BinaryPatch(
        offset=0x1DAC81, enable_value="0x009E59E8", disable_value="0x009E597C",
        comment="handbrake (7C 59 9E 00) -> (E8 59 9E 00) ( 1.0 -> 0.01)",
        value_is_offset=True
    ),
    BinaryPatch(
        offset=0x0017DB, enable_value="0xBDCCCCCD", disable_value="0x000080BF",
        comment="break (00 00 80 BF) -> (CD CC CC BD) (-1.0 -> -0.1)",
        value_is_offset=True
    )
]

hq_reflections_patches = [
    BinaryPatch(
        offset=0x1C14C9, enable_value="0x00000400", disable_value="0x00000200",
        value_is_offset=True
    )
]

default_difficulty_lowest_patches = [
    BinaryPatch(
        offset=0x000E387, enable_value="05", disable_value="0B",
        comment="Sets default difficulty to index 0 (lowest difficulty), instead of index 1 (second lowest)"
    )
]

peace_price_from_schwarz_patches = [
    BinaryPatch(
        offset=0x0346D7A, enable_value="A6", disable_value="8D",
        comment=("When calculating price of making peace with faction,"
        "game gets part of player money. Reroute this to use PlayersSchwarz, "
        "this wont allow to make peace for free if player has no money")
    )
]

no_money_in_player_schwarz_patches = [
    BinaryPatch(
        offset=0x0251381, enable_value="31F6EB02", disable_value="8BB11801",
        comment=("All dyn.quests calculate rewards from player's vehicle schwarz, "
                 "but hunt uses PlayerSchwarz, equal to VehicleSchwarz+PlayerMoney. "
                 "This makes PlayerSchwarz equal to VehicleSchwarz, ignoring player's money.")
    )
]

# were precalculated and hardcoded as we don't support changing the fov dynamically
# ASPECT_RATIO = TARGET_RES_X / TARGET_RES_Y

# PARTIAL_STRETCH_OFFSET = 0.07
# PARTIAL_STRETCH = 1 / (1 - 2 * PARTIAL_STRETCH_OFFSET)

# TARGET_FOV_X_DEG = 90.0
# TARGET_FOV_X_RADS = math.radians(TARGET_FOV_X_DEG)
# TARGET_FOV_Y_RADS = 2 * math.atan(math.tan(TARGET_FOV_X_RADS / 2) * (1 / ASPECT_RATIO))
# TARGET_FOV_Y_DEG = math.degrees(TARGET_FOV_Y_RADS)
# COEFF_FOV_X_FROM_Y = TARGET_FOV_X_RADS / TARGET_FOV_Y_RADS
# COEFF_FOV_Y_FROM_X = TARGET_FOV_Y_RADS / TARGET_FOV_X_RADS

# OFFSET_UI_X = round((TARGET_RES_X - ORIG_RES_X * ENLARGE_UI_COEF) / 2)
# OFFSET_UI_Y = round((TARGET_RES_Y - ORIG_RES_Y * ENLARGE_UI_COEF) / 2)

# cheat sheet table of used available empty spaces (align) in binary
# 0x5E2BCB
# 0x5E300C # sell price coeff
# 0x5E306C # 0.08 move fog start closer to camera
# 0x5E3204 # 28.0 for max drawDistance before min offset (+ 4.0 = 32.0)
# 0x5E3C61 # min damage resistance coeff
# 0x5E41EA # logo x size
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

minimal_mm_inserts = {
    # 4GB patch
    0x00015E: "2E",
    # stack size - 4 Mb
    0x1A8: "00004000"
    }

additional_mm_inserts = {
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
    }

binary_inserts = {
    # void __cdecl _E17()
    # 0x5FF000: "00DF9800",

    # Init Kraken
    # 0x58DF00: "5589E583EC0C6863ED9F00FF158CE198008945FC837DFC000F850B0000006AFFFF15BCE3980083C4046A018B45FC50FF1590E198008945F8837DF8000F850B0000006AFFFF15BCE3980083C4048B4DF8894DF48B55FC52FF55F483C40489EC5DC3CCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",

    # dllLibrary
    # 0x5FED63: "6B72616B656E2E646C6C",

    # ConstantDLLName "library.dll"
    0x5FED63: "6C6962726172792E646C6C00",

    # disabling blast damage friendly fire
    0x3DFADC: "00",
    # removing player death count from stats screen
    0x108E3A: "EB0F",

    # Treecollisionfix
    # ai::BreakableObjectPrototypeInfo::RefreshFromXml
    0x453B57: "5E83C418C20800CCCCCCCCCCCCCCCCCC",
    # ai::BreakableObjectPrototypeInfo::LoadFromXML
    0x452D6C: "6A06",

    # near plane fix 1.0 -> 0.1 (TODO: seems like it doesn't have an intended effect)
    0x3AB7FB: "68CDCCCC3D",

    # animation moveframe (vehichle spawn freeze fix)
    0x30A620: "515355568BF1578B7E2485FF0F84AF00000033ED4566396F040F8CA20000008B5E2C2B5C2418834E60FF895E2C85DB0F8F900000000FBF4F048BC399F7F98B4E282BE803CD894E280FBF47040FAFC5894C241803C389462C0FBF470289442410483BC87C440FBF5F0885DB7911C74664010000000FBF470248894628EB2B8B4E206A342BB99C0000008BC79959F7F93BC3750E8B44241899F77C2410895628EB08538BCEE877FDFFFF8B46682BC5837E6C00894668740E85C0790A83666C00EB04836628005F5E5D5B59C204000400CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",

    # CFile free errors
    #   0x346960: "8B410485C0740750FF1508700710C3CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC",
    # foxie.dll support
    #   0x24ED5C: "909090909090",
    #   0x18C480: "57566A44E8D98C3D0083C40489C685C07501CC686FED9F00FF158CE1980089C785C07501CC6A0157FF1590E1980085C07501CC893EC7460462519600C7460868519600C7460C00000000C746108C98A000C746148098A000C74618F0BB7400C7461CB04E6600C74620B0246600C7462460516600C7462800496400C7462CD0316200C7463050AF7400C7463480955800C74638A0955800C7463C940CA000C74640680EA00056FFD083C40485C07501CC5E5FC3CCCCCCCCCCCCCCCCCCCCCCCCCC",
    #   0x5FED6F: "666F7869652E646C6C00",

    # luabridge
    0x2368D0: "575681EC8000000089CEFF15B8E1980089C789E06A006880000000506A00576A006800120000FF1570E0980085C0740B89E289F1E847E82500EB0F576881ED9F0056E8C9E8250083C40C81C4800000005E5FC3CCCCCCCCCCCCCCCCCCCCCCCCCC53575689CEBA010000006A00E86F04260089C789F1BA020000006A00E85F04260089C357FF158CE1980085C0742B89C75350FF1590E1980085C0743989C389F189FAE839E9250089F189DA6A01E88EE82500B801000000EB4289F1E850E7250089F1E839FFFFFF89F1BA77ED9F00E8ADE72500EB2189F1E834E7250089F1E81DFFFFFF89F1BA7CED9F00E891E7250057FF15A0E19800B8030000005E5F5BC3CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC8B0DF82DA100BA6FED9F00E850E725008B0DF82DA1006A00BA30696300E8FEE725008B0DF82DA100BAEFD8FFFFE89EEA2500E9F9C7FEFFCCCCCCCCCCCCCCCCCC",
    0x2231D0: "568BF1E8C8D2270085C0A3F82DA1007507B8060000005EC38BC8E8B1CE27008B0DF82DA100E8F6B927008B0DF82DA100E87B9F27008B0DF82DA100E8309527008B0DF82DA100E8A57C2700E9D03701008B0DF82DA100BAD45D9900E8201F27008B0DF82DA1006A00BA501B6200E8CE1F27008B0DF82DA100BAEFD8FFFFE86E2227008B0DF82DA100BAD05D9900E8EE1E27008B0DF82DA1006A00BA001D6200E89C1F27008B0DF82DA100BAEFD8FFFFE83C2227008B0DF82DA100BAC05D9900E8BC1E27008B0DF82DA1006A00BA102B6200E86A1F27008B0DF82DA100BAEFD8FFFFE80A2227008B0DF82DA100BAB85D9900E88A1E27008B0DF82DA1006A00BAA00E6200E8381F27008B0DF82DA100BAEFD8FFFFE8D82127008B0DF82DA100E88D6627008B0DF82DA100E8125A27008B0DF82DA100E8B72027008B0DF82DA100BAB05D9900E8371E27008B0DF82DA1006A00BAB01C6200E8E51E27008B0DF82DA100BAFDFFFFFFE8852127008B0DF82DA100BAF0D8FFFFE8C53327008B0DF82DA100A3F02DA100E8652027008B0DF82DA100BAB05D9900E8E51D27008B0DF82DA1006A00BA800A6200E8931E27008B0DF82DA100BAFDFFFFFFE8332127008B0DF82DA100BAF0D8FFFFE8733327008B0DF82DA100BA605D9900A3EC2DA100E89E1D27008B0DF82DA100BAEFD8FFFFE80E1F27008B0DF82DA10083CAFFE8F01B27008B0DF82DA100BAFEFFFFFFA3E82DA100E85B1627008B0DF82DA1006A00BAF0FA6100E8191E27008B0DF82DA100BA605D9900E8491D27008B0DF82DA100BAFEFFFFFFE8C91627008B0DF82DA100BAEFD8FFFFE8992027008935C854A3008935F42DA100C646580133C05EC3CCCCCCCCCC",
    0x5FED6F: "6C6F61646C6962006F70656E00696E69740073797374656D206572726F722025645C6E00",
    }

offsets_exe_fixes = {
    # aspect ratio hack for Frustum Culling
    0x3A6128: 1.5707963267948966,  # TARGET_FOV_X_RADS,   # fov_x passed to CClipper::CreateScreenFrustums
    0x5E497C: 1.5328148297998656,  # COEFF_FOV_X_FROM_Y,  # hacked "aspect_ratio" coeff to calc fov_y

    # back sliding vehicle throttle lock coeff
    0x1DABEE: "0x009E59EC",

    # max_resistance_for_damage
    0x2D72A5: "0x009E5A28",  # 25.0 -> 100.0
    # min_resistance_for_damage
    0x2D7295: "0x009E3C61",
    0x5E3C61: -101.0,  # -25.0 -> -101.0
    }

offsets_dll = {
    # to keep 1/1024 intact for other uses, redirect aspect ratio correction
    0x006E35: "0x1016E6F3",

    # and use this value instead of the original one
    0x16E6F3: 1/1920.0,
    0x16E618: 1/1080.0,
    0x16E624: 1080.0,
    0x16E628: 1920.0
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

# values writen as is, tuned for 1920x1080 UI grid used in ComRem
offsets_comrem_absolute = {
   # base UI resolution without aspect ratio correction
   0x5E5A3C: 1920.0,  # 1024.0 CMiracle3D:Render
   0x5E5A38: 1080.0,  # 768.0 CMiracle3D:Render
   0x19786: 1920.0,   # 1024.0 CMiracle3d::DrawBackground - can't find result
   0x1977E: 1080.0,   # 768.0 CMiracle3d::DrawBackground - can't find result
   # autoScrollPixelSpeed maxWidth - can't find result
   0xA5B58: 1920.0,

   # mouse cursor coordinates - OnGameMouse and CaptureMouse
   0x1203: 960.0,  # 1920 / 2,
   0x18053: 960.0,  # 1920 / 2,
   0x120B: 540.0,  # 1080 / 2,
   0x1805B: 540.0,  # 1080 / 2,

   # move 1024.0 to another address for use in m3d::Landscape::BuildSolidLandscape
   0x5E5A14: 1024.0,  # 009E5A14
   # start to use it
   0x3A6B9B: "0x009E5A14",  # m3d::Landscape::BuildSolidLandscape

   0x30808B: 2048,  # model rendering resolution in interface (render to texture)
   0x308092: 2048,  # same as previous

   # text adjustment
   0x590248: 0.0005208333333333333,  # 1 / 1920.0,  # originally 1/1024

   # save screenshot resolution
   0x17BCA8: 512,
   0x17BCAF: 256,

   # PostEffectManager
   0x26B416: 1920.0,
   0x26B49D: 1920.0,
   0x26B495: 1080.0,
   0x26B40E: 25.0 * 1.40625,  # 25.0 * ENLARGE_UI_COEF
   0x26B4A5: (1080.0 - (25.0 * 1.40625)),  # (1080.0 - (25.0 * ENLARGE_UI_COEF))

   # target capturing cursor
   0x12864C: 12,  # 12, numCapturingSectors

   # radar turret ico size redirect
   0x5E576C: 14.0,
   0x12C3D1: "0x009E576C",

   # NpcList spacing
   0x5E59C8: 8.0,

   # SaveSellList spacing (def - 5.0)
   0x103829: "0x009E5A80",

   # GameMenuWnd (pause menu)
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

   # cabin SecondGunOrigin
   0x5E5B34: 370.0,  # x - 144.0
   # cabinFirstGunOrigin
   0x5E5B3C: 736.0  # x - 368.0
   }

#  requires correction, floats and int are multiplied by data.ENLARGE_UI_COEF
offsets_comrem_relative = {
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

    # bindKeysWnd item X - 32.0
    0x6A6DA: "0x009E5B0C",

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
    0x5C3B10: 448.0,
    }

configurable_offsets = {
    "gravity": 0x202D25,
    "skins_in_shop_0": 0x181DCA,
    "skins_in_shop_1": 0x181C95,
    "skins_in_shop_2": 0x181E75,
    "blast_damage_friendly_fire": 0x3DFADC,
    "sell_price_coeff_new": 0x5E300C
    }

sell_price_offsets = {
    0x2B8995: "0x009E300C"
}

# hidden_values = {
    # "low_fuel_threshold": [0.25, 0x124CCD, "pointer", "used_elsewhere"],
    # "low_fuel_blinking_period": [300, 0x124CF3, "direct", "single_use"],
    #  "min_resistance_for_damage": [-25.1, 0x2D7295, "pointer", "single_use"],
    #  "max_resistance_for_damage": [25.0, 0x2D72A5, "pointer", "used_elsewhere"],
    # "blast_damage_friendly_fire": [0x01, 0x3DFADC, "direct", "single_use"]}  # bool


em_102_icon_offset = 0x60A3A8
em_102_icon_size = 5694

rva_offset = 0x3D000
size_of_image = 0x198

offset_of_rsrc = 0x60A000
resource_dir_size = 0x1D4
size_of_rsrc_offset = 0x2C0
size_of_rsrc = 6632
raw_size_of_rsrc_offset = 0x2C8

offset_of_reloc_offset = 0x2EC
size_of_reloc_offset = 0x2E8

offset_of_reloc_raw = 0x2F4

new_icon_group_info = "0000010001000000000001002000F38E00000100"
new_icon_header_ends = 0x16

new_icon_size_offset = 0x60A0BC
new_icon_group_offset = 0x60A0C8


def get_title() -> str:
    return f"DEM Community Mod Manager {OWN_VERSION}"


def set_title() -> None:
    system("title " + get_title())


def get_text_offsets(version: str) -> dict:
    if version == "patch":
        version_text = COMPATCH_VER
    elif version == "remaster":
        version_text = COMREM_VER
    elif version == "minimal":
        version_text = COMPATCH_MIN
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


class SupportedGames(StrEnum):
    EXMACHINA = "exmachina"
    M113 = "m113"
    ARCADE = "arcade"

    @classmethod
    def _missing_(cls, value: str):
        value = value.lower()
        for member in cls:
            if member == value:
                return member
        return None
