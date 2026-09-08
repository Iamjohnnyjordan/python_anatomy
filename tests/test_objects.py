import unittest
from backend.analyzer import analyze
from test_analyzer import walk


class ObjectTests(unittest.TestCase):
    def test_class_instance_methods_defaults_and_keywords(self):
        source = 'class Store:\n    def __init__(self, name="Shop"):\n        self.name = name\n    def greet(self):\n        print(self.name)\nstore = Store(name="Mini")\nstore.greet()'
        result = analyze(source)
        nodes = list(walk(result.root))
        self.assertEqual(sum(n.kind == 'method' for n in nodes), 2)
        init = next(n for n in nodes if n.kind == 'method' and '__init__' in n.label)
        self.assertIn('does not itself create', init.explanation)
        receiver = next(n for n in nodes if n.kind == 'parameter' and n.label == 'self')
        self.assertIn('not a keyword', receiver.explanation)
        self.assertTrue(any(n.kind == 'keyword_argument_separator' for n in nodes))
        self.assertTrue(any(n.kind == 'default_value' for n in nodes))

    def test_method_skips_class_namespace_for_bare_names(self):
        result = analyze('name = "global"\nclass Store:\n    name = "class"\n    def read(self):\n        return name')
        nodes = {n.id:n for n in walk(result.root)}
        use = next(n for n in nodes.values() if n.kind == 'name' and n.label == 'name' and n.span.start_line == 5)
        edges = [e for e in result.connections if e.target_id == use.id]
        self.assertEqual(len(edges), 1)
        self.assertEqual(nodes[edges[0].source_id].span.start_line, 1)

    def test_object_member_connections(self):
        result = analyze('class C:\n    def f(self):\n        return 1\nobj = C()\nobj.f()')
        nodes = {n.id:n for n in walk(result.root)}
        edges = [e for e in result.connections if e.label.startswith('Possible member')]
        self.assertEqual(len(edges),1)
        self.assertEqual(nodes[edges[0].source_id].kind,'function_name')
        self.assertEqual(nodes[edges[0].target_id].kind,'attribute_name')
