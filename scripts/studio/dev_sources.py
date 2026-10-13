"""Static, bounded references to actual route branches. No new write permissions."""
import ast
from pathlib import Path
import editor, drafts, page_catalog

_cache = {}
def route_sources(root, page):
    root=Path(root); route=next((p['route'] for p in page_catalog.pages(root) if p['key']==page),None)
    if route is None: raise ValueError('Unknown application page')
    meta,data=drafts.read_source(root,'app.py');text=data.decode('utf-8-sig')
    cache_key=(str(root),meta['sha256'])
    if cache_key not in _cache:
        tree=ast.parse(text); matches={};aliases={a.asname or a.name:a.name for n in tree.body if isinstance(n,ast.Import) for a in n.names};functions={n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
        for node in ast.walk(tree):
            if not isinstance(node,ast.If):continue
            test=node.test
            if not (isinstance(test,ast.Compare) and isinstance(test.left,ast.Name) and test.left.id=='current_page' and len(test.ops)==1):continue
            expression=test.comparators[0];routes=[]
            if isinstance(test.ops[0],ast.Eq) and isinstance(expression,ast.Constant) and isinstance(expression.value,str):routes=[expression.value]
            elif isinstance(test.ops[0],ast.In):
                try:
                    if isinstance(expression,ast.Attribute) and isinstance(expression.value,ast.Name):
                        module=aliases.get(expression.value.id,expression.value.id)
                        routes=page_catalog.Static(root).module(module)[expression.attr]
                    else:routes=ast.literal_eval(expression)
                    if not isinstance(routes,(list,tuple)) or len(routes)>200 or not all(isinstance(v,str) for v in routes):routes=[]
                except (ValueError,KeyError,OSError,TypeError):routes=[]
            if not routes:continue
            # The elif chain's end_lineno includes other pages; bound this branch to its own body.
            end=max((n.end_lineno for n in node.body),default=node.lineno)
            modules=[]
            for body in node.body:
                for child in ast.walk(body):
                    if isinstance(child,ast.ImportFrom) and child.level==0 and child.module and '.' not in child.module: modules.append(child.module+'.py')
            matched=[]
            matched.append((node.lineno,end,modules))
            # Only local functions directly called by this branch; no guesses by filename.
            calls={n.func.id for b in node.body for n in ast.walk(b) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)}
            for name in sorted(calls):
                function=functions.get(name)
                if function:
                    imported=[]
                    for child in ast.walk(function):
                        if isinstance(child,ast.Call) and isinstance(child.func,ast.Attribute) and isinstance(child.func.value,ast.Name) and child.func.value.id=='importlib' and child.func.attr=='import_module' and child.args and isinstance(child.args[0],ast.Constant) and isinstance(child.args[0].value,str):
                            module=child.args[0].value
                            if module.isidentifier():imported.append(module+'.py')
                        if isinstance(child,ast.ImportFrom) and child.level==0 and child.module and child.module.isidentifier():imported.append(child.module+'.py')
                    matched.append((function.lineno,function.end_lineno,imported))
            for route_name in routes:matches.setdefault(route_name,[]).extend(matched)
        _cache.clear();_cache[cache_key]=matches
    blocks=_cache[cache_key].get(route,[])
    refs=[];lines=text.splitlines()
    for start,end,modules in blocks[:8]:
        refs.append({'path':'app.py','line':start,'source':'\n'.join(lines[start-1:min(end,start+119)]),'mode':'read-only','relationship':'Verified route branch'})
        for name in modules[:6]:
            if any(r['path']==name for r in refs):continue
            try:
                _,source=drafts.read_source(root,name)
                decoded=source.decode('utf-8-sig');constants={n.value for n in ast.walk(ast.parse(decoded)) if isinstance(n,ast.Constant) and isinstance(n.value,str)}
                refs.append({'path':name,'line':1,'source':decoded[:60000],'truncated':len(decoded)>60000,'confirmed_sources':[n for n in editor.CODE_FILES if Path(n).name in constants],'mode':'read-only','relationship':'Imported by this route branch'})
            except (ValueError,OSError):continue
    components=[]
    if page=='__signin__':
        for key,value in editor.visual_values(text).items():
            components.append({'key':key,'label':value['label'],'location':editor.locations(text).get(key),'editable':True})
    # Existing allowlisted source remains accessible. Only claim page relevance where the
    # imported module contains a literal reference to that exact source filename.
    files=[]
    for name in editor.CODE_FILES:
        related=any(name in r.get('confirmed_sources',[]) or Path(name).name in r['source'] for r in refs)
        shared=False
        loader=root/'top_bar.py'
        if name=='components/sports_cave_top_bar/index.html' and loader.is_file():
            _,loader_data=drafts.read_source(root,'top_bar.py')
            shared='sports_cave_top_bar' in loader_data.decode('utf-8-sig') and 'index.html' in loader_data.decode('utf-8-sig')
        files.append({'path':name,'group':'Header / shared navigation' if shared else 'Current page source' if related else 'Authorised source library','editable':True})
    return {'page':page,'components':components,'files':files,'references':refs,'notice':'Only verified component mappings are editable. Python references are read-only; no HTML is fabricated.'}
