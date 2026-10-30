"""Cross-version tests for repository scan boundary helpers."""
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pathguard import is_contained, is_linklike


class PathGuardTests(unittest.TestCase):
    def test_reparse_attribute_is_linklike_without_modern_junction_api(self):
        fake_stat = Mock(st_file_attributes=0x400)
        with patch.object(Path, 'is_symlink', return_value=False), \
             patch.object(Path, 'is_junction', return_value=False, create=True), \
             patch.object(Path, 'lstat', return_value=fake_stat):
            self.assertTrue(is_linklike(Path('synthetic-reparse-point')))

    def test_containment_resolves_parent_segments(self):
        root=Path.cwd().resolve()
        self.assertTrue(is_contained(root/'child',root))
        self.assertFalse(is_contained(root.parent/'outside',root))


if __name__ == '__main__':
    unittest.main()
