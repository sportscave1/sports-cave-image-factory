import unittest,uuid
from desktop_recorder.contract import browser_identity,Invalid,permitted_origin
from urllib.parse import urlsplit
class ProductionOriginTests(unittest.TestCase):
    def test_only_exact_scoped_origins_and_identity_fields(self):
        value={'profile':str(uuid.uuid4()),'page':'','frame':'top','control':'id:example'}
        for origin in ('http://127.0.0.1:18962','http://127.0.0.1:18963','https://sports-cave-image-factory.onrender.com','https://sports-cave-image-factory.onrender.com:443','https://chatgpt.com','https://chatgpt.com:443'):
            browser_identity(dict(value,page=origin+'/?page=task_recorder'))
        for origin in ('http://sports-cave-image-factory.onrender.com','https://sports-cave-image-factory.onrender.com:444','https://evil.sports-cave-image-factory.onrender.com','https://sports-cave-image-factory.onrender.com.evil.test','https://user@sports-cave-image-factory.onrender.com','http://127.0.0.1:18964','https://example.com'):
            with self.subTest(origin=origin),self.assertRaises(Invalid):browser_identity(dict(value,page=origin+'/?page=task_recorder'))
        for suffix in ('/#fragment','/?secret=x','/?arbitrary=x'):
            with self.assertRaises(Invalid):browser_identity(dict(value,page='https://sports-cave-image-factory.onrender.com'+suffix))
        for origin in ('http://chatgpt.com','https://chatgpt.com:444','https://chatgpt.com.evil.test','https://user@chatgpt.com'):
            with self.subTest(origin=origin),self.assertRaises(Invalid):browser_identity(dict(value,page=origin+'/'))
        self.assertFalse(permitted_origin(urlsplit('https://chatgpt.com/download')))
        self.assertTrue(permitted_origin(urlsplit('https://chatgpt.com/'),chatgpt=True))
