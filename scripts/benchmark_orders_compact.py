"""CPU-only render preparation comparison; no database, API or writes."""
import ast
import json
from pathlib import Path
import statistics
import subprocess
import sys
import timeit
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import orders_page as orders

source=subprocess.check_output(['git','show','HEAD:orders_page.py'],text=True)
tree=ast.parse(source)
functions=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('_selected_rows_from_state','_display_rows')]
baseline=dict(vars(orders))
exec(compile(ast.Module(body=functions,type_ignores=[]),'baseline','exec'),baseline)
rows=[{'order':f'#SC{3000+i//2}','edition_number':i+1,'allocation_index':i%2+1,
       'variant':'Black / 60 x 90 cm','customer':'Fixture Collector'} for i in range(62)]
baseline['_selected_indices_from_state']=lambda:[]
def before():
    baseline['_selected_rows_from_state'](rows)
    return baseline['_display_rows']([orders._normalise_row(r) for r in rows])
def after():
    orders._selected_rows_from_state(rows)
    return orders._display_rows([orders._normalise_row(r) for r in rows],normalised=True)
with patch.object(orders,'_selected_indices_from_state',return_value=[]):
    assert before()==after()
    result={key:round(statistics.median(timeit.repeat(fn,number=100,repeat=7))*10,3) for key,fn in [('before_ms',before),('after_ms',after)]}
    result.update(rows=62,before_normalisations=186,after_normalisations=62)
    print(json.dumps(result))
