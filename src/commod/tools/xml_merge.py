from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from lxml import etree, objectify

from commod.helpers import file_ops, parse_ops


class InvalidMergeCommandError(Exception):
    ...

class AmbiguousMergeCommandError(Exception):
    ...

class ActionType(Enum):
    ADD = "Add"
    REPLACE = "Replace"
    ADD_OR_REPLACE = "AddOrReplace"
    MODIFY = "Modify"
    REMOVE = "Remove"

    @classmethod
    def list_values(cls) -> list[str]:
        return [c.value for c in cls]

def reformat_xml(input_path: Path, output_path: Path) -> None:
    input_tree = parse_ops.xml_to_objfy(input_path)
    file_ops.write_xml_to_file(input_tree, output_path, machina_beautify=True, use_utf=False)

@dataclass
class Command:
    action: ActionType
    parent_path: str
    selector: str
    tag: str
    node_attrs: dict
    selector_keys: Iterable[str]
    children_nodes: list[objectify.ObjectifiedElement] | None
    merge_author: str = ""
    desired_count: int = 1
    source_node: objectify.ObjectifiedElement | None = None
    modded_node: objectify.ObjectifiedElement | None = None

def traverse_path(tree: objectify.ObjectifiedElement, full_path: str) -> objectify.ObjectifiedElement:
    element = tree
    if full_path == f"//{element.tag}":
        return element

    full_path = full_path.replace(f"//{element.tag}/", "//")
    elements = tree.xpath(full_path)

    if not elements:
        raise InvalidMergeCommandError(
            f"No elements found for path '{full_path}'")
    if len(elements) > 1:
        raise AmbiguousMergeCommandError(
            f"Multiple possible elements found for path '{full_path}'")
    return elements[0]



def parse_commands(xml_node: objectify.ObjectifiedElement,
                   commands: list[Command],
                   current_path: str, merge_author: str) -> list[Command]:
    if xml_node.tag == "comment":
        return commands

    action_parsed = xml_node.attrib.get("_Action")
    desired_count = xml_node.attrib.get("_DesiredCount", 1)
    selector_keys_parsed = xml_node.attrib.get("_SelectorKeys", "").replace(" ", "")
    parent_path = xml_node.attrib.get("_ParentXPath", "").rstrip("/")
    selector = xml_node.attrib.get("_Selector", "").rstrip("/")

    if parent_path:
        try:
            xml_node.xpath(parent_path)
        except etree.XPathEvalError:
            raise InvalidMergeCommandError(
                f"Invalid ParentXPath specified: '{parent_path}'") from None

    if action_parsed and action_parsed not in ActionType.list_values():
        raise InvalidMergeCommandError(f"Invalid action type: '{action_parsed}'")

    action = ActionType(action_parsed)

    if selector_keys_parsed:
        if selector_keys_parsed == "*":
            selector_keys = [key for key in xml_node.attrib if not key.startswith("_")]
        else:
            selector_keys = selector_keys_parsed.split(",")
        if not selector_keys:
            raise InvalidMergeCommandError(f"{selector_keys=} are invalid")
    else:
        selector_keys = []

    if selector_keys and selector:
        raise InvalidMergeCommandError("Defined both _Selector and _SelectorKeys, need only one")

    if action in [ActionType.REPLACE, ActionType.ADD_OR_REPLACE,
                  ActionType.MODIFY, ActionType.REMOVE] and not (selector_keys or selector):
        raise InvalidMergeCommandError(f"'{action}' actions must define _Selector or _SelectorKeys attribute")

    if isinstance(desired_count, str) and not desired_count.isnumeric():
        raise InvalidMergeCommandError(f"_DesiredCount must be numeric instead of '{desired_count}'")

    desired_count = int(desired_count)

    max_desired_count = 50
    if desired_count > max_desired_count:
        raise InvalidMergeCommandError(f"Too many repeated actions, limited to {max_desired_count}")

    children_nodes = xml_node.getchildren()

    if action in [ActionType.REMOVE, ActionType.MODIFY] and children_nodes:
        raise InvalidMergeCommandError(f"'{action}' actions can't have children nodes")

    if action:
        # maybe need to implicitly add/merge parent even when _Action is not specified
        commands.append(
            Command(
                action=action,
                parent_path=parent_path,
                selector=selector,
                tag=str(xml_node.tag),
                node_attrs=xml_node.attrib,
                selector_keys=selector_keys,
                children_nodes=children_nodes,
                merge_author=merge_author,
                desired_count=desired_count))
        return commands

    if not action:
        raise NotImplementedError("Nested actions are TBD")
        for child in children_nodes:
            new_path = f"{parent_path}/{xml_node.tag}"
            if current_path != "/":
                if len(xml_node.attrib) > 1:
                    raise InvalidMergeCommandError
                if xml_node.attrib:
                    key, el_id = xml_node.attrib.items()[0]
                    new_path = f'{new_path}[@{key}="{el_id}"]'

            parse_commands(child, commands, new_path, merge_author)
    # we directy add all children nodes for Add actions, without processing them separately
    # if action == ActionType.Add:
        # return commands

    return commands

def apply_command(tree: objectify.ObjectifiedElement, command: Command) -> objectify.ObjectifiedElement:
    # if not command.parent_path.startswith(f"//{tree.tag}"):
        # raise InvalidMergeCommandError

    elm = traverse_path(tree, command.parent_path) if command.parent_path else tree

    if command.selector_keys:
        selector = command.tag + "".join(f'[@{key}="{command.node_attrs.get(key)}"]'
                                         for key in command.selector_keys)
    else:
        selector = command.selector

    elements = elm.xpath(selector)

    if command.action == ActionType.ADD_OR_REPLACE:
        if not elements:
            command.action = ActionType.ADD
        else:
            command.action = ActionType.REPLACE
        apply_command(tree, command)
    elif command.action == ActionType.ADD:
        if elements:
            raise InvalidMergeCommandError(
                f"Can't Add node, matching element already exist for selector '{selector}'")

        for _ in range(command.desired_count):
            new_elm = objectify.Element(command.tag)
            for attr_key, attr_val in command.node_attrs.items():
                if not attr_key.startswith("_"):
                    new_elm.set(attr_key, attr_val)
            new_elm.set("_MergeAuthor", command.merge_author)

            if command.children_nodes:
                new_elm.extend(command.children_nodes)

            elm.append(new_elm)
    elif command.action == ActionType.REPLACE:
        if not elements:
            raise InvalidMergeCommandError(
                f"Can't Replace node, nothing matches selector '{selector}'")
        if len(elements) > 1:
            raise InvalidMergeCommandError(
                f"Can't Replace node, multiple matches found for selector '{selector}'")
        element = elements[0]
        element.attrib.clear()

        for child in element.getchildren():
            element.remove(child)

        for attr_key, attr_val in command.node_attrs.items():
            if not attr_key.startswith("_"):
                element.set(attr_key, attr_val)
        element.set("_MergeAuthor", command.merge_author)

        if command.children_nodes:
            element.extend(command.children_nodes)

    elif command.action == ActionType.MODIFY:
        if not elements:
            raise InvalidMergeCommandError(
                f"Can't Modify node, nothing matches selector '{selector}'")
        for elem in elements:
            for attr_key, attr_val in command.node_attrs.items():
                if not attr_key.startswith("_") and attr_key not in command.selector_keys:
                    elem.set(attr_key, attr_val)
            elem.set("_MergeAuthor", command.merge_author)
    elif command.action == ActionType.REMOVE:
        if not elements:
            print(f"Remove command is useless, had no matching nodes for selector '{selector}' anyway")
            return tree
        element = elements[0]
        elm.remove(element)
    else:
        raise InvalidMergeCommandError(f"Unknown merge command: {command.action}")
    return tree

def apply_commands(base_tree: objectify.ObjectifiedElement, commands: list[Command]) -> objectify.ObjectifiedElement:
    for command in commands:
        apply_command(base_tree, command)
    objectify.deannotate(base_tree, cleanup_namespaces=True)
    return base_tree

def parse_command_tree(command_tree: objectify.ObjectifiedElement,
                       merge_author: str) -> list[Command]:
    commands = []
    for command_node in command_tree.getchildren():
        parse_commands(command_node, commands, "/", merge_author)
    return commands

def combine_two_xmls(base_path: Path, commands_file: Path,
                     output_path: Path,
                     merge_author: str) -> None:
    base_tree = parse_ops.xml_to_objfy(base_path)
    commands_tree = parse_ops.xml_to_objfy(commands_file)

    if base_tree.tag != commands_tree.tag:
        raise InvalidMergeCommandError(
            "Merge mod should have the same base node as the target document: "
            f"'{base_tree.tag}' != '{commands_tree.tag}'")

    commands = parse_command_tree(commands_tree, merge_author)

    updated_tree = apply_commands(base_tree, commands)
    file_ops.write_xml_to_file(updated_tree, output_path, machina_beautify=True)
    print(f"Combined xmls, output: {output_path}")
