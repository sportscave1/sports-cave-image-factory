import hashlib
import html
import json
import re
import unittest
from copy import deepcopy
from unittest.mock import patch

import product_upload_recorder as recorder


class RecorderIdentityTests(unittest.TestCase):
    def marker(self, row, name="Example café", category="sport-1"):
        with patch.object(recorder.st, "html") as render:
            recorder.publish(row, name, {"id": category})
        markup = render.call_args.args[0]
        values = {k: html.unescape(v) for k, v in re.findall(r'data-([\w-]+)="([^"]*)"', markup)}
        expected = hashlib.sha256(json.dumps(json.loads(values['context']), sort_keys=True,
                                              separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        self.assertEqual(values['product-sha256'], expected)
        return values

    def test_ready_context_is_bound_to_every_product_field(self):
        row = {'id': 'workflow-1', 'data': {'source': {'content_hash': 'a'*64,
               'id': 'source-1', 'rev': 'revision-1'}, 'server_artwork': {'state': 'Ready'}}}
        first = self.marker(row)
        self.assertEqual(first['ready'], 'true')
        self.assertNotEqual(first['product-sha256'], self.marker(row, name='Other')['product-sha256'])
        self.assertNotEqual(first['product-sha256'], self.marker(row, category='sport-2')['product-sha256'])
        for field in ('content_hash', 'id', 'rev'):
            other = deepcopy(row)
            other['data']['source'][field] += '-changed'
            self.assertNotEqual(first['product-sha256'], self.marker(other)['product-sha256'])
        row['data']['server_artwork']['state'] = 'Preparing'
        self.assertEqual(self.marker(row)['ready'], 'false')


if __name__ == '__main__':
    unittest.main()
