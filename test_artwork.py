import base64
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import artwork
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
    def write_automatic_artwork(self,target_id='first',roles=('icon','overlay','background'),mutate=None,data=None):
        presentation=self.root/target_id/'presentation';presentation.mkdir(parents=True,exist_ok=True)
        data=base64.b64decode(PNG) if data is None else bytes(data);digest=hashlib.sha256(data).hexdigest();artwork={}
        names={'icon':'ICON0.PNG','overlay':'PIC0.PNG','background':'PIC1.PNG'}
        for role in roles:
            name=names[role];(presentation/name).write_bytes(data)
            artwork[role]={'path':name,'mime':'image/png','byteCount':len(data),'width':1,'height':1,'sha256':digest}
        manifest={'schema':'ps3-workbench/artwork-v1','artwork':artwork}
        if mutate:mutate(manifest)
        (presentation/'artwork.json').write_text(json.dumps(manifest),encoding='utf-8')
        return data,digest
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
    def test_target_manifest_populates_all_roles_without_changing_target(self):
        data,digest=self.write_automatic_artwork()
        source=self.root/'first'/'presentation'/'ICON0.PNG';before=hashlib.sha256(source.read_bytes()).hexdigest()
        branding=self.ws.catalog()['targets'][0]['branding']
        self.assertEqual(branding['artworkOrigin'],'target')
        for role in ('icon','overlay','background'):
            self.assertEqual(branding[f'{role}Url'],f'/artwork/auto/{digest}.png')
            self.assertEqual((branding[f'{role}Width'],branding[f'{role}Height']),(1,1))
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)
        self.assertEqual((self.root/'artwork'/'auto'/f'{digest}.png').read_bytes(),data)
        self.assertEqual(self.ws.catalog()['targets'][1]['branding']['iconUrl'],'')
    def test_manual_cover_overrides_icon_slot_and_reset_reveals_automatic(self):
        self.write_automatic_artwork(roles=('icon','background'))
        automatic=self.ws.catalog()['targets'][0]['branding']
        self.assertTrue(automatic['iconUrl'])
        self.ws.set_branding('shared',{'studio':'Studio','subtitle':'Edition','source':'','image':'data:image/png;base64,'+PNG})
        manual=self.ws.catalog()['targets'][0]['branding']
        self.assertEqual(manual['artworkOrigin'],'manual')
        self.assertTrue(manual['coverUrl'].startswith('/artwork/custom/'))
        self.assertEqual(manual['iconUrl'],automatic['iconUrl'])
        self.assertEqual(manual['backgroundUrl'],automatic['backgroundUrl'])
        self.ws.set_branding('shared',{'reset':True})
        restored=self.ws.catalog()['targets'][0]['branding']
        self.assertEqual(restored['artworkOrigin'],'target')
        self.assertEqual(restored['coverUrl'],'')
        self.assertEqual(restored['iconUrl'],automatic['iconUrl'])
    def test_invalid_manifest_or_asset_falls_back_without_leaking_details(self):
        cases=(
            lambda value:value.update(schema='wrong'),
            lambda value:value['artwork']['icon'].update(sha256='0'*64),
            lambda value:value['artwork']['icon'].update(path='../ICON0.PNG'),
            lambda value:value['artwork']['icon'].update(byteCount=True),
            lambda value:value['artwork']['icon'].update(width=2),
            lambda value:value['artwork']['icon'].update(mime='image/jpeg'),
        )
        for index,mutate in enumerate(cases):
            with self.subTest(index=index):
                self.ws.artwork_cache.clear();self.write_automatic_artwork(roles=('icon',),mutate=mutate)
                branding=self.ws.catalog()['targets'][0]['branding']
                self.assertEqual(branding['iconUrl'],'')
                self.assertEqual(branding['artworkOrigin'],'')
    def test_manifest_refresh_changes_content_addressed_url(self):
        _,first=self.write_automatic_artwork(roles=('icon',))
        self.assertIn(first,self.ws.catalog()['targets'][0]['branding']['iconUrl'])
        presentation=self.root/'first'/'presentation';data=bytearray(base64.b64decode(PNG));data[-5]^=1
        second=hashlib.sha256(data).hexdigest();(presentation/'ICON0.PNG').write_bytes(data)
        manifest=json.loads((presentation/'artwork.json').read_text(encoding='utf-8'))
        manifest['artwork']['icon'].update(byteCount=len(data),sha256=second)
        (presentation/'artwork.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        self.assertIn(second,self.ws.catalog()['targets'][0]['branding']['iconUrl'])
        self.assertNotEqual(first,second)
    def test_corrupt_cached_file_is_rebuilt_before_fast_path_return(self):
        data,digest=self.write_automatic_artwork(roles=('icon',))
        self.ws.catalog();cached=self.root/'artwork'/'auto'/f'{digest}.png'
        corrupt=bytearray(data);corrupt[-5]^=1;cached.write_bytes(corrupt)
        branding=self.ws.catalog()['targets'][0]['branding']
        self.assertEqual(branding['iconUrl'],f'/artwork/auto/{digest}.png')
        self.assertEqual(cached.read_bytes(),data)
    def test_automatic_cache_is_bounded_and_evictions_invalidate_memory(self):
        first_data,_=self.write_automatic_artwork(roles=('icon',))
        second_data=bytearray(first_data);second_data[-5]^=1
        _,second_digest=self.write_automatic_artwork('third',roles=('icon',),data=second_data)
        limit=len(first_data)+10
        with patch.object(artwork,'AUTO_CACHE_LIMIT',limit):
            self.ws.presentation(self.ws.targets[0])
            current=self.ws.presentation(self.ws.targets[2])['branding']
        files=list((self.root/'artwork'/'auto').glob('*.png'))
        self.assertLessEqual(sum(path.stat().st_size for path in files),limit)
        self.assertEqual(current['iconUrl'],f'/artwork/auto/{second_digest}.png')
        self.assertNotIn(str((self.root/'first').resolve()),self.ws.artwork_cache)
    def test_dedicated_background_is_global_and_not_hero_or_cover_fallback(self):
        public=Path(__file__).parent/'public'
        markup=(public/'index.html').read_text(encoding='utf-8')
        self.assertLess(markup.index('id="workspace-backdrop"'),markup.index('<aside class="sidebar">'))
        hero=markup[markup.index('<div class="game-identity">'):markup.index('<a id="cover-credit"')]
        self.assertNotIn('id="game-backdrop"',hero)
        self.assertIn('id="game-overlay"',hero)
        script=(public/'branding.js').read_text(encoding='utf-8')
        self.assertIn('loadArtwork(backdrop,[backgroundUrl]',script)
        self.assertNotIn('loadArtwork(backdrop,[backgroundUrl,coverUrl',script)
        self.assertIn("backdrop.getAttribute('src')===backgroundUrl",script)
    def test_active_formats_and_arbitrary_paths_are_rejected(self):
        for value in ['data:image/svg+xml;base64,PHN2Zy8+','data:image/png;base64,'+base64.b64encode(b'not an image'*3).decode()]:
            with self.assertRaises(ValueError):save_cover(value,self.root/'artwork')
        self.assertEqual(cover_url('custom/../../private.txt'),'')
        self.assertEqual(cover_url('https://example.com/private.png'),'')
        with self.assertRaises(ValueError):validate_metadata({'source':'javascript:alert(1)'})
        with self.assertRaises(ValueError):self.ws.set_branding('not-registered',{})

if __name__=='__main__':unittest.main()
