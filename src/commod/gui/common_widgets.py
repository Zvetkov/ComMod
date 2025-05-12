import contextlib
from pathlib import Path
from typing import Literal

import flet as ft
from flet import Column, Icon, Row, Text

from commod.localisation.service import tr


class TitleButton(ft.IconButton):
    def __init__(self, icon: ft.Icons, icon_size: int,
                 hover_color: ft.Colors | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self.icon = icon
        self.icon_size = icon_size

        color_dict: dict[ft.ControlState, str] = {ft.ControlState.DEFAULT: ft.Colors.ON_SURFACE}
        if hover_color is not None:
            color_dict[ft.ControlState.HOVERED] = hover_color
        self.style = ft.ButtonStyle(
            color=color_dict,
            padding={ft.ControlState.DEFAULT: 0},
            shape={ft.ControlState.DEFAULT: ft.RoundedRectangleBorder(radius=2)})

class ExpandableContainer(ft.Container):
    def __init__(self, label_expanded: str, label_collapsed: str, content: ft.Control,
                 expanded: bool = True,
                 min_height: int = 48,
                 border_thickness: int = 2,
                 vertical_margin: int = 15,
                 horizontal_margin: int = 20,
                 color: str = ft.Colors.SECONDARY_CONTAINER,
                 **kwargs) -> None:
        kwargs.setdefault("content", content)
        kwargs.setdefault("animate", ft.animation.Animation(200, ft.AnimationCurve.EASE_IN_OUT))
        kwargs.setdefault("border_radius", 10)
        kwargs.setdefault("padding", 11)
        kwargs.setdefault("border", ft.border.all(border_thickness, color))
        super().__init__(**kwargs)

        self.user_content = content
        self.horizontal_margin = horizontal_margin
        self.vertical_margin = vertical_margin

        self.color = color
        self.min_height = min_height
        self.label_expanded = label_expanded
        self.label_collapsed = label_collapsed
        self.expanded = expanded
        self.icon = ft.Icons.KEYBOARD_ARROW_RIGHT_OUTLINED
        self.toggle_icon = ft.Ref[Icon]()
        self.label_text = ft.Ref[Text]()
        self.rotation_angle = 0.5 * 3.1416

        self.on_click =         self.toggle
        self.height =           None if self.expanded else min_height
        self.animate =          ft.animation.Animation(200, ft.AnimationCurve.EASE_IN_OUT)
        self.clip_behavior =    ft.ClipBehavior.HARD_EDGE

    def build(self) -> None:
        self.content = \
            Column([
                ft.Container(Row([
                    Icon(self.icon,
                         ref=self.toggle_icon,
                         rotate=ft.Rotate(angle=0 if not self.expanded else self.rotation_angle,
                                          alignment=ft.alignment.center),
                         animate_rotation=ft.animation.Animation(duration=200)),
                    Text(self.label_expanded if self.expanded else self.label_collapsed,
                         color=self.color,
                         ref=self.label_text)
                    ]), margin=ft.margin.symmetric(horizontal=5)),
                ft.Container(self.user_content, margin=ft.margin.only(
                    left=self.horizontal_margin, right=self.horizontal_margin, bottom=self.vertical_margin))
            ], spacing=13)


    def minimize(self) -> None:
        self.height = self.min_height
        self.expanded = False
        self.toggle_icon.current.rotate = ft.Rotate(angle=0, alignment=ft.alignment.center)
        self.label_text.current.value = self.label_collapsed
        # self.toggle_icon.current.update()
        self.update()

    def maximize(self) -> None:
        self.height = None
        self.expanded = True
        self.toggle_icon.current.rotate = ft.Rotate(angle=self.rotation_angle, alignment=ft.alignment.center)
        self.label_text.current.value = self.label_expanded
        # self.toggle_icon.current.update()
        self.update()

    def toggle(self, e: ft.ControlEvent) -> None:
        if self.expanded:
            self.minimize()
        else:
            self.maximize()
        self.update()

class TextField(ft.TextField):
    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("height", 42)
        kwargs.setdefault("text_size", 13)
        kwargs.setdefault("label_style", ft.TextStyle(size=13, weight=ft.FontWeight.BOLD))
        kwargs.setdefault("text_style", ft.TextStyle(size=13, weight=ft.FontWeight.BOLD))
        kwargs.setdefault("border_color", ft.Colors.OUTLINE)
        kwargs.setdefault("focused_border_color", ft.Colors.PRIMARY)
        super().__init__(**kwargs)

class BrowseFileButton(ft.Row):
    def __init__(self, text: str,
                 controled_text_field: ft.TextField,
                 allowed_extensions: list[str],
                 mode: Literal["open", "save"] = "open",
                 initial_dir: str | Path | None = None,
                 allow_multiple: bool = False,
                 **kwargs) -> None:
        kwargs.setdefault("spacing", 0)
        super().__init__(**kwargs)
        self.btn = ft.Button(text, expand=True)
        self.get_file_dialog = ft.FilePicker()
        self.get_file_dialog.on_result = self.file_pick_result if mode == "open" else self.save_file_result
        self.controls = [self.btn, self.get_file_dialog]

        self.text_field = controled_text_field
        self.allowed_extensions = allowed_extensions
        self.allow_multiple = allow_multiple
        if initial_dir is not None and Path(initial_dir).exists():
            self.initial_dir = str(initial_dir)
        else:
            self.initial_dir = None
        if mode == "open":
            self.btn.on_click = self.pick_file_for_field
        else:
            self.btn.on_click = self.save_file_for_field

    def save_file_for_field(self, e: ft.ControlEvent) -> None:
        file_name = "_commands.xml"
        if self.text_field.value and self.text_field.value.endswith(".xml"):
            with contextlib.suppress(Exception):
                file_name = Path(self.text_field.value).name
        if self.text_field.value and Path(self.text_field.value).parent.exists():
            init_dir = Path(self.text_field.value).parent
        else:
            init_dir = self.initial_dir

        self.get_file_dialog.save_file(
            dialog_title=tr("choose_file"),
            file_name=file_name,
            initial_directory=str(init_dir),
            allowed_extensions=self.allowed_extensions
        )

    def pick_file_for_field(self, e: ft.ControlEvent) -> None:
        if self.text_field.value:
            if self.allow_multiple:
                try:
                    parent_path = self.text_field.value.split(", ")[0]
                    parent = Path(parent_path) if Path(parent_path).is_dir() else Path(parent_path).parent
                except IndexError:
                    parent = Path("")
            else:
                parent = Path(self.text_field.value).parent
            if str(parent) != "." and parent.is_dir():
                self.initial_dir = str(parent)

        return self.get_file_dialog.pick_files(
            dialog_title=tr("choose_files") if self.allow_multiple else tr("choose_file"),
            allowed_extensions=self.allowed_extensions,
            initial_directory=self.initial_dir,
            allow_multiple=self.allow_multiple)

    def save_file_result(self, e: ft.FilePickerResultEvent) -> None:
        if self.get_file_dialog.result and self.get_file_dialog.result.path:
            self.text_field.value = self.get_file_dialog.result.path
            self.text_field.update()

    def file_pick_result(self, e: ft.FilePickerResultEvent) -> None:
        self.text_field.value = (
            ", ".join([file.path for file in e.files]) if e.files else self.text_field.value
        )
        self.text_field.update()

class MarkdownWithCode(ft.Markdown):
    def __init__(self, value: str, use_colored_headers: bool = True,
                 **kwargs) -> None:
        kwargs.setdefault("auto_follow_links", True)
        kwargs.setdefault("code_theme", ft.MarkdownCodeTheme.ATOM_ONE_DARK)
        kwargs.setdefault(
            "code_style_sheet",
            ft.MarkdownStyleSheet(
                code_text_style=ft.TextStyle(
                        font_family="Fira Code", size=13),
            )
        )
        kwargs.setdefault(
            "md_style_sheet",
            ft.MarkdownStyleSheet(
                horizontal_rule_decoration=ft.BoxDecoration(
                    shape=ft.BoxShape.RECTANGLE,
                    border=ft.Border(
                        top=ft.BorderSide(2, color=ft.Colors.ORANGE_200),
                        # bottom=ft.BorderSide(10, color=ft.Colors.ORANGE_400),
                        # right=ft.BorderSide(5, color=ft.Colors.ORANGE_400),
                        # left=ft.BorderSide(5, color=ft.Colors.ORANGE_400)
                    ),
                ),
                blockquote_decoration=ft.BoxDecoration(
                    shape=ft.BoxShape.RECTANGLE,
                    border_radius=5,
                    border=ft.Border(top=ft.BorderSide(2, color=ft.Colors.SECONDARY_CONTAINER),
                                     bottom=ft.BorderSide(2, color=ft.Colors.SECONDARY_CONTAINER),
                                     left=ft.BorderSide(2, color=ft.Colors.SECONDARY_CONTAINER),
                                     right=ft.BorderSide(2, color=ft.Colors.SECONDARY_CONTAINER)),
                ),
                blockquote_text_style=ft.TextStyle(color=ft.Colors.ON_SECONDARY_CONTAINER),
                h1_text_style=ft.TextStyle(color=ft.Colors.ORANGE_500,
                                           weight=ft.FontWeight.W_700) if use_colored_headers else None,
                h2_text_style=ft.TextStyle(color=ft.Colors.ORANGE_500,
                                           weight=ft.FontWeight.W_700) if use_colored_headers else None,
                h3_text_style=ft.TextStyle(color=ft.Colors.ORANGE_500,
                                           weight=ft.FontWeight.W_700) if use_colored_headers else None,
                h4_text_style=ft.TextStyle(color=ft.Colors.ORANGE_500,
                                           weight=ft.FontWeight.W_700) if use_colored_headers else None,
            )
        )
        kwargs.setdefault("expand", True)
        kwargs.setdefault("extension_set", ft.MarkdownExtensionSet.GITHUB_WEB)
        super().__init__(value, **kwargs)
