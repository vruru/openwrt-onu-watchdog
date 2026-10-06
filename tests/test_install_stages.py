"""Run the complete installer against a temporary device and mock services."""
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
FILES = ('onu-watchdog', 'onu-watchdog.init', 'onu_watchdog.uci',
         'luci-app-onu-watchdog.menu.json', 'luci-app-onu-watchdog.acl.json',
         'onu-watchdog.js', 'onu-watchdog-log.js')


class InstallStages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.device = self.root / 'device'
        self.source.mkdir()
        for name in FILES:
            shutil.copyfile(REPO / name, self.source / name)
        # The installer copies this service mock instead of invoking OpenWrt rc.common.
        (self.source / 'onu-watchdog.init').write_text('#!/bin/sh\nexit 0\n')
        for directory in ('www/luci-static/resources', 'usr/sbin', 'etc/init.d',
                          'etc/config', 'root', 'tmp/luci-modulecache'):
            (self.device / directory).mkdir(parents=True)
        for name in ('onu_watchdog', 'network', 'firewall'):
            (self.device / 'etc/config' / name).write_text('existing legal configuration\n')
        for name in ('last_reboot', 'events'):
            (self.device / ('etc/onu-watchdog.' + name)).write_text('existing state\n')
        for service in ('network', 'firewall', 'rpcd'):
            target = self.device / 'etc/init.d' / service
            target.write_text('#!/bin/sh\nexit 0\n')
            target.chmod(0o755)
        # Mock platform commands. Nothing reads or changes a real device.
        prefix = '''id() { echo 0; }
command() { return 0; }
sleep() { :; }
uci() {
 case "$*" in
  *'get onu_watchdog.main.enabled') echo 0;;
  *'get network.lan.ipaddr') echo fixture;;
  *) return 0;;
 esac
}
'''
        raw = (REPO / 'install.sh').read_text()
        raw = re.sub(r'/(?:usr|etc|www|root|tmp)/',
                     lambda match: str(self.device) + match.group(), raw)
        # Fault at a phase entrance. All earlier phases execute unchanged.
        raw = raw.replace('started\\n\' "$INSTALL_STAGE" >> "$BACKUP_DIR/install-stage.log"\n\tfi',
                          'started\\n\' "$INSTALL_STAGE" >> "$BACKUP_DIR/install-stage.log"\n\tfi\n'
                          '\t[ "$INSTALL_STAGE" != "${FAIL_STAGE:-}" ] || return 71')
        self.script = self.source / 'install.sh'
        self.script.write_text(prefix + raw)

    def run_install(self, stage=''):
        return subprocess.run(['/bin/sh', str(self.script)],
                              env=dict(os.environ, FAIL_STAGE=stage),
                              capture_output=True, text=True, timeout=10)

    def assert_config_state_preserved(self):
        for name in ('onu_watchdog', 'network', 'firewall'):
            self.assertEqual((self.device / 'etc/config' / name).read_text(),
                             'existing legal configuration\n')
        for name in ('last_reboot', 'events'):
            self.assertEqual((self.device / ('etc/onu-watchdog.' + name)).read_text(),
                             'existing state\n')

    def test_missing_source_fails_before_backup_or_copy(self):
        (self.source / 'onu_watchdog.uci').unlink()
        result = self.run_install()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('阶段=preflight', result.stderr)
        self.assertEqual(list((self.device / 'root').iterdir()), [])
        self.assertFalse((self.device / 'usr/sbin/onu-watchdog').exists())
        self.assert_config_state_preserved()

    def test_failure_journal_identifies_every_mutating_stage(self):
        for stage in ('dependencies', 'backup', 'runtime-files', 'uci-config',
                      'network-reload', 'firewall-reload', 'service-restart', 'acceptance'):
            with self.subTest(stage=stage):
                # Independent invocation/device for each failure.
                with tempfile.TemporaryDirectory() as isolated:
                    source = self.source / 'install.sh'
                    original = source.read_text()
                    try:
                        source.write_text(original.replace(str(self.device / 'root'), isolated))
                        result = self.run_install(stage)
                    finally:
                        source.write_text(original)
                    self.assertEqual(result.returncode, 71, result.stderr)
                    self.assertIn('阶段=' + stage, result.stderr)
                    journals = list(Path(isolated).glob('*/install-stage.log'))
                    if stage not in ('dependencies', 'backup'):
                        self.assertEqual(len(journals), 1)
                        self.assertIn(stage + ' failed exit=71', journals[0].read_text())
                    else:
                        self.assertEqual(journals, [])
                    self.assert_config_state_preserved()

    def test_success_records_complete_and_keeps_current_configuration(self):
        result = self.run_install()
        self.assertEqual(result.returncode, 0, result.stderr)
        journals = list((self.device / 'root').glob('*/install-stage.log'))
        self.assertEqual(len(journals), 1)
        self.assertIn('complete started', journals[0].read_text())
        self.assert_config_state_preserved()


if __name__ == '__main__':
    unittest.main()
