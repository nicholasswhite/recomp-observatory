"""Tests for dashboard telemetry only; never execute port or game code."""
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest

from collector import collect_snapshot


class CollectorTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).parent / "work"
        scratch.mkdir(exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temporary.name)
        (self.root / "reports").mkdir()
        (self.root / "src").mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def report(self, name, value):
        path = self.root / "reports" / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_missing_is_unknown_and_malformed_does_not_use_last_good_data(self):
        missing = collect_snapshot(self.root)
        self.assertIsNone(missing["ppu"]["emissionPercent"])
        self.assertIsNone(missing["build"]["testsRun"])
        self.assertIsNone(missing["imports"]["unresolvedCount"])
        report = self.report("ppu-generation.json", {"words_processed": 10, "words_with_implemented_emission": 8, "words_with_explicit_unimplemented_failure": 2})
        self.assertEqual(collect_snapshot(self.root)["ppu"]["emissionPercent"], 80)
        report.write_text('{"words_processed":', encoding="utf-8")
        broken = collect_snapshot(self.root)
        self.assertIsNone(broken["ppu"]["emissionPercent"])
        self.assertTrue(any(e["path"] == "reports/ppu-generation.json" for e in broken["errors"]))

    def test_counts_are_source_byte_coverage_not_overall_completion(self):
        self.report("ppu-generation.json", {"words_processed": 10, "words_with_implemented_emission": 8, "words_with_explicit_unimplemented_failure": 2, "source_words_by_image": {"game/EBOOT.ELF": 6, "firmware/module": 4}})
        self.report("static-image.json", {"unresolved_imports": [], "modules_initialized": False, "boot_ready": False})
        data = collect_snapshot(self.root)
        self.assertEqual(data["ppu"]["sourceBytes"], 40)
        self.assertEqual(data["ppu"]["emittedSourceBytes"], 32)
        self.assertEqual(data["imports"]["unresolvedCount"], 0)
        self.assertIs(data["imports"]["modulesInitialized"], False)
        self.assertIsNone(data["project"]["completionPercent"])
        self.assertTrue(all(row["emissionPercent"] is None for row in data["modules"]))
        self.report("ppu-generation.json", {"words_processed": 10, "words_with_implemented_emission": 9, "words_with_explicit_unimplemented_failure": 2})
        self.assertIsNone(collect_snapshot(self.root)["ppu"]["emissionPercent"])

    def test_overall_weights_by_words_and_requires_both_reports(self):
        self.report("ppu-generation.json", {"words_processed": 90, "words_with_implemented_emission": 45, "words_with_explicit_unimplemented_failure": 45})
        self.assertIsNone(collect_snapshot(self.root)["overall"]["translationPercent"])
        self.report("spu-generation.json", {"words_processed": 10, "words_with_implemented_emission": 10, "words_with_explicit_unimplemented_failure": 0})
        overall = collect_snapshot(self.root)["overall"]
        self.assertEqual(overall["translationPercent"], 55)  # Not mean(50, 100).
        self.assertEqual(overall["scannedSourceBytes"], 400)
        self.assertEqual(overall["supportedSourceBytes"], 220)
        self.assertEqual(overall["failureSourceBytes"], 180)
        self.assertIsNone(overall["decompilationPercent"])
        self.assertIsNone(overall["gameCompletionPercent"])
        self.report("spu-generation.json", {"words_processed": 10, "words_with_implemented_emission": 11, "words_with_explicit_unimplemented_failure": 0})
        self.assertIsNone(collect_snapshot(self.root)["overall"]["translationPercent"])

    def test_raw_spu_is_separate_scoped_telemetry(self):
        self.report("ppu-generation.json", {"words_processed": 90, "words_with_implemented_emission": 45, "words_with_explicit_unimplemented_failure": 45})
        self.report("spu-generation.json", {"words_processed": 10, "words_with_implemented_emission": 10, "words_with_explicit_unimplemented_failure": 0})
        before = collect_snapshot(self.root)
        self.assertFalse(before["rawSpu"]["available"])
        self.assertFalse(any(error["path"] == "reports/spu-raw-generation.json" for error in before["errors"]))
        self.report("spu-raw-generation.json", {
            "words_processed": 20,
            "words_with_implemented_emission": 15,
            "words_with_explicit_unimplemented_failure": 5,
            "translation_units": ["one", "two"],
            "overlays": [{"name": "a"}, {"name": "b"}, {"name": "c"}],
        })
        data = collect_snapshot(self.root)
        self.assertEqual(data["rawSpu"]["emissionPercent"], 75)
        self.assertEqual(data["rawSpu"]["translationUnits"], 2)
        self.assertEqual(data["rawSpu"]["overlayCount"], 3)
        self.assertIs(data["rawSpu"]["includedInOverall"], False)
        self.assertEqual(data["overall"]["translationPercent"], 55)
        self.assertNotIn("spu-raw-generation.json", data["overall"]["reportPaths"])
        (self.root / "reports" / "spu-raw-generation.json").write_text('{"words_processed":', encoding="utf-8")
        broken = collect_snapshot(self.root)
        self.assertIsNone(broken["rawSpu"]["emissionPercent"])
        self.assertTrue(any(error["path"] == "reports/spu-raw-generation.json" for error in broken["errors"]))

    def test_component_receipt_history_and_pending_work_state_are_evidence_scoped(self):
        source = self.root / "src" / "renderer.cpp"
        source.write_text("newer source", encoding="utf-8")
        current = self.report("native-build.json", {
            "status": "compiled-untested-incomplete", "sha256": "c", "translation_units": 12, "bytes": 120,
            "feature_a_compiled": True, "feature_b_integrated": True, "feature_c_ready": True,
            "tests_run": False, "game_run": False, "game_complete": False,
        })
        archived = [
            ("old", 10, "a", {"feature_a_compiled": True, "feature_b_integrated": False}),
            ("new", 11, "b", {"feature_a_compiled": True, "feature_b_integrated": True}),
        ]
        work = self.root / "work"
        work.mkdir()
        for index in range(130):
            (work / f"decoy-{index:03}.txt").write_text("not a receipt", encoding="utf-8")
        for index, (folder, units, digest, flags) in enumerate(archived):
            directory = work / folder
            directory.mkdir(parents=True)
            path = directory / "native-build.json"
            path.write_text(json.dumps({"status": "compiled-untested-incomplete", "sha256": digest, "translation_units": units, "bytes": units * 10, **flags}), encoding="utf-8")
            os.utime(path, (current.stat().st_mtime - 20 + index * 10, current.stat().st_mtime - 20 + index * 10))
        os.utime(source, (current.stat().st_mtime + 10, current.stat().st_mtime + 10))
        data = collect_snapshot(self.root)
        self.assertEqual(data["build"]["componentSummary"]["trueCount"], 3)
        self.assertEqual(data["build"]["componentSummary"]["total"], 3)
        self.assertEqual(len(data["build"]["milestoneHistory"]), 3)
        self.assertEqual(data["build"]["milestoneHistory"][1]["newlyTrue"], ["feature_b_integrated"])
        self.assertEqual(data["build"]["milestoneHistory"][2]["newlyTrue"], ["feature_c_ready"])
        self.assertEqual(data["build"]["workState"]["state"], "source-changed-receipt-pending")
        self.assertIsNone(data["build"]["workState"]["progressPercent"])
        self.assertIsNone(data["build"]["workState"]["wholeGamePercent"])

    def test_recorded_source_hash_changes_are_detected_even_with_old_mtime(self):
        source = self.root / "src" / "file.cpp"
        source.write_bytes(b"old source")
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        report = self.report("native-build.json", {"status": "compiled-untested-incomplete", "source_and_header_sha256": {str(source): digest, str(self.root / "work/generated/untouched.cpp"): "do-not-read"}})
        before = collect_snapshot(self.root)
        self.assertEqual(before["build"]["recordedSourcesChecked"], 1)
        self.assertEqual(before["build"]["excludedRecordedFiles"], 1)
        source.write_bytes(b"new source")
        old = report.stat().st_mtime - 60
        os.utime(source, (old, old))
        after = collect_snapshot(self.root)
        self.assertEqual(after["build"]["changedRecordedSources"], ["src/file.cpp"])
        self.assertIs(after["build"]["stale"], True)

    def test_build_generation_report_identity_mismatch_is_detected(self):
        source = self.report("ppu-generation.json", {"words_processed": 4, "words_with_implemented_emission": 3, "words_with_explicit_unimplemented_failure": 1})
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        self.report("native-build.json", {"generation_report_sha256": digest})
        self.assertEqual(collect_snapshot(self.root)["build"]["reportHashMismatches"], [])
        self.report("ppu-generation.json", {"words_processed": 4, "words_with_implemented_emission": 4, "words_with_explicit_unimplemented_failure": 0})
        data = collect_snapshot(self.root)
        self.assertEqual(data["build"]["reportHashMismatches"], ["reports/ppu-generation.json"])
        self.assertIs(data["build"]["stale"], True)


if __name__ == "__main__":
    unittest.main()
