import unittest
from backend.analyzer import analyze, AnalysisError
from test_analyzer import walk


class LoopTests(unittest.TestCase):
    def test_boolean_short_circuit_explanations_and_tokens(self):
        result = analyze('ready = not closed and cart or fallback')
        nodes = list(walk(result.root))
        operators = {n.label:n for n in nodes if n.kind == 'boolean_operator'}
        self.assertEqual(set(operators), {'not','and','or'})
        self.assertIn('always a Boolean', operators['not'].explanation)
        self.assertIn('returns that value', operators['and'].explanation)
        self.assertIn('Later parts may never run', operators['or'].explanation)
        for node in operators.values():
            self.assertEqual(result.source[node.span.start:node.span.end], node.label)

    def test_nearest_loop_connections(self):
        result = analyze('while ready:\n    for item in items:\n        if item:\n            continue\n        break\n    break')
        nodes = {n.id:n for n in walk(result.root)}
        controls = [e for e in result.connections if 'this loop' in e.label]
        self.assertEqual(len(controls),3)
        targets = [(nodes[e.source_id].kind,nodes[e.target_id].kind) for e in controls]
        self.assertEqual(targets,[('continue','for_loop'),('break','for_loop'),('break','while_loop')])
        loop = next(n for n in nodes.values() if n.kind == 'while_loop')
        self.assertIn('zero times',loop.explanation)
        self.assertTrue(loop.overview)

    def test_invalid_control_and_loop_else(self):
        for source in ['break','continue','def f():\n    break',
                       'while ready:\n    break\nelse:\n    print(1)']:
            with self.subTest(source=source), self.assertRaises(AnalysisError):
                analyze(source)
