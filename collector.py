"""Read-only, bounded telemetry for native recompilation projects.

Only report JSON and source/document file metadata are inspected. This module
never imports the port's Python modules or executes its tools or target code.
Emission coverage measures original aligned words with an emitter, not playable
game completion, correctness, reachability, or byte equality with native output.
"""

from __future__ import annotations

import json
import hashlib
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pathguard import is_safe_entry

_REPORTS = (
    "ppu-generation.json", "spu-generation.json", "spu-raw-generation.json", "native-build.json",
    "static-image.json", "inventory.json", "self-recovery.json",
    "spu-assets.json", "input-provenance.json",
)
_OPTIONAL_REPORTS = {"spu-raw-generation.json"}
_MAX_REPORT_BYTES = 16 * 1024 * 1024
_MAX_ARCHIVED_BUILD_REPORTS = 128
_CACHE: dict[str, tuple[tuple[int, int], dict | None, str | None]] = {}
_HASH_CACHE: dict[str, tuple[tuple[int, int], str]] = {}
_LOCK = threading.RLock()


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _boolean(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _array(value: Any) -> list:
    return value if isinstance(value, list) else []


def _mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _bytes(words: int | None) -> int | None:
    return words * 4 if words is not None else None


def _small_file_hash(path: Path) -> str:
    """Hash bounded telemetry/source files, caching unchanged file identities."""
    before = path.stat()
    if before.st_size > _MAX_REPORT_BYTES:
        raise ValueError("File exceeds the 16 MiB identity-check limit")
    signature = (before.st_mtime_ns, before.st_size)
    cached = _HASH_CACHE.get(str(path))
    if cached and cached[0] == signature:
        return cached[1]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    after = path.stat()
    if (after.st_mtime_ns, after.st_size) != signature:
        raise ValueError("File changed during identity check")
    _HASH_CACHE[str(path)] = (signature, digest)
    return digest


def _recorded_identity(root: Path, recorded: dict) -> dict:
    result: dict[str, Any] = {"checked": 0, "changed": [], "unavailable": [], "excluded": 0}
    for filename, expected in recorded.items():
        path = Path(filename)
        if not path.is_absolute():
            path = root / path
        try:
            path = path.resolve()
            relative = path.relative_to(root)
            # Generated source, original binaries and libraries are excluded.
            if not relative.parts or relative.parts[0] not in {"src", "tools"}:
                result["excluded"] += 1
                continue
            digest = _small_file_hash(path)
            result["checked"] += 1
            if digest != expected:
                result["changed"].append(relative.as_posix())
        except (OSError, ValueError) as exc:
            result["unavailable"].append({"path": filename if not path.is_absolute() else path.name, "message": str(exc)})
    return result


def _read_report(root: Path, name: str) -> tuple[dict, dict]:
    path = root / "reports" / name
    evidence: dict[str, Any] = {"name": name, "path": f"reports/{name}", "modifiedAt": None, "size": None, "status": "missing", "error": None}
    try:
        if not path.resolve().is_relative_to(root):
            raise ValueError("Report resolves outside the selected source root")
        before = path.stat()
        evidence.update(modifiedAt=_iso(before.st_mtime), size=before.st_size)
        signature = (before.st_mtime_ns, before.st_size)
        cached = _CACHE.get(str(path))
        if cached and cached[0] == signature:
            data, error = cached[1:]
        else:
            data, error = None, None
            try:
                if before.st_size > _MAX_REPORT_BYTES:
                    raise ValueError("Report exceeds the 16 MiB read limit")
                data = json.loads(path.read_text(encoding="utf-8-sig"))
                after = path.stat()
                if (after.st_mtime_ns, after.st_size) != signature:
                    raise ValueError("Report changed while being read; waiting for the next refresh")
                if not isinstance(data, dict):
                    raise ValueError("Report JSON must be an object")
            except (OSError, UnicodeError, ValueError) as exc:
                data, error = None, str(exc)
            _CACHE[str(path)] = (signature, data, error)
        evidence.update(status="ok" if data is not None else "unavailable", error=error)
        return data or {}, evidence
    except FileNotFoundError:
        evidence["error"] = "Report has not been found"
    except (OSError, ValueError) as exc:
        evidence.update(status="unavailable", error=str(exc))
    return {}, evidence


def _emission(report: dict, evidence: dict, processor: str, errors: list) -> dict:
    total = _integer(report.get("words_processed"))
    implemented = _integer(report.get("words_with_implemented_emission"))
    unsupported = _integer(report.get("words_with_explicit_unimplemented_failure"))
    consistent = all(v is not None for v in (total, implemented, unsupported)) and implemented + unsupported == total
    if report and not consistent:
        errors.append({"path": evidence["path"], "message": "Emission counts are missing or inconsistent; coverage is unknown"})
    units = report.get("translation_units")
    return {
        "available": bool(report), "words": total, "implementedWords": implemented,
        "unsupportedWords": unsupported, "sourceBytes": _bytes(total),
        "emittedSourceBytes": _bytes(implemented), "unsupportedSourceBytes": _bytes(unsupported),
        "emissionPercent": round(implemented * 100 / total, 4) if consistent and total else None,
        "translationUnits": len(units) if isinstance(units, list) else None,
        "nativeChunks": _integer(report.get("native_chunks")),
        "imageCount": len(report["images"]) if isinstance(report.get("images"), list) else (len(report["source_words_by_image"]) if isinstance(report.get("source_words_by_image"), dict) else None),
        "generatedAt": evidence["modifiedAt"], "reportPath": evidence["path"],
        "generationSeconds": report.get("generation_seconds"),
        "limitations": _array(report.get("limitations")),
        "basis": "Aligned source words × 4 bytes. Includes possible embedded data; emitted semantics are untested.",
        "processor": processor,
    }


def _component_rows(report: dict) -> list[dict]:
    """Return report-declared implementation flags, not completion claims."""
    excluded = {"tests_run", "game_run", "game_complete"}
    return [
        {"name": key, "value": value}
        for key, value in report.items()
        if isinstance(value, bool) and key not in excluded
    ]


def _component_summary(rows: list[dict]) -> dict:
    true_count = sum(row.get("value") is True for row in rows)
    false_count = sum(row.get("value") is False for row in rows)
    return {
        "available": bool(rows),
        "trueCount": true_count if rows else None,
        "falseCount": false_count if rows else None,
        "total": len(rows) if rows else None,
        "basis": "Boolean implementation evidence declared by the selected build receipt. Counts are not whole-game completion.",
    }


def _read_archived_build(path: Path, root: Path) -> tuple[dict, float] | None:
    """Read one tightly bounded archived receipt without exposing its contents."""
    try:
        resolved = path.resolve()
        if path.is_symlink() or not resolved.is_relative_to(root):
            return None
        before = path.stat()
        if before.st_size > _MAX_REPORT_BYTES:
            return None
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        after = path.stat()
        if (after.st_mtime_ns, after.st_size) != (before.st_mtime_ns, before.st_size):
            return None
        if not isinstance(value, dict) or _integer(value.get("translation_units")) is None:
            return None
        return value, before.st_mtime
    except (OSError, UnicodeError, ValueError):
        return None


def _build_milestone_history(root: Path, current: dict, current_stamp: str | None) -> list[dict]:
    """Compare same-target archived build receipts using only their declared booleans."""
    candidates: list[tuple[dict, float]] = []
    work = root / "work"
    try:
        if is_safe_entry(work, root) and work.is_dir():
            candidate_directories = 0
            for child in work.iterdir():
                if not is_safe_entry(child, root) or not child.is_dir():
                    continue
                candidate_directories += 1
                if candidate_directories > _MAX_ARCHIVED_BUILD_REPORTS:
                    break
                read = _read_archived_build(child / "native-build.json", root)
                if read:
                    candidates.append(read)
    except OSError:
        pass
    if current and current_stamp:
        try:
            stamp = datetime.fromisoformat(current_stamp.replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError):
            stamp = time.time()
        candidates.append((current, stamp))

    # One receipt per linked artifact; saved copies of the current report are common.
    unique: dict[tuple, tuple[dict, float]] = {}
    for report, stamp in candidates:
        artifact = report.get("sha256")
        key = (artifact,) if isinstance(artifact, str) and artifact else (
            _integer(report.get("translation_units")),
            _integer(report.get("bytes")),
            round(stamp),
        )
        previous = unique.get(key)
        if previous is None or stamp > previous[1]:
            unique[key] = (report, stamp)

    ordered = sorted(unique.values(), key=lambda item: item[1])[-24:]
    events, previous_values = [], None
    for report, stamp in ordered:
        rows = _component_rows(report)
        values = {row["name"]: row["value"] for row in rows}
        true_names = {row["name"] for row in rows if row["value"] is True}
        false_names = {row["name"] for row in rows if row["value"] is False}
        newly_true = sorted(name for name in true_names if previous_values is not None and previous_values.get(name) is not True)
        newly_false = sorted(name for name in false_names if previous_values is not None and previous_values.get(name) is True)
        events.append({
            "at": _iso(stamp),
            "translationUnits": _integer(report.get("translation_units")),
            "executableBytes": _integer(report.get("bytes")),
            "trueCount": len(true_names) if rows else None,
            "falseCount": len(false_names) if rows else None,
            "newlyTrue": newly_true[:40],
            "newlyFalse": newly_false[:40],
            "baseline": previous_values is None,
            "scope": "Archived build receipt from this selected target; flags are compile/integration evidence, not whole-game completion.",
        })
        previous_values = values
    return events


def _activity(root: Path, errors: list) -> list[dict]:
    rows = []
    # Deliberately exclude work/, generated output, assets, saves, and third_party/.
    for category in ("src", "tools", "docs", "reports"):
        directory = root / category
        if not directory.exists():
            continue
        try:
            if not is_safe_entry(directory, root):
                errors.append({"path": category, "message": "Metadata scan excludes linked directories outside the selected source root"})
                continue
            for current, directories, filenames in os.walk(directory, followlinks=False):
                current = Path(current)
                if not is_safe_entry(current, root):
                    directories[:] = []
                    continue
                directories[:] = [d for d in directories if not d.startswith(".") and d != "__pycache__" and is_safe_entry(current / d, root)]
                for filename in filenames:
                    path = current / filename
                    if path.suffix.lower() not in {".cpp", ".hpp", ".h", ".c", ".py", ".ps1", ".md", ".json"}:
                        continue
                    if not is_safe_entry(path, root):
                        continue
                    stat = path.stat()
                    rows.append({"path": path.relative_to(root).as_posix(), "category": category, "modifiedAt": _iso(stat.st_mtime), "size": stat.st_size, "_mtime": stat.st_mtime})
                    if len(rows) >= 5000:
                        errors.append({"path": category, "message": "Source metadata scan reached the 5,000-file limit"})
                        return rows
        except OSError as exc:
            errors.append({"path": category, "message": f"Metadata scan incomplete: {exc}"})
    return rows


def _overall_progress(ppu: dict, spu: dict) -> dict:
    """Weight selected PPU/SPU emission by source words; never game completion."""
    valid = all(
        metric.get("emissionPercent") is not None
        and all(_integer(metric.get(key)) is not None for key in ("words", "implementedWords", "unsupportedWords"))
        and metric["implementedWords"] + metric["unsupportedWords"] == metric["words"]
        for metric in (ppu, spu)
    )
    total = sum(metric["words"] for metric in (ppu, spu)) if valid else None
    supported = sum(metric["implementedWords"] for metric in (ppu, spu)) if valid else None
    failures = sum(metric["unsupportedWords"] for metric in (ppu, spu)) if valid else None
    return {
        "translationPercent": round(supported * 100 / total, 4) if total else None,
        "scannedWords": total, "supportedWords": supported, "failureWords": failures,
        "scannedSourceBytes": _bytes(total), "supportedSourceBytes": _bytes(supported),
        "failureSourceBytes": _bytes(failures),
        "decompilationPercent": None, "gameCompletionPercent": None,
        "basis": "Sum of supported PPU and SPU word counts divided by their summed scanned word counts. Selected game/firmware extents and SPU variants may include data; this is report volume, not unique game bytes or game completion.",
        "reportPaths": ["reports/ppu-generation.json", "reports/spu-generation.json"],
    }


def collect_snapshot(root: Path, *, empty: bool = False) -> dict:
    """Return a fresh metadata snapshot; unchanged JSON is cached by size/mtime.

    Missing or malformed report values stay None. Report timestamps are file
    modification times, not a fabricated compiler event or live chat state.
    Calls are serialized so a threaded local server may safely share the cache.
    """
    started = time.perf_counter()
    root = Path(root).resolve()
    with _LOCK:
        errors: list[dict] = []
        reports, evidence = {}, []
        for name in _REPORTS:
            report, item = ({}, {"name": name, "path": f"reports/{name}", "modifiedAt": None, "size": None, "status": "missing", "error": "No report reader supplied"}) if empty else _read_report(root, name)
            reports[name] = report
            evidence.append(item)
            if item["status"] != "ok" and (name not in _OPTIONAL_REPORTS or item["status"] != "missing"):
                errors.append({"path": item["path"], "message": item["error"]})
        ev = {item["name"]: item for item in evidence}
        ppu_report, spu_report = reports["ppu-generation.json"], reports["spu-generation.json"]
        raw_spu_report = reports["spu-raw-generation.json"]
        build_report, link = reports["native-build.json"], reports["static-image.json"]
        recovery_report, provenance = reports["self-recovery.json"], reports["input-provenance.json"]
        assets_report = reports["spu-assets.json"]
        ppu = _emission(ppu_report, ev["ppu-generation.json"], "PPU", errors)
        spu = _emission(spu_report, ev["spu-generation.json"], "SPU", errors)
        raw_spu = _emission(raw_spu_report, ev["spu-raw-generation.json"], "Raw SPU", errors)
        raw_spu["overlayCount"] = len(raw_spu_report["overlays"]) if isinstance(raw_spu_report.get("overlays"), list) else None
        raw_spu["includedInOverall"] = False
        raw_spu["basis"] = "Raw SPU overlay words covered by their own report. This scope remains separate from canonical SPU and combined coverage because overlap is not established."
        all_activity = [] if empty else _activity(root, errors)
        build_stamp = ev["native-build.json"]["modifiedAt"]
        source_activity = [row for row in all_activity if row["category"] in {"src", "tools"}]
        newer_sources = sorted([row for row in source_activity if build_stamp and row["modifiedAt"] > build_stamp], key=lambda row: row["modifiedAt"], reverse=True)
        generation_newer = [name for name in ("ppu-generation.json", "spu-generation.json", "spu-raw-generation.json", "static-image.json") if build_stamp and ev[name]["modifiedAt"] and ev[name]["modifiedAt"] > build_stamp]
        scan_incomplete = any("Metadata scan" in (item.get("message") or "") or "metadata scan" in (item.get("message") or "") for item in errors)
        identity = _recorded_identity(root, _mapping(build_report.get("source_and_header_sha256")))
        report_mismatches, report_identity_errors = [], []
        for report_name, hash_key in (("ppu-generation.json", "generation_report_sha256"), ("spu-generation.json", "spu_generation_report_sha256"), ("spu-raw-generation.json", "raw_spu_generation_report_sha256")):
            expected = build_report.get(hash_key)
            if not expected:
                continue
            try:
                path = root / "reports" / report_name
                if not path.resolve().is_relative_to(root):
                    raise ValueError("Report resolves outside the source root")
                if _small_file_hash(path) != expected:
                    report_mismatches.append(f"reports/{report_name}")
            except (OSError, ValueError) as exc:
                report_identity_errors.append({"path": f"reports/{report_name}", "message": str(exc)})
        for processor, report, metric in (("PPU", ppu_report, ppu), ("SPU", spu_report, spu), ("Raw SPU", raw_spu_report, raw_spu)):
            generator_identity = _recorded_identity(root, _mapping(report.get("generator_sources_sha256")))
            metric["changedGeneratorSources"] = generator_identity["changed"]
            metric["generatorIdentityChecked"] = generator_identity["checked"]
            metric["generatorIdentityUnavailable"] = generator_identity["unavailable"]
            metric["generatorChangedSinceReport"] = bool(generator_identity["changed"]) if generator_identity["checked"] else None
        definite_change = bool(identity["changed"] or report_mismatches)
        freshness_unknown = scan_incomplete or bool(identity["unavailable"] or report_identity_errors)
        stale = (True if definite_change else (None if freshness_unknown else bool(newer_sources or generation_newer))) if build_report else None
        components = _component_rows(build_report)
        milestone_history = [] if empty else _build_milestone_history(root, build_report, build_stamp)
        latest_source_at = _iso(max(row["_mtime"] for row in newer_sources)) if newer_sources else None
        if not build_report:
            work_state = "unavailable"
        elif stale is None:
            work_state = "freshness-unknown"
        elif stale:
            work_state = "source-changed-receipt-pending"
        else:
            work_state = "successful-receipt-current"
        build = {
            "available": bool(build_report), "status": build_report.get("status"),
            "linkedAt": build_stamp, "translationUnits": _integer(build_report.get("translation_units")),
            "objectsCompiled": _integer(build_report.get("objects_compiled")),
            "objectsReused": _integer(build_report.get("objects_reused")),
            "executableBytes": _integer(build_report.get("bytes")),
            "elapsedSeconds": build_report.get("elapsed_seconds"),
            "testsRun": _boolean(build_report.get("tests_run")), "gameRun": _boolean(build_report.get("game_run")),
            "gameComplete": _boolean(build_report.get("game_complete")), "stale": stale,
            "newerSourceCount": len(newer_sources) if build_report else None,
            "newerSources": [row["path"] for row in newer_sources[:30]],
            "generationReportsNewer": generation_newer,
            "recordedSourcesChecked": identity["checked"], "changedRecordedSources": identity["changed"],
            "unavailableRecordedSources": identity["unavailable"], "excludedRecordedFiles": identity["excluded"],
            "reportHashMismatches": report_mismatches, "reportIdentityErrors": report_identity_errors,
            "freshnessBasis": "SHA-256 of recorded src/tools files and PPU/SPU/raw-SPU report identities, plus newer source/tool modification times. Generated game code and native binaries are excluded; no complete build freshness claim is made.",
            "remaining": _array(build_report.get("remaining")),
            "components": components,
            "componentSummary": _component_summary(components),
            "milestoneHistory": milestone_history,
            "workState": {
                "available": bool(build_report),
                "state": work_state,
                "latestSourceAt": latest_source_at,
                "changedSourceCount": len(newer_sources) if build_report else None,
                "progressPercent": None,
                "wholeGamePercent": None,
                "basis": "Compares the latest successful build receipt with recorded source/report identity. It does not infer a running process or compile percentage.",
            },
            "reportPath": "reports/native-build.json",
        }
        unresolved = link.get("unresolved_imports")
        imports = {
            "available": bool(link), "gameBound": _integer(link.get("game_function_imports_bound")),
            "gameTotal": _integer(build_report.get("known_import_total")),
            "boundFunctions": _integer(link.get("bound_function_imports")),
            "boundVariables": _integer(link.get("bound_variable_imports")),
            "unresolvedCount": len(unresolved) if isinstance(unresolved, list) else None,
            "unresolved": [{"importer": item.get("importer"), "library": item.get("library"), "kind": item.get("kind"), "nid": item.get("nid_hex"), "reason": item.get("reason")} for item in _array(unresolved) if isinstance(item, dict)],
            "bootReady": _boolean(link.get("boot_ready")),
            "modulesInitialized": _boolean(link.get("modules_initialized")),
            "selectedModules": len(link["selected_modules"]) if isinstance(link.get("selected_modules"), list) else None,
            "reportPath": "reports/static-image.json",
            "basis": "Static address binding to original firmware providers; not native-service correctness or executed module startup.",
        }
        payloads = recovery_report.get("payloads")
        nonempty_load = [item for item in _array(payloads) if isinstance(item, dict) and item.get("type") == 2 and (_integer(item.get("decoded_size")) or 0) > 0]
        recovery = {
            "available": bool(recovery_report), "originalBytes": _integer(recovery_report.get("source_size")),
            "recoveredBytes": _integer(recovery_report.get("elf_size")),
            "completeElfRecovered": _boolean(recovery_report.get("complete_elf_recovered")),
            "uncoveredBytes": _integer(recovery_report.get("uncovered_bytes")),
            "authenticatedLoadSegments": sum(item.get("authenticated") is True and item.get("matches_baseline") is True for item in nonempty_load) if isinstance(payloads, list) else None,
            "totalNonemptyLoadSegments": len(nonempty_load) if isinstance(payloads, list) else None,
            "wholeElfDigestMatches": _boolean(provenance.get("full_elf_digest_matches")),
            "scope": recovery_report.get("evidence_scope"), "status": recovery_report.get("recovery_status"),
            "reportPath": "reports/self-recovery.json",
        }
        stats = _mapping(assets_report.get("statistics"))
        assets = {
            "available": bool(assets_report), "archiveCount": _integer(stats.get("archive_count")),
            "archiveNames": _integer(stats.get("archive_payload_names")), "sourceBytes": _integer(stats.get("source_size_bytes")),
            "sourceBytesRead": _integer(stats.get("source_bytes_read")), "packageSamples": len(assets_report["package_samples"]) if isinstance(assets_report.get("package_samples"), list) else None,
            "limitations": _array(assets_report.get("limitations")), "reportPath": "reports/spu-assets.json",
        }
        modules = [{"name": name, "kind": "game" if name.startswith("game/") else "firmware", "words": _integer(words), "sourceBytes": _bytes(_integer(words)), "emissionPercent": None} for name, words in _mapping(ppu_report.get("source_words_by_image")).items()]
        modules.sort(key=lambda item: (item["kind"] != "game", -(item["words"] or 0), item["name"]))
        unsupported = [{"processor": processor, "name": name, "words": _integer(words), "sourceBytes": _bytes(_integer(words))} for processor, report in (("PPU", ppu_report), ("SPU", spu_report)) for name, words in _mapping(report.get("unimplemented_classes")).items()]
        unsupported.sort(key=lambda item: -(item["words"] or 0))
        activity = sorted(all_activity, key=lambda row: row["modifiedAt"], reverse=True)[:40]
        for row in activity:
            row.pop("_mtime", None)
        result = {
            "schemaVersion": 1, "collectedAt": _iso(time.time()), "sourceRoot": str(root),
            "project": {"title": "Selected game", "mode": "Independent native port", "completionPercent": None, "testingPolicy": "Use the selected target's recorded testing policy and evidence.", "summary": "Static translation and compilation evidence. Playable completion is not measured.", "ps3RecompUsed": _boolean(provenance.get("ps3recomp_used")), "activityBasis": "Recent file modification times; not live chat messages, execution tracing, or confirmed current compiler activity."},
            "ppu": ppu, "spu": spu, "rawSpu": raw_spu, "overall": _overall_progress(ppu, spu), "build": build, "imports": imports,
            "recovery": recovery, "assets": assets, "modules": modules,
            "unsupported": unsupported, "activity": activity, "evidence": evidence,
            "errors": errors, "collectionMs": round((time.perf_counter() - started) * 1000, 3),
        }
        return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    arguments = parser.parse_args()
    print(json.dumps(collect_snapshot(arguments.root), indent=2))
