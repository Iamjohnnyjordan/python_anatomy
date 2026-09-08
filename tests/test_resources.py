import unittest
from backend.analyzer import analyze, AnalysisError
from test_analyzer import walk


class ResourceTests(unittest.TestCase):
    def test_exceptions_files_imports_comments_indentation(self):
        source = 'from math import ceil as round_up\n# Receipt example\ntry:\n    with open("receipt.txt", "w", encoding="utf-8") as receipt:\n        receipt.write("Milk")\nexcept OSError as error:\n    print(error)\nelse:\n    print("Saved")\nfinally:\n    print("Finished")'
        result = analyze(source)
        nodes = list(walk(result.root))
        self.assertTrue({'import_alias','comment','indentation','try_statement','with_statement','except_handler','exception_branch'} <= {n.kind for n in nodes})
        self.assertTrue(any('file is closed' in n.explanation for n in nodes))
        for node in nodes:
            for child in node.children:
                self.assertLessEqual(node.span.start,child.span.start)
                self.assertGreaterEqual(node.span.end,child.span.end)
        comment = next(n for n in nodes if n.kind == 'comment')
        self.assertEqual(source[comment.span.start:comment.span.end], '# Receipt example')

    def test_raise_and_more_operators(self):
        for source in ['x = 7 // 2', 'x = 2 ** 3', 'x = 8 % 3', 'x = a is not None', 'x = 2\nx += 1', 'raise ValueError("No stock") from None']:
            with self.subTest(source=source):
                self.assertIsNotNone(analyze(source).root)

    def test_comments_are_not_code_and_continuation_indentation(self):
        result = analyze('# def not_a_function():\nx = [\n    "# text",\n    "Milk",\n]')
        nodes = list(walk(result.root))
        self.assertEqual(sum(n.kind == 'comment' for n in nodes),1)
        self.assertFalse(any(n.kind == 'function' for n in nodes))
        self.assertFalse(any(n.kind == 'indentation' for n in nodes))
