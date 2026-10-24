"""Required CI must cover code changes and allow documentation-only PRs."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ci_changes', ROOT / 'scripts/ci-changes.py')
CI = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CI)


class ChangeScopeTests(unittest.TestCase):
    def test_documentation_only_does_not_need_images(self):
        self.assertFalse(CI.requires_images(['README.md', 'AI-INSTALL.md',
            'docs/images/example.png', 'workstation/README.md',
            '.github/ISSUE_TEMPLATE/bug.yml']))

    def test_code_and_mixed_changes_need_images(self):
        for code in ['compose.yaml', 'workstation/Dockerfile', 'gateway/app/server.py',
                     'workstation/scripts/reset-claude-user.py', 'tests/test_ci_changes.py',
                     '.github/workflows/images.yml', 'docs-example.py']:
            with self.subTest(code=code):
                self.assertTrue(CI.requires_images(['README.md', code]))

    def test_renames_out_of_docs_are_still_checked(self):
        self.assertTrue(CI.requires_images(['docs/source.py', 'gateway/app/source.py']))

    def test_empty_pr_does_not_need_images(self):
        self.assertFalse(CI.requires_images([]))


if __name__ == '__main__':
    unittest.main()
