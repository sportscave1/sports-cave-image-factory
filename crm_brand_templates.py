"""Small reusable header/footer records in the existing CRM template tables."""
from copy import deepcopy
import json
import uuid
from crm_store import Store
from crm_navigation import require
from crm_campaign_sections import section_defaults
from crm_campaign_html import import_html
from crm_campaign_footer import prepare_footer, render_footer
from crm_logic import now

FORMAT='campaign_brand_section_v1'
DEFAULT_KEY='email_brand_defaults'


def section_source(kind,source):
    if kind not in ('header','footer') or not isinstance(source,str) or len(source.encode('utf-8'))>30000:
        raise ValueError('Use Header or Footer HTML up to 30 KB.')
    if kind=='footer':
        source=prepare_footer(source)
        if len(source.encode('utf-8'))>30000:raise ValueError('Footer HTML including required content must be at most 30 KB.')
        _,_,checks=render_footer(source,{})
    else:_,_,checks=import_html(source)
    if not all(v for k,v in checks.items() if k!='HTML content present'):
        raise ValueError('Remove unsafe markup and use HTTPS image/link URLs with image alt text.')
    return source


class BrandTemplates(Store):
    def section_templates(self,kind,cfg):
        if kind not in ('header','footer'):raise ValueError('Unknown brand section.')
        rows=self.q("SELECT * FROM crm_templates WHERE content->>'format'=%s AND content->>'section'=%s AND archived_at IS NULL ORDER BY name,id",(FORMAT,kind))
        defaults=self.q('SELECT value FROM crm_workspace_settings WHERE key=%s',(DEFAULT_KEY,),True)
        default=(defaults or {}).get('value',{}).get(kind)
        builtin={'id':'builtin_'+kind,'name':'Sports Cave Default '+kind.title(),'version':0,
                 'content':{'format':FORMAT,'section':kind,'html':section_defaults(cfg)[kind]},'builtin':True}
        result=[builtin,*rows]
        # Read-time compatibility only; existing stored versions remain immutable.
        for row in rows:
            if kind=='footer':row['content']={**row['content'],'html':prepare_footer(row['content']['html'])}
        # Fail closed rather than silently changing new campaigns after registry corruption.
        if default and not any(str(r['id'])==default for r in rows):raise ValueError('Default brand template is unavailable. Ask an administrator to select a default.')
        for row in result:row['is_default']=str(row['id'])==(default or builtin['id'])
        return result

    def default_sections(self,cfg):
        return {kind:next(r['content']['html'] for r in self.section_templates(kind,cfg) if r['is_default']) for kind in ('header','footer')}

    def _brand_lock(self,conn,actor):
        # Existing settings row serializes default/edit/delete races. Only explicit writes call this.
        conn.execute('INSERT INTO crm_workspace_settings(key,value,updated_by) VALUES(%s,%s::jsonb,%s) ON CONFLICT DO NOTHING',(DEFAULT_KEY,json.dumps({'header':None,'footer':None}),actor))
        return conn.execute('SELECT * FROM crm_workspace_settings WHERE key=%s FOR UPDATE',(DEFAULT_KEY,)).fetchone()

    def _brand_default(self,conn,registry,kind,identity,actor):
        values=deepcopy(registry['value']);values[kind]=identity
        row=conn.execute('UPDATE crm_workspace_settings SET value=%s::jsonb,version=version+1,updated_by=%s,updated_at=now() WHERE key=%s RETURNING *',(json.dumps(values),actor,DEFAULT_KEY)).fetchone()
        conn.execute('INSERT INTO crm_settings_history(key,version,value,actor) VALUES(%s,%s,%s::jsonb,%s)',(DEFAULT_KEY,row['version'],json.dumps(values),actor))

    def save_section_template(self,user,kind,name,source,*,identity=None,version=None,confirmed=False,make_default=False):
        require(user,'crm_templates_manage')
        if make_default or identity:
            from crm_workspace_store import admin
            admin(user)
        if identity and not confirmed:raise ValueError('Confirm overwriting this shared template.')
        if not isinstance(name,str) or not name.strip() or len(name)>150:raise ValueError('Use a template name of 1–150 characters.')
        source=section_source(kind,source);actor=str(user.get('id',''));stamp=now().isoformat()
        with self.db() as conn:
            registry=self._brand_lock(conn,actor)
            duplicate=conn.execute("SELECT id FROM crm_templates WHERE content->>'format'=%s AND content->>'section'=%s AND lower(name)=lower(%s) AND archived_at IS NULL",(FORMAT,kind,name.strip())).fetchone()
            if duplicate and str(duplicate['id'])!=str(identity):raise ValueError('A template with this name already exists in this section. Choose another name.')
            content={'format':FORMAT,'section':kind,'html':source,'created_by':actor,'created_at':stamp,'updated_by':actor,'action':'created'}
            if identity:
                old=conn.execute("SELECT * FROM crm_templates WHERE id=%s AND content->>'format'=%s AND content->>'section'=%s AND archived_at IS NULL FOR UPDATE",(identity,FORMAT,kind)).fetchone()
                if not old or old['version']!=version:raise ValueError('Template changed elsewhere. Reload before editing.')
                content.update(created_by=old['content']['created_by'],created_at=old['content']['created_at'],action='edited')
                row=conn.execute('UPDATE crm_templates SET name=%s,content=%s::jsonb,version=version+1,updated_at=now() WHERE id=%s RETURNING *',(name.strip(),json.dumps(content),identity)).fetchone()
            else:
                row=conn.execute("INSERT INTO crm_templates(template_key,name,kind,content) VALUES(%s,%s,'Campaign',%s::jsonb) RETURNING *",('brand_'+uuid.uuid4().hex,name.strip(),json.dumps(content))).fetchone()
            conn.execute('INSERT INTO crm_template_versions(template_id,version,content) VALUES(%s,%s,%s::jsonb)',(row['id'],row['version'],json.dumps(content)))
            if make_default:self._brand_default(conn,registry,kind,str(row['id']),actor)
            return row

    def set_section_default(self,user,kind,identity):
        from crm_workspace_store import admin
        admin(user)
        if kind not in ('header','footer'):raise ValueError('Unknown brand section.')
        actor=str(user.get('id',''))
        with self.db() as conn:
            registry=self._brand_lock(conn,actor)
            if identity=='builtin_'+kind:identity=None
            elif not conn.execute("SELECT id FROM crm_templates WHERE id=%s AND content->>'format'=%s AND content->>'section'=%s AND archived_at IS NULL",(identity,FORMAT,kind)).fetchone():raise ValueError('Select an active template for this section.')
            self._brand_default(conn,registry,kind,identity,actor)

    def delete_section_template(self,user,identity,version,*,confirmed=False):
        from crm_workspace_store import admin
        admin(user)
        if not confirmed:raise ValueError('Confirm deleting this custom template.')
        if str(identity).startswith('builtin_'):raise ValueError('The built-in default cannot be deleted.')
        actor=str(user.get('id',''))
        with self.db() as conn:
            registry=self._brand_lock(conn,actor)
            if str(identity) in registry['value'].values():raise ValueError('Choose another default before deleting this template.')
            old=conn.execute("SELECT * FROM crm_templates WHERE id=%s AND content->>'format'=%s AND archived_at IS NULL FOR UPDATE",(identity,FORMAT)).fetchone()
            if not old or old['version']!=version:raise ValueError('Template changed elsewhere. Reload before deleting.')
            content={**old['content'],'updated_by':actor,'action':'deleted'}
            row=conn.execute('UPDATE crm_templates SET archived_at=now(),updated_at=now(),version=version+1,content=%s::jsonb WHERE id=%s RETURNING *',(json.dumps(content),identity)).fetchone()
            conn.execute('INSERT INTO crm_template_versions(template_id,version,content) VALUES(%s,%s,%s::jsonb)',(identity,row['version'],json.dumps(content)))
            # Logical deletion retains the existing template audit/version history.
            return row
