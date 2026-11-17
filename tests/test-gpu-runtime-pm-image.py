#!/usr/bin/env python3
"""Exercise real GPU policy migration and rejection of incomplete ext4 delivery."""
import os
import subprocess
import unittest

from image_delivery import ImageTest, PROJECT, load_verifier

verifier = load_verifier('gpu-runtime-pm')
UNIT = 'gpu-runtime-pm.service'
OLD = 'gpu-runtime-active.service'


class GPUImageTests(ImageTest):
    def setUp(self):
        super().setUp()
        # The installer must work offline without executing the target shell.
        self.put('usr/bin/bash', b'#!/bin/sh\nexit 99\n', 0o755)
        self.link('usr/bin/sh', 'bash')

    def install(self):
        subprocess.run(['bash', str(PROJECT / 'scripts/configure-gpu-runtime-pm.sh'),
                        str(self.root), str(self.logs)], check=True, capture_output=True,
                       env=dict(os.environ, SUDO_UID='0', SUDO_GID='0'))

    def verify(self):
        self.image()
        return verifier.verify(self.base, self.logs)

    def test_fresh_install_and_migration(self):
        self.install()
        self.assertEqual(self.verify()['power_control'], 'auto')
        # Old completion markers and old enablement must not bypass migration.
        self.link(f'etc/systemd/system/graphical.target.wants/{OLD}', f'../{OLD}')
        self.put(f'etc/systemd/system/{UNIT}', b'old unit\n')
        (self.logs / 'images.complete').touch()
        self.install()
        self.assertFalse((self.logs / 'images.complete').exists())
        self.assertTrue((self.logs / 'images.complete.before-gpu-runtime-pm').exists())
        self.assertFalse((self.root / f'etc/systemd/system/graphical.target.wants/{OLD}').is_symlink())
        self.assertFalse(self.verify()['forced_active_enabled'])
        subprocess.run(['sha256sum', '--check', '--status',
                        str(self.logs / 'gpu-runtime-pm-sources.sha256')], cwd=PROJECT, check=True)
        self.install()
        self.verify()

    def test_missing_enablement_is_rejected(self):
        self.install()
        (self.root / f'etc/systemd/system/graphical.target.wants/{UNIT}').unlink()
        with self.assertRaises(RuntimeError):
            self.verify()

    def test_forced_active_in_any_target_is_rejected(self):
        self.install()
        self.link(f'etc/systemd/system/multi-user.target.wants/{OLD}', f'../{OLD}')
        with self.assertRaisesRegex(RuntimeError, 'Forced-active'):
            self.verify()

    def test_old_policy_or_wrong_permissions_are_rejected(self):
        self.install()
        path = self.root / f'etc/systemd/system/{UNIT}'
        good = path.read_bytes()
        path.write_bytes(good.replace(b'printf auto', b'printf on'))
        with self.assertRaisesRegex(RuntimeError, 'mismatch'):
            self.verify()
        path.write_bytes(good)
        path.chmod(0o666)
        with self.assertRaisesRegex(RuntimeError, 'mode 0644'):
            self.verify()

    def test_missing_fallback_unit_is_rejected(self):
        self.install()
        (self.root / f'etc/systemd/system/{OLD}').unlink()
        with self.assertRaises(RuntimeError):
            self.verify()


if __name__ == '__main__':
    unittest.main()
