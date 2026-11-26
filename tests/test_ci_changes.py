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
        self.assertFalse(CI.requires_images(['README.md', 'README.en.md', 'AI-INSTALL.md',
            'docs/images/example.png', 'workstation/README.md',
            '.github/ISSUE_TEMPLATE/bug.yml', 'CODE_OF_CONDUCT.md']))

    def test_code_and_mixed_changes_need_images(self):
        for code in ['compose.yaml', 'workstation/Dockerfile', 'gateway/app/server.py',
                     'workstation/desktop/niu.sh', 'tests/test_ci_changes.py',
                     '.github/workflows/images.yml', 'docs-example.py']:
            with self.subTest(code=code):
                self.assertTrue(CI.requires_images(['README.md', code]))

    def test_workflow_skips_exactly_the_documentation_paths(self):
        workflow = (ROOT / '.github/workflows/images.yml').read_text()
        block = workflow.split('paths-ignore:\n', 1)[1].split('\n  #', 1)[0]
        ignored = tuple(line.strip()[3:-1] for line in block.splitlines() if line.strip().startswith('- '))
        self.assertEqual(ignored, CI.DOCUMENTATION)

    def test_renames_out_of_docs_are_still_checked(self):
        self.assertTrue(CI.requires_images(['docs/source.py', 'gateway/app/source.py']))

    def test_empty_pr_does_not_need_images(self):
        self.assertFalse(CI.requires_images([]))


def built(result):
    return sorted(f"{entry['component']}/{entry['arch']}" for entry in result['matrix']['include'])


class JobPlanTests(unittest.TestCase):
    def test_documentation_runs_nothing(self):
        result = CI.plan(['README.md', 'docs/images/a.png', 'gateway/DESIGN.md'], pull_request=True)
        self.assertEqual([result[key] for key in ('checks', 'images', 'native', 'windows')], [False] * 4)

    def test_pull_requests_run_fast_checks_without_images_for_tested_code(self):
        for path in ['gateway/app/proxy_editor.py', 'gateway/web/app.js', 'gateway/tests/test_backend.py',
                     'workstation/tests/test-region.py', 'tests/test_deploy.py', 'scripts/ai-install-plan.py']:
            with self.subTest(path=path):
                result = CI.plan([path], pull_request=True)
                self.assertTrue(result['checks'])
                self.assertFalse(result['images'])
                self.assertFalse(result['native'])

    def test_pull_requests_build_only_the_changed_image_on_amd64(self):
        for path, image in [('gateway/runtime/nginx.conf', 'gateway'), ('gateway/Dockerfile', 'gateway'),
                            ('gateway/components.lock.json', 'gateway'), ('workstation/desktop/niu.sh', 'workstation'),
                            ('workstation/versions.env', 'workstation')]:
            with self.subTest(path=path):
                result = CI.plan([path, 'gateway/web/app.js'], pull_request=True)
                self.assertEqual(built(result), [image + '/amd64'])
                self.assertTrue(result['native'])

    def test_native_and_windows_checks_follow_their_files(self):
        result = CI.plan(['install-native.py'], pull_request=True)
        self.assertTrue(result['native'])
        self.assertFalse(result['images'])
        self.assertFalse(result['windows'])
        for path in ['deploy.ps1', 'compose.workstation.yaml', 'scripts/ai-install-plan.py']:
            self.assertTrue(CI.plan([path], pull_request=True)['windows'], path)

    def test_ci_changes_and_full_runs_verify_everything(self):
        for result in (CI.plan(['scripts/ci-changes.py'], pull_request=True),
                       CI.plan(['.github/workflows/images.yml'], pull_request=True),
                       CI.plan(['README.md'], pull_request=True, full=True),
                       CI.plan(None, pull_request=False)):
            self.assertEqual(len(result['matrix']['include']), len(CI.MATRIX))
            self.assertTrue(all(result[key] for key in ('checks', 'gateway', 'workstation', 'native', 'windows')))

    def test_main_rebuilds_changed_images_on_every_architecture(self):
        result = CI.plan(['gateway/web/app.js'], pull_request=False)
        self.assertEqual(built(result), sorted(['gateway/' + arch for arch in ('amd64', 'arm64', '386', 'armv5', 'armv7', 'riscv64')]))
        self.assertFalse(result['workstation'])
        self.assertTrue(result['native'])
        result = CI.plan(['tests/test_deploy.py', 'gateway/tests/test_backend.py'], pull_request=False)
        self.assertTrue(result['checks'])
        self.assertFalse(result['images'] or result['native'])

    def test_only_main_and_release_tags_publish(self):
        self.assertTrue(CI.publishes('push', 'refs/heads/main'))
        self.assertTrue(CI.publishes('push', 'refs/tags/v1.2.0'))
        self.assertTrue(CI.publishes('workflow_dispatch', 'refs/heads/main'))
        self.assertFalse(CI.publishes('workflow_dispatch', 'refs/heads/feature'))
        self.assertFalse(CI.publishes('pull_request', 'refs/pull/48/merge'))


if __name__ == '__main__':
    unittest.main()
