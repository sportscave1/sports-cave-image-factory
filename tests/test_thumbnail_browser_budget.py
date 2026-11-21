"""Opt-in headless browser acceptance: synthetic images, all network blocked."""
from io import BytesIO
import os
import socket
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from crm_thumbnail_render import render
from tests.test_thumbnail_memory_budget import png


@unittest.skipUnless(os.getenv('THUMBNAIL_BROWSER_CHECKS') == '1', 'Opt-in installed browser check')
class ThumbnailBrowserTests(unittest.TestCase):
    def draw(self, size):
        data = BytesIO()
        with Image.new('RGB', size, 'red') as image:
            image.save(data, format='PNG')
        response = Mock(status_code=200, headers={'Content-Type': 'image/png'})
        response.iter_content.return_value = iter([data.getvalue()])
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        session = Mock()
        session.get.return_value = response
        html = '<html><body style="margin:0;background:white"><img src="https://cdn.shopify.com/s/files/fixture.png" style="width:600px;height:790px"></body></html>'
        original_connect = socket.socket.connect
        def loopback_only(sock, address):
            if isinstance(address, tuple) and address[0] in ('127.0.0.1', '::1'):
                return original_connect(sock, address)
            raise AssertionError('External network forbidden')
        with patch('requests.Session', return_value=session), \
                patch('crm_thumbnail_render.preview_document', side_effect=lambda doc: doc), \
                patch('crm_campaign_content.render_campaign', return_value={'html': html}), \
                patch('socket.socket.connect', loopback_only):
            result = render({}, {})
        session.get.assert_called_once()
        session.close.assert_called_once()
        response.__exit__.assert_called_once()
        with Image.open(BytesIO(result)) as image:
            self.assertEqual(image.size, (240, 316))
            return image.convert('RGB').getpixel((120, 158))

    def test_normal_image_reaches_browser(self):
        red, green, blue = self.draw((100, 100))
        self.assertGreater(red, 220)
        self.assertLess(green, 30)
        self.assertLess(blue, 30)

    def test_oversize_image_is_omitted_but_preview_completes(self):
        self.assertTrue(all(channel > 240 for channel in self.draw((2048, 2048))))


if __name__ == '__main__':
    unittest.main()
