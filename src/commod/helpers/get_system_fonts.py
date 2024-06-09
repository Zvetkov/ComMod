import platform
from typing import ClassVar


def get_fonts() -> list:
    font_list = []

    def font_enum(logfont, textmetricex, fonttype, param):
        face_name = logfont.contents.lfFaceName
        if (any(face_name in s for s in font_list) is False):
            font_list.append(face_name)
        return True

    try:
        if "Windows" in platform.system():
            from ctypes import windll, wintypes  # noqa: I001
            import ctypes
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

            font_emum_proc = ctypes.WINFUNCTYPE(
                ctypes.c_int, ctypes.POINTER(LOGFONT), wintypes.LPVOID, wintypes.DWORD, wintypes.LPARAM)

            hdc = windll.user32.GetDC(None)
            windll.gdi32.EnumFontFamiliesExW(hdc, None, font_emum_proc(font_enum), 0, 0)
            windll.user32.ReleaseDC(None, hdc)
        else:
            pass # Not implemented
    except (ImportError, NameError):
        pass

    return font_list
