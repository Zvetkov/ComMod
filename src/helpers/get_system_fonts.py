import sys
import inspect

def getmember(obj, name):
    return [member
            for _name, member in inspect.getmembers(obj)
            if name == _name][0]

def get_fonts(under_windows: bool = True):
    if under_windows:
        helpers_module = __import__("helpers.get_system_fonts_linux")
        get_system_fonts_linux_module = getmember(helpers_module, "get_system_fonts_linux")
        get_system_fonts_class = getattr(get_system_fonts_linux_module, "get_fonts")
        print(f"GET FONTS LINUX:{get_system_fonts_class.get_fonts()}", file=sys.stderr)
    else:
        helpers_module = __import__("helpers.get_system_fonts_windows")
        get_system_fonts_linux_module = getmember(helpers_module, "get_system_fonts_windows")
        get_system_fonts_class = getattr(get_system_fonts_linux_module, "get_fonts")
        print(f"GET FONTS WINDOWS:{get_system_fonts_class.get_fonts()}", file=sys.stderr)






