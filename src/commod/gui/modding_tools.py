import asyncio
import contextlib
import json
import logging
import time
from pathlib import Path

import flet as ft
from lxml import etree, objectify

from commod.gui import app_widgets
from commod.gui import common_widgets as cw
from commod.helpers import file_ops, parse_ops
from commod.localisation.service import SupportedLanguages, get_current_lang, tr
from commod.tools import xml_diff, xml_merge
from commod.tools.xml_helpers import ActionType, Command, InvalidMergeCommandError

logger = logging.getLogger("dem")

class ModdingTools(ft.Tabs):
    def __init__(self, app: "app_widgets.App", **kwargs) -> None:
        kwargs.setdefault("padding", ft.padding.all(10))
        kwargs.setdefault("divider_height", 1)
        kwargs.setdefault("animation_duration", 25)
        super().__init__(**kwargs)

        self.refreshing = False

            # ft.Text(tr("merge_mod_creation").capitalize(),
            #         theme_style=ft.TextThemeStyle.TITLE_MEDIUM),
            # ft.Divider(height=5, color=ft.Colors.TRANSPARENT),

        self.tabs = [
            ft.Tab(
                text=tr("merge_mod_creation").capitalize(),
                content=ft.Container(
                    content=MergeTool(app), alignment=ft.alignment.center
                ),
                height=35
            ),
            ft.Tab(
                text=tr("documentation"),
                content=ft.Container(
                    content=MergeModsDocs(app), alignment=ft.alignment.top_left,
                    padding=ft.padding.all(10)
                ),
                height=35
            ),
        ]


class MergeModsDocs(ft.Row):
    def __init__(self, app: "app_widgets.App", **kwargs) -> None:
        super().__init__(**kwargs)
        self.md_container = ft.Ref[ft.Container]()
        self.btn_list = ft.Ref[ft.Column]()
        self.doc_content_container = ft.Column([
            ft.Container(
                None,
                ref=self.md_container,
                padding=ft.padding.only(left=15, right=10),
                margin=ft.margin.only(right=10),
                ),
            ],
            alignment=ft.MainAxisAlignment.START,
            scroll=ft.ScrollMode.ADAPTIVE,
            expand=True,
        )
        self.merge_docs_list = [
            "whats_merge_mod",
            "using_differ",
            "types_of_commands"
        ]

        self.controls = [
            ft.Column(controls=[
                ft.Container(ft.Text(tr("doc_sections"),
                                     weight=ft.FontWeight.BOLD),
                                     padding=ft.padding.only(left=10)),
                ft.Column([
                    ft.TextButton(
                        tr(key),
                        on_click=self.select_document,
                        style=ft.ButtonStyle(visual_density=ft.VisualDensity.COMPACT),
                        data=key) for key in self.merge_docs_list
                    ],
                    spacing=2,
                    ref=self.btn_list
                )
            ], width=190, expand_loose=True),
            ft.VerticalDivider(),
            self.doc_content_container
        ]

        first_doc = self.btn_list.current.controls[0]
        if isinstance(first_doc, ft.TextButton) and first_doc.data:
            first_doc.icon = ft.Icons.SUBDIRECTORY_ARROW_RIGHT
            self.md_container.current.content = self.get_md_doc(first_doc.data)

    def get_md_doc(self, name: str) -> ft.Markdown:
        try:
            lang = get_current_lang()
            if not file_ops.get_internal_file_path(f"assets/docs/{name}_{lang}.md").exists():
                lang = SupportedLanguages.ENG.value
            with open(file_ops.get_internal_file_path(f"assets/docs/{name}_{lang}.md"),
                      encoding="utf-8") as fh:
                md1 = fh.read()
                return cw.MarkdownWithCode(
                    md1,
                    selectable=True,
                    )
        except FileNotFoundError:
            return ft.Markdown("NO CONTENT AVAILABLE", expand=True)

    def select_document(self, e: ft.ControlEvent) -> None:
        if not isinstance(e.control, ft.TextButton):
            return

        if e.control.data:
            self.md_container.current.content = self.get_md_doc(e.control.data)
            self.md_container.current.update()
            for btn in self.btn_list.current.controls:
                if isinstance(btn, ft.TextButton):
                    btn.icon = None
                    # btn.update()
            e.control.icon = ft.Icons.SUBDIRECTORY_ARROW_RIGHT
            self.btn_list.current.update()

class MergeTool(ft.Column):
    def __init__(self, app: "app_widgets.App", **kwargs) -> None:
        kwargs.setdefault("spacing", 2)
        super().__init__(**kwargs)
        self.app = app
        self.ctrl_pressed = False

        diff_guides_path = file_ops.get_internal_file_path("assets/diff_guides.json")
        self.differs = {}
        if diff_guides_path.exists():
            try:
                diff_guides = []
                diff_guides_file = file_ops.read_json(diff_guides_path)
                if isinstance(diff_guides, list):
                    diff_guides = [xml_diff.DiffGuide(**config) for config in diff_guides_file]
                    self.differs = {guide.root_tag: xml_diff.Differ(guide) for guide in diff_guides}
                else:
                    raise TypeError("Incorrect diff guide provided!")
            except (json.decoder.JSONDecodeError, AssertionError, ValueError, TypeError):
                    logger.exception("Failed to load a diff guide!")

        logger.info(f"Loaded {len(self.differs)} differ schemes")

        self.command_preview = CommandPreview(modding_tools=self)
        self.current_command_card: CommandCard | None = None
        self.commands_view = ft.ListView(
            controls=[ft.Container(
                 ft.Placeholder(color=ft.Colors.SECONDARY_CONTAINER),
                 padding=ft.padding.symmetric(vertical=3))],
            padding=ft.padding.only(right=10))
        self.commands_container = ft.Container(
            self.commands_view, expand=True)

        self.source_path: Path | None = None
        self.modded_path: Path | None = None
        self.source_node_view = NodePreview(modding_tools=self)
        self.modded_node_view = NodePreview(modding_tools=self)

        self.source_path_field = cw.TextField(
            label=tr("enter_path_to_source"),
            dense=True,
            expand=5,
            )
        self.modded_path_field = cw.TextField(
            label=tr("enter_path_to_moddified"),
            dense=True,
            expand=5,
            )
        self.preload_checkbox = ft.Checkbox(value=True, on_change=self.toggle_preload)
        self.preload_commands_field = cw.TextField(
            label=tr("preload_existing_commands"),
            dense=True,
            expand=5,
        )
        self.output_path_field = cw.TextField(
            label=tr("enter_path_to_output"),
            dense=True,
            expand=6,
            )

        self.source_tree: objectify.ObjectifiedElement | None = None
        self.modded_tree: objectify.ObjectifiedElement | None = None
        self.source_tree_map: dict[str, objectify.ObjectifiedElement] = {}
        self.modded_tree_map: dict[str, objectify.ObjectifiedElement] = {}
        self.commands: list[Command] = []
        self.preloaded_commands: dict[str, list[Command]] = {}

        self.command_counter = CircleCounter()
        self.node_counter = CircleCounter(default_bg_color=ft.Colors.TERTIARY_CONTAINER)
        self.preloaded_counter = CircleCounter(default_bg_color=ft.Colors.TERTIARY_CONTAINER)

        self.select_all_btn = ft.Button(tr("select_all"), on_click=self.select_all, disabled=True)
        self.deselect_all_btn = ft.Button(tr("deselect_all"), on_click=self.deselect_all, disabled=True)
        self.invert_select_btn = ft.Button(tr("invert_selection"), on_click=self.select_invert, disabled=True)
        self.save_selected_btn = ft.OutlinedButton(
            tr("save_selected"), on_click=self.save_selected_ask, disabled=True)
        self.save_all_btn = ft.OutlinedButton(
            tr("save_all"), on_click=self.save_all_ask, disabled=True)
        self.calculate_diff_btn = ft.OutlinedButton(
            tr("calculate_diff"), scale=1.1, on_click=self.calculate_diff)

    def toggle_preload(self, e: ft.ControlEvent) -> None:
        self.preload_commands_field.disabled = not e.control.value
        self.preload_commands_field.update()

    def toggle_output_btns(self, enable: bool = False) -> None:
        for btn in [self.select_all_btn, self.deselect_all_btn, self.invert_select_btn,
                    self.save_selected_btn, self.save_all_btn, self.calculate_diff_btn]:
            btn.disabled = not enable
            btn.update()

    def select_invert(self, e: ft.ControlEvent) -> None:
        for card in self.commands_view.controls:
            if isinstance(card, CommandCard):
                card.checkbox.value = not card.checkbox.value
        self.commands_view.update()

    def select_all(self, e: ft.ControlEvent) -> None:
        for card in self.commands_view.controls:
            if isinstance(card, CommandCard):
                card.checkbox.value = True
        self.commands_view.update()

    def deselect_all(self, e: ft.ControlEvent) -> None:
        for card in self.commands_view.controls:
            if isinstance(card, CommandCard):
                card.checkbox.value = False
        self.commands_view.update()

    def close_bottom_sheet(self, e: ft.ControlEvent) -> None:
        with contextlib.suppress(ValueError):
            self.app.page.overlay.remove(e.control)

    def show_bottom_sheet(self, text: str) -> None:
        bs = ft.BottomSheet(
            ft.Container(
                ft.Row([
                    ft.Text(text, no_wrap=False)
                    ], tight=True),
                padding=20
            ),
            open=True,
            on_dismiss=self.close_bottom_sheet
        )
        self.app.page.open(bs)

    async def save_selected_ask(self, e: ft.ControlEvent) -> None:
        if not self.output_path_field.value or self.source_tree is None:
            self.show_bottom_sheet(tr("enter_path_to_output"))
            return

        if Path(self.output_path_field.value).exists():
            await self.app.show_modal(text=tr("overwrite_file_are_you_sure"),
                                      additional_text=self.output_path_field.value,
                                      on_yes=self.save_selected,
                                      on_no=self.app.close_alert)
        else:
            await self.save_selected()

    async def save_selected(self, e: ft.ControlEvent | None = None) -> None:
        self.app.close_alert()
        if self.source_tree is None:
            return

        try:
            if not self.output_path_field.value:
                return

            out_path = Path(self.output_path_field.value)
            if not out_path.parent.is_dir():
                await self.app.show_alert(tr("saving_commands_error"),
                                          f"Directory doesn't exist: {out_path.parent}",
                                          allow_copy=True)
                return
        except Exception as ex:
            await self.app.show_alert(tr("saving_commands_error"), str(ex),
                                      allow_copy=True)
            logger.exception("Unable to save selected commands")
            return

        if not self.commands:
            return

        cmds = [cmd_card.command for cmd_card in self.commands_view.controls
                if isinstance(cmd_card, CommandCard) and cmd_card.checkbox.value]

        if not cmds:
            self.show_bottom_sheet(tr("no_selected"))
            return

        self.show_bottom_sheet(tr("num_commands_saved", num_cmds=str(len(cmds))))

        commands_xml = xml_diff.Differ.serialize_commands(cmds, root_tag=str(self.source_tree.tag))
        await file_ops.write_xml_to_file_async(
            commands_xml, out_path, machina_beautify=True, use_utf=False)

    async def save_all_ask(self, e: ft.ControlEvent) -> None:
        if not self.output_path_field.value or self.source_tree is None:
            self.show_bottom_sheet(tr("enter_path_to_output"))
            return

        if Path(self.output_path_field.value).exists():
            await self.app.show_modal(text=tr("overwrite_file_are_you_sure"),
                                      additional_text=self.output_path_field.value,
                                      on_yes=self.save_all,
                                      on_no=self.app.close_alert)
        else:
            await self.save_all()


    async def save_all(self, e: ft.ControlEvent | None = None) -> None:
        self.app.close_alert()
        if self.source_tree is None:
            return

        try:
            if not self.output_path_field.value:
                return

            out_path = Path(self.output_path_field.value)
            if not out_path.parent.is_dir():
                await self.app.show_alert(tr("saving_commands_error"),
                                          f"Directory doesn't exist: {out_path.parent}",
                                          allow_copy=True)
                return
        except Exception as ex:
            await self.app.show_alert(tr("saving_commands_error"), str(ex),
                                      allow_copy=True)
            logger.exception("Unable to save all commands")
            return

        cmds = self.commands
        if not cmds:
            self.show_bottom_sheet(text=tr("no_selected"))
            return

        self.show_bottom_sheet(tr("num_commands_saved", num_cmds=str(len(cmds))))

        commands_xml = xml_diff.Differ.serialize_commands(cmds, root_tag=str(self.source_tree.tag))
        await file_ops.write_xml_to_file_async(commands_xml, out_path, machina_beautify=True, use_utf=False)

    def open_path(self, path_field: ft.TextField) -> None:
        if path_field.value:
            if not Path(path_field.value).exists():
                self.app.page.run_task(
                    self.app.show_alert,
                    f'{tr("file_doesnt_exist")}:\n`{path_field.value}`')
                return
            file_ops.open_file_in_editor(path_field.value, editor=self.app.config.code_editor)

    def build(self) -> None:
        self.horizontal_alignment=ft.CrossAxisAlignment.CENTER
        self.controls = [
            ft.Divider(height=5, color=ft.Colors.TRANSPARENT),
            ft.Row([self.source_path_field,
                    ft.IconButton(icon=ft.Icons.EDIT_NOTE,
                                  on_click=lambda _: self.open_path(path_field=self.source_path_field),
                                  tooltip=tr("open_in_editor")),
                    cw.BrowseFileButton(
                        tr("choose_path"), self.source_path_field,
                        allowed_extensions=["xml", "ssl"], expand=1,
                        initial_dir=self.app.config.last_differ_source)], spacing=5),
            ft.Row([self.modded_path_field,
                    ft.IconButton(icon=ft.Icons.EDIT_NOTE,
                                  on_click=lambda _: self.open_path(path_field=self.modded_path_field),
                                  tooltip=tr("open_in_editor")),
                    cw.BrowseFileButton(
                        tr("choose_path"), self.modded_path_field,
                        allowed_extensions=["xml", "ssl"], expand=1,
                        initial_dir=self.app.config.last_differ_modded)], spacing=5),
            ft.Row([self.preload_checkbox,
                    self.preload_commands_field,
                    cw.BrowseFileButton(
                        tr("choose_path"), self.preload_commands_field,
                        allowed_extensions=["xml"], expand=1,
                        allow_multiple=True,
                        initial_dir=self.app.config.last_differ_modded)], spacing=5),
            ft.Row([
                ft.Row([ft.Text(f"{tr("preloaded_commands")}: "), self.preloaded_counter], spacing=0),
                self.calculate_diff_btn,
                ft.Row([ft.Text(f"{tr("nodes_processed")}: "), self.node_counter], spacing=0),
                ft.Row([ft.Text(f"{tr("parsed_commands")}: "), self.command_counter], spacing=0),
                ], alignment=ft.MainAxisAlignment.CENTER, spacing=30),
            ft.Divider(height=10, thickness=2),
            ft.Row([
                ft.Column([
                    ft.Row([ft.Text(tr("command_list"))],
                           alignment=ft.MainAxisAlignment.CENTER),
                    self.commands_container,
                    ], expand=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Column([
                    ft.Text(tr("command_preview")),
                    self.command_preview,
                    ], expand=1,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.VerticalDivider(),
                ft.Column([
                    ft.Text(tr("source_node")),
                    self.source_node_view,
                    ], expand=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Column([
                    ft.Text(tr("moddified_node")),
                    self.modded_node_view,
                    ], expand=1, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ], expand=True, spacing=5, alignment=ft.MainAxisAlignment.CENTER),
            ft.Divider(height=5, color=ft.Colors.TRANSPARENT),
            ft.Row([self.select_all_btn, self.deselect_all_btn, self.invert_select_btn]),
            ft.Divider(height=5, color=ft.Colors.TRANSPARENT),
            ft.Row([self.output_path_field,
                    ft.IconButton(icon=ft.Icons.EDIT_NOTE,
                                  on_click=lambda _: self.open_path(path_field=self.output_path_field),
                                  tooltip=tr("open_in_editor")),
                    cw.BrowseFileButton(
                        tr("choose_path"), self.output_path_field,
                        mode="save", allowed_extensions=["xml"],
                        initial_dir=self.app.config.last_differ_modded),
                    self.save_selected_btn, self.save_all_btn]),
        ]

    def preview_current_node(self) -> None:
        if self.current_command_card is None:
            return

        self.current_command_card.elevation = 0
        self.current_command_card.update()
        cmd = self.current_command_card.command
        self.command_preview.update()

        if cmd.source_node is not None:
            self.source_node_view.node = cmd.source_node
            self.source_node_view.count = cmd.existing_count
        else:
            self.source_node_view.node = None

        self.source_node_view.file_path = self.source_path
        self.source_node_view.update()

        self.modded_node_view.node = cmd.modded_node if cmd.modded_node is not None else None
        self.modded_node_view.count = cmd.desired_count
        self.modded_node_view.file_path = self.modded_path
        self.modded_node_view.update()

    def click_command(self, e: ft.ControlEvent) -> None:
        if self.current_command_card is not None:
            self.current_command_card.elevation = 7
            self.current_command_card.update()

        self.current_command_card = e.control.parent
        self.preview_current_node()

    def secondary_click_command(self, e: ft.ControlEvent) -> None:
        e.control.parent.checkbox.value = not e.control.parent.checkbox.value
        e.control.parent.update()

    def cleanup(self, e: ft.ControlEvent | None = None) -> None:
        self.commands_container.content = None
        self.commands_container.update()
        self.current_command_card = None
        self.commands_view.controls.clear()
        self.commands.clear()
        self.preloaded_commands.clear()
        self.command_preview.update()

        self.source_node_view.reset()
        self.modded_node_view.reset()
        self.source_node_view.update()
        self.modded_node_view.update()

        self.command_counter.count = 0
        self.node_counter.count = 0
        self.preloaded_counter.count = 0

        self.enable_diff_btn()
        self.toggle_output_btns(enable=True)

    def enable_diff_btn(self) -> None:
        self.calculate_diff_btn.disabled = False
        self.calculate_diff_btn.update()

    def set_last_differ_paths_to_config(self) -> None:
        if self.source_path_field.value and Path(self.source_path_field.value).exists():
            self.app.config.set_last_differ_source(Path(self.source_path_field.value).parent)
        if self.modded_path_field.value and Path(self.modded_path_field.value).exists():
            self.app.config.set_last_differ_modded(Path(self.modded_path_field.value).parent)

    async def calculate_diff(self, e: ft.ControlEvent) -> None:  # noqa: PLR0911
        if not self.source_path_field.value or not self.modded_path_field.value:
            await self.app.show_alert(tr("need_two_paths_for_comparison"))
            return

        if not Path(self.source_path_field.value).exists():
            await self.app.show_alert(tr("source_path_doesnt_exist"), self.source_path_field.value)
            return
        if not Path(self.modded_path_field.value).exists():
            await self.app.show_alert(tr("modded_path_doesnt_exist"), self.modded_path_field.value)
            return

        self.toggle_output_btns(enable=False)

        self.current_command_card = None
        self.commands_view.controls.clear()
        self.commands.clear()
        self.preloaded_commands.clear()

        self.command_counter.count = 0
        self.node_counter.count = 0
        self.preloaded_counter.count = 0


        self.commands_container.content = ft.Container(
            ft.Column([ft.ProgressRing(width=100, height=100)],
                      alignment=ft.MainAxisAlignment.CENTER))
        self.commands_container.update()

        try:
            self.source_tree = parse_ops.xml_to_objfy(self.source_path_field.value)
            self.modded_tree = parse_ops.xml_to_objfy(self.modded_path_field.value)
            if self.source_tree.tag != self.modded_tree.tag:
                raise ValueError(
                    "Can't produce diff for trees with different root tags: "
                    f"'{self.source_tree.tag}' vs '{self.modded_tree.tag}'")

            if self.source_tree.xpath(".//*[@_Action]"):
                raise ValueError(
                    f"Can't produce diff for file containing commands:\n> {self.source_path_field.value}"
                )
            if self.modded_tree.xpath(".//*[@_Action]"):
                raise ValueError(
                    f"Can't produce diff for file containing commands:\n> {self.modded_path_field.value}"
                )

            if self.preload_commands_field.value and not self.preload_commands_field.disabled:
                for source_file_path in self.preload_commands_field.value.split(","):
                    source_file = Path(source_file_path.strip())
                    if not source_file.exists() or source_file.suffix != ".xml":
                        await self.app.show_alert(
                            f'{tr("command_path_doesnt_exist")}:\n\n`{source_file}`')
                        logger.warning(f"Incorrect file found in preload commands: '{source_file}', skipping")
                        self.cleanup()
                        raise InvalidMergeCommandError
                    preloaded_commands = parse_ops.xml_to_objfy(source_file)
                    if preloaded_commands.tag != self.source_tree.tag:
                        await self.app.show_alert(
                            tr("incorrect_commands_for_source",
                            cmd_path=source_file_path))
                    else:
                        try:
                            commands = xml_merge.parse_command_tree(
                                preloaded_commands, merge_author=source_file.name)
                            self.preloaded_commands[str(source_file)] = commands
                        except InvalidMergeCommandError as ex:
                            await self.app.show_alert(tr("existing_command_reading_error") +
                                                      f":\n\n{source_file_path}\n",
                                                      str(ex), allow_copy=True)
                            logger.exception("Can't load existing files or commands")
                            self.cleanup()
                            return
            try:
                for key, command_list in self.preloaded_commands.items():
                    logger.info(f"Attempting to apply commands from {key}")
                    xml_merge.apply_commands(self.source_tree, command_list)
                    self.preloaded_counter.count += len(command_list)
                await asyncio.sleep(0.001)
            except Exception as ex:
                await self.app.show_alert(tr("unable_to_apply_commands",
                                             target=self.source_path_field.value), str(ex),
                                          allow_copy=True)
                logger.exception("Unable to apply commands to source tree")
                self.cleanup()
                return

            if differ := self.differs.get(str(self.source_tree.tag)):
                self.differ = differ
            else:
                self.show_bottom_sheet(tr("using_fallback_differ"))
                logger.info("Unknown file type, diffs will be unusable")
                self.differ = xml_diff.Differ(
                    xml_diff.DiffGuide(root_tag=str(self.source_tree.tag)))

            self.differ.annotate_tree(self.source_tree)
            self.differ.annotate_tree(self.modded_tree)
            self.source_path = Path(self.source_path_field.value)
            self.modded_path = Path(self.modded_path_field.value)
        except UnicodeDecodeError:
            await self.app.show_alert(tr("cant_load_files_for_diffing"),
                                      f'{tr("unsupported_file_or_encoding")}: '
                                      f'{Path(self.source_path_field.value).name}',
                                      allow_copy=True)
            logger.exception("Can't load files for diffing, decoding failed")
            self.cleanup()
            return
        except Exception as ex:
            await self.app.show_alert(tr("cant_load_files_for_diffing"), str(ex),
                                      allow_copy=True)
            logger.exception("Can't load files for diffing")
            self.cleanup()
            return

        self.commands_container.content = self.commands_view
        self.commands_container.update()

        self.command_counter.counting = True
        self.node_counter.counting = True

        start = time.perf_counter()

        commands_generator = self.differ.calculate_diff(
            self.source_tree, self.modded_tree)

        total_processed = 0
        try:
            cmd = None
            while cmd is None:
                cmd = next(commands_generator)
                total_processed += 1
            self.commands.append(cmd)
            cmd_card = CommandCard(self, cmd)
            self.current_command_card = cmd_card
            self.commands_view.controls.append(cmd_card)
            self.command_counter.count = len(self.commands)
            self.node_counter.count = total_processed
            self.commands_view.update()
            self.preview_current_node()
            await asyncio.sleep(0.001)
        except StopIteration:
            self.node_counter.count = total_processed
            self.node_counter.counting = False
            self.set_last_differ_paths_to_config()
            logger.debug("No commands generated, files seem to be equal!")
            await self.app.show_alert(tr("diffed_files_are_equal"),
                                      header_loc_str="info",
                                      header_ico_color=ft.Colors.BLUE,
                                      on_dismiss=self.cleanup)
            return

        last_upd_nodes = time.perf_counter()
        last_upd_cmds = time.perf_counter()
        try:
            for cmd in commands_generator:
                total_processed += 1
                if (time.perf_counter() - last_upd_nodes) > self.node_counter.update_timeout:
                    self.node_counter.count = total_processed
                    await asyncio.sleep(0.001)
                    last_upd_nodes = time.perf_counter()

                if cmd is None:
                    continue

                self.commands.append(cmd)
                self.commands_view.controls.append(CommandCard(self, cmd))

                if (time.perf_counter() - last_upd_cmds) > self.node_counter.update_timeout:
                    self.command_counter.count = len(self.commands)
                    self.commands_view.update()
                    await asyncio.sleep(0.001)
                    last_upd_cmds = time.perf_counter()

        except StopIteration:
            pass
        except Exception as ex:
            await self.app.show_alert(tr("command_generation_error"), str(ex),
                                      allow_copy=True)
            logger.exception("Exception occured when generating commands")
            self.cleanup()
            return

        logger.debug(f"Generated commands from diffs in "
                      f"{round(time.perf_counter() - start, 3)} seconds")

        self.command_counter.count = len(self.commands)
        self.command_counter.counting = False
        self.node_counter.count = total_processed
        self.node_counter.counting = False
        self.commands_view.update()
        self.set_last_differ_paths_to_config()
        self.toggle_output_btns(enable=True)

class CommandPreview(ft.Container):
    def __init__(self, modding_tools: "MergeTool") -> None:
        super().__init__()
        self.modding_tools = modding_tools
        self.expand = True

    def before_update(self) -> None:
        if self.modding_tools.current_command_card is None:
            self.content = ft.Column([
                    ft.Row([
                        ft.Container(
                           ft.Placeholder(color=ft.Colors.SECONDARY_CONTAINER),
                            margin=ft.margin.symmetric(horizontal=10, vertical=3),
                            clip_behavior=ft.ClipBehavior.NONE)],
                        wrap=True)],
                    scroll=ft.ScrollMode.AUTO)
            return

        cmd = self.modding_tools.current_command_card.command
        serizalized_cmd = xml_diff.Differ.serialize_command(cmd) #, keep_attrs=["_DuplicateCount"])
        objectify.deannotate(serizalized_cmd, cleanup_namespaces=True)

        etree.indent(serizalized_cmd, space="    ")
        cmd_xml_string = \
            parse_ops.beautify_machina_xml(
                etree.tostring(
                    serizalized_cmd,
                    encoding="utf-8",
                    pretty_print=True)
                ).decode().strip() #.replace("&quot;", "''")

        self.content = \
                ft.Column([
                    ft.Row([
                        ft.Container(
                           cw.MarkdownWithCode(
                                f"```xml\n{cmd_xml_string}\n```",
                                selectable=True),
                            margin=ft.margin.only(right=15),
                            border_radius=10, clip_behavior=ft.ClipBehavior.ANTI_ALIAS)],
                        wrap=True)],
                    scroll=ft.ScrollMode.ALWAYS)

class NodePreview(ft.Container):
    def __init__(self, modding_tools: "MergeTool",
                 node: objectify.ObjectifiedElement | None = None,
                 file_path: Path | None = None,
                  **kwargs) -> None:
        super().__init__(**kwargs)
        self.modding_tools = modding_tools
        self.file_path = file_path
        self.node = node
        self.count = 1
        self.expand = True
        self.edit_btn = ft.IconButton(
            icon=ft.Icons.EDIT_NOTE,
            on_click=self.open_path,
            tooltip=tr("open_in_editor"),
            icon_color=ft.Colors.WHITE70,
            scale=0.8,
            padding=0
            )

    def open_path(self, e: ft.ControlEvent) -> None:
        if (isinstance(self.node, objectify.ObjectifiedElement)
            and isinstance(self.file_path, Path)
            and self.node.sourceline is not None):
            file_ops.open_file_in_editor(self.file_path, line=int(self.node.sourceline),
                                         editor=self.modding_tools.app.config.code_editor)

    def reset(self) -> None:
        self.content = ft.Container(
            ft.Placeholder(color=ft.Colors.SECONDARY_CONTAINER),
            padding=ft.padding.symmetric(horizontal=10, vertical=3))

    def before_update(self) -> None:
        if not self.modding_tools.current_command_card:
            self.reset()
            return

        self.edit_btn.disabled = self.node is None

        if self.node is not None:
            etree.indent(self.node, space="    ")
            node_string = parse_ops.beautify_machina_xml(
                etree.tostring(
                    self.node,
                    encoding="utf-8",
                    pretty_print=True)
                ).decode().strip() # .replace("&quot;", "''")
            self.content = \
                ft.Stack([
                    ft.Column([
                        ft.Row([
                            ft.Container(
                                cw.MarkdownWithCode(
                                    f"```html\n{node_string}\n```",
                                    selectable=True),
                                margin=ft.margin.only(right=15),
                                border_radius=10,
                                clip_behavior=ft.ClipBehavior.ANTI_ALIAS)],
                            wrap=True),
                        ft.Container(
                            ft.Text(f"x{self.count}", color=ft.Colors.BLACK, weight=ft.FontWeight.BOLD)
                            if self.count != 1 else None,
                            padding=ft.padding.all(3),
                            margin=ft.margin.only(top=-25),
                            bgcolor=ft.Colors.AMBER,
                            shape=ft.BoxShape.CIRCLE,
                            visible=self.count!=1
                        )],
                        scroll=ft.ScrollMode.ALWAYS),
                    ft.Container(
                        self.edit_btn,
                        margin=ft.margin.only(right=15),
                        padding=0)
                ], alignment=ft.alignment.top_right)
        else:
            self.content = \
                ft.Column([
                    ft.Row([
                        ft.Container(
                            ft.Text(tr("node_not_found"),
                                color=ft.Colors.RED,
                                font_family="Fira Code",
                                weight=ft.FontWeight.W_500,
                                text_align=ft.TextAlign.CENTER,
                                # expand=True
                                ),
                            padding=30,
                            border_radius=10,
                            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                            bgcolor="#282c34")], wrap=True)])

class CircleCounter(ft.Stack):
    def __init__(self, default_bg_color: ft.Colors = ft.Colors.RED, **kwargs) -> None:
        super().__init__(**kwargs)
        self.update_timeout = 0.05
        self.alignment = ft.alignment.center
        self._count = 0
        self.default_bg_color = default_bg_color

        self.container = ft.Container(shape=ft.BoxShape.CIRCLE, width=39, height=39,
                                      bgcolor=default_bg_color,
                                      alignment=ft.alignment.center)
        self.ring = ft.ProgressRing(visible=False, height=39, width=39,
                                    color=ft.Colors.ON_TERTIARY_CONTAINER,
                                    stroke_width=2,
                                    stroke_align=-1.0)
        self.controls = [self.container, self.ring]

        self._counting = False

    @property
    def counting(self) -> bool:
        return self._counting

    @counting.setter
    def counting(self, val: bool) -> None:
        if self._counting == val:
            return
        self._counting = val
        self.update()

    @property
    def count(self) -> int:
        return self._count

    @count.setter
    def count(self, val: int) -> None:
        if self._count == val:
            return
        self._count = val
        self.update()

    def before_update(self) -> None:
        self.container.content = ft.Text(str(self.count),
                                         color=ft.Colors.ON_TERTIARY_CONTAINER,
                                         weight=ft.FontWeight.W_500)
        if self.count == 0:
            self.ring.visible = False
            self.container.bgcolor = self.default_bg_color
        elif self.counting:
            self.container.bgcolor = ft.Colors.ORANGE_900
            self.container.content.color = ft.Colors.ORANGE_100
            self.ring.visible = True
        else:
            self.container.bgcolor = ft.Colors.GREEN_900
            self.container.content.color = ft.Colors.GREEN_100
            self.ring.visible = False

class CommandCard(ft.Card):
    def __init__(self, modding_tools: "MergeTool", command: Command, **kwargs) -> None:
        super().__init__(**kwargs, elevation=7)
        self.modding_tools = modding_tools
        self.command = command
        if command.action in [ActionType.ADD,
                              ActionType.REPLACE,
                              ActionType.ADD_OR_REPLACE]:
            type_color = ft.Colors.GREEN
        elif command.action in [ActionType.MODIFY, ActionType.MODIFY_OR_FAIL]:
            type_color = ft.Colors.ORANGE
        else:
            type_color = ft.Colors.RED

        self.surface_tint_color = type_color

        self.checkbox = ft.Checkbox(scale=0.9)
        self.content = ft.GestureDetector(
            ft.Container(ft.Column([
                ft.Row([self.checkbox,
                        ft.Text(str(command.action.value), weight=ft.FontWeight.W_700, color=type_color)]),
                ft.Text(command.selector),
                ft.Text(f"Parent: {command.parent_path or 'root'}", opacity=0.8),
                ]),
                padding=ft.padding.symmetric(5, 10)),
            on_tap=self.modding_tools.click_command,
            on_secondary_tap=self.modding_tools.secondary_click_command,
            mouse_cursor=ft.MouseCursor.CLICK)


