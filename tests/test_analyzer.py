import unittest
from backend.analyzer import analyze, AnalysisError


def walk(node):
    yield node
    for child in node.children:
        yield from walk(child)


class AnalyzerTests(unittest.TestCase):
    def test_structure_and_punctuation(self):
        result = analyze('products = ["Milk", "Bread", "Eggs"]')
        nodes = list(walk(result.root))
        self.assertEqual([n.value for n in nodes if n.kind == 'string'], ['Milk', 'Bread', 'Eggs'])
        self.assertEqual(len([n for n in nodes if n.kind == 'quote']), 6)
        self.assertEqual(len([n for n in nodes if n.kind == 'separator']), 2)
        self.assertEqual([n.kind for n in result.root.children], ['name', 'assignment_operator', 'list'])

    def test_unicode_and_multiline_positions(self):
        source = 'café = [\n "🥛",\n "Bread",\n]'
        result = analyze(source)
        for node in walk(result.root):
            fragment = source[node.span.start:node.span.end]
            self.assertTrue(fragment)
            if node.kind in ('name', 'string', 'quote', 'separator', 'list_delimiter', 'assignment_operator'):
                self.assertEqual(fragment, node.label)
        self.assertEqual(result.root.children[0].label, 'café')

    def test_empty_and_escaped(self):
        self.assertEqual(analyze('x = []').root.children[2].label, 'List')
        strings = [n for n in walk(analyze(r'''x = ["a\"b", 'c']''').root) if n.kind == 'string']
        self.assertEqual(strings[0].value, 'a"b')

    def test_unsupported_and_invalid(self):
        for source in ['x = [v for v in data]', 'a = b = []', 'x = [',
                       'x = ["a" "b"]', 'x = [r"a"]', 'x = [("a")]',
                       'x = f"a"']:
            with self.subTest(source=source), self.assertRaises(AnalysisError):
                analyze(source)

    def test_basic_values_keep_their_types(self):
        for source, kind, value in [('x = 3', 'integer', 3), ('x = 2.99', 'float', 2.99),
                                    ('x = True', 'boolean', True), ('x = False', 'boolean', False),
                                    ('x = None', 'none', None), ('x = "Milk"', 'string', 'Milk')]:
            with self.subTest(source=source):
                node = analyze(source).root.children[2]
                self.assertEqual(node.kind, kind)
                self.assertIs(type(node.value), type(value))
                self.assertEqual(node.value, value)
                self.assertIn('variable name', analyze(source).root.children[0].explanation)

    def test_collections_and_nesting(self):
        for source, kind in [('x = ()', 'tuple'), ('x = (1,)', 'tuple'), ('x = 1, 2', 'tuple'),
                             ('x = {}', 'dictionary'), ('x = {1, 2, 1}', 'set'),
                             ('x = {"Milk": [2.99, None], "available": True}', 'dictionary')]:
            with self.subTest(source=source):
                result = analyze(source)
                self.assertEqual(result.root.children[2].kind, kind)
                nodes = list(walk(result.root))
                self.assertEqual(len(nodes), len({n.id for n in nodes}))
                for parent in nodes:
                    for child in parent.children:
                        self.assertLessEqual(parent.span.start, child.span.start)
                        self.assertGreaterEqual(parent.span.end, child.span.end)
                # Every non-whitespace character belongs to a visible syntax piece.
                structural = {'assignment', 'list', 'tuple', 'dictionary', 'set', 'entry', 'element', 'signed_number'}
                covered = set()
                for n in nodes:
                    if n.kind not in structural:
                        covered.update(range(n.span.start, n.span.end))
                self.assertTrue(all(i in covered for i, c in enumerate(source) if not c.isspace()))

    def test_contextual_separators(self):
        nodes = list(walk(analyze('x = {"a": (1,)}').root))
        colon = next(n for n in nodes if n.kind == 'key_value_separator')
        self.assertIn('dictionary entry', colon.explanation)
        comma = next(n for n in nodes if n.kind == 'separator')
        self.assertIn('single item needs a comma', comma.explanation)
        items = [n for n in walk(analyze('x = {1, 1}').root) if n.kind == 'element']
        self.assertTrue(all('sets have no indexes' in n.explanation for n in items))

    def test_signed_numbers(self):
        result = analyze('balance = -2.5')
        signed = result.root.children[2]
        self.assertEqual(signed.kind, 'signed_number')
        self.assertEqual(signed.children[0].label, '-')
        self.assertEqual(signed.children[1].value, 2.5)

    def test_invalid_values_and_limits(self):
        for source in ['x = {[1]}', 'x = {[1]: 2}', 'x = {(1, []): 2}', 'x = 1e999',
                       'x = (1)', 'x = ((1), 2)', 'x = b"abc"', 'x = 2j',
                       'x = {**other}', 'x = [*other]', 'x = -True', 'x = ...',
                       'x = ' + '[' * 15 + '1' + ']' * 15, 'x = [' + '1,' * 800 + ']']:
            with self.subTest(source=source), self.assertRaises(AnalysisError):
                analyze(source)


if __name__ == '__main__':
    unittest.main()
