"""Matched real Chromium progress observations on large synthetic conversations."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def run(source):
    output = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for size in (32768, 262144):
                page = browser.new_page()
                page.route('**/*', lambda route:route.fulfill(body='<main></main>',content_type='text/html'))
                page.goto('https://chatgpt.com/g/g-p-6a1e449948e881919c1e345006d63654/c/00000000-0000-0000-0000-000000000001')
                page.clock.install()
                page.evaluate('''size=>{
                    const root=document.querySelector('main');
                    for(let i=0;i<100;i++){
                        const turn=document.createElement('div');turn.dataset.messageAuthorRole='assistant';
                        turn.textContent='Earlier synthetic conversation. '.repeat(40);root.append(turn);
                    }
                    const last=document.createElement('div');last.id='latest';last.dataset.messageAuthorRole='assistant';
                    last.textContent=('Synthetic design reasoning and delivery notes. '.repeat(size)).slice(0,size);root.append(last);
                    window.chrome={runtime:{id:'synthetic-extension',onMessage:{addListener(fn){window.progressListener=fn;}},
                        sendMessage:async()=>({accepted:true})}};
                }''', size)
                page.add_script_tag(content=source)
                samples = page.evaluate('''()=>{
                    const samples=[];
                    const read=()=>{let result;progressListener({type:'project:progress'},{id:'synthetic-extension'},v=>result=v);return result;};
                    for(let trial=0;trial<3;trial++){
                        document.getElementById('latest').append(' '+trial);
                        const cold=performance.now();const expected=read();const coldMs=performance.now()-cold;
                        const start=performance.now();let result;
                        for(let i=0;i<100;i++)result=read();
                        if(JSON.stringify(result)!==JSON.stringify(expected))throw Error('unstable repeated response');
                        samples.push({cold_ms:coldMs,repeated_100_ms:performance.now()-start,result});
                    }
                    return samples;
                }''')
                output.append(dict(latest_response_chars=size, earlier_turns=100, samples=samples))
                page.close()
            return output
        finally:
            browser.close()


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    baseline = run(Path('/tmp/composer-baseline.js').read_text())
    candidate = run((root/'windows-upload-companion/composer.js').read_text())
    for before, after in zip(baseline, candidate):
        for old, new in zip(before['samples'], after['samples']):
            assert old['result'] == new['result']
    print(json.dumps(dict(synthetic=True, provider_work_measured=False,baseline=baseline,candidate=candidate),indent=2))
