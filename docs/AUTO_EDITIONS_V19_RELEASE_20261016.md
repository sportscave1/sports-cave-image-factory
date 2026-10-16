# Auto Editions V19 release — 16 October 2026

The owner authorised committing, pushing and deploying completed project work.
The release starts from verified live revision
`b7dfa951103d709a07eece1391a154034eb6e787`, which already contains V18,
trusted automatic visual approval safeguards and Orders V20. The two completed
Files V6 commits have patch-equivalent commits on main and are not reapplied.
Unfinished task worktrees are preserved.

This release adds native Photoshop stage instrumentation, an isolated benchmark
harness, strict output comparisons and conservative cleanup/ownership recovery.
The existing `duplicate_merged` exporter remains the production default.
`history_merged_crop` remains restricted to the explicitly isolated native
benchmark. Real Photoshop speedup is unverified because active companion
ownership prevented safe benchmarking; model tests are not native benchmarks.

Automatic visual approval remains opt-in, with an empty approved reference
policy registry. This release does not enable it or approve existing artwork.
Supplier approval requirements remain in force. No live companion installation,
original Dropbox PSD, queue, edition allocation, certificate or asset is changed
by this release operation. The installed companion requires a separate safe
idle update to consume the new local scripts.

The original V19 task and its evidence remain intact. See
`AUTO_EDITIONS_V19_NATIVE_PERFORMANCE.md` for benchmark limitations and quality
protections. Combined release validation is recorded in the isolated release
task's `output/release/` and Developer Studio test evidence.

Only the existing canonical `sports-cave-os` Render service is updated through
its Git-backed main branch. No Blueprint sync or infrastructure change is needed.
