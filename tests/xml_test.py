import unittest
import xml.etree.ElementTree as ET

from pathlib import Path

import commod.helpers.parse_ops as parse_ops

XMLS_PATH = Path(__file__).parent / "assets"

class TestXmlHelperMethods(unittest.TestCase):
    def test_find_node(self):
        tree = parse_ops.xml_to_etree(XMLS_PATH / "property_tree.xml")
        repository = parse_ops.find_node(tree, "Repository")

        self.assertIsInstance(repository, ET.Element)
        self.assertEqual(repository.tag, "Repository")            

        difficulty = parse_ops.find_node(tree, "DifficultyLevels")
        first_level = parse_ops.find_node(difficulty, "Level")
        self.assertIsNone(parse_ops.find_node(difficulty, "NestedNodeName", do_not_warn=True))

        self.assertEqual(parse_ops.get_attrib(first_level, "Name"), "Easy")

        nonexistent_node = parse_ops.find_node(tree, "SomeName", do_not_warn=True)
        self.assertIsNone(nonexistent_node)

    def test_find_nodes(self):
        tree = parse_ops.xml_to_etree(XMLS_PATH / "property_tree.xml")
        difficulty = parse_ops.find_node(tree, "DifficultyLevels")
        all_levels = parse_ops.find_nodes(difficulty, "Level")
        self.assertIsInstance(all_levels, list)
        self.assertIsInstance(all_levels[0], ET.Element)
        
        level_elements = [level.tag for level in all_levels]
        self.assertEqual(len(level_elements), 2)
        self.assertEqual(set(level_elements), {"Level"})

        nonexistent_nodes = parse_ops.find_nodes(tree, "SomeName", do_not_warn=True)
        self.assertIsInstance(nonexistent_nodes, list)
        self.assertFalse(nonexistent_nodes)

    def test_get_attrib(self):
        tree = parse_ops.xml_to_etree(XMLS_PATH / "property_tree.xml")
        difficulty = parse_ops.find_node(tree, "DifficultyLevels")
        first_level = parse_ops.find_node(difficulty, "Level")
        self.assertEqual(parse_ops.get_attrib(first_level, "Name"), "Easy")
        self.assertEqual(parse_ops.get_attrib(first_level, "OtherName", do_not_warn=True), None)


if __name__ == "__main__":
    unittest.main()