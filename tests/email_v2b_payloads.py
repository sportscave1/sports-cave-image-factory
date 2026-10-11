"""Generate malicious synthetic reader documents for actual browser/CSP tests."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from support_email_render import sanitize_received_html,reader_document
u='https://127.0.0.1:8844'
cases={
 'attributes':f'<img src="{u}/attr" srcset="{u}/srcset 2x" onerror="fetch(\'{u}/error\')"><input type=image src="{u}/input">',
 'css':f'<style>@import "{u}/import";@font-face{{font-family:x;src:url({u}/font)}}p{{background-image:url({u}/css)}}</style><p style="background:&#117;rl({u}/inline);cursor:url({u}/cursor),auto">Hello</p>',
 'escaped_css':f'<p style="background-image:\\75rl({u}/escaped);color:expression(fetch(\'{u}/expression\'))">Hello</p>',
 'svg':f'<svg><image xlink:href="{u}/svg"/><foreignObject><iframe src="{u}/nested"></iframe></foreignObject><script>fetch("{u}/svgscript")</script></svg>',
 'navigation':f'<base href="{u}/base"><meta http-equiv="refresh" content="0;url={u}/refresh"><link rel="preload" as="image" href="{u}/preload"><a href="{u}/link" ping="{u}/ping">Link</a>',
 'media':f'<video poster="{u}/poster" autoplay><source src="{u}/video"></video><audio autoplay src="{u}/audio"></audio><object data="{u}/object"></object><embed src="{u}/embed">',
 'polyglot':f'<math><mtext><table><mglyph><style><!--</style><img title="--><img src={u}/poly onerror=alert(1)>"></math><p>End</p>',
 'encoded':f'&lt;div&gt;&lt;img src="{u}/encoded"&gt;&lt;script&gt;alert(1)&lt;/script&gt;&lt;/div&gt;',
}
documents=[{'name':name,'document':reader_document(sanitize_received_html(html))} for name,html in cases.items()]
# Bypass sanitizer deliberately to prove the independent CSP/sandbox layer.
raw=f'''<img src="{u}/csp-image" srcset="{u}/csp-srcset 2x"><style>@import '{u}/csp-style';
@font-face{{font-family:x;src:url({u}/csp-font)}}p{{font-family:x;background:url({u}/csp-css)}}</style>
<p>Defense</p><iframe src="{u}/csp-frame"></iframe><script>window.executed=true;fetch('{u}/csp-fetch')</script>'''
documents.append({'name':'independent_csp','document':reader_document(raw)})
Path('docs/email-inbox-outlook-v2b-evidence/attack-documents.json').write_text(json.dumps(documents))
