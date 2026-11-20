import json
import re
import subprocess
import unittest
from prompt_clipboard import copy_html


class ClipboardTests(unittest.TestCase):
    def test_full_text_and_browser_fallback(self):
        text = 'Full prompt \"quoted\" <tag> </script> & \n' + chr(0x1f3c6) + 'x' * 200000
        html = copy_html(text)
        self.assertEqual(html.count('</script>'), 1)
        script = re.search(r'<script>(.*?)</script>', html, re.S)[1]
        harness = r'''const fs = require('fs'), vm = require('vm'), assert = require('assert');
const {script, expected} = JSON.parse(fs.readFileSync(0, 'utf8'));
(async () => {
  for (const mode of ['clipboard', 'fallback', 'blocked']) {
    let copied, field;
    const button = {focus() {}}, status = {};
    const document = {
      getElementById: id => id === 'copy' ? button : status,
      createElement: () => field = {style: {}, select() {}, remove() {}},
      body: {appendChild() {}},
      execCommand: () => { if (mode === 'blocked') return false; copied = field.value; return true; }
    };
    const navigator = mode === 'clipboard' ? {clipboard: {writeText: async value => { copied = value; }}} : {};
    vm.runInNewContext(script, {document, navigator});
    await button.onclick();
    if (mode === 'blocked') assert(status.textContent.includes('preview'));
    else { assert.strictEqual(copied, expected); assert.strictEqual(status.textContent, 'Copied!'); }
  }
})().catch(e => { console.error(e); process.exit(1); });'''
        result = subprocess.run(['node', '-e', harness], input=json.dumps({'script': script, 'expected': text}), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
