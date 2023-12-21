import flet as ft
from flet import Column, Icon, Row, Text


class ExpandableContainer(ft.Container):
    def __init__(self, label_expanded: str, label_collapsed: str, content: ft.Control,
                 expanded: bool = True, min_height: int = 48,
                 *args, **kwargs) -> None:
        kwargs.setdefault("content", self.internal_content)
        kwargs.setdefault("animate", ft.animation.Animation(200, ft.AnimationCurve.EASE_IN_OUT))
        super().__init__(*args, **kwargs)

        self.min_height = min_height
        self.label_expanded = label_expanded
        self.label_collapsed = label_collapsed
        self.expanded = expanded
        self.icon = ft.icons.KEYBOARD_ARROW_RIGHT_OUTLINED
        self.toggle_icon = ft.Ref[Icon]()
        self.rotation_angle = 0.5 * 3.1416
        self.internal_content = ft.Container(
            Column([
                ft.Container(Row([
                    Icon(self.icon,
                         ref=self.toggle_icon,
                         rotate=ft.Rotate(angle=0 if not self.expanded else self.rotation_angle,
                                          alignment=ft.alignment.center),
                         animate_rotation=ft.animation.Animation(duration=200)),
                    Text(self.label_expanded if expanded else self.label_collapsed)
                    ]), margin=ft.margin.symmetric(horizontal=5)),
                ft.Container(content, margin=ft.margin.only(left=20, right=20, bottom=15))
            ], spacing=13),
            on_click=self.toggle,
            height=None if self.expanded else min_height,
            animate=ft.animation.Animation(200, ft.AnimationCurve.EASE_IN_OUT),
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
            border=ft.border.all(2, ft.colors.SECONDARY_CONTAINER),
            padding=11, border_radius=10
        )


    async def minimize(self) -> None:
        self.internal_content.height = self.min_height
        self.expanded = False
        self.toggle_icon.current.rotate = ft.Rotate(angle=0, alignment=ft.alignment.center)
        await self.toggle_icon.current.update_async()
        await self.update_async()

    async def maximize(self) -> None:
        self.internal_content.height = None
        self.expanded = True
        self.toggle_icon.current.rotate = ft.Rotate(angle=self.rotation_angle, alignment=ft.alignment.center)
        await self.toggle_icon.current.update_async()
        await self.update_async()

    async def toggle(self, e: ft.ControlEvent) -> None:
        if self.expanded:
            await self.minimize()
        else:
            await self.maximize()
        await self.update_async()
