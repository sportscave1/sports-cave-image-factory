"""Read-only source inventory; never runs application renderers or providers."""
import ast,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import os_accounts
class Surfaces(ast.NodeVisitor):
 def __init__(self,name):self.file=name;self.owner=[];self.rows=[]
 def visit_FunctionDef(self,node):
  self.owner.append(node.name);self.generic_visit(node);self.owner.pop()
 def visit_Call(self,node):
  if isinstance(node.func,ast.Attribute) and node.func.attr in ('title','header','subheader','dialog','tabs','popover','expander','form','file_uploader') and ast.unparse(node.func.value) in ('st','streamlit'):
   self.rows.append({'file':self.file,'line':node.lineno,'owner':'.'.join(self.owner),'kind':node.func.attr,'label':ast.unparse(node.args[0]) if node.args else ''})
  self.generic_visit(node)
rows=[];errors=[]
for path in sorted(ROOT.glob('*.py')):
 try:
  visitor=Surfaces(path.name);visitor.visit(ast.parse(path.read_text(encoding='utf-8-sig')));rows.extend(visitor.rows)
 except (SyntaxError,UnicodeError) as error:errors.append({'file':path.name,'error':type(error).__name__})
dispatch=next(n for n in ast.parse((ROOT/'app.py').read_text(encoding='utf-8-sig')).body if isinstance(n,ast.FunctionDef) and n.name=='render_selected_page')
branches=[]
for node in ast.walk(dispatch):
 if isinstance(node,ast.If):branches.append({'condition':ast.unparse(node.test),'line':node.lineno,'calls':[ast.unparse(c.func) for n in node.body for c in ast.walk(n) if isinstance(c,ast.Call)]})
output=ROOT/'docs/appwide-ui-v1-evidence'
output.mkdir(parents=True,exist_ok=True)
(output/'source-inventory.json').write_text(json.dumps({'routes':list(os_accounts.PAGE_REGISTRY),'dispatcher_branches':branches,'presentation_components':rows,'custom_component_sources':[str(p.relative_to(ROOT)) for p in sorted((ROOT/'components').rglob('index.html'))],'source_parse_errors':errors},indent=2))
criteria=['Header and top spacing','Heading size','Vertical whitespace','Footer/bottom whitespace','Button styling','Button alignment','Search/filter controls','Forms and input fields','Tables','Dialogs and popovers','Information density','Responsiveness','Navigation speed','Initial loading','Warm loading','Ease of use','Visual consistency','Accessibility','Existing functional correctness']
changed={'Prodigi','Webhook Events','Sync Runs','App Errors','Persistence Check','Image Protection','Product Uploads','Design Studio','Ads','Reporting','Weekly Review','Accounts & Access','Developer','Products','Product Assets','Analytics Overview','Traffic & Acquisition','Pages & Engagement','Analytics Ecommerce','Analytics Realtime','Edition Ops','Social Media','Wall Preview Inbox','AI Reels','Creative Refresh','Posting','Meta Review','SEO Overview','Keywords & Rankings','SEO Opportunities','SEO Landing Pages','Keyword Mapping','SEO Blog','SEO Health & Fixes'}
assessments=[]
for page in os_accounts.PAGE_REGISTRY:
 route=page['route'];verified=route in changed
 scores={c:'Pending: no representative isolated workflow/browser observation' for c in criteria}
 if verified:
  for c in ['Header and top spacing','Heading size','Vertical whitespace','Button styling','Button alignment','Tables','Information density','Responsiveness','Visual consistency']:
   scores[c]='Verified only for synthetic page-body fixture; full shell/data-dependent acceptance pending'
  scores['Warm loading']='Pending comparable populated-workflow timing'
  if route in {'Prodigi','Webhook Events','Sync Runs','App Errors','Persistence Check'}:scores['Warm loading']='20 identical warm AppTest reruns per phase; render and driver p50/p95 recorded'
  scores['Existing functional correctness']='Targeted regression tests and unchanged callback/read paths; production not exercised'
  if route=='Prodigi':
   scores['Search/filter controls']='Browser Enter submit, filter query retention and lookup validation verified'
   scores['Forms and input fields']='Native controls preserved; search and empty-input validation tested'
   scores['Accessibility']='Keyboard Tab to Find Order and 2px focus outline verified; full a11y audit pending'
   scores['Dialogs and popovers']='Reference expander verified; populated QA/certificate dialogs pending'
 assessments.append({'route':route,'label':page['label'],'initial_assessment':'UPGRADE REQUIRED' if verified else 'VERIFICATION BLOCKED','action':'Scoped presentation upgrade' if verified else 'Preserve pending representative runtime audit','final_status':'Implemented locally; remaining acceptance pending' if verified else 'Pending','criteria':scores})
(output/'page-assessments.json').write_text(json.dumps(assessments,indent=2))
print(json.dumps({'registered_routes':len(os_accounts.PAGE_REGISTRY),'source_surfaces':len(rows),'source_parse_errors':errors,'locally_changed_routes':len(changed)}))
