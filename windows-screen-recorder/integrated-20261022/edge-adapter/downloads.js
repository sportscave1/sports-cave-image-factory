/* Local preview download receipts only. Never reads file contents or opens files.
 * No downloads from other origins are forwarded to the local helper. */
'use strict';
const previewOrigins = new Set(['http://127.0.0.1:18962','http://127.0.0.1:18963']);
function scoped(item) {
  try {
    const url = new URL(item.url);
    return previewOrigins.has(url.origin) && !url.username && !url.password &&
      /^[0-9a-f-]{36}$/.test(url.searchParams.get('sc_download') || '');
  } catch { return false; }
}
function receipt(item, event) {
  if (!scoped(item)) return;
  chrome.runtime.sendNativeMessage('com.sportscave.recorder.downloads', {
    v:1, event, id:String(item.id), url:item.url, final_url:item.finalUrl,
    filename:item.filename, state:item.state, bytes:item.fileSize,
    started:item.startTime, ended:item.endTime || '', error:item.error || '',
    observed:Date.now()
  }, response => {
    const error=chrome.runtime.lastError;
    if(error) console.warn('Recorder download receipt bridge: '+error.message);
    else if(response?.accepted!==true) console.warn('Recorder download receipt bridge rejected metadata.');
  });
}
chrome.downloads.onCreated.addListener(item => receipt(item,'created'));
chrome.runtime.onMessage.addListener((message,sender) => {
  try {
    if(message.kind!=='save_as'||!previewOrigins.has(new URL(sender.url).origin)||
       !scoped({url:message.url})||new URL(sender.url).origin!==new URL(message.url).origin||
       typeof message.filename!=='string'||!message.filename||message.filename.length>180||/[\\/]/.test(message.filename))return;
    chrome.downloads.download({url:message.url,filename:message.filename,conflictAction:'uniquify',saveAs:true},()=>{void chrome.runtime.lastError;});
  } catch {}
});
chrome.downloads.onChanged.addListener(change => {
  if (!change.state && !change.filename && !change.error) return;
  chrome.downloads.search({id:change.id}, items => {
    if (items.length === 1) receipt(items[0],'changed');
  });
});
