"""Offline route discovery/rotation. Does not import or start the OS app."""
import argparse
import ast
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from speed_optimisation import fingerprint, prioritise


def discover(root):
    root = Path(root)
    sections = {}
    # Read every source file: new routes and *_page modules need no manual enrolment.
    sources = list(root.glob('*.py'))
    for source in sources:
        try:
            tree = ast.parse(source.read_text(encoding='utf-8-sig'))
        except (SyntaxError, UnicodeError):
            continue
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == 'route' and isinstance(value, ast.Constant) and isinstance(value.value, str):
                        names.add(value.value)
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                if any(isinstance(t, ast.Name) and t.id.endswith('_ROUTE') for t in node.targets):
                    names.add(node.value.value)
        if source.stem.endswith('_page'):
            names.add(source.stem.removesuffix('_page').replace('_', ' ').title())
        for name in names:
            if not name.startswith('/') and name not in {'Speed Optimisation', 'Speed Optimisation Api'}:
                sections.setdefault(name, set()).add(source.name)
    # External surfaces must be located explicitly; never guess domains or repos.
    for name in ('Marketplace', 'Website'):
        matched = [s.name for s in sources if name.lower() in s.stem.lower()]
        if matched:
            sections.setdefault(name, set()).update(matched)
    return [{'name': name, 'files': sorted(files), 'fingerprint': fingerprint(root, files)}
            for name, files in sections.items()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--history', type=Path, help='JSON array of previous reports (local or exported from OS)')
    args = parser.parse_args()
    history = json.loads(args.history.read_text(encoding='utf-8')) if args.history else []
    sections = prioritise(discover(args.root), history)
    print(json.dumps({'next_section': sections[0] if sections else None, 'sections': sections}, indent=2))


if __name__ == '__main__':
    main()
