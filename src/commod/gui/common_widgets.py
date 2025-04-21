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

        color_dict = {ft.ControlState.DEFAULT: ft.Colors.ON_SURFACE}
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
        self.get_file_dialog.save_file(
            dialog_title=tr("choose_file"),
            file_name="commands.xml", # read from field if changed there
            initial_directory=self.initial_dir,
            allowed_extensions=self.allowed_extensions
        )

    def pick_file_for_field(self, e: ft.ControlEvent) -> None:
        if self.text_field.value:
            parent = Path(self.text_field.value).parent
            if str(parent) != "." and parent.is_dir():
                self.initial_dir = str(parent)

        return self.get_file_dialog.pick_files(
            dialog_title=tr("choose_files") if self.allow_multiple else tr("choose_file"),
            allowed_extensions=self.allowed_extensions,
            initial_directory=self.initial_dir,
            allow_multiple=self.allow_multiple)

    def save_file_result(self, e: ft.FilePickerResultEvent) -> None:
        if self.get_file_dialog.result:
            self.text_field.value = self.get_file_dialog.result.path
            self.text_field.update()

    def file_pick_result(self, e: ft.FilePickerResultEvent) -> None:
        self.text_field.value = (
            ", ".join([file.path for file in e.files]) if e.files else self.text_field.value
        )
        self.text_field.update()
