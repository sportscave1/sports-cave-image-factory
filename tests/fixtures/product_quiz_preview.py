"""Generate an isolated static visual harness. Imports no app/server/providers."""
from pathlib import Path
import sys
import json
from urllib.parse import quote
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from product_quiz import DEFAULT
from copy import deepcopy


def build(target):
    target.mkdir(parents=True,exist_ok=True)
    products=[]
    for number,(name,sport,subject,pref,color) in enumerate([
        ('Air · Legacy Edition','Basketball','Michael Jordan','Legacy','#9f3430'),
        ('The Last Shot','Basketball','Michael Jordan','Defining moment','#baa679'),
        ('Eternal Rivals','Basketball','Michael Jordan','Rivalry','#888381'),
        ('The King of Spin','Cricket','Shane Warne','Legacy','#ad8536'),
        ('Lights Out','Formula One','Lewis Hamilton','Defining moment','#5c8988'),
        ('Hamilton vs Verstappen','Formula One','Max Verstappen','Rivalry','#bc5a30')],1):
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="500" viewBox="0 0 400 500"><rect width="400" height="500" fill="#090909"/><rect x="25" y="25" width="350" height="450" fill="#171717" stroke="#a48b58"/><circle cx="200" cy="190" r="100" fill="{color}" opacity=".75"/><path d="M90 300L185 80L220 260L320 190" fill="none" stroke="#e5dfce" stroke-width="8"/><text x="200" y="355" fill="#eee7d8" text-anchor="middle" font-family="Georgia" font-size="23">{subject.upper()}</text><text x="200" y="390" fill="#c6a76b" text-anchor="middle" font-family="sans-serif" font-size="12" letter-spacing="3">{pref.upper()}</text><text x="200" y="440" fill="#817b70" text-anchor="middle" font-family="sans-serif" font-size="9">SYNTHETIC PREVIEW ARTWORK</text></svg>'
        products.append(dict(id='gid://shopify/Product/'+str(number),handle='edition-'+str(number),title=name,image='data:image/svg+xml,'+quote(svg),sports=[sport],subjects=[subject]+(['Lewis Hamilton'] if number==6 else []),preferences=[pref],featured=0))
    config=deepcopy(DEFAULT)
    config['collections']={'basketball':'Basketball'}
    data=json.dumps({'config':config,'manifest':{'version':'a'*24},'preview':{'products':products,'catalogue':{'sports':{s:'preview' for p in products for s in p['sports']}}}}).replace('<','\\u003c')
    runtime=(Path(__file__).resolve().parents[2]/'static/product-quiz/runtime.js').read_text(encoding='utf-8')
    html='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Find Your Edition · Local Preview</title><body style="margin:0;background:#101011;color:#f5f0e6;font:14px system-ui"><main style="max-width:1000px;margin:40px auto;padding:20px"><p style="color:#c6a76b;letter-spacing:.2em;font-size:11px">SPORTS CAVE / LOCAL PREVIEW</p><h1 style="font:36px Georgia">Find the edition that feels like you.</h1><p style="color:#aaa">Synthetic catalogue · no Shopify installation · no tracking</p><div id="button"></div><hr style="border:0;border-top:1px solid #302a20;margin:32px 0"><div id="inline"></div></main><script>'''+runtime+'''</script><script>const data='''+data+''';for(const [id,mode] of [['button','button'],['inline','inline']]){const host=document.getElementById(id),shadow=host.attachShadow({mode:'open'}),launcher=document.createElement('button');launcher.textContent='Find your edition ↗';launcher.style.cssText='color:#f5f0e6;background:#151412;border:1px solid #c6a76b;border-radius:6px;padding:14px 24px;font:14px system-ui;cursor:pointer';shadow.append(launcher);if(mode==='inline')SportsCaveQuizRuntime.mount({host,shadow,launcher,mode,base:'',...data});else {let instance;launcher.onclick=async()=>{if(instance)instance.open();else instance=await SportsCaveQuizRuntime.mount({host,shadow,launcher,mode,base:'',...data});};}}</script></body></html>'''
    (target/'index.html').write_text(html,encoding='utf-8')
    return target/'index.html'


if __name__=='__main__': print(build(Path(sys.argv[1]) if len(sys.argv)>1 else Path('tmp/product-quiz-preview')).resolve())
