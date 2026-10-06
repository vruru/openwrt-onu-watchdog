"""Exercise the real installer preflight without touching an OpenWrt system."""

from pathlib import Path
import shlex
import subprocess
import unittest


INSTALLER = (Path(__file__).resolve().parents[1] / 'install.sh').read_text()
START = INSTALLER.index('\nset --\n')
END = INSTALLER.index('set_stage backup', START)
SNIPPET = INSTALLER[START:END] + '\necho PREFLIGHT_OK\n'


def run_preflight(missing=(), has_opkg=True, install_fails=False, omit_flock=False):
    available = [cmd for cmd in (
        'sha256sum', 'awk', 'sed', 'ubus', 'uci',
        'curl', 'openssl', 'jsonfilter', 'flock',
    ) if cmd not in missing]
    if has_opkg:
        available.append('opkg')
    script = f'''
set -eu
available={shlex.quote(' '.join(available))}
install_fails={int(install_fails)}
omit_flock={int(omit_flock)}
command() {{
    [ "$1" = '-v' ] || return 2
    case " $available " in
        *" $2 "*) return 0 ;;
        *) return 1 ;;
    esac
}}
opkg() {{
    printf 'OPKG'
    printf ' <%s>' "$@"
    printf '\\n'
    [ "$1" = update ] && return 0
    [ "$install_fails" = 0 ] || return 1
    [ "$1" = install ] || return 2
    shift
    for pkg in "$@"; do
        case "$pkg" in
            openssl-util) available="$available openssl" ;;
            flock) [ "$omit_flock" = 1 ] || available="$available flock" ;;
            *) available="$available $pkg" ;;
        esac
    done
    return 0
}}
{SNIPPET}
'''
    return subprocess.run(['/bin/sh'], input=script, text=True,
                          capture_output=True, timeout=10)


class TestPreflight(unittest.TestCase):
    def assert_success(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PREFLIGHT_OK', result.stdout)

    def assert_failure(self, result):
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('PREFLIGHT_OK', result.stdout)

    def test_all_present(self):
        result = run_preflight()
        self.assert_success(result)
        self.assertNotIn('OPKG', result.stdout)

    def test_flock_missing(self):
        result = run_preflight(missing=('flock',))
        self.assert_success(result)
        self.assertEqual([line for line in result.stdout.splitlines()
                          if line.startswith('OPKG')],
                         ['OPKG <update>', 'OPKG <install> <flock>'])

    def test_all_four_missing(self):
        result = run_preflight(missing=('curl', 'openssl', 'jsonfilter', 'flock'))
        self.assert_success(result)
        self.assertIn('OPKG <install> <curl> <openssl-util> <jsonfilter> <flock>\n',
                      result.stdout)

    def test_no_opkg(self):
        result = run_preflight(missing=('flock',), has_opkg=False)
        self.assert_failure(result)
        self.assertIn('缺少 opkg', result.stderr)
        self.assertNotIn('OPKG', result.stdout)

    def test_install_fail(self):
        result = run_preflight(missing=('flock',), install_fails=True)
        self.assert_failure(result)
        self.assertIn('OPKG <install> <flock>', result.stdout)

    def test_flock_omit_after_install(self):
        result = run_preflight(missing=('flock',), omit_flock=True)
        self.assert_failure(result)
        self.assertIn('缺少必要命令：flock', result.stderr)


if __name__ == '__main__':
    unittest.main()
