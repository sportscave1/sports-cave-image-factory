"""Singleton email defaults, retaining the previous template registry for audit."""
from copy import deepcopy
from collections import OrderedDict
import json
import threading
from crm_store import Store
from crm_campaign_sections import section_defaults
from crm_campaign_html import import_html
from crm_campaign_footer import render_footer, has_unsubscribe_link

FORMAT='campaign_brand_section_v1'
DEFAULT_KEY='email_brand_defaults'
DEFAULT_KEYS={'header':'email_default_header','footer':'email_default_footer'}
_CACHE=OrderedDict()
_LOCK=threading.RLock()


def section_source(kind,source):
    if kind not in DEFAULT_KEYS or not isinstance(source,str) or len(source.encode('utf-8'))>30000:
        raise ValueError('Use Header or Footer HTML up to 30 KB.')
    if kind=='footer':
        _,_,checks=render_footer(source,{})
    else:_,_,checks=import_html(source)
    if not all(v for k,v in checks.items() if k!='HTML content present'):
        raise ValueError('Remove unsafe markup and use HTTPS image/link URLs with image alt text.')
    return source


class BrandTemplates(Store):
    def email_defaults(self,cfg):
        # Read small revisions every time; cache HTML by revision, never by stale TTL.
        keys=list(DEFAULT_KEYS.values())
        revisions=self.q('SELECT key,version FROM crm_workspace_settings WHERE key=ANY(%s) ORDER BY key',(keys,))
        if len(revisions)!=2:
            self._initialize_email_defaults(cfg)
            revisions=self.q('SELECT key,version FROM crm_workspace_settings WHERE key=ANY(%s) ORDER BY key',(keys,))
        cache_key=(self.connect,tuple((r['key'],r['version']) for r in revisions))
        with _LOCK:
            if cache_key in _CACHE:return deepcopy(_CACHE[cache_key])
        rows=self.q('SELECT * FROM crm_workspace_settings WHERE key=ANY(%s)',(keys,))
        result={kind:next(r for r in rows if r['key']==key) for kind,key in DEFAULT_KEYS.items()}
        # Key by the versions actually loaded, including a concurrent admin edit.
        cache_key=(self.connect,tuple(sorted((r['key'],r['version']) for r in rows)))
        with _LOCK:
            _CACHE[cache_key]=deepcopy(result)
            while len(_CACHE)>16:_CACHE.popitem(last=False)
        return result

    def _initialize_email_defaults(self,cfg):
        with self.db() as conn:
            # Same lock as the old registry; initialization never overwrites HTML.
            conn.execute('INSERT INTO crm_workspace_settings(key,value,updated_by) VALUES(%s,%s::jsonb,%s) ON CONFLICT DO NOTHING',(DEFAULT_KEY,json.dumps({'header':None,'footer':None}),'system:email-defaults'))
            registry=conn.execute('SELECT value FROM crm_workspace_settings WHERE key=%s FOR UPDATE',(DEFAULT_KEY,)).fetchone()['value']
            for kind,key in DEFAULT_KEYS.items():
                if conn.execute('SELECT 1 FROM crm_workspace_settings WHERE key=%s',(key,)).fetchone():continue
                identity=registry.get(kind)
                source=section_defaults(cfg)[kind]
                if identity:
                    row=conn.execute("SELECT content FROM crm_templates WHERE id=%s AND content->>'format'=%s AND content->>'section'=%s AND archived_at IS NULL",(identity,FORMAT,kind)).fetchone()
                    if not row:raise ValueError('Current default '+kind+' is unavailable. Restore its source before continuing.')
                    source=row['content']['html']
                value={'html':source,'source_template_id':identity}
                row=conn.execute('INSERT INTO crm_workspace_settings(key,value,updated_by) VALUES(%s,%s::jsonb,%s) ON CONFLICT DO NOTHING RETURNING *',(key,json.dumps(value),'system:email-defaults')).fetchone()
                if row:conn.execute('INSERT INTO crm_settings_history(key,version,value,actor) VALUES(%s,%s,%s::jsonb,%s)',(key,row['version'],json.dumps(value),'system:email-defaults'))

    def default_sections(self,cfg):
        return {kind:row['value']['html'] for kind,row in self.email_defaults(cfg).items()}

    def save_email_default(self,user,kind,source,version):
        from crm_workspace_store import admin
        admin(user)
        source=section_source(kind,source)
        if kind=='footer' and not has_unsubscribe_link(source):
            raise ValueError('Default footer must include a visible {{UNSUBSCRIBE_URL}} link.')
        key=DEFAULT_KEYS[kind];actor=str(user.get('id',''))
        with self.db() as conn:
            row=conn.execute("UPDATE crm_workspace_settings SET value=jsonb_set(value,'{html}',%s::jsonb),version=version+1,updated_by=%s,updated_at=now() WHERE key=%s AND version=%s RETURNING *",(json.dumps(source),actor,key,version)).fetchone()
            if not row:raise ValueError('Default changed elsewhere. Reopen the editor before saving.')
            conn.execute('INSERT INTO crm_settings_history(key,version,value,actor) VALUES(%s,%s,%s::jsonb,%s)',(key,row['version'],json.dumps(row['value']),actor))
        with _LOCK:_CACHE.clear()
        return row

    # Old write entry points fail explicitly; audit rows remain readable in storage.
    def save_section_template(self,*args,**kwargs):
        raise ValueError('Edit Default Header or Default Footer in Email defaults.')

    def set_section_default(self,*args,**kwargs):
        raise ValueError('Header and Footer are single global defaults.')

    def delete_section_template(self,*args,**kwargs):
        raise ValueError('Email defaults cannot be deleted; historical templates are retained for audit.')
