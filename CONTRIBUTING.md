# Contributing to Recomp Observatory

Thanks for helping make recompilation work easier to understand.

## Ground rules

- Submit only software, documentation, and synthetic fixtures you are allowed to redistribute.
- Never attach or commit game binaries, firmware, keys, saves, proprietary reports, generated game code, copyrighted cover art, or private filesystem paths.
- Keep target repositories read-only. An adapter may inspect bounded files and metadata; it must never import or execute target tools, compilers, games, or tests.
- Preserve evidence boundaries. Unknown values stay `null`; emitted-code coverage, function mapping, compiled units, and runtime results must not be presented as whole-game completion.
- New readers must be schema-specific. Do not reuse counters from another toolchain merely because filenames look similar.

## Development setup

Recomp Observatory requires Python 3.10 or newer and has no third-party Python dependencies. Node.js is used only for JavaScript checks.

```text
python -m unittest discover -v
node --check public/app.js
node --check public/workspace-ui.js
node --check public/progress.js
node test_progress.cjs
python package_dashboard.py
```

Tests must use isolated synthetic repositories under the dashboard's ignored `work/` directory. Never point tests at a real game project.

## Pull requests

Explain the evidence contract for any new metric or adapter. Include tests for malformed, missing, changing, and out-of-scope inputs. Confirm that release packaging contains no local workspace data or third-party game assets.
