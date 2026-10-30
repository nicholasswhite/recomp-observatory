import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from ps3_metrics import summarize, scan_source

class Ps3MetricsTests(unittest.TestCase):
    def setUp(self):
        scratch=Path(__file__).parent/'work';scratch.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=scratch);self.root=Path(self.temp.name)
        for d in ['project/recompiled','project/spu','analysis/spu']:(self.root/d).mkdir(parents=True,exist_ok=True)
    def tearDown(self):self.temp.cleanup()
    def write(self,name,value):
        p=self.root/name;p.write_text(value,encoding='utf-8');return p
    def test_original_entry_mapping_is_not_semantic_coverage(self):
        self.write('project/recompiled/ppu_recomp_000.cpp','void func_00000100(ppu_context* ctx) {\n/* TODO: .word 0 */;\n}\nvoid func_00000200(ppu_context* ctx) {\n/* trap: foo */;\n}\n')
        self.write('analysis/EBOOT.functions.json',json.dumps([{'start':'0x100'},{'start':'0x100'},{'start':'0x300'}]))
        r=summarize(self.root,{})
        self.assertEqual(r['ppu']['originalEntries'],2)
        self.assertEqual(r['ppu']['mappingPercent'],50)
        self.assertEqual(r['ppu']['todoCount'],1)
        self.assertEqual(r['ppu']['extraDefinitions'],1)
        self.assertIsNone(r['freshness']['stale'])
    def test_missing_spu_inventory_does_not_become_full_coverage(self):
        self.write('project/spu/one_recomp.c','void example_one_spu_func_00000100(spu_context* ctx) {}\n')
        self.write('project/spu/two_recomp.c','void example_two_spu_func_00000200(spu_context* ctx) {}\n')
        self.write('analysis/spu/one.functions.json',json.dumps([{'start':'0x100'}]))
        r=summarize(self.root,{})['spu']
        self.assertEqual(r['generatedFunctions'],2)
        self.assertEqual(r['programsWithInventories'],1)
        self.assertEqual(r['mappedSubsetMatches'],1)
        self.assertIsNone(r['mappingPercent'])
    def test_build_hash_changes_and_excluded_scope(self):
        p=self.write('project/main.cpp','old source')
        manifest={'source_sha256':{'project/main.cpp':hashlib.sha256(p.read_bytes()).hexdigest(),'game/EBOOT.ELF':'never read'}}
        self.assertIs(summarize(self.root,manifest)['freshness']['stale'],False)
        p.write_text('new source',encoding='utf-8')
        r=summarize(self.root,manifest)['freshness']
        self.assertIs(r['stale'],True);self.assertEqual(r['changedFiles'],['project/main.cpp']);self.assertEqual(r['excludedFiles'],1)
    def test_chunk_boundary_definition_is_not_lost_or_counted_twice(self):
        p=self.root/'project/recompiled/ppu_recomp_000.cpp'
        lead=b'//'+b'x'*(1024*1024-43)+b'\n'
        p.write_bytes(lead+b'void func_00000100(ppu_context* ctx)\n{\n/* TODO: .word 0 */;\n}\n')
        r=scan_source(p)
        self.assertEqual(r['definitions'],{256});self.assertEqual(r['todoCount'],1)
        self.assertEqual(r['sha256'],hashlib.sha256(p.read_bytes()).hexdigest())

if __name__=='__main__':unittest.main()
