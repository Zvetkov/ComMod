import ctypes
from ctypes import wintypes
from typing import ClassVar


class LOGFONT(ctypes.Structure):
    _fields_: ClassVar =\
        [("lfHeight", wintypes.LONG),
         ("lfWidth", wintypes.LONG),
         ("lfEscapement", wintypes.LONG),
         ("lfOrientation", wintypes.LONG),
         ("lfWeight", wintypes.LONG),
         ("lfItalic", wintypes.BYTE),
         ("lfUnderline", wintypes.BYTE),
         ("lfStrikeOut", wintypes.BYTE),
         ("lfCharSet", wintypes.BYTE),
         ("lfOutPrecision", wintypes.BYTE),
         ("lfClipPrecision", wintypes.BYTE),
         ("lfQuality", wintypes.BYTE),
         ("lfPitchAndFamily", wintypes.BYTE),
         ("lfFaceName", ctypes.c_wchar*32)]


FONTENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.POINTER(LOGFONT),
                                  wintypes.LPVOID, wintypes.DWORD, wintypes.LPARAM)


def get_fonts() -> list:
    font_list = []

    def font_enum(logfont, textmetricex, fonttype, param):
        face_name = logfont.contents.lfFaceName
        if (any(face_name in s for s in font_list) is False):
            font_list.append(face_name)
        return True

    hdc = ctypes.windll.user32.GetDC(None)
    ctypes.windll.gdi32.EnumFontFamiliesExW(hdc, None, FONTENUMPROC(font_enum), 0, 0)
    ctypes.windll.user32.ReleaseDC(None, hdc)
    return font_list
