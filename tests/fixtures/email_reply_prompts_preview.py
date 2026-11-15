"""Isolated reply-prompt browser fixture; reuses the offline desktop mailbox harness."""
from pathlib import Path
source_path=Path(__file__).with_name('email_desktop_preview.py')
source=source_path.read_text(encoding='utf-8')
source=source.replace('super().__init__(75)', '''super().__init__(3)
        self.messages[-1].update(subject="Mark James left a 5 star review for 'Six Laps Ahead Peter Brock Wall Art'", sender={'name':'Judge.me','email':'support@judge.me'})''')
a=source.index('    def read_message(self, message):')
b=source.index('    def related_headers_many(',a)
source=source[:a]+'''    def read_message(self, message):
        result=super().read_message(message)
        if message['uid']=='3':
            result['text']="Mark James left a 5 star review for 'Six Laps Ahead Peter Brock Wall Art'\\n\\n<b>Happy</b>\\n<i>I am more than happy with my purchase</i>\\n\\nMark James is a verified buyer.\\nKind regards,\\nJudge.me Team\\nsupport@judge.me"
        return result

'''+source[b:]
exec(compile(source,str(source_path),'exec'))
