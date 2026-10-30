"""Workspace isolation tests use synthetic repositories, never game code."""
import json
import tempfile
import unittest
from unittest.mock import patch
import copy
from pathlib import Path
from workspace import Workspace, discover, identity

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        scratch=Path(__file__).parent/'work';scratch.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=scratch);self.root=Path(self.temp.name)
        self.workspace=Workspace(self.root/'catalog.json',self.root/'history')

    def tearDown(self): self.temp.cleanup()

    def target(self,id,folder,game='Game A',adapter='independent-reports-v1'):
        return {'id':id,'gameId':game.lower().replace(' ','-'),'gameTitle':game,'title':id,'root':str(folder),'adapter':adapter,'toolchain':adapter,'reports':{}}

    def reports(self,folder,supported):
        (folder/'reports').mkdir(parents=True)
        for processor in ('ppu','spu'):
            (folder/f'reports/{processor}-generation.json').write_text(json.dumps({'words_processed':10,'words_with_implemented_emission':supported,'words_with_explicit_unimplemented_failure':10-supported}))

    def test_two_attempts_have_separate_cache_evidence_and_history(self):
        a,b=self.root/'a',self.root/'b';self.reports(a,8);self.reports(b,3)
        targets=[self.target('a',a),self.target('b',b)]
        self.workspace.add(targets)
        one=self.workspace.snapshot('a');two=self.workspace.snapshot('b');again=self.workspace.snapshot('a')
        self.assertEqual(one['overall']['translationPercent'],80)
        self.assertEqual(two['overall']['translationPercent'],30)
        self.assertEqual(again['overall']['translationPercent'],80)
        self.assertEqual(one['target']['id'],'a');self.assertEqual(two['sourceRoot'],str(b))
        self.assertEqual(one['history'][0]['ppu'],32);self.assertEqual(two['history'][0]['ppu'],12)
        self.assertEqual(len(list((self.root/'history').glob('*.json'))),2)
        with self.assertRaises(KeyError):self.workspace.snapshot('missing')
        one['ppu']['emissionPercent']=100
        self.assertEqual(self.workspace.snapshot('a')['ppu']['emissionPercent'],80)

    def test_discovery_multiple_games_and_idempotent_save(self):
        self.reports(self.root/'one',8);self.reports(self.root/'two',3)
        result=discover(self.root)
        self.assertEqual(len(result['targets']),2)
        self.workspace.add(result['targets']);self.workspace.add(result['targets'])
        saved=Workspace(self.root/'catalog.json',self.root/'history')
        self.assertEqual(len(saved.targets),2)
        self.assertEqual(len({t['gameId'] for t in saved.targets}),2)

    def test_manifest_two_attempts_grouped_inside_selected_root(self):
        a,b=self.root/'a',self.root/'b';a.mkdir();b.mkdir()
        values=[self.target('a',a),self.target('b',b)]
        (self.root/'observatory.project.json').write_text(json.dumps({'schemaVersion':1,'targets':values}))
        found=discover(self.root)['targets'];self.workspace.add(found)
        self.assertEqual(len({t['gameId'] for t in self.workspace.targets}),1)
        self.assertEqual(len(found),2)

    def test_manifest_cannot_expand_observation_outside_selected_root(self):
        selected=self.root/'selected';outside=self.root/'outside';selected.mkdir();outside.mkdir()
        for target_root in ('../outside',str(outside)):
            candidate=self.target('outside',target_root,adapter='inventory-v1')
            (selected/'observatory.project.json').write_text(json.dumps({'schemaVersion':1,'targets':[candidate]}))
            result=discover(selected)
            self.assertTrue(any('must stay inside' in warning for warning in result['warnings']))
            self.assertEqual(len(result['targets']),1)
            self.assertEqual(Path(result['targets'][0]['root']),selected.resolve())

    def test_nested_links_are_excluded_from_discovery_and_activity(self):
        selected=self.root/'selected';outside=self.root/'outside';selected.mkdir();outside.mkdir()
        self.reports(outside/'attempt',8)
        (outside/'source').mkdir();(outside/'source/secret.py').write_text('outside = True')
        try:
            (selected/'linked-attempt').symlink_to(outside/'attempt',target_is_directory=True)
            (selected/'src').symlink_to(outside/'source',target_is_directory=True)
        except OSError as error:
            self.skipTest(f'Directory links unavailable: {error}')
        result=discover(selected)
        self.assertEqual(len(result['targets']),1)
        self.assertEqual(result['targets'][0]['adapter'],'inventory-v1')
        self.workspace.add(result['targets'])
        activity=self.workspace.snapshot(result['targets'][0]['id'])['activity']
        self.assertFalse(any(row['path'].endswith('secret.py') for row in activity))

    def test_reader_does_not_inherit_independent_reports(self):
        folder=self.root/'repo';self.reports(folder,10)
        self.workspace.add([self.target('generic',folder,adapter='inventory-v1')])
        d=self.workspace.snapshot('generic')
        self.assertIsNone(d['overall']['translationPercent'])
        self.assertIsNone(d['build']['gameRun'])
        self.assertFalse(d['capabilities']['translation'])

    def test_independent_history_records_build_components_and_separate_raw_spu(self):
        folder=self.root/'repo';self.reports(folder,8)
        (folder/'reports/spu-raw-generation.json').write_text(json.dumps({
            'words_processed':10,'words_with_implemented_emission':9,
            'words_with_explicit_unimplemented_failure':1,'overlays':[{}]
        }))
        (folder/'reports/native-build.json').write_text(json.dumps({
            'status':'compiled-untested-incomplete','translation_units':12,
            'feature_compiled':True,'feature_ready':False,
            'tests_run':False,'game_run':False,'game_complete':False
        }))
        self.workspace.add([self.target('a',folder)])
        data=self.workspace.snapshot('a');point=data['history'][-1]
        self.assertEqual(point['rawSpu'],36)
        self.assertEqual(point['rawSpuTotal'],40)
        self.assertEqual(point['buildUnits'],12)
        self.assertEqual(point['componentTrue'],1)
        self.assertEqual(point['componentTotal'],2)

    def test_legacy_fps_requires_same_executable(self):
        folder=self.root/'legacy';folder.mkdir()
        (folder/'build.json').write_text(json.dumps({'status':'production_build_succeeded_native_pending','compile_proof':{'object_targets':['one','two']},'executable_sha256':'abc'}))
        performance=folder/'performance.json'
        performance.write_text(json.dumps({'status':'ADMITTED_SAMPLE','executable_sha256':'other','gameplay_fps':60,'frames':10}))
        t=self.target('legacy',folder,adapter='ps3recomp-manifest-v1');t['reports']={'build':'build.json','performance':'performance.json'}
        self.workspace.add([t]);d=self.workspace.snapshot('legacy')
        self.assertIsNone(d['recordedRuntime']);self.assertIsNone(d['build']['gameRun'])
        self.assertEqual(d['build']['translationUnits'],2)
        performance.write_text(json.dumps({'status':'ADMITTED_SAMPLE','executable_sha256':'abc','gameplay_fps':3,'frames':10}))
        self.workspace.cache.clear();d=self.workspace.snapshot('legacy')
        self.assertEqual(d['recordedRuntime']['fps'],3)
        self.assertIsNone(d['overall']['translationPercent'])

    def test_missing_root_and_report_escape(self):
        t=self.target('absent',self.root/'absent',adapter='inventory-v1')
        self.workspace.add([t]);self.assertFalse(self.workspace.catalog()['targets'][0]['available'])
        self.assertTrue(self.workspace.snapshot('absent')['errors'])
        t=self.target('escape',self.root);t['reports']={'build':'../private.json'}
        with self.assertRaises(ValueError):self.workspace.add([t])
        self.assertEqual(len(self.workspace.targets),1)

    def test_bad_manifest_has_a_reviewable_warning(self):
        (self.root/'observatory.project.json').write_text('[]')
        result=discover(self.root)
        self.assertTrue(result['warnings'])
        self.assertEqual(result['targets'][0]['adapter'],'inventory-v1')

    def test_unchanged_history_gets_heartbeat_without_inventing_old_totals(self):
        folder=self.root/'repo';self.reports(folder,8)
        self.workspace.add([self.target('a',folder)])
        first=self.workspace.snapshot('a')
        history_path=self.root/'history'/f"{identity(self.workspace.targets[0])}.json"
        old={'at':'2026-01-01T00:00:00Z','ppu':32,'spu':32,'unresolved':None,'buildAt':None}
        history_path.write_text(json.dumps([old]))
        sample=copy.deepcopy(first);sample['collectedAt']='2026-01-01T00:01:00Z'
        self.workspace.cache.clear()
        with patch('workspace.collect_target',return_value=sample):
            recorded=self.workspace.snapshot('a')
        self.assertNotIn('ppuTotal',recorded['history'][0])
        self.assertEqual(recorded['history'][-1]['ppuTotal'],40)
        self.assertEqual(len(recorded['history']),2)
        self.workspace.cache.clear();sample['collectedAt']='2026-01-01T00:01:20Z'
        with patch('workspace.collect_target',return_value=sample):
            self.assertEqual(len(self.workspace.snapshot('a')['history']),2)
        self.workspace.cache.clear();sample['collectedAt']='2026-01-01T00:02:00Z'
        with patch('workspace.collect_target',return_value=sample):
            self.assertEqual(len(self.workspace.snapshot('a')['history']),3)

if __name__=='__main__':unittest.main()
