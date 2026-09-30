"""Offline HTML reader fixture. No real mail operations; HTTPS fixture image is public."""
from pathlib import Path
source_path=Path(__file__).with_name('email_desktop_preview.py')
source=source_path.read_text(encoding='utf-8').replace('super().__init__(75)', '''super().__init__(4)
        self.messages[-1].update(folder='INBOX.Sent Items',subject='Sent HTML fixture')
        self.messages[-2].update(subject='HTML review with inline and remote images')''')
a=source.index('    def read_message(self, message):');b=source.index('    def related_headers_many(',a)
source=source[:a]+'''    def read_message(self, message):
        time.sleep(0.6)
        result=super().read_message(message)
        if message['uid'] in {'3','4'}:
            from support_email_signatures import logo_data_uri
            result['html']='<table width="600" align="center" style="background-color:#fffaf0;padding:18px;font-family:Georgia"><tr><td><img src="cid:logo" width="56"><h2>Your Sports Cave review</h2><p><b><i>Mark James</i></b></p><p><b>Happy</b><br><i>I am more than happy with my purchase</i></p><ul><li>Premium artwork</li><li>Carefully framed</li></ul><a href="https://example.test/product">View product</a><p>Public remote image fixture:</p><img src="https://www.python.org/static/community_logos/python-logo.png" width="300"><img src="cid:missing" alt="Missing image fallback"></td></tr></table><script>throw new Error("UNSAFE")</script>'
            result['inline_images']={'logo':logo_data_uri()}
            result['text']='Mark James\\nHappy\\nI am more than happy with my purchase'
        return result

'''+source[b:]
source=source.replace('if not state.get("loaded"): w.load()', 'if not state.get("loaded"): w.load(defer_body=True)')
exec(compile(source,str(source_path),'exec'))
