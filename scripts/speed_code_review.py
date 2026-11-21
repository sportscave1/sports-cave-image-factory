"""Read-only unused-import candidates for the selected section; never deletes code."""
import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def inspect(root, names):
    results = []
    for name in names:
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or path.suffix != '.py' or not path.is_file():
            raise ValueError('Choose existing Python source files inside the worktree.')
        tree = ast.parse(path.read_text(encoding='utf-8-sig'))
        used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}
        exports = {value.value for node in ast.walk(tree) if isinstance(node, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == '__all__' for t in node.targets)
                   for value in ast.walk(node.value) if isinstance(value, ast.Constant) and isinstance(value.value, str)}
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)) or getattr(node, 'module', '') == '__future__':
                continue
            for alias in node.names:
                bound = alias.asname or (alias.name.split('.')[0] if isinstance(node, ast.Import) else alias.name)
                if bound != '*' and bound not in used and bound not in exports:
                    results.append({'file': name, 'line': node.lineno, 'name': bound,
                                    'status': 'candidate_only',
                                    'required_evidence': 'Check exports, dynamic references, registration side effects and regression tests before removal.'})
    return {'candidates': results, 'code_deleted': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+')
    args = parser.parse_args()
    print(json.dumps(inspect(ROOT, args.files), indent=2))


if __name__ == '__main__':
    main()
