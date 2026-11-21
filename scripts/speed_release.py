"""Exact-commit Speed release from its owned Studio branch; never touches local main.

Reuses the normal deployment helper's Git-object export and offline validation.
The only new path is publishing an already committed, preview-verified task SHA.
Render verification remains explicit after GitHub's normal auto-deploy trigger.
"""
import argparse
import json
import math
from pathlib import Path
import re
import statistics
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts' / 'studio'), str(ROOT / 'scripts'), str(ROOT)]
import studio
from sports_cave_deploy import Git, ORIGINS, Stop, export_tree, safe_path, validate

INSTALLATION_BASE = 'bcd10fe0f0ab67e7408238b02c8362b5e088e1ea'
INSTALLATION_TASK = '20261121-d5f7b916'


def reviewed_server_source(before, after):
    # Fresh user authorisation covers installing Speed's report routes. Accept
    # only those two additions, never a general sensitive-file override.
    anchor = b'from worker_health_api import ROUTES as WORKER_HEALTH_ROUTES\n'
    route = b'        *WORKER_HEALTH_ROUTES,\n'
    if before.count(anchor) != 1 or before.count(route) != 1:
        raise Stop('Server route anchors changed; separate source review required.')
    expected = before.replace(anchor, anchor + b'from speed_optimisation_api import ROUTES as SPEED_OPTIMISATION_ROUTES\n')
    expected = expected.replace(route, route + b'        *SPEED_OPTIMISATION_ROUTES,\n')
    if after != expected:
        raise Stop('Server change exceeds the authorised Speed route registration.')


def check_gate(gate, head, base, task_id):
    if gate.get('commit') != head or gate.get('phase2_verified') is not True or gate.get('functional_checks_passed') is not True:
        raise Stop('Exact-commit synthetic preview and functional evidence required.')
    if gate.get('purpose') == 'installation':
        if base != INSTALLATION_BASE or task_id != INSTALLATION_TASK:
            raise Stop('Installation exception is limited to the initial authorised Speed task and base.')
        return
    if gate.get('behaviour_preserved') is not True:
        raise Stop('Nightly fixes require behaviour and visual parity.')
    samples = [gate.get(key) for key in ('baseline_samples_ms', 'candidate_samples_ms')]
    if any(not isinstance(values, list) or len(values) < 3 or any(
            type(n) not in (int, float) or not math.isfinite(n) or n <= 0 for n in values) for values in samples):
        raise Stop('Repeated finite baseline/candidate workflow measurements required.')
    before, after = (statistics.median(values) for values in samples)
    if not (after < before or (gate.get('code_smaller') is True and after <= before)):
        raise Stop('No proven improvement or non-regressing cleanup.')


def release(root, task_id, owner, base, evidence, push=False):
    git = Git(root)
    for attempt in range(30):
        try:
            with studio.locked(studio.DEFAULT_HOME) as file:
                registry = studio.read(file)
                task = studio.task_by_id(registry, task_id, owner)
                if studio.identity(registry, task).resolve() != root.resolve():
                    raise Stop('Release must use its exact owned Studio worktree.')
            break
        except RuntimeError as error:
            if not str(error).startswith('Registry occupied.') or attempt == 29:
                raise
            time.sleep(1)
    if git.text('status', '--porcelain'):
        raise Stop('Commit and test only the focused task files first. Working tree must be clean.')
    if git.text('remote', 'get-url', 'origin') not in ORIGINS or git.text('remote', 'get-url', '--push', 'origin') not in ORIGINS:
        raise Stop('Unexpected GitHub origin.')
    head = git.text('rev-parse', 'HEAD')
    if not re.fullmatch('[0-9a-f]{40}', base):
        raise Stop('Pin the exact reviewed main revision.')
    git.run('merge-base', '--is-ancestor', base, head)
    paths = git.text('diff', '--name-only', base, head).splitlines()
    if not paths:
        raise Stop('No Speed changes selected.')
    gate = json.loads(evidence.read_text(encoding='utf-8'))
    check_gate(gate, head, base, task_id)
    selected = {name: git.run('show', head + ':' + name) if (root / name).exists() else None for name in paths}
    for name in paths:
        if name == 'sports_cave_server.py' and base == INSTALLATION_BASE and task_id == INSTALLATION_TASK:
            reviewed_server_source(git.run('show', base + ':' + name), selected[name])
        else:
            safe_path(root, name)
    manifest = {'version': 1, 'mode': 'normal', 'base': base,
                'tests': ['tests.test_speed_release.SpeedReleaseChecks'],
                'imports': ['speed_optimisation', 'speed_optimisation_api'],
                'files': [{'path': name} for name in paths]}
    with tempfile.TemporaryDirectory(prefix='sports-cave-speed-release-') as directory:
        candidate = Path(directory) / 'candidate'
        candidate.mkdir()
        export_tree(git, head, candidate)
        validate(candidate, selected, manifest)
    if git.text('status', '--porcelain') or git.text('rev-parse', 'HEAD') != head:
        raise Stop('Source changed during release validation.')
    git.run('fetch', 'origin', 'refs/heads/main:refs/remotes/origin/main')
    if git.text('rev-parse', 'origin/main') != base:
        raise Stop('GitHub main advanced. Reconcile, retest and refresh exact preview evidence.')
    receipt = {'commit': head, 'base': base, 'files': paths, 'validated': True, 'pushed': False}
    if push:
        git.run('push', 'origin', head + ':refs/heads/main')
        remote = git.text('ls-remote', 'origin', 'refs/heads/main').split()[0]
        if remote != head:
            raise Stop('GitHub push revision mismatch. Stop and inspect; do not push again.')
        receipt['pushed'] = True
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--id', required=True)
    parser.add_argument('--owner', required=True)
    parser.add_argument('--base', required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--push', action='store_true')
    args = parser.parse_args()
    print(json.dumps(release(ROOT, args.id, args.owner, args.base, args.evidence, args.push), indent=2))


if __name__ == '__main__':
    main()
