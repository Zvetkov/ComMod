from enum import Enum


class bcolors(Enum):
    HEADER = '\033[95m'   # Bright Magenta
    OKBLUE = '\033[94m'   # Bright Blue
    OKCYAN = '\033[96m'   # Bright Cyan
    OKGREEN = '\033[92m'  # Bright Green
    WARNING = '\033[93m'  # Bright Yellow
    RED = '\033[91m'      # Bright Red
    GRAY = '\033[90m'     # Bright Black (Gray)
    ENDC = '\033[0m'      # closing code 'tag'
    BOLD = '\033[1m'
    FAINT = '\033[2m'     # decreased intensity or dim
    ITALIC = '\033[3m'
    UNDERLINE = '\033[4m'

    def __str__(self):
        return self.value


def format_text(string: str, style: bcolors | list[bcolors] = bcolors.BOLD) -> str:
    if isinstance(style, list):
        for color in style:
            string = f"{color}{string}{bcolors.ENDC}"
    else:
        string = f"{style}{string}{bcolors.ENDC}"
    return string


def remove_colors_from_list(text: list):
    decoloured_text = text.copy()
    for line in decoloured_text:
        remove_colors(line)


def remove_colors(text: str):
    if not isinstance(text, str):
        return ''
    for color in bcolors:
        text = text.replace(color.value, '')
    return text
