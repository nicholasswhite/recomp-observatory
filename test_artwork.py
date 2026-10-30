import base64
import tempfile
import unittest
from pathlib import Path
from artwork import save_cover,cover_url,validate_metadata
from workspace import Workspace

PNG='iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jTioAAAAASUVORK5CYII='

class ArtworkTests(unittest.TestCase):
    def setUp(self):
        scratch=Path(__file__).parent/'work';scratch.mkdir(exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=scratch);self.root=Path(self.temp.name)
        self.ws=Workspace(self.root/'workspace.json',self.root/'history')
        def target(id,game):
            return {'id':id,'gameId':game,'gameTitle':'Example Game' if game=='shared' else 'Other Game','title':id,'toolchain':'Fixture','root':str(self.root/id),'adapter':'inventory-v1','reports':{}}
        self.ws.add([target('first','shared'),target('second','shared'),target('third','other')])
    def tearDown(self):self.temp.cleanup()
    def test_saved_cover_is_shared_by_game_not_other_games(self):
        self.ws.set_branding('shared',{'studio':'Example Studio','subtitle':'Test edition','source':'https://example.com/cover','image':'data:image/png;base64,'+PNG})
        a,b,c=self.ws.catalog()['targets']
        self.assertEqual(a['branding'],b['branding'])
        self.assertTrue(a['branding']['coverUrl'].startswith('/artwork/custom/'))
        self.assertEqual(c['branding']['coverUrl'],'')
        self.assertEqual(c['branding']['studio'],'')
        restored=Workspace(self.root/'workspace.json',self.root/'history')
        self.assertEqual(restored.catalog()['targets'][0]['branding'],a['branding'])
        self.ws.set_branding('shared',{'reset':True})
        self.assertEqual(self.ws.catalog()['targets'][0]['branding']['coverUrl'],'')
    def test_repeated_repository_add_preserves_artwork(self):
        self.ws.set_branding('other',{'studio':'My Studio','subtitle':'My Game','source':''})
        self.ws.add(self.ws.targets)
        restored=Workspace(self.root/'workspace.json',self.root/'history')
        self.assertEqual(restored.catalog()['targets'][2]['branding']['studio'],'My Studio')
    def test_active_formats_and_arbitrary_paths_are_rejected(self):
        for value in ['data:image/svg+xml;base64,PHN2Zy8+','data:image/png;base64,'+base64.b64encode(b'not an image'*3).decode()]:
            with self.assertRaises(ValueError):save_cover(value,self.root/'artwork')
        self.assertEqual(cover_url('custom/../../private.txt'),'')
        self.assertEqual(cover_url('https://example.com/private.png'),'')
        with self.assertRaises(ValueError):validate_metadata({'source':'javascript:alert(1)'})
        with self.assertRaises(ValueError):self.ws.set_branding('not-registered',{})

if __name__=='__main__':unittest.main()
