/* Tab-local recovery only. Never stores MIME, received mail, credentials or file bytes.
 * Eight-hour retention, actor+credential+mailbox scope supplied by the server.
 * sessionStorage survives navigation/reload; browser session restore is best effort.
 */
(function(global){
  'use strict';
  const PREFIX='sc-email-draft-v2:', TTL=8*60*60*1000;
  function create(storage,scope,clock=Date.now){
    const prefix=PREFIX+scope+':';
    function sweep(){
      for(let i=storage.length-1;i>=0;i--){
        const key=storage.key(i);if(!key?.startsWith(PREFIX))continue;
        let row;try{row=JSON.parse(storage.getItem(key));}catch(_){}
        if(!key.startsWith(prefix)||!row||clock()-row.updated_at>TTL)storage.removeItem(key);
      }
    }
    sweep();
    return {
      write(draft){
        if(!scope||!draft?.id)return;
        const data={};
        for(const key of ['id','to','cc','bcc','subject','html','signature','include_quote','edit_revision','storage_version','attachment_ids'])data[key]=draft[key];
        const encoded=JSON.stringify({draft:data,updated_at:clock()});
        if(encoded.length>1100000)throw Error('Recovery text exceeds storage limit');
        storage.setItem(prefix+draft.id,encoded);
      },
      list(){sweep();const rows=[];for(let i=0;i<storage.length;i++){
        const key=storage.key(i);if(key.startsWith(prefix)){const row=JSON.parse(storage.getItem(key));rows.push(row.draft);}
      }return rows;},
      acknowledge(id,revision){
        const key=prefix+id,row=JSON.parse(storage.getItem(key)||'null');
        if(row&&Number(row.draft.edit_revision)<=Number(revision))storage.removeItem(key);
      },
      remove(id){storage.removeItem(prefix+id);},
      clear(){for(let i=storage.length-1;i>=0;i--){const key=storage.key(i);if(key?.startsWith(PREFIX))storage.removeItem(key);}}
    };
  }
  global.EmailDraftJournal={create};
})(typeof window!=='undefined'?window:globalThis);
