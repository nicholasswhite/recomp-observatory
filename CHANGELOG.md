# Changelog

All notable changes to Recomp Observatory are documented here.

## Unreleased

- Added verified local PS3 presentation manifests for automatic game icons, title overlays, and backgrounds, with manual-cover overrides and share-safe caching.
- Extended detected game backgrounds across the app workspace while keeping the navigation sidebar and dashboard panels readable.
- Reworked the game hero around an adaptive title slot: optional title artwork is alpha-trimmed and adaptively sized, while the semantic text title remains the accessible and error fallback.
- Moved selected game artwork into the sidebar and left-aligned the adaptive title artwork while keeping target and live-observation context inside the hero.

## 0.1.0 — 2026-10-30

- Added multi-game and multi-attempt workspaces with local repository discovery.
- Added independent-report, PS3Recomp-manifest, and metadata-only readers.
- Added translation coverage, successful-build history, raw-SPU scope, implementation receipts, evidence tables, and responsive progress graphs.
- Added local cover uploads and per-game branding without bundled game artwork.
- Added loopback-only serving, bounded reads, isolated history, share-safe packaging, and public contribution/security guidance.
