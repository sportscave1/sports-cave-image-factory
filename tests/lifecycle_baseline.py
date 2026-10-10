"""Load saved, pre-task Python sources with their original resource paths."""
import importlib.abc,importlib.util,sys,linecache
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
class Baseline(importlib.abc.MetaPathFinder,importlib.abc.Loader):
    def find_spec(self,fullname,path=None,target=None):
        if '.' not in fullname and (ROOT/'tmp/lifecycle-baseline'/f'{fullname}.py').is_file():
            return importlib.util.spec_from_loader(fullname,self)
    def create_module(self,spec):return None
    def exec_module(self,module):
        module.__file__=str(ROOT/(module.__name__+'.py'))
        source=(ROOT/'tmp/lifecycle-baseline'/(module.__name__+'.py')).read_text(encoding='utf-8-sig')
        linecache.cache[module.__file__]=(len(source),None,source.splitlines(keepends=True),module.__file__)
        exec(compile(source,module.__file__,'exec'),module.__dict__)

def install():sys.meta_path.insert(0,Baseline())
