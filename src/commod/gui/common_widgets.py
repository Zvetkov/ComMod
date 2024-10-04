import flet as ft
from flet import Column, Icon, Row, Text


def title_btn_style(hover_color: str | None = None) -> ft.ButtonStyle:
    color_dict = {ft.ControlState.DEFAULT: ft.colors.ON_BACKGROUND}
    if hover_color is not None:
        color_dict[ft.ControlState.HOVERED] = ft.colors.RED
    return ft.ButtonStyle(
        color=color_dict,
        padding={ft.ControlState.DEFAULT: 0},
        shape={ft.ControlState.DEFAULT: ft.RoundedRectangleBorder(radius=2)}
    )

class ExpandableContainer(ft.Container):
    def __init__(self, label_expanded: str, label_collapsed: str, content: ft.Control,
                 expanded: bool = True,
                 min_height: int = 48,
                 border_thickness: int = 2,
                 vertical_margin: int = 15,
                 horizontal_margin: int = 20,
                 color: str = ft.colors.SECONDARY_CONTAINER,
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
        self.icon = ft.icons.KEYBOARD_ARROW_RIGHT_OUTLINED
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
