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


class css(Enum):
    HEADER = 'font-size: 16pt'
    BLUE = 'color:CornflowerBlue'
    ORANGE = 'color: orange'
    CYAN = 'color:cyan'
    GREEN = 'color:green'
    LGREEN = 'color:LightGreen'
    YELLOW = 'color:yellow'
    GOLD = 'color:gold'
    RED = 'color:red'
    GRAY = 'color:gray'
    WHITE = 'color:white'
    BOLD = 'font-weight: bold'
    ITALIC = 'font-style: italic'
    UNDERLINE = 'text-decoration: underline'

    def __str__(self):
        return self.value


def fconsole(string: str,
             style: bcolors | list[bcolors] = bcolors.BOLD) -> str:
    '''Format text with terminal color codes and styles'''
    if isinstance(style, list):
        for color in style:
            string = f"{color}{string}{bcolors.ENDC}"
    else:
        string = f"{style}{string}{bcolors.ENDC}"
    return string


def fcss(string: str,
         style: css | list[css] = css.BOLD,
         p: bool = False) -> str:
    '''Format text with css/html color and styles tags,
    setting p=True wraps text to paragraph tag <p>'''
    if isinstance(style, list):
        style = [str(st) for st in style]
        style = "; ".join(style)

    if p:
        style = f'<p style="{style}">'
        end = "</p>"
    else:
        style = f'<span style="{style}">'
        end = "</span>"

    new_line_formatted = br(string)
    return f"{style}{new_line_formatted}{end}"


def br(string: str):
    '''Replaces escaped new lines with <br>'''
    return string.replace("\n", "<br>")


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
