import unittest
from pathlib import Path
from backend.analyzer import analyze, AnalysisError
from test_analyzer import walk


class ProgramTests(unittest.TestCase):
    def test_complete_store_and_connections(self):
        source = Path('examples/mini_store.py').read_text()
        result = analyze(source)
        nodes = list(walk(result.root))
        by_id = {n.id: n for n in nodes}
        self.assertEqual(result.root.kind, 'module')
        kinds = {n.kind for n in nodes}
        self.assertTrue({'function','parameter','for_loop','while_loop','if_statement',
                         'dictionary','list','tuple','set','import','call','lookup','return',
                         'class','method','try_statement','except_handler','with_statement',
                         'raise','comment','indentation','augmented_assignment'} <= kinds)
        self.assertEqual(sum(n.kind == 'for_loop' for n in nodes), 2)
        self.assertTrue(result.connections)
        for edge in result.connections:
            self.assertIn(edge.source_id, by_id)
            self.assertIn(edge.target_id, by_id)
            if edge.label.startswith('Possible'):
                self.assertEqual(by_id[edge.source_id].label, by_id[edge.target_id].label)
        for node in nodes:
            for child in node.children:
                self.assertLessEqual(node.span.start, child.span.start)
                self.assertGreaterEqual(node.span.end, child.span.end)
        # All meaningful characters are represented, not just large AST wrappers.
        coverage = set()
        for node in nodes:
            if not node.children or node.kind == 'string':
                coverage.update(range(node.span.start,node.span.end))
        self.assertTrue(all(i in coverage for i,c in enumerate(source) if not c.isspace()))

    def test_scope_shadowing(self):
        result = analyze('x = 1\ndef f(x):\n    return x\ny = f(x)')
        nodes = {n.id:n for n in walk(result.root)}
        use = next(n for n in nodes.values() if n.label == 'x' and n.span.start_line == 3)
        edges = [e for e in result.connections if e.target_id == use.id]
        self.assertEqual(len(edges), 1)
        self.assertEqual(nodes[edges[0].source_id].kind, 'parameter')

    def test_in_and_parentheses_have_context(self):
        result = analyze('def f(items):\n    for x in items:\n        if x in items:\n            print(x)\n    return 1')
        nodes = list(walk(result.root))
        ins = [n for n in nodes if n.label == 'in']
        self.assertTrue(any('iterable' in n.explanation for n in ins))
        self.assertTrue(any('membership' in n.explanation for n in ins))
        parens = [n for n in nodes if n.label == '(']
        self.assertTrue(any('parameter list' in n.explanation for n in parens))
        self.assertTrue(any('arguments for this call' in n.explanation for n in parens))

    def test_unimplemented_and_invalid_programs(self):
        for source in ['return 1', 'def f(*args):\n    return args', 'from math import *',
                       'x = [v for v in items]', 'print((1))', 'def f():\n    x = (1)']:
            with self.subTest(source=source), self.assertRaises(AnalysisError):
                analyze(source)

    def test_assignment_value_roles(self):
        for source, expected in [('prices = {"Milk": 2.99}', 'dictionary'), ('cart = ["Milk"]', 'list')]:
            node = analyze(source).root
            self.assertEqual(node.kind, 'assignment')
            self.assertIn(expected, node.explanation)
            self.assertIn('Assignment is the action', node.explanation)
        self.assertIn('does not infer', analyze('x = unknown()').root.explanation)
