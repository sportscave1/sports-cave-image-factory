"""Guarded Git deployment. No Render API, app imports, migrations or credentials.

Run through deploy.ps1 from the repository. Tests use disposable local origins;
the CLI always requires the real Sports Cave origin and the main branch.
"""
from __future__ import annotations

import argparse
import ast
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tokenize
from fnmatch import fnmatchcase
from collections.abc import Callable

REPOSITORY = "sportscave1/sports-cave-image-factory"
ORIGINS = {
    f"https://github.com/{REPOSITORY}",
    f"https://github.com/{REPOSITORY}.git",
    f"git@github.com:{REPOSITORY}.git",
    f"ssh://git@github.com/{REPOSITORY}.git",
}

# Deliberately specific: shopify_theme/assets is a served OS runtime, not an audit.
LOCAL_ONLY_PATTERNS = (
    '.tmp-*', 'shopify_theme_reviews/*', 'test-results/*',
    'artifacts/email-sent-verification/*', 'tmp/pdfs/certificate-layout-check/*',
    'docs/evidence/*', 'et', '.env', '.env.*', '.streamlit/secrets.toml',
    'client_secret.json', 'token.json', 'credentials.json', 'service-account.json',
    '.shopify/*', '.render/*',
)


def local_only_path(name: str) -> bool:
    name = name.replace('\\', '/').casefold()
    if name in {'.env.example', '.env.sample'}:
        return False
    return any(fnmatchcase(name, pattern) for pattern in LOCAL_ONLY_PATTERNS)


def validate_deploy_paths(git: 'Git') -> None:
    # Deletions used to untrack old evidence are permitted; inspect the final index.
    blocked = sorted(name for name in git.names('ls-files', '-z') if local_only_path(name))
    if blocked:
        sample = ', '.join(blocked[:5])
        raise DeployError(f'Local-only files remain in the Git index ({len(blocked)}): {sample}. '
                          'Remove from the index with git rm --cached; keep local files.')


class DeployError(RuntimeError):
    pass


class Git:
    def __init__(self, root: Path):
        self.root = root

    def run(self, *args: str, allowed: tuple[int, ...] = (0,), input: bytes | None = None) -> bytes:
        result = subprocess.run(["git", *args], cwd=self.root, capture_output=True, input=input)
        command = next(arg for arg in args if not arg.startswith("-"))
        if result.returncode not in allowed:
            # Never echo remote URLs/credentials. Local check diagnostics are safe.
            if args[:2] == ("diff", "--cached") or args[0] == "commit":
                print((result.stdout + result.stderr).decode("utf-8", "replace"))
            raise DeployError(f"git {command} failed (exit {result.returncode}); stopped.")
        if result.stderr and command in {"add", "diff"}:
            print(result.stderr.decode("utf-8", "replace").rstrip())
        return result.stdout

    def text(self, *args: str) -> str:
        return self.run(*args).decode("utf-8").strip()

    def names(self, *args: str) -> set[str]:
        return {os.fsdecode(p) for p in self.run(*args).split(b"\0") if p}


def normalize(path: Path) -> bool:
    """Repair only syntax-proven harmless whitespace, never literal strings.

    Python and JSON get equivalence checks. Other formats/literal HTML/JS are
    deliberately left for manual review; changing those can change output.
    """
    suffix = path.suffix.lower()
    if suffix not in {".py", ".json"} or path.is_symlink() or not path.is_file():
        return False
    original = path.read_bytes()
    if b"\0" in original:
        return False
    try:
        source = original.decode("utf-8-sig")
    except UnicodeDecodeError:
        return False
    protected: set[int] = set()
    try:
        if suffix == ".py":
            before = ast.dump(ast.parse(source), include_attributes=False)
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                if token.type == tokenize.STRING:
                    protected.update(range(token.start[0], token.end[0] + 1))
        elif suffix == ".json":
            before = json.loads(source)
        else:
            return False
        lines = source.splitlines(keepends=True)
        cleaned = []
        for number, line in enumerate(lines, 1):
            ending = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            body = line[:-len(ending)] if ending else line
            cleaned.append((body if number in protected else body.rstrip(" \t")) + ending)
        while cleaned and not cleaned[-1].strip() and len(cleaned) not in protected:
            cleaned.pop()
        candidate = "".join(cleaned)
        if candidate and not candidate.endswith("\n"):
            candidate += "\r\n" if "\r\n" in source else "\n"
        after = ast.dump(ast.parse(candidate), include_attributes=False) if suffix == ".py" else json.loads(candidate)
        if before != after:
            return False
    except (SyntaxError, ValueError, tokenize.TokenError, IndentationError):
        return False
    encoded = candidate.encode("utf-8")
    if original.startswith(b"\xef\xbb\xbf"):
        encoded = b"\xef\xbb\xbf" + encoded
    if encoded == original:
        return False
    path.write_bytes(encoded)
    return True


def validate_staged(git: Git, names: set[str]) -> None:
    """Compile staged Python without executing it or creating bytecode."""
    for name in sorted(names):
        if not name.endswith(".py") or not (git.root / name).is_file():
            continue
        try:
            compile(git.run("show", f":{name}"), name, "exec")
        except SyntaxError as exc:
            raise DeployError(f"Python syntax error: {name}:{exc.lineno}: {exc.msg}") from None


def deploy(
    root: Path, message: str, *, paths: list[str] | None = None,
    check_only: bool = False, push_existing: bool = False,
    expected_origin: str | None = None,
    validate: Callable[[Git, set[str]], None] = validate_staged,
) -> str:
    git = Git(root)
    actual_root = Path(git.text("rev-parse", "--show-toplevel")).resolve()
    if actual_root != root.resolve() or not (root / "sports_cave_server.py").is_file():
        raise DeployError("Run from the Sports Cave repository root.")
    if git.text("branch", "--show-current") != "main":
        raise DeployError("Production uses main; refusing detached HEAD or another branch.")
    origins = {expected_origin} if expected_origin else ORIGINS
    if git.text("remote", "get-url", "origin") not in origins or git.text("remote", "get-url", "--push", "origin") not in origins:
        raise DeployError("origin fetch/push must both be the Sports Cave repository.")
    # No continuation of merges/rebases/cherry-picks, including conflict-free ones.
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
        marker_path = Path(git.text("rev-parse", "--git-path", marker))
        if not marker_path.is_absolute():
            marker_path = root / marker_path
        if marker_path.exists():
            raise DeployError("Finish or cancel the current Git operation before deploying.")
    if git.run("ls-files", "--unmerged", "-z"):
        raise DeployError("Unresolved Git conflicts; deployment stopped.")
    validate_deploy_paths(git)
    print("Repository verified. Branch: main. Fetching origin/main...", flush=True)
    git.run("fetch", "origin", "refs/heads/main:refs/remotes/origin/main")
    local = git.text("rev-parse", "HEAD")
    remote = git.text("rev-parse", "refs/remotes/origin/main")
    staged = git.names("diff", "--cached", "--name-only", "-z", "--no-renames")
    unstaged = git.names("diff", "--name-only", "-z", "--no-renames")
    untracked = git.names("ls-files", "--others", "--exclude-standard", "-z")
    if not (staged | unstaged | untracked):
        print("Working tree clean — nothing new to commit.")
        print("HEAD matches origin/main." if local == remote else "HEAD differs from origin/main; no automatic commit or push.")
        if not push_existing or local == remote:
            print("NOTHING TO DEPLOY")
            return "NOTHING TO DEPLOY"
    if git.text("merge-base", local, remote) != remote:
        raise DeployError("origin/main has commits missing locally. Reconcile it first; no automatic merge/force push.")
    if push_existing and (staged | unstaged | untracked):
        raise DeployError("--push-existing requires a clean tree; preserve/commit changes first.")
    if paths:
        intended = set()
        changed = staged | unstaged | untracked
        for name in paths:
            resolved = (root / name).resolve()
            if not resolved.is_relative_to(root.resolve()):
                raise DeployError("Selected paths must stay within this repository.")
            relative = resolved.relative_to(root.resolve()).as_posix()
            selected = {p for p in changed if relative == "." or p == relative or p.startswith(relative + "/")}
            if not selected:
                raise DeployError(f"No changed files match selected path: {name}")
            intended.update(selected)
        if staged - intended:
            raise DeployError("Other files are already staged. Unstage them or include them explicitly.")
    else:
        # A staged selection is authoritative. Never swallow partially staged edits.
        intended = staged or (unstaged | untracked)
    if staged & unstaged & intended:
        raise DeployError("Partially staged files detected. Finish staging or unstage those files first; selection preserved.")
    # git rm --cached deliberately leaves local evidence on disk. Do not re-add it.
    index_removals = git.names('diff', '--cached', '--name-only', '--diff-filter=D', '-z')
    to_stage = intended - index_removals
    print(f"Changes: {len(staged)} staged, {len(unstaged)} unstaged, {len(untracked)} untracked.")
    for name in sorted(intended):
        print(f"  {name}")
        if name in to_stage and normalize(root / name):
            print(f"  Repaired harmless whitespace: {name}")
    if to_stage:
        # Literal pathspecs prevent wildcard/metacharacter filenames staging others.
        # NUL-delimited stdin avoids Windows command-length limits and shell quoting.
        git.run("--literal-pathspecs", "add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul",
                input=b'\0'.join(os.fsencode(name) for name in sorted(to_stage)) + b'\0')
    validate_deploy_paths(git)
    staged = git.names("diff", "--cached", "--name-only", "-z", "--no-renames")
    git.run("diff", "--cached", "--check")
    if not staged and not push_existing:
        print("NOTHING TO DEPLOY — no staged changes after safe normalization.")
        return "NOTHING TO DEPLOY"
    # Also validate already-committed changes after an earlier rejected push.
    validate(git, staged | git.names("diff", "--name-only", "-z", remote, "HEAD"))
    if check_only:
        print("CHECKS PASSED — selected changes staged; no commit or push.")
        return "CHECKS PASSED"
    if staged:
        if not message.strip():
            raise DeployError("Provide a non-empty commit message.")
        git.run("commit", "-m", message)
        print("COMMITTED", flush=True)
    # Reject hook-created unstaged deltas in the just-committed selection.
    if git.run("diff", "--cached", "--name-only") or (intended & git.names("diff", "--name-only", "-z")):
        raise DeployError("Files changed during commit; inspect them before pushing.")
    local = git.text("rev-parse", "HEAD")
    git.run("push", "origin", "HEAD:refs/heads/main")
    git.run("fetch", "origin", "refs/heads/main:refs/remotes/origin/main")
    if git.text("rev-parse", "refs/remotes/origin/main") != local:
        raise DeployError("Push verification failed: HEAD differs from origin/main.")
    print("PUSHED — local HEAD matches origin/main. Render build status must be checked separately.")
    return "PUSHED"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message", default="Deploy Sports Cave OS updates")
    parser.add_argument("--path", action="append")
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--push-existing", action="store_true")
    args = parser.parse_args()
    try:
        root = Path(__file__).resolve().parents[1]
        # Avoid silently deploying a different checkout when launched elsewhere.
        cwd_root = Git(Path.cwd()).text("rev-parse", "--show-toplevel")
        if Path(cwd_root).resolve() != root:
            raise DeployError("Run this helper inside its Sports Cave checkout.")
        deploy(root, args.message, paths=args.path, check_only=args.check_only, push_existing=args.push_existing)
        return 0
    except (DeployError, OSError) as exc:
        print(f"DEPLOYMENT STOPPED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
