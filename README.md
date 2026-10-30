# Recomp Observatory

[![CI](https://github.com/nicholasswhite/recomp-observatory/actions/workflows/ci.yml/badge.svg)](https://github.com/nicholasswhite/recomp-observatory/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A local, read-only PlayStation 3 recompilation dashboard for tracking translation coverage, successful build receipts, implementation evidence, and progress over time.

Recomp Observatory does not recompile games itself. It observes reports and repository metadata produced by separate recompilation toolchains. It can group several games and several recompilation attempts in one workspace, keeps each target's history isolated, and makes unknown values explicit. It never treats emitted code, compiled units, function mappings, or a historical runtime sample as proof that a game is complete or playable.

## Highlights

- Multiple games and recompilation attempts in one dashboard.
- Five-second UI refresh with persistent, target-specific history.
- PPU/SPU translation coverage and separately scoped raw-SPU telemetry.
- Successful-build growth, source/build freshness, and implementation-receipt milestones.
- PS3Recomp function-entry and service evidence for a narrowly supported manifest layout.
- Local folder picker, explicit project manifests, custom game branding, and responsive PlayStation-inspired presentation.
- No Python packages, frontend build, cloud service, or database required.

## Safety and evidence boundaries

Recomp Observatory is local-first:

- The server binds only to `127.0.0.1` and rejects non-loopback host headers and cross-site writes.
- Target repositories are read-only. The observer does not execute target scripts, compilers, generated code, tests, games, shaders, or emulators.
- File reads and discovery are bounded. Symlinked target directories and oversized or changing evidence files are rejected or left unknown.
- Workspace configuration, histories, generated observer reports, logs, PIDs, and uploaded artwork stay under the ignored `work/` directory.
- Release packaging uses an explicit allowlist and is checked for private paths, proprietary identifiers, game assets, and runtime data.

Do not bind this server to `0.0.0.0`, expose its port publicly, or place it behind a public reverse proxy. See [SECURITY.md](SECURITY.md).

## Quick start

Requirements:

- Python 3.10 or newer.
- A modern browser.
- Node.js 22 or newer only if you want to run the JavaScript development checks.

### Windows

```powershell
git clone https://github.com/nicholasswhite/recomp-observatory.git
cd recomp-observatory
.\Start Dashboard.cmd
```

### macOS, Linux, or command-line launch

```bash
git clone https://github.com/nicholasswhite/recomp-observatory.git
cd recomp-observatory
python server.py
```

Open [http://127.0.0.1:8768/](http://127.0.0.1:8768/).

There is no application build step. The server uses only the Python standard library and serves the checked-in HTML, CSS, and JavaScript directly.

## Add a repository

Choose **Add repository**, enter or browse to a local repository or parent directory, and select **Scan folder**. Review the detected game, attempt, and toolchain names before saving them.

Discovery inspects at most 1,000 directories to depth four and skips common build, generated, dependency, work, log, and save directories. Folder names and file layouts can only suggest project identity; the user confirms every saved target.

For precise boundaries, add an `observatory.project.json` file to a repository. Start from [observatory.project.example.json](observatory.project.example.json). Relative target roots are resolved from the manifest directory. Attempts for the same game should share a `gameId`; each target must have a unique `id`.

## Report readers

| Reader | Scope |
| --- | --- |
| `independent-reports-v1` | Reads a defined `reports/` schema for PPU/SPU generation, optional raw-SPU generation, native build receipts, imports, recovery, and assets. Combined coverage uses canonical PPU+SPU words only. Raw-SPU remains separate because overlap is not established. |
| `ps3recomp-manifest-v1` | Reads one supported PS3Recomp-oriented manifest and bounded generated-source inventories. It can show function-entry mapping, scoped build identity, service audits, and a pinned historical runtime measurement. It does not invent instruction-emission coverage. |
| `inventory-v1` | Metadata-only fallback for unknown layouts. Translation, build, and runtime metrics remain unknown unless a supported reader supplies them. |

These are schema-specific readers, not universal compatibility claims. See [CONTRIBUTING.md](CONTRIBUTING.md) before proposing another reader.

## What the numbers mean

- **Emission coverage** counts aligned source words for which a generator emitted an implementation. Executable sections can contain data, and emitted semantics can still be wrong or untested.
- **Function-entry mapping** compares known original entry addresses with generated definitions. It is not instruction coverage.
- **Compiled translation units** come from successful build receipts. Unit counts can increase or decrease after refactoring and are not a completion percentage.
- **Implementation receipts** count boolean evidence declared by a build schema. The denominator can grow, and a true flag is not runtime proof.
- **Freshness** compares a bounded set of recorded hashes and modification times. A matching subset is not a whole-build guarantee.
- **Runtime results** remain tied to their recorded executable and measurement scope. A historical sample does not establish current gameplay performance.

Unknown stays unknown: the dashboard does not synthesize whole-game completion, an ETA, decompilation coverage, or gameplay results.

## History and exports

While the server is running, configured targets are sampled sequentially every 30 seconds. History is retained in `work/history/` for up to 10,080 observations per target. Repeated heartbeats are collapsed in the activity view so meaningful report and successful-build changes remain visible.

The progress graph can display supported source bytes, translation coverage, generated functions, unresolved imports, or compiled translation units. It preserves decreases, flags measurement gaps, and can use either a focused or zero-based scale.

**Export statistics** downloads a sanitized summary for the selected target without absolute repository paths, raw reports, source bodies, or assets.

## Artwork and branding

No game artwork is bundled with the public repository. Unknown games use a generated monogram. Use **Edit artwork** to add a local JPEG, PNG, or WebP cover up to 4 MiB, plus optional studio, subtitle, and source-credit metadata.

Uploaded artwork is stored under ignored local workspace data and is excluded from source packages.

## Development

Run the full observer test suite and JavaScript checks:

```text
python -m unittest discover -v
node --check public/app.js
node --check public/workspace-ui.js
node --check public/progress.js
node test_progress.cjs
python package_dashboard.py
python verify_package.py work/recomp-observatory.zip
```

Tests create synthetic fixtures only; they never execute or modify a target project.

To use a different ignored local workspace or port:

```text
python server.py --workspace work/secondary-workspace.json --port 8768
python server.py --source "C:\Git\my-repository"
python server.py --source /home/user/my-repository
```

Writable workspace catalogs are deliberately confined to this dashboard's ignored `work/` folder. Target repositories remain read-only.
Repository source paths must be absolute, and manifest-declared targets must remain inside the selected repository folder.
Repository sources must be absolute local paths. Targets declared by `observatory.project.json` must remain inside the folder selected for discovery.

## Source packages

```text
python package_dashboard.py
```

This creates `work/recomp-observatory.zip` from an explicit public allowlist. The package includes source, launchers, documentation, tests, and the package verifier. It excludes workspace configuration, histories, reports, logs, uploaded artwork, screenshots, and all target-project data.

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md), especially the rules around synthetic fixtures, bounded readers, proprietary material, and honest metric scopes.

## License and trademarks

Recomp Observatory is available under the [MIT License](LICENSE).

This project is independent and unaffiliated with Sony Interactive Entertainment, PlayStation, game publishers, game developers, or the projects whose report formats it observes. Product names, trademarks, and artwork belong to their respective owners.

## Acknowledgements

The interface includes a community acknowledgement for the PS3Recomp maintainers and contributors whose open tooling and documentation have helped advance PS3 recompilation research. Recomp Observatory is an independent observer and does not bundle PS3Recomp code.
