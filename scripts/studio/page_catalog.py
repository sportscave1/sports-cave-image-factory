"""Bounded static page discovery. Never imports or executes application modules."""
import ast
from pathlib import Path

MODULES={"os_accounts","social_media","ads_navigation","analytics_navigation","seo_workspace","seo_navigation","crm_navigation"}
class Static:
    def __init__(self,root):self.root=Path(root);self.cache={}
    def module(self,name):
        if name not in MODULES:raise ValueError("Unapproved page-definition module")
        if name in self.cache:return self.cache[name]
        path=self.root/({"seo_workspace":"seo_navigation"}.get(name,name)+".py")
        if path.is_symlink() or not path.resolve().is_relative_to(self.root.resolve()):raise ValueError("Unsafe page module")
        text=path.read_text(encoding="utf-8-sig")
        if len(text)>5*1024*1024:raise ValueError("Oversized page module")
        env={};self.cache[name]=env
        for node in ast.parse(text).body:
            if isinstance(node,ast.ImportFrom) and node.level==0 and node.module in MODULES:
                for item in node.names:
                    try:env[item.asname or item.name]=self.module(node.module)[item.name]
                    except (ValueError,KeyError):pass
            if isinstance(node,ast.Assign):
                try:value=self.value(node.value,env)
                except (ValueError,KeyError,TypeError,IndexError,AttributeError):continue
                for target in node.targets:
                    if isinstance(target,ast.Name):env[target.id]=value
                    elif isinstance(target,ast.Subscript) and isinstance(target.value,ast.Name) and isinstance(env.get(target.value.id),dict):
                        env[target.value.id][self.value(target.slice,env)]=value
            if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):
                call=node.value
                if isinstance(call.func,ast.Attribute) and isinstance(call.func.value,ast.Name) and call.func.attr=='update' and len(call.args)==1 and not call.keywords:
                    target=env.get(call.func.value.id)
                    try:delta=self.value(call.args[0],env)
                    except (ValueError,KeyError,TypeError):continue
                    if isinstance(target,dict) and isinstance(delta,dict) and len(target)+len(delta)<=200:target.update(delta)
        return env
    def value(self,n,env):
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id in {"tuple","list"} and len(n.args)==1 and not n.keywords:
            value=self.value(n.args[0],env)
            if not isinstance(value,(list,tuple,dict)) or len(value)>200:raise ValueError("Unsupported static sequence")
            return tuple(value) if n.func.id=="tuple" else list(value)
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='zip' and len(n.args)==2 and not n.keywords:
            a,b=(self.value(v,env) for v in n.args)
            if not isinstance(a,(list,tuple)) or not isinstance(b,(list,tuple)) or max(len(a),len(b))>200:raise ValueError('Unsupported static zip')
            return list(zip(a,b))
        if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='dict' and len(n.args)==1 and not n.keywords:
            value=self.value(n.args[0],env)
            if not isinstance(value,(list,tuple,dict)) or len(value)>200:raise ValueError('Unsupported static dictionary')
            return dict(value)
        if isinstance(n,ast.Constant):return n.value
        if isinstance(n,ast.Name):return env[n.id]
        if isinstance(n,ast.Attribute) and isinstance(n.value,ast.Name):return self.module(n.value.id)[n.attr]
        if isinstance(n,(ast.Tuple,ast.List)):
            out=[]
            for el in n.elts:
                v=self.value(el.value if isinstance(el,ast.Starred) else el,env)
                out.extend(v) if isinstance(el,ast.Starred) else out.append(v)
            return out
        if isinstance(n,ast.Dict):return {self.value(k,env):self.value(v,env) for k,v in zip(n.keys,n.values)}
        if isinstance(n,ast.Subscript):return self.value(n.value,env)[self.value(n.slice,env)]
        if isinstance(n,ast.Slice):return slice(*(self.value(v,env) if v else None for v in (n.lower,n.upper,n.step)))
        if isinstance(n,ast.Compare) and len(n.ops)==1 and isinstance(n.ops[0],ast.NotEq):return self.value(n.left,env)!=self.value(n.comparators[0],env)
        if isinstance(n,(ast.GeneratorExp,ast.ListComp)) and len(n.generators)==1:
            loop=n.generators[0]
            if loop.is_async:raise ValueError("Unsupported page expression")
            rows=self.value(loop.iter,env)
            if len(rows)>200:raise ValueError("Too many pages")
            out=[]
            for row in rows:
                local=dict(env)
                targets=loop.target.elts if isinstance(loop.target,ast.Tuple) else [loop.target]
                values=row if isinstance(loop.target,ast.Tuple) else [row]
                for target,value in zip(targets,values):
                    if not isinstance(target,ast.Name):raise ValueError("Unsupported target")
                    local[target.id]=value
                if all(self.value(test,local) for test in loop.ifs):out.append(self.value(n.elt,local))
            return out
        raise ValueError("Non-literal page expression")

def pages(root):
    registry=Static(root).module("os_accounts").get("PAGE_REGISTRY")
    if not isinstance(registry,list) or len(registry)>200:raise ValueError("Page registry cannot be resolved statically; no application code was executed")
    out=[{"key":"__signin__","route":"","label":"Sign in","group":"Session"}]
    for row in registry:
        if not all(isinstance(row.get(k),str) and 0<len(row[k])<120 for k in ("key","route","label")):raise ValueError("Invalid page definition")
        out.append({k:row[k] for k in ("key","route","label")}|{"group":row.get("parent_key","OS pages")})
    return out
