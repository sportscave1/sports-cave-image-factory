"""Export only read-path definitions for isolated, non-deploying SQL profiling."""
import ast
import json
from pathlib import Path
import sys
import textwrap


def build(root):
    def function(file, name):
        source = (root / file).read_text(encoding='utf-8')
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
        return ast.get_source_segment(source, node) + '\n'
    def methods(file, cls, names):
        source = (root / file).read_text(encoding='utf-8')
        node = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == cls)
        result = ''
        for method in node.body:
            if isinstance(method, ast.FunctionDef) and method.name in names:
                value = textwrap.dedent(ast.get_source_segment(source, method))
                # get_source_segment leaves the first line unindented.
                value = value.splitlines()[0] + '\n' + textwrap.dedent('\n'.join(value.splitlines()[1:]))
                value = value.splitlines()[0] + '\n' + textwrap.indent('\n'.join(value.splitlines()[1:]), '    ')
                value = value.replace('def '+method.name+'(', 'def _v20_'+method.name+'(', 1)
                result += value + '\n'+cls+'.'+method.name+' = _v20_'+method.name+'\n'
        return result
    return {
        'orders_read_executor': (root/'orders_read_executor.py').read_text(),
        'orders_read_batch': (root/'orders_read_batch.py').read_text(),
        'orders_display_reads': (root/'orders_display_reads.py').read_text(),
        'auto_editions_store': methods('auto_editions_store.py', 'Preparations', {'layouts','index'}),
        'auto_editions_quality_store': methods('auto_editions_quality_store.py', 'Quality', {'index'}),
        'auto_editions_runtime': function('auto_editions_runtime.py', 'download_links'),
        'supabase_backend': function('supabase_backend.py', 'list_hybrid_order_rows'),
        'orders_page': 'from orders_read_executor import ReadQueueFull\n' + function('orders_page.py', '_order_display_resources'),
    }


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[1]
    bundle = build(root)
    for name, source in bundle.items(): compile(source, name, 'exec')
    Path(sys.argv[1]).write_text(json.dumps(bundle), encoding='utf-8')
