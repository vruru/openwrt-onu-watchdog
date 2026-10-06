"""Exercise the actual shell functions with isolated paths and fake devices."""
import json
import os
from pathlib import Path
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'onu-watchdog'
RANGES = {'check_interval': (5, 300), 'fail_seconds': (30, 3600),
          'post_reboot_wait': (120, 1800), 'reboot_cooldown': (600, 86400)}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.config = {k: str(lo) for k, (lo, hi) in RANGES.items()}
        self.config.update(modem_url='http://fixture.invalid', modem_password='fixture', wan_interface='WAN')
        self.cfg = self.root / 'uci.json'
        self.cfg.write_text(json.dumps(self.config))
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        CFG=str(self.cfg), SIDE_EFFECTS=str(self.root / 'effects'))
        self.fake('uci', '#!' + sys.executable + '\nimport json,os,sys\n'
                  'key=sys.argv[-1]\n'
                  'if key == "onu_watchdog.main": print("watchdog"); sys.exit(0)\n'
                  'print(json.load(open(os.environ["CFG"]))[key.rsplit(".",1)[-1]])\n', shell=False)
        self.fake('logger', 'printf "%s\\n" "$*" >&2')
        self.fake('ubus', 'echo ubus >> "$SIDE_EFFECTS"; echo fixture')
        self.fake('jsonfilter', 'cat >/dev/null; case "$2" in "@.up") echo true;; *) echo eth0;; esac')
        self.fake('ping', 'echo "$*" >> "$SIDE_EFFECTS"; for target; do :; done; [ "$target" = "$PING_OK" ]')
        self.fake('curl', 'echo curl >> "$SIDE_EFFECTS"; exit 99')
        raw = SOURCE.read_text().replace('/etc/onu-watchdog', str(self.root / 'onu-watchdog'))
        raw = raw.replace('/var/lock/', str(self.root) + '/').replace('/tmp/onu-reboot.', str(self.root / 'reboot.'))
        self.functions = raw.split('case "${1:-daemon}" in')[0]
        self.raw = raw
        self.events = self.root / 'onu-watchdog.events'
        self.state = self.root / 'onu-watchdog.last_reboot'

    def fake(self, name, text, shell=True):
        p = self.bin / name
        p.write_text(('#!/bin/sh\n' if shell else '') + text + '\n')
        p.chmod(0o755)

    def script(self, body, full=False):
        p = self.root / ('script-' + str(time.monotonic_ns()))
        p.write_text((self.raw if full else self.functions + '\n' + body) + '\n')
        return p

    def run_script(self, body='', full=False, args=(), extra=None):
        return subprocess.run(['/bin/sh', str(self.script(body, full)), *args],
                              env=dict(self.env, **(extra or {})), capture_output=True,
                              text=True, timeout=15)

    def spawn(self, body):
        p = subprocess.Popen(['/bin/sh', str(self.script(body))], env=self.env,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
        self.addCleanup(self.stop, p)
        self.assertTrue(select.select([p.stdout], [], [], 10)[0], 'child did not become ready')
        self.assertEqual(p.stdout.readline().strip(), 'ready')
        return p

    @staticmethod
    def stop(p):
        if p.poll() is None:
            os.killpg(p.pid, signal.SIGTERM)
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
                p.wait(timeout=5)
        for pipe in (p.stdin, p.stdout, p.stderr):
            if pipe and not pipe.closed:
                pipe.close()

    def test_all_numeric_boundaries_and_invalid_inputs(self):
        for key, (lo, hi) in RANGES.items():
            for value, valid in [(str(lo), True), (str(hi), True),
                                 ('000' + str(lo), True), (str(lo - 1), False),
                                 (str(hi + 1), False), ('0', False), ('-1', False),
                                 ('abc', False), ('1.5', False), ('9' * 1000, False),
                                 ('１２', False), (' 30', False)]:
                with self.subTest(key=key, value=value[:12]):
                    cfg = dict(self.config, **{key: value})
                    self.cfg.write_text(json.dumps(cfg))
                    result = self.run_script('printf "%s\\n" "$' + key.upper() + '"')
                    self.assertEqual(result.returncode == 0, valid, result.stderr)
                    if valid:
                        self.assertEqual(result.stdout.strip(), str(int(value)))
                    else:
                        self.assertIn(key.upper(), result.stderr)
                        self.assertFalse((self.root / 'effects').exists())
                        self.assertFalse(self.events.exists())
            self.cfg.write_text(json.dumps(self.config))

    def test_invalid_config_blocks_every_dispatch(self):
        self.cfg.write_text(json.dumps(dict(self.config, check_interval='0')))
        for mode in ('daemon', 'check', 'reboot-now', 'events', 'clear-events'):
            result = self.run_script(full=True, args=(mode,))
            self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.root / 'effects').exists())
        self.assertFalse(self.events.exists())

    def test_legacy_config_and_missing_defaults(self):
        self.fake('uci', 'exit 1')
        (self.root / 'onu-watchdog.conf').write_text('CHECK_INTERVAL=00008\nMODEM_PASSWORD=fixture\n')
        result = self.run_script('printf "%s %s %s %s\\n" "$CHECK_INTERVAL" "$FAIL_SECONDS" "$POST_REBOOT_WAIT" "$REBOOT_COOLDOWN"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), '8 60 300 21600')
        (self.root / 'onu-watchdog.conf').write_text('FAIL_SECONDS=-1\n')
        self.assertNotEqual(self.run_script().returncode, 0)

    def test_probe_either_target_and_all_failed(self):
        for target, expected in [('223.5.5.5', 0), ('119.29.29.29', 0), ('none', 1)]:
            with self.subTest(target=target):
                result = self.run_script('internet_ok', extra={'PING_OK': target})
                self.assertEqual(result.returncode, expected, result.stderr)
        self.assertNotIn('curl', (self.root / 'effects').read_text())

    @unittest.skipUnless(shutil.which('flock'), 'Linux flock needed')
    def test_daemon_second_instance_and_exit_release(self):
        first = self.spawn('internet_ok() { echo ready; read -r answer; }; run_daemon')
        count = self.events.read_text().count('service_started')
        second = self.run_script('internet_ok() { echo unwanted; }; run_daemon')
        self.assertEqual(second.returncode, 2, second.stderr)
        self.assertIn('already running', second.stderr)
        self.assertNotIn('unwanted', second.stdout)
        self.assertEqual(self.events.read_text().count('service_started'), count)
        self.stop(first)
        restarted = self.spawn('internet_ok() { echo ready; read -r answer; }; run_daemon')
        self.stop(restarted)
        self.assertTrue((self.root / 'onu-watchdog-daemon.lock').exists())

    @unittest.skipUnless(shutil.which('flock'), 'Linux flock needed')
    def test_reboot_exclusion_persistence_and_latest_cooldown(self):
        first = self.spawn('modem_reboot() { echo ready; read -r answer; }; reboot_with_state manual 0')
        busy = self.run_script('modem_reboot() { echo unwanted; }; reboot_with_state automatic 60')
        self.assertEqual(busy.returncode, 2, busy.stderr)
        self.assertNotIn('unwanted', busy.stdout)
        self.assertFalse(self.state.exists())
        first.stdin.write('finish\n')
        first.stdin.flush()
        self.assertEqual(first.wait(timeout=5), 0, first.stderr.read())
        self.assertEqual(self.state.read_text().split()[1], 'manual')
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o600)
        cooldown = self.run_script('modem_reboot() { echo unwanted; }; reboot_with_state automatic 60')
        self.assertEqual(cooldown.returncode, 2, cooldown.stderr)
        self.assertNotIn('unwanted', cooldown.stdout)
        self.assertNotIn('reboot_failed', self.events.read_text())
        # The manual entry point can acquire the released lock.
        again = self.run_script('modem_reboot() { return 0; }; reboot_with_state manual 0')
        self.assertEqual(again.returncode, 0, again.stderr)

    @unittest.skipUnless(shutil.which('flock'), 'Linux flock needed')
    def test_event_line_limit_latest_record_and_permissions(self):
        self.events.write_text(''.join(f'{i}\tt\ts\t0\tdetail\n' for i in range(500)))
        result = self.run_script('record_event_at 999 new source 0 detail')
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = self.events.read_text().splitlines()
        self.assertEqual(len(lines), 400)
        self.assertTrue(lines[-1].startswith('999\tnew\t'))
        self.assertEqual(self.events.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.root.glob('*.tmp.*')), [])

    @unittest.skipUnless(shutil.which('flock'), 'Linux flock needed')
    def test_event_byte_limit_preserves_complete_unicode_records(self):
        detail = '光猫' * 100
        self.events.write_text(''.join(f'{i}\tt\ts\t0\t{detail}\n' for i in range(400)))
        result = self.run_script('record_event_at 999 new source 0 "恢复正常"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLessEqual(self.events.stat().st_size, 131072)
        lines = self.events.read_text(encoding='utf-8').splitlines()
        self.assertTrue(all(x.endswith(detail) for x in lines[:-1]))
        self.assertTrue(lines[-1].endswith('恢复正常'))
        self.assertEqual(list(self.root.glob('*.tmp.*')), [])

    @unittest.skipUnless(shutil.which('flock'), 'Linux flock needed')
    def test_oversize_newest_record_is_dropped_without_byte_slicing(self):
        self.events.write_text('1\tt\ts\t0\t保留\n')
        (self.root / 'huge').write_text('界' * 50000)
        result = self.run_script('record_event_at 2 t s 0 "$(cat "' + str(self.root / 'huge') + '")"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.events.read_text(), '1\tt\ts\t0\t保留\n')


if __name__ == '__main__':
    unittest.main()
