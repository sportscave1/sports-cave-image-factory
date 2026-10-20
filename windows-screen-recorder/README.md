# Windows desktop recorder — Phase 1

Status: **local foundation and bounded Windows assessment complete; desktop recording and playback are not implemented or installed.**

This is a component folder in the existing repository on `main`, not an isolated
checkout. The user explicitly assigned this folder. See `ownership.json` before
editing shared files. No parent branch, Studio registry or existing worktree was
changed. There is no registered Studio task for this folder; do not report it as
Studio-tested or release-ready.

- [Assessment, reuse map and Phase 2 handoff](PHASE1.md)
- [Recovery manifest](recovery/manifest.json) — 67 source files; all 40 dirty/untracked paths.
- [Recoverable source archive](recovery/recorder-source.zip)
- [Windows observations](windows-observations.json)
- [Verification](verification.json)

The Python foundation implements a serialized recording lifecycle, explicit
desktop schema and capability checks, immutable saved definitions, recoverable
drafts, and cancellation/cleanup boundaries. It has no native input backend,
global hooks, toolbar, background service, task runner or network connection.
The storage adapter takes the existing recorder's `atomic` and `Store.revision`
functions; tests load those unchanged from the checkpoint into disposable storage.
Do not point it at installed helper data.

Run these checks from this folder:

```powershell
& '..\.venv\Scripts\python.exe' -B -m unittest discover -s tests -p test_foundation.py -v
node tests/diagnostics.test.mjs
```

Read-only Windows diagnostic entry point, within the supported Computer Use
`node_repl` runtime after following that skill's initialization:

```javascript
var diagnostic = await import("file:///C:/Users/hello/Documents/sports-cave-image-factory/windows-screen-recorder/diagnostics.mjs");
nodeRepl.write(await diagnostic.listWindows(sky));
// Select one current, non-sensitive test window ID from that returned inventory.
nodeRepl.write(await diagnostic.inspectWindow(sky, selectedWindowId));
```

No direct COM, PowerShell UIA, helper protocol or debugging port is used. The
diagnostic requests a single accessibility snapshot of the selected window,
without screenshot or activation. It emits at most 100 control roles/indexes,
disabled flags and focus presence. Indexes are diagnostic-only and expire with
the snapshot. It does not persist names, titles, values or document text.
The runtime internally returns a window tree which can contain document text:
select harmless windows; this is not yet the production privacy-safe capture
adapter. No automatic repetition, arbitrary background monitoring or execution
is available. Normal Node without the supported `sky` client cannot inspect
Windows through this module.

Extract the source archive into a separate review directory to recover it.
Verify its entries against the manifest SHA-256 hashes. Do not extract over the
old owned task or the shared parent repository. The archive is a source subset,
not a runnable whole-project clone or backup of installed task data.
