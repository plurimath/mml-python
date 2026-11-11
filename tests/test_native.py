import json
from pathlib import Path
import unittest
from xml.dom import Node, minidom

from mml import NativeError, parse, runtime_info

FIXTURES = Path(__file__).parent / "fixtures"


def xml_tree(text):
    def visit(element):
        attributes = sorted(
            (attribute.namespaceURI or "", attribute.localName, attribute.value)
            for attribute in element.attributes.values()
            if attribute.namespaceURI != "http://www.w3.org/2000/xmlns/"
        )
        has_elements = any(node.nodeType == Node.ELEMENT_NODE
                           for node in element.childNodes)
        children = []
        for node in element.childNodes:
            if node.nodeType == Node.ELEMENT_NODE:
                children.append(visit(node))
            elif node.nodeType == Node.TEXT_NODE:
                if has_elements and not node.data.strip():
                    continue
                children.append(["text", node.data])
            elif node.nodeType == Node.CDATA_SECTION_NODE:
                children.append(["cdata", node.data])
            elif node.nodeType == Node.COMMENT_NODE:
                children.append(["comment", node.data])
            elif node.nodeType == Node.PROCESSING_INSTRUCTION_NODE:
                children.append(["instruction", node.target, node.data])
        return [element.namespaceURI, element.localName, attributes, children]
    return visit(minidom.parseString(text).documentElement)


def compare_getters(test, expected, actual, names, counts):
    if isinstance(expected, dict) and "class" in expected:
        attributes = expected["attributes"]
        for key in set(actual) - set(attributes) - {"__lml_content"}:
            test.assertTrue(actual[key] is None or actual[key] in ([], {}, ""),
                            f"unexpected nonempty native field {key}")
        for key, value in attributes.items():
            compare_getters(test, value, actual[key], names, counts)
        if "__lml_content" in actual:
            order = []
            for token in actual["__lml_content"]:
                if token["kind"] == "element":
                    attribute = token["attribute"]
                    test.assertLess(token["index"], len(actual[attribute]))
                    order.append(["element", names[expected["class"]][attribute]])
                else:
                    text = token.get("literal")
                    if text is None:
                        text = actual[token["attribute"]][token["index"]]
                    order.append([token["kind"], text])
            test.assertEqual(order, expected["order"])
            counts["ordered_models"] += 1
        counts["models"] += 1
    elif isinstance(expected, list):
        test.assertEqual(len(actual), len(expected))
        for source, target in zip(expected, actual):
            compare_getters(test, source, target, names, counts)
    else:
        test.assertEqual(actual, expected)
        counts["leaf_values"] += 1


class NativeMathMLTest(unittest.TestCase):
    def test_native_xml_and_reused_handle(self):
        corpus = json.loads((FIXTURES / "native-xml-cases.json").read_text())
        for row in corpus["rows"]:
            with self.subTest(row["id"]):
                with parse(row["input"], version=row["version"],
                           model=row["model"]) as model:
                    first = model.snapshot()
                    self.assertIsInstance(first, dict)
                    self.assertEqual(xml_tree(model.to_xml()),
                                     xml_tree(row["expected_xml"]))
                    self.assertEqual(model.snapshot(), first)
                    with parse(model.to_xml(), version=row["version"],
                               model=row["model"]) as replay:
                        self.assertEqual(replay.snapshot(), first)
                    self.assertEqual(xml_tree(model.to_xml()),
                                     xml_tree(row["expected_xml"]))

    def test_source_getters_and_mixed_order(self):
        corpus = json.loads((FIXTURES / "native-xml-cases.json").read_text())
        oracles = json.loads((FIXTURES / "native-getter-oracle.json").read_text())
        expected = {row["id"]: row["snapshot"] for row in oracles["rows"]}
        names = json.loads((FIXTURES / "xml-member-names.json").read_text())
        counts = {"models": 0, "ordered_models": 0, "leaf_values": 0}
        for row in corpus["rows"]:
            with self.subTest(row["id"]):
                with parse(row["input"], version=row["version"],
                           model=row["model"]) as model:
                    compare_getters(self, expected[row["id"]], model.snapshot(),
                                    names, counts)
        self.assertGreater(counts["ordered_models"], 0)
        print("SOURCE_MODEL_COUNTS " + json.dumps(counts, sort_keys=True))

    def test_structured_xml_refusal_and_runtime_reuse(self):
        for version in (3, 4):
            for xml in ("<math", "<math xmlns='urn:foreign'><mi>x</mi></math>"):
                with self.subTest(version=version, xml=xml):
                    with self.assertRaises(NativeError) as failure:
                        parse(xml, version=version)
                    self.assertTrue(failure.exception.reason)
                    self.assertEqual(failure.exception.details["format"], "xml")
            with parse('<math xmlns="http://www.w3.org/1998/Math/MathML">'
                       '<mi>x</mi></math>', version=version) as model:
                self.assertEqual(model.snapshot()["mi_value"][0]["value"], ["x"])

    def test_ownership_and_close(self):
        for version in (3, 4):
            for _ in range(20):
                model = parse('<mi xmlns="http://www.w3.org/1998/Math/MathML">'
                              'x</mi>', version=version, model="Mi")
                self.assertEqual(model.snapshot()["value"], ["x"])
                model.close()
                model.close()
                with self.assertRaises(ValueError):
                    model.snapshot()
                with self.assertRaises(ValueError):
                    model.to_xml()
            with parse('<mi xmlns="http://www.w3.org/1998/Math/MathML">x</mi>',
                       version=version, model="Mi") as model:
                self.assertEqual(model.snapshot()["value"], ["x"])
            with self.assertRaises(ValueError):
                model.snapshot()

    def test_runtime_manifest_and_arguments(self):
        for version, count in ((3, 194), (4, 195)):
            info = runtime_info(version)
            self.assertEqual(info["version"], version)
            self.assertEqual(info["snapshot"], "mml-typed-model-snapshot-v1")
            self.assertEqual(info["model_manifest"]["versions"][str(version)]["models"],
                             count)
        for version in (0, 2, 5, True, "3"):
            with self.assertRaises(ValueError):
                parse("<math/>", version=version)
        with self.assertRaises(ValueError):
            parse("<math/>", model="unknown")
        with self.assertRaises(TypeError):
            parse(123)


if __name__ == "__main__":
    unittest.main()
