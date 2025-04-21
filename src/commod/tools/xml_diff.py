import asyncio
from itertools import batched
import logging
import math
import time
from collections import Counter
from collections.abc import AsyncGenerator, Iterable, Iterator
from copy import deepcopy, copy
from dataclasses import dataclass
from enum import Enum
from functools import lru_cache, cached_property
from pathlib import Path

from lxml import objectify
from pydantic import BaseModel, computed_field, model_validator

from commod.helpers import file_ops, parse_ops
from commod.tools.xml_merge import ActionType, Command, InvalidMergeCommandError

# Some nodes use unique tag names, we can handle them safely if we know that.
# UNIQUE_TAGS = ["TargetNamesForDestroy", "params", "Files"]

# Some nodes can't be uniquely identified by their own attributes or tag.
# We note nodes then can be then uniquely adressed relative to their children here.
# NESTED_SIGNATURES = {
    # "Object": [("Post", ("ServerObjName", "LpName")),
            #    ("Post", ("NodesNameHierarchy", "LpName"))]
# }

# In some cases game engine can't guarantee a stable floating point precision for coordinates
# we note attributes that store coordinates and round them to 0.1 for a cleaner automatic diffs
# COORDINATES_TO_ROUND = {"Pos", "PostTiePos"}

# Keys represent tag of base node, values - list of expected children.
# At least one child tag from the list needs to be present to decide that parent is atomic.
# KNOWN_ATOMIC_NODES = {
#     "trigger": ("event", "script"),
#     "EntryPath": ("Point", "CameraPoint"),
#     "ExitPath": ("Point", "CameraPoint"),
#     "Polygon": ("Point"),
#     "DropOut": ("Point"),
#     "Wheels": ("Wheel"),
#     "Shape": ("object"),
#     "Animations": ("AnimationOnShow", "AnimationOnHide"),
#     "Path": ("Point"),
#     "Set": ("Item")
    # "Parts": ("Part"),
    # "MainPartDescription": ("PartDescription")
# }

logger = logging.getLogger("dem")

class NodeSignature(BaseModel):
    tag: str | None = None
    parent_tag: str | None = None
    unique_keys: list[str] | None = None
    significant_keys: list[str] | None = None
    insignificant_keys: list[str] | None = None
    ignored_keys: list[str] | None = None
    # other than being shortcut, also allows ignoring order and count of children
    children_tags: list[str] | None = None
    children: list["NodeSignature"] | None = None

    @model_validator(mode="after")
    def child_validation(self) -> "NodeSignature":
        if self.children_tags and self.children:
            raise AssertionError("Can't specify both children_tags and children for the same node!")
        # if self.children_tags and not self.unique_keys:
            # raise AssertionError("Atomic nodes must specify unique_keys")
        if self.children and any(child.unique_keys is None for child in self.children):
            raise AssertionError("Nested signatures' children must specify unique keys")
        if self.children and len(self.children) != 1:
            raise AssertionError("Nested signatures currently support only single child fingerprint")

        return self

    @computed_field
    @cached_property
    def node_type(self) -> "NodeType":
        if self.children:
            return NodeType.UNIQUE_NESTED

        if self.children_tags:
            return NodeType.ATOMIC

        if self.unique_keys:
            return NodeType.UNIQUE_KEYS

        if self.tag and not self.unique_keys and not self.parent_tag:
            return NodeType.UNIQUE_TAG

        return NodeType.NON_UNIQUE

    def is_matching(self, node: objectify.ObjectifiedElement) -> bool: # noqa: PLR0911
        if self.tag and self.tag != node.tag:
            return False
        if self.parent_tag:
            parent_node = node.getparent()
            if parent_node is None or self.parent_tag != parent_node.tag:
                return False
        if (self.unique_keys
           and not set(self.unique_keys) <= {key for key, value in node.attrib.items() if value}):
            return False
        if self.significant_keys and not set(self.significant_keys) <= set(node.attrib.keys()):
            return False
        if self.children_tags:
            node_child_tags = [child.tag for child in node.getchildren()]
            if not set(self.children_tags) <= set(node_child_tags):
                return False
        if self.children:
            if len(self.children) > node.countchildren():
                return False
            for i, child_sig in enumerate(self.children):
                if not child_sig.is_matching(node.getchildren()[i]):
                    return False

        return True


class InvalidDiffError(Exception):
    ...

class IncorrectSelectorError(Exception):
    ...

class IncorrectDiffGuideError(Exception):
    ...

class Change(Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    NONE = "none"

class NodeType(Enum):
    UNIQUE_KEYS =   "UniqueKeys"
    UNIQUE_TAG =    "UniqueTag"
    ATOMIC =        "UniqueAtomic"
    UNIQUE_NESTED = "UniqueNested"
    NON_UNIQUE =    "NonUnique"

@dataclass
class Diff:
    change_type: Change
    xpath: str = ""
    parent_xpath: str = ""
    source: objectify.ObjectifiedElement | None = None
    result: objectify.ObjectifiedElement | None = None


class DiffGuide(BaseModel):
    root_tag: str
    unique_signatures: list[NodeSignature] = []
    non_unique_signatures: list[NodeSignature] = []
    float_list_to_round: list[str] = []

    @computed_field
    @cached_property
    def signatures_dict(self) -> dict[str | None, list[NodeSignature]]:
        all_sigs = []
        all_sigs.extend(self.unique_signatures)
        all_sigs.extend(self.non_unique_signatures)

        sig_dict = {node.tag: [] for node in all_sigs}
        for tag_name, val in sig_dict.items():
            val.extend([node for node in all_sigs
                if node.tag is None or node.tag == tag_name])
        return sig_dict

    def get_signatures_for_tag(self, tag: str) -> list[NodeSignature]:
        if tag in self.signatures_dict:
            return self.signatures_dict[tag]
        return self.signatures_dict.get(None, [])

class Differ:
    def __init__(self, diff_guide: DiffGuide) -> None:
        self.diff_guide = diff_guide

    @staticmethod
    def describe_diff(
        left_node: objectify.ObjectifiedElement | None,
        right_node: objectify.ObjectifiedElement | None) -> Diff:

        if left_node is None and right_node is not None:
            change = Change.ADDED
            source_node = right_node
        elif right_node is None and left_node is not None:
            change = Change.REMOVED
            source_node = left_node
        elif left_node is not None and right_node is not None:
            change = Change.MODIFIED
            source_node = right_node
        else:
            raise InvalidDiffError("Nothing to diff, nodes haven't been provided!")

        selector = source_node.get("_Selector")
        parent_xpath = source_node.get("_ParentXPath") or ""

        if selector is None:
            raise InvalidDiffError("Can't produce diff without selector")

        return Diff(change, selector, parent_xpath, left_node, right_node)

    @staticmethod
    def get_child_fingerprint(node: objectify.ObjectifiedElement) -> str:
        children_hash = ""
        for child in node.getchildren():
            significant_attribs = [(k, v) for k, v in child.attrib.items() if not k.startswith("_")]
            child_hash = str(child.tag) + str(sorted(significant_attribs, key=lambda d: d[0]))
            if child.text:
                # ignoring whitespace and comments, currently tuned to increase uniqueness check for triggers
                child_hash += "\n".join([line.strip() for line in child.text.strip().split()
                                         if not line.strip().startswith("--")])
            children_hash += child_hash
            if child.countchildren():
                children_hash += "".join(Differ.get_child_fingerprint(child))
        return children_hash

    @staticmethod
    def get_child_hash(node: objectify.ObjectifiedElement) -> str:
        children_hash = node.get("_ChildrenHash") or ""
        if children_hash:
            return children_hash

        fingerprint = ""
        subchildren_hashes = []
        for child in node.getchildren():
            significant_attribs = [(k, v) for k, v in child.attrib.items() if not k.startswith("_")]
            child_fingerprint = str(child.tag) + str(sorted(significant_attribs, key=lambda d: d[0]))
            if child.text:
                # ignoring whitespace and comments, currently tuned to increase uniqueness check for triggers
                child_fingerprint += "\n".join([line.strip() for line in child.text.strip().split()
                                                if not line.strip().startswith("--")])
            fingerprint += child_fingerprint
            if child.countchildren():
                subchildren_hashes.append(Differ.get_child_hash(child))
        if fingerprint:
            children_hash = "".join([str(hash(fingerprint)), *subchildren_hashes])
            node.set("_ChildrenHash", children_hash)
        return children_hash

    @staticmethod
    def generate_selector_by_tag(node: objectify.ObjectifiedElement) -> str:
        return str(node.tag)

    @staticmethod
    def generate_selector_by_attr(node: objectify.ObjectifiedElement,
                                  unique_keys: Iterable[str] | None = None) -> str:
        if unique_keys:
            significant_attrs = [(key, val) for key, val in node.attrib.items()
                                 if key in unique_keys]
        else:
            significant_attrs = [(key, val) for key, val in node.attrib.items()
                                 if not key.startswith("_")]

        selector = "".join(f"[@{key}='{value.replace("'", "&apos;").replace('"', "&quot;")}']"
                           for key, value in significant_attrs)
        return f"{node.tag}{selector}"

    def get_selector_nested(self, node: objectify.ObjectifiedElement,
                            signature: NodeSignature) -> str:
        # Object[Post[1][@ServerObjName="stolb1"] and Post[2][@ServerObjName="stolb2"]]
        if not signature.children:
            raise IncorrectDiffGuideError("Nested unique must contain children!")

        child_tag = signature.children[0].tag
        unique_keys = signature.children[0].unique_keys
        if unique_keys is None:
            raise IncorrectDiffGuideError("Nested signatures must specify unique keys")

        keys_selector = "".join(f"[@{unique_key}]" for unique_key in unique_keys)
        all_child_selector = f"{child_tag}{keys_selector}"
        children = node.xpath(all_child_selector)

        if not children:
            raise IncorrectDiffGuideError("Nested unique node must contain children!")

        sub_selectors = []
        for i, child in enumerate(children):
            attrib_selectors = []
            for unique_key in unique_keys:
                unique_key_val = child.get(unique_key)
                if unique_key_val:
                   attrib_selectors.append(f"[@{unique_key}='{unique_key_val.replace("'", "&apos;").replace('"', "&quot;")}']")

            if len(attrib_selectors) == len(unique_keys):
                child_selector = "".join(attrib_selectors)
                sub_selectors.append(f"{child_tag}[{i + 1}]{child_selector}")
        if not sub_selectors:
            raise IncorrectDiffGuideError("Couldn't create nested selector from signature provided")

        return f"{node.tag}[{' and '.join(sub_selectors)}]"


    # def is_atomic(self, node: objectify.ObjectifiedElement) -> bool:
    #     """Determine if the node is non-divisible unit of comparison.

    #     For atomic nodes we never produce partial changes (MODIFY), and never process them
    #     separately from their children, and otherwise - don't process children separately.
    #     Instead of MODIFY command we utilize ADD_OR_REPLACE for them.

    #     This is done to reduce a chance on user error when creating merge mods.
    #     """
    #     atomic_signature = self.diff_guide.atomic_nodes_dict.get(str(node.tag))
    #     if atomic_signature is None:
    #         return False

    #     if atomic_signature.children is not None:
    #         child_tags = [child.tag for child in atomic_signature.children]
    #     elif atomic_signature.children_tags:
    #         child_tags = atomic_signature.children_tags
    #     else:
    #         raise IncorrectDiffGuideError("Atomic signatures must specify child tags")

    #     return any(child.tag in child_tags for child in node.getchildren())

    def get_selector_non_unique(self, node: objectify.ObjectifiedElement,
                            signature: NodeSignature) -> str:
        if signature.significant_keys:
            significant_attrs = [(key, val) for key, val in node.attrib.items()
                                 if key in signature.significant_keys]
        else:
            significant_attrs = [(key, val) for key, val in node.attrib.items()
                                 if not key.startswith("_")]

        selector = "".join(f"[@{key}='{value.replace("'", "&apos;").replace('"', "&quot;")}']"
                           for key, value in significant_attrs)
        return f"{node.tag}{selector}"

    def generate_selector_by_signature(
            self, node: objectify.ObjectifiedElement,
            sig: NodeSignature) -> str:
        match sig.node_type:
            # case NodeType.ATOMIC:
                # return self.generate_selector_by_attr(node, sig.unique_keys)
            case NodeType.UNIQUE_KEYS | NodeType.ATOMIC:
                return self.generate_selector_by_attr(node, sig.unique_keys)
            case NodeType.UNIQUE_TAG:
                return self.generate_selector_by_tag(node)
            case NodeType.UNIQUE_NESTED:
                return self.get_selector_nested(node, sig)
            case NodeType.NON_UNIQUE:
                return self.get_selector_non_unique(node, sig)
            case _:
                raise NotImplementedError("Unknown selector type")

    def generate_selector(
            self, node: objectify.ObjectifiedElement) -> tuple[str, NodeSignature | None]:
        unique_sigs = self.diff_guide.get_signatures_for_tag(str(node.tag))
        for sig in unique_sigs:
            if sig.is_matching(node):
                return self.generate_selector_by_signature(node, sig), sig

        return self.generate_selector_by_attr(node), None


    @staticmethod
    def serialize_command(command: Command, keep_attrs: list[str] | None = None) -> objectify.ObjectifiedElement:
        keep_attrs = keep_attrs if keep_attrs is not None else []
        cmd_node = objectify.Element(command.tag)
        cmd_node.set("_Action", command.action.value)

        if command.parent_path:
            cmd_node.set("_ParentXPath", command.parent_path)

        if command.selector_keys:
            cmd_node.set("_SelectorKeys", ",".join(command.selector_keys))
        else:
            cmd_node.set("_Selector", command.selector)

        if command.desired_count != 1:
            cmd_node.set("_DesiredCount", str(command.desired_count))

        for k, v in command.node_attrs.items():
            if not k.startswith("_") and k not in keep_attrs:
                cmd_node.set(k, v)

        if command.children_nodes:
            cmd_node.extend(command.children_nodes)
        return cmd_node

    @staticmethod
    def serialize_commands(commands: list[Command], root_tag: str) -> objectify.ObjectifiedElement:
        root = objectify.Element(root_tag)

        for command in commands:
            cmd_node = Differ.serialize_command(command)
            root.append(cmd_node)

        objectify.deannotate(root, cleanup_namespaces=True)
        return root

    @staticmethod
    def annotate_float_list_attr(node: objectify.ObjectifiedElement,
                                 float_list_attribs: Iterable[str]) -> objectify.ObjectifiedElement:
        for attrib_name in float_list_attribs:
            if not (val := node.get(attrib_name)):
                continue

            parts = val.split()
            if len(parts) not in (3, 4):
                continue

            # cast to float to check will allow "infinity", "100e-1" etc. to pass, invalid here
            if not all(part.removeprefix("-").replace(".", "", 1).isdigit() for part in parts):
                continue

            node.set(f"_{attrib_name}", val)
            parts = [round(float(part), 1) for part in parts]
            annotated_attrib = " ".join([str(part) if part != -0.0 else "0.0" for part in parts])
            node.set(attrib_name, annotated_attrib)

        return node

    @staticmethod
    def cleanup_temp_attributes(
        node: objectify.ObjectifiedElement,
        floatl_attribs: Iterable[str],
        keep_attrs: list[str] | None = None) -> objectify.ObjectifiedElement:
        keep_attrs = keep_attrs if keep_attrs is not None else []
        for key in node.attrib:
            if key.startswith("_") and key not in keep_attrs:
                val = node.attrib.pop(key)
                if (node_name := key.removeprefix("_")) in floatl_attribs:
                    node.set(node_name, val)
        for child in node.getchildren():
            Differ.cleanup_temp_attributes(child, floatl_attribs)
        return node

    @staticmethod
    def annotate_float_lists(node: objectify.ObjectifiedElement,
                             float_list_attribs: Iterable[str]) -> objectify.ObjectifiedElement:
        if node.attrib:
            # calculates the set of coordinate attribs that node has
            if coord_attrib := set(node.attrib) & set(float_list_attribs):
                Differ.annotate_float_list_attr(node, coord_attrib)
                ...

        return node

    @staticmethod
    def float_list_is_close(first_list: str, second_list: str) -> bool:
        first_parts = first_list.split()
        second_parts = second_list.split()

        if len(first_parts) != len(second_parts):
            return False

        if (not all(part.removeprefix("-").replace(".", "", 1).isdigit() for part in first_parts)
           or not all(part.removeprefix("-").replace(".", "", 1).isdigit() for part in second_parts)):
            return False

        f_parts_float = [float(part) for part in first_parts]
        s_parts_float = [float(part) for part in second_parts]

        return all(math.isclose(f_parts_float[i], s_parts_float[i], abs_tol=0.05)
                   for i in range(len(f_parts_float)))



    def annotate_tree(self, tree: objectify.ObjectifiedElement,
                      unique_keys: Iterable[str] | None = None,
                      parent_selector: str | None = None) -> objectify.ObjectifiedElement:
        # if unique_keys is None:
            # unique_keys = self.diff_guide.primary_unique_keys

        for node in tree.getchildren():
            if node.tag == "comment" or node.get("_Duplicate"):
                tree.remove(node)
                continue

            if node.get("_NodeType") is not None:
                # already annotated
                continue

            # we use two separate code paths to handle rounding errors in some float vectors/lists
            # 1) in case of shallow nodes (here), we directly compare closeness of these attributes for nodes
            # For that we specify list of attributes that require this type of comparison in _FloatLists
            # 2) in case of nested nodes, as we compare those by child hashes,
            # we first annotate lists by rounding them, thus helping produce more similar child hashes
            # Later we deanotate these lists, returning original, non rounded lists for the final command
            # See logic below for ATOMIC and UNIQUE_NESTED
            if coord_attrib := set(node.attrib) & set(self.diff_guide.float_list_to_round):
                node.set("_FloatLists", ",".join(coord_attrib))

            if parent_selector:
                node.set("_ParentXPath", parent_selector)
            selector, signature = self.generate_selector(node)
            if signature and signature.node_type == NodeType.NON_UNIQUE:
                if signature.ignored_keys:
                    for key in signature.ignored_keys:
                        if node.get(key):
                            node.attrib.pop(key)

                matching_nodes = tree.xpath(selector)
                node.set("_DuplicateCount", str(len(matching_nodes)))
                for matching_node in matching_nodes:
                    matching_node.set("_Duplicate", "True")

            node_type = signature.node_type if signature else NodeType.NON_UNIQUE

            node.set("_Selector", selector)
            if signature:
                if signature.unique_keys:
                    node.set("_SelectorKeys", ",".join(signature.unique_keys))
                elif signature.significant_keys:
                    node.set("_SelectorKeys", ",".join(signature.significant_keys))
            node.set("_NodeType", node_type.value)

            if node_type in [NodeType.ATOMIC, NodeType.UNIQUE_NESTED]:
                for child in node.getchildren():
                    # required explicitly because _ChildrenHash will change based on the annotation
                    self.annotate_float_lists(child, self.diff_guide.float_list_to_round)
                node.set("_ChildrenHash", self.get_child_hash(node))
            else:
                full_parent_selector = f"{parent_selector}/{selector}" if parent_selector else selector
                self.annotate_tree(node, unique_keys, full_parent_selector)

        return tree

    @staticmethod
    def are_equivalent_nodes(first_node: objectify.ObjectifiedElement,
                             second_node: objectify.ObjectifiedElement) -> bool:

        if first_float_list := first_node.get("_FloatLists"):
            first_node_float_list_attrs = {key:val for key,val in first_node.attrib.items()
                                           if key in first_float_list.split(",")}
        else:
            first_node_float_list_attrs = {}

        if second_float_list := second_node.get("_FloatLists"):
            second_node_float_list_attrs = {key:val for key,val in second_node.attrib.items()
                                            if key in second_float_list.split(",")}
        else:
            second_node_float_list_attrs = {}

        if first_node_float_list_attrs.keys() != second_node_float_list_attrs.keys():
            return False

        float_lists_are_close = all(
            Differ.float_list_is_close(val, second_node_float_list_attrs[key])
            for key, val in first_node_float_list_attrs.items())

        if not float_lists_are_close:
            return False

        if first_node.get("_DuplicateCount") != second_node.get("_DuplicateCount"):
            return False

        first_node_attrs = {key:val for key,val in first_node.attrib.items()
                            if not key.startswith("_") and key not in first_node_float_list_attrs}
        second_node_attrs = {key:val for key,val in second_node.attrib.items()
                             if not key.startswith("_") and key not in second_node_float_list_attrs}

        first_node_text = first_node.text.replace("\n", "").strip() if first_node.text is not None else ""
        second_node_text = second_node.text.replace("\n", "").strip() if second_node.text is not None else ""

        first_children_hash = first_node.get("_ChildrenHash")
        second_children_hash = second_node.get("_ChildrenHash")

        return all([
            first_node.tag == second_node.tag,
            first_node_attrs == second_node_attrs,
            first_node_text == second_node_text,
            first_children_hash == second_children_hash,
            ])

    @staticmethod
    def get_annotated_selector(node: objectify.ObjectifiedElement) -> str:
        selector = node.get("_Selector")
        if not selector:
            raise IncorrectSelectorError
        return selector

    @staticmethod
    def parse_diffs(base_tree: objectify.ObjectifiedElement,
                    modded_tree: objectify.ObjectifiedElement) -> Iterator[Diff]:
        for right_node in modded_tree.getchildren():
            selector = Differ.get_annotated_selector(right_node)
            try:
                matching_base_nodes = base_tree.xpath(selector)
            except Exception as ex:
                ...

            left_node = matching_base_nodes[0] if matching_base_nodes else None

            if left_node is not None and Differ.are_equivalent_nodes(left_node, right_node):
                if left_node.get("_NodeType") not in [NodeType.ATOMIC.value, NodeType.UNIQUE_NESTED.value]:
                    for diff in Differ.parse_diffs(left_node, right_node):
                        yield diff
                base_tree.remove(left_node)
                modded_tree.remove(right_node)
                yield Diff(change_type=Change.NONE)
                continue

            if len(matching_base_nodes) > 1:
                # TODO
                logger.warning(f"Multiple matching nodes found for selector '{selector}'")

            diff = Differ.describe_diff(left_node, right_node)
            modded_tree.remove(right_node)

            if left_node is not None:
                base_tree.remove(left_node)

            yield diff

        for left_node in base_tree.getchildren():
            selector = Differ.get_annotated_selector(left_node)
            matching_modded_nodes = modded_tree.xpath(selector)

            if len(matching_modded_nodes) == 1:
                raise ValueError("Debug: unexpected result, matching node should have been proccessed earlier!")

            if len(matching_modded_nodes) > 1:
                raise ValueError("Debug: unexpected result, matching node should have been proccessed earlier!")
                # TODO
                # logger.warning(f"Multiple matching nodes found for selector '{selector}'")
                # continue

            diff = Differ.describe_diff(left_node, None)
            yield diff

        # return diffs

    def calculate_diff(self,
                       base_tree: objectify.ObjectifiedElement,
                       modded_tree: objectify.ObjectifiedElement,
                       unique_keys: Iterable[str] | None = None) -> Iterator[Command | None]:
        # if unique_keys is None:
            # unique_keys = self.diff_guide.primary_unique_keys

        if base_tree.tag != modded_tree.tag:
            raise InvalidMergeCommandError(
                "Can't produce diff for trees with different root tags: "
                f"'{base_tree.tag}' vs '{modded_tree.tag}'")

        start = time.perf_counter()
        base_tree = self.annotate_tree(base_tree)
        modded_tree = self.annotate_tree(modded_tree)
        logger.debug(f"Annotated trees in "
              f"{round(time.perf_counter() - start, 3)} seconds")

        # file_ops.write_xml_to_file(base_tree, DESKTOP / "base.xml", machina_beautify=True, use_utf=False)
        # file_ops.write_xml_to_file(modded_tree, DESKTOP / "modded.xml", machina_beautify=True, use_utf=False)
        # return

        for diff in self.parse_diffs(base_tree, modded_tree):
            yield self.generate_command_from_diff(diff)

    def generate_command_from_diff(self, diff: Diff) -> Command | None:
        start = time.perf_counter()
        if diff.change_type == Change.NONE:
            return None

        primary_node = diff.source if diff.change_type is Change.REMOVED else diff.result
        if primary_node is None:
            raise InvalidDiffError("Missmatch of diff type and it's nodes, primary is missing!"
                                   f"{diff}")

        node_type = primary_node.get("_NodeType")
        selector_keys_attr = primary_node.get("_SelectorKeys")
        selector_keys = selector_keys_attr.split(",") if selector_keys_attr else []
        attr_list = []
        desired_count = 1
        children = None

        if node_type == NodeType.UNIQUE_KEYS.value:
            attr_list.extend(selector_keys)

        if diff.change_type is Change.ADDED:
            action = ActionType.ADD
            if node_type == NodeType.NON_UNIQUE.value:
                # if primary_node.getchildren():
                    # raise IncorrectDiffGuideError("Non unique nodes can't have child nodes!")
                action = ActionType.ADD_OR_REPLACE
                attr_list.extend([attr for attr in primary_node.attrib
                                  if not attr.startswith("_")
                                  and attr not in attr_list])
                desired_count = primary_node.get("_DuplicateCount", "1")
                if not desired_count.isnumeric():
                    raise InvalidDiffError(
                        f"Desired count must be numeric instead of {desired_count}!"
                        f"({primary_node.tag}[{primary_node.attrib}])")
                desired_count = int(desired_count)
            else:
                attr_list.extend([attr for attr in primary_node.attrib
                                  if not attr.startswith("_")
                                  and attr not in attr_list])
            children = diff.result.getchildren()

        elif diff.change_type is Change.REMOVED:
            action = ActionType.REMOVE
            children = None
            attr_list.extend([attr for attr in primary_node.attrib
                              if attr in selector_keys
                              and attr not in attr_list])
        else:
            if diff.source is None or diff.result is None:
                raise InvalidDiffError(
                    f"Missmatch for modified diff, one of nodes is missing!"
                    f"({primary_node.tag}[{primary_node.attrib}])")

            significant_attrs_source = [attr for attr, val in diff.source.attrib.items()
                                       if not attr.startswith("_") and val
                                       and attr not in selector_keys]
            significant_attrs_result = [attr for attr, val in diff.result.attrib.items()
                                        if not attr.startswith("_") and val
                                        and attr not in selector_keys]
            removes_keys = set(significant_attrs_source) > set(significant_attrs_result)

            equivalent_children = False
            has_children = primary_node.countchildren()

            if has_children:
                equivalent_children = self.get_child_hash(diff.source) == self.get_child_hash(diff.result)

            if (node_type == NodeType.ATOMIC.value
                or removes_keys
                or (has_children and not equivalent_children)):

                action = ActionType.ADD_OR_REPLACE
                attr_list.extend([attr for attr in primary_node.attrib
                                  if not attr.startswith("_")
                                  and attr not in attr_list])
                children = primary_node.getchildren()
            elif node_type == NodeType.NON_UNIQUE.value:
                # if primary_node.getchildren():
                    # raise IncorrectDiffGuideError("Non unique nodes can't have child nodes!")
                action = ActionType.ADD_OR_REPLACE
                attr_list.extend([attr for attr in primary_node.attrib
                                  if not attr.startswith("_")
                                  and attr not in attr_list])
                desired_count = primary_node.get("_DuplicateCount", "1")
                if not desired_count.isnumeric():
                    raise InvalidDiffError(
                        f"Desired count must be numeric instead of {desired_count}!"
                        f"({primary_node.tag}[{primary_node.attrib}])")
                desired_count = int(desired_count)
                children = primary_node.getchildren()
            else:
                action = ActionType.MODIFY
                attr_list.extend([attr for attr, val in diff.result.attrib.items()
                                  if not attr.startswith("_") and diff.source.get(attr) != val
                                  and attr not in attr_list])
                children = None

        tag = str(primary_node.tag)

        parent_path = primary_node.get("_ParentXPath") or ""
        selector = self.get_annotated_selector(primary_node)

        self.cleanup_temp_attributes(primary_node, self.diff_guide.float_list_to_round,
                                     ["_DuplicateCount"])

        if diff.source is not None:
            source = self.cleanup_temp_attributes(copy(diff.source),
                                                  self.diff_guide.float_list_to_round,
                                                  ["_DuplicateCount"])
        else:
            source = None

        if diff.result is not None:
            result = self.cleanup_temp_attributes(copy(diff.result),
                                                  self.diff_guide.float_list_to_round)
        else:
            result = None

        attr_dict = {attr: primary_node.get(attr) for attr in attr_list}
        selector_keys = selector_keys if all(key in attr_dict for key in selector_keys) else []
        if selector_keys and set(selector_keys) == set(attr_dict.keys()) and len(selector_keys) != 1:
            selector_keys = ["*"]
        end = time.perf_counter()

        if (end - start) > 0.01:
            logger.debug(f"Generated command from diff in "
                  f"{round(end - start, 3)} seconds")

        return Command(
            action=action,
            parent_path=parent_path,
            selector=selector,
            tag=tag,
            node_attrs=attr_dict,
            selector_keys=selector_keys,
            children_nodes=children,
            source_node=source,
            modded_node=result,
            desired_count=desired_count)

def create_xml_diff(base_path: Path, modded_path: Path, output_path: Path,
                    differ: Differ | None = None) -> None:
    base_tree = parse_ops.xml_to_objfy(base_path)
    modded_tree = parse_ops.xml_to_objfy(modded_path)

    differ = Differ(DiffGuide(root_tag=str(base_tree.tag))) if differ is None else differ

    start = time.perf_counter()
    commands = differ.calculate_diff(base_tree, modded_tree)

    list_of_commands = []
    for batch in batched(commands, 25):
        list_of_commands.extend([cmd for cmd in batch if cmd is not None])
    logger.debug(f"Calculated diffs in "
          f"{round(time.perf_counter() - start, 3)} seconds")

    start = time.perf_counter()
    commands_xml = Differ.serialize_commands(list_of_commands, root_tag=str(base_tree.tag))
    logger.debug(f"Serialized commands in "
          f"{round(time.perf_counter() - start, 3)} seconds")

    # file_ops.write_xml_to_file(commands_xml, output_path, machina_beautify=True, use_utf=False)

