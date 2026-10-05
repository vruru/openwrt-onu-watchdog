"""Run the real backup loop in a temporary filesystem, never on OpenWrt."""

import hashlib
from pathlib import Path
import re
import shlex
import stat
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]
INSTALLER = (REPO / 'install.sh').read_text()
SNIPPET = INSTALLER[INSTALLER.index('mkdir -p "$BACKUP_DIR"'):
                    INSTALLER.index('cp "$ROOT/onu-watchdog"')]
# Redirect only the source list and strip that test prefix at the destination.
SNIPPET = re.sub(r'(?m)^(\s*)(/(?:usr|etc|www)/[^\s;]+)',
                 r'\1"$TEST_ROOT\2"', SNIPPET)
SNIPPET = SNIPPET.replace('"$BACKUP_DIR$file"',
                          '"$BACKUP_DIR${file#"$TEST_ROOT"}"')
SOURCES = {
    'usr/sbin/onu-watchdog': 'onu-watchdog',
    'etc/init.d/onu-watchdog': 'onu-watchdog.init',
    'usr/share/luci/menu.d/luci-app-onu-watchdog.json':
        'luci-app-onu-watchdog.menu.json',
    'usr/share/rpcd/acl.d/luci-app-onu-watchdog.json':
        'luci-app-onu-watchdog.acl.json',
    'www/luci-static/resources/view/services/onu-watchdog.js': 'onu-watchdog.js',
    'www/luci-static/resources/view/services/onu-watchdog-log.js':
        'onu-watchdog-log.js',
}
STATE = ('etc/config/onu_watchdog', 'etc/onu-watchdog.last_reboot',
         'etc/onu-watchdog.events', 'etc/config/network', 'etc/config/firewall')
COLLISIONS = (
    ('usr/sbin/onu-watchdog', 'etc/init.d/onu-watchdog'),
    ('usr/share/luci/menu.d/luci-app-onu-watchdog.json',
     'usr/share/rpcd/acl.d/luci-app-onu-watchdog.json'),
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestInstallBackups(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='onu backup test ')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'device root'
        self.backup = Path(temp.name) / 'backup root'
        self.root.mkdir()
        self.contents = {rel: (REPO / source).read_bytes()
                         for rel, source in SOURCES.items()}
        self.contents.update({rel: (rel + '\n').encode() for rel in STATE})
        for rel, content in self.contents.items():
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            path.chmod(0o750 if rel in COLLISIONS[0] else 0o600)

    def run_backup(self, fault=''):
        script = (f'set -eu\nTEST_ROOT={shlex.quote(str(self.root))}\n'
                  f'BACKUP_DIR={shlex.quote(str(self.backup))}\n'
                  + fault + '\n' + SNIPPET + '\necho INSTALL_STARTED\n')
        return subprocess.run(['/bin/sh'], input=script, text=True,
                              capture_output=True, timeout=10)

    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('INSTALL_STARTED', result.stdout)

    def assert_originals_unchanged(self):
        for rel, content in self.contents.items():
            self.assertEqual((self.root / rel).read_bytes(), content, rel)

    def test_real_hash_collisions_preserve_both_files(self):
        # Reproduce the documented old copy order using the real source bytes.
        for first, second in COLLISIONS:
            self.assertEqual(Path(first).name, Path(second).name)
            self.assertNotEqual(sha256(self.root / first), sha256(self.root / second))
            flat = self.root / Path(first).name
            for rel in (first, second):
                subprocess.run(['cp', '-a', str(self.root / rel), str(flat)],
                               check=True, capture_output=True)
            self.assertEqual(sha256(flat), sha256(self.root / second))
        self.assert_success(self.run_backup())
        for pair in COLLISIONS:
            for rel in pair:
                self.assertEqual(sha256(self.backup / rel), sha256(self.root / rel))
        self.assert_originals_unchanged()

    def test_all_eleven_paths_content_and_permissions(self):
        self.assert_success(self.run_backup())
        actual = {str(path.relative_to(self.backup))
                  for path in self.backup.rglob('*') if path.is_file()}
        self.assertEqual(actual, set(self.contents))
        for rel in self.contents:
            source, saved = self.root / rel, self.backup / rel
            self.assertEqual(sha256(saved), sha256(source), rel)
            self.assertEqual(stat.S_IMODE(saved.stat().st_mode),
                             stat.S_IMODE(source.stat().st_mode), rel)

    def test_missing_files_are_skipped(self):
        missing = ('etc/onu-watchdog.last_reboot', 'etc/config/firewall')
        for rel in missing:
            (self.root / rel).unlink()
        self.assert_success(self.run_backup())
        for rel in self.contents:
            self.assertEqual((self.backup / rel).exists(), rel not in missing)

    def test_no_existing_files(self):
        for rel in self.contents:
            (self.root / rel).unlink()
        self.assert_success(self.run_backup())
        self.assertTrue(self.backup.is_dir())
        self.assertEqual(list(self.backup.iterdir()), [])

    def test_copy_failure_aborts_before_install(self):
        result = self.run_backup('''
cp() {
    case "$3" in */etc/init.d/onu-watchdog) return 71 ;; esac
    command cp "$@"
}
''')
        self.assertEqual(result.returncode, 71, result.stderr)
        self.assertNotIn('INSTALL_STARTED', result.stdout)
        self.assertEqual(sha256(self.backup / 'usr/sbin/onu-watchdog'),
                         sha256(self.root / 'usr/sbin/onu-watchdog'))
        self.assert_originals_unchanged()

    def test_directory_failure_aborts_before_install(self):
        result = self.run_backup('''
mkdir() {
    case "$2" in "$BACKUP_DIR"/etc/init.d) return 72 ;; esac
    command mkdir "$@"
}
''')
        self.assertEqual(result.returncode, 72, result.stderr)
        self.assertNotIn('INSTALL_STARTED', result.stdout)
        self.assert_originals_unchanged()


if __name__ == '__main__':
    unittest.main()
