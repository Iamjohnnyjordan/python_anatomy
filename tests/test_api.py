"""Exercise FastAPI's ASGI request boundary without a network server."""
import json
import unittest
from backend.main import app, health, mini_store_source


class ApiTests(unittest.IsolatedAsyncioTestCase):
    def test_health_check(self):
        self.assertEqual(health(), {'status': 'ok'})

    def test_guided_store_has_beginner_synopses(self):
        source = mini_store_source()
        self.assertIn('# Function: Calculate and return the total price', source)
        self.assertIn('# For loop: Visit every product key', source)
        self.assertIn('# Class: Define the data and behavior', source)

    async def request(self, payload):
        messages = []
        async def receive():
            return {'type': 'http.request', 'body': json.dumps(payload).encode(), 'more_body': False}
        async def send(message):
            messages.append(message)
        await app({'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                   'method': 'POST', 'scheme': 'http', 'path': '/analyze', 'raw_path': b'/analyze',
                   'query_string': b'', 'headers': [(b'content-type', b'application/json')],
                   'client': ('test', 1), 'server': ('test', 80), 'root_path': ''}, receive, send)
        return messages[0]['status'], json.loads(b''.join(m.get('body', b'') for m in messages[1:]))

    async def test_serialized_types(self):
        status, data = await self.request({'source': 'x = [True, 3, 2.5, None]'})
        self.assertEqual(status, 200)
        self.assertEqual(data['schema_version'], '0.5')
        items = [n for n in data['root']['children'][2]['children'] if n['kind'] == 'element']
        values = [n['children'][0]['value'] for n in items]
        self.assertEqual([type(v) for v in values], [bool, int, float, type(None)])

    async def test_validation_and_analysis_errors(self):
        for payload in [{'source': ''}, {'source': 'async def f(): pass'}, {'source': 'x = 1e999'}, {}]:
            status, data = await self.request(payload)
            self.assertEqual(status, 422)
            self.assertIn('detail', data)
