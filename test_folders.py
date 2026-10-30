"""Folder picker tests use synthetic local directories, never target game files."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from folders import browse_folders


class FolderTests(unittest.TestCase):
    def setUp(self):
        scratch = Path(__file__).parent / 'work'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temp.name).resolve()
        self.shortcuts = [{'name': 'Fixture', 'path': str(self.root)}]
        self.shortcut_patch = patch('folders._shortcuts', return_value=self.shortcuts)
        self.shortcut_patch.start()

    def tearDown(self):
        self.shortcut_patch.stop()
        self.temp.cleanup()

    def test_lists_only_immediate_folders_in_name_order(self):
        for name in ('Zulu', 'alpha', 'Beta'):
            (self.root / name).mkdir()
        (self.root / 'alpha' / 'nested').mkdir()
        (self.root / 'secret.txt').write_text('Not returned or read by the picker', encoding='utf-8')
        result = browse_folders(str(self.root))
        self.assertEqual([f['name'] for f in result['folders']], ['alpha', 'Beta', 'Zulu'])
        self.assertEqual(result['path'], str(self.root))
        self.assertEqual(result['parent'], str(self.root.parent))
        self.assertEqual(result['folders'][0]['path'], str(self.root / 'alpha'))
        self.assertFalse(result['truncated'])

    def test_default_uses_first_accessible_shortcut(self):
        self.assertEqual(browse_folders()['path'], str(self.root))
        self.assertEqual(browse_folders()['shortcuts'], self.shortcuts)

    def test_invalid_missing_and_file_paths(self):
        for path in (123, {}, '', '.', '../other', 'bad\0path', '//server/share', r'\\?\C:\Git'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                browse_folders(path)
        with self.assertRaisesRegex(ValueError, 'does not exist'):
            browse_folders(str(self.root / 'missing'))
        file = self.root / 'file.txt'
        file.write_text('fixture', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'rather than a file'):
            browse_folders(str(file))

    def test_bounds_number_of_results_and_entries(self):
        for name in ('a', 'b', 'c'):
            (self.root / name).mkdir()
        with patch('folders.MAX_FOLDERS', 2):
            result = browse_folders(str(self.root))
            self.assertEqual([f['name'] for f in result['folders']], ['a', 'b'])
            self.assertTrue(result['truncated'])
        with patch('folders.MAX_ENTRIES', 1):
            result = browse_folders(str(self.root))
            self.assertEqual(len(result['folders']), 1)
            self.assertTrue(result['truncated'])

    def test_unreadable_folder_has_actionable_message(self):
        with patch('folders.os.scandir', side_effect=PermissionError('denied')):
            with self.assertRaisesRegex(ValueError, 'access permissions'):
                browse_folders(str(self.root))

    def test_does_not_follow_directory_symlinks(self):
        target = self.root / 'target'
        target.mkdir()
        link = self.root / 'link'
        try:
            os.symlink(target, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('Directory symlink creation is unavailable')
        self.assertEqual([f['name'] for f in browse_folders(str(self.root))['folders']], ['target'])

    def test_rejects_network_mapped_drive(self):
        with patch('folders._is_local_drive', return_value=False):
            with self.assertRaisesRegex(ValueError, 'local drive'):
                browse_folders(str(self.root))


if __name__ == '__main__':
    unittest.main()
