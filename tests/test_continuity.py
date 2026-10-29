import copy
import datetime as dt
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from workbrain import continuity, notifications
from workbrain.cli import initialize, main
from workbrain.config import DEFAULT, validate
from workbrain.storage import BrainError, write_json


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.config = copy.deepcopy(DEFAULT)
        self.day = dt.datetime.now(dt.timezone.utc).date().isoformat()

    def test_opt_in_and_no_implicit_home_scan(self):
        with patch('workbrain.sessions.scan') as scan:
            self.assertIsNone(continuity.scan(self.root, self.config))
            scan.assert_not_called()
        for sources in ([], [{'tool': 'codex', 'path': str(Path.home())}], [{'tool': 'other', 'path': '/path/to/logs'}]):
            self.config['sessions'] = {'enabled': True, 'sources': sources}
            with self.assertRaises(BrainError):
                validate(self.config)

    def test_focus_and_routine_check_uses_names_not_emoji(self):
        day = '2026-01-12'
        self.config['projects'] = [{'id': 'alpha', 'name': 'Project Alpha'}]
        self.config['weekly_focus'] = {'1': ['alpha']}
        good = '# Today · ' + day + '\n\nProject Alpha\nWrite\n' + 'Evidence remains unverified. ' * 12
        continuity.validate_today(good, self.config, day)
        for omitted in ('Project Alpha', 'Write'):
            with self.assertRaises(BrainError):
                continuity.validate_today(good.replace(omitted, ''), self.config, day)
        self.config['non_working_dates'] = [day]
        continuity.validate_today(good.replace('Write', '').replace('Project Alpha', ''), self.config, day)

    def test_same_day_stale_scan_cannot_replace_report(self):
        p = self.root / 'report.md'
        p.write_text('# Today · ' + self.day + '\n\nExisting evidence\n')
        before = p.read_bytes()
        packet = {'snapshot_at': self.day + 'T00:00:00+00:00', 'coverage': {}, 'pending': {}}
        with self.assertRaises(BrainError):
            continuity.attach(p, packet, self.day, not_before=dt.datetime.now(dt.timezone.utc).timestamp() + 1)
        self.assertEqual(p.read_bytes(), before)

    def test_notification_timeout_retry_is_identical_and_acknowledgement_deduplicates(self):
        self.config['notifications'] = {'enabled': True, 'command': ['/path/to/adapter']}
        p = self.root / 'report.md'; p.write_text('Reviewed original report')
        requests = []
        def send(argv, **kwargs):
            requests.append(json.loads(kwargs['input']))
            if len(requests) == 1:
                raise subprocess.TimeoutExpired('adapter', 30)
            return subprocess.CompletedProcess(argv, 0, json.dumps({'accepted': True, 'request_id': requests[-1]['request_id']}))
        with patch('workbrain.notifications.subprocess.run', send):
            with self.assertRaises(BrainError):
                notifications.deliver(self.root, self.config, p, self.day)
            p.write_text('Changed report after an ambiguous timeout')
            self.assertEqual(notifications.deliver(self.root, self.config, p, self.day)['state'], 'accepted')
            self.assertEqual(notifications.deliver(self.root, self.config, p, self.day)['state'], 'already_accepted')
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0], requests[1])
        self.assertEqual((self.root / '.brain/delivery' / (self.day + '.json')).stat().st_mode & 0o777, 0o600)

    def test_morning_attaches_coverage_and_missing_source_withholds_notification(self):
        initialize(self.root)
        self.config['sessions'] = {'enabled': True, 'sources': [{'tool': 'codex', 'path': str(self.root / 'missing')}]}
        self.config['notifications'] = {'enabled': True, 'command': ['/path/to/adapter']}
        write_json(self.root / '.brain/config.json', self.config)
        with patch('workbrain.notifications.deliver') as delivery:
            self.assertEqual(main(['--root', str(self.root), 'morning']), 1)
            delivery.assert_not_called()
        text = (self.root / 'daily' / (self.day + '.source.md')).read_text()
        self.assertIn('Discovery errors: 1', text)
        self.assertIn(continuity.START, text)

    def test_weekday_schedule_generation_does_not_activate_any_job(self):
        import plistlib
        initialize(self.root)
        self.assertEqual(main(['--root', str(self.root), 'launchd', '--hour', '7', '--minute', '0', '--weekdays']), 0)
        config = plistlib.loads((self.root / '.brain/dev.brain.morning.plist').read_bytes())
        self.assertEqual(config['StartCalendarInterval'], [{'Weekday': d, 'Hour': 7, 'Minute': 0} for d in range(1, 6)])

    def test_successful_morning_delivers_current_coverage_only_after_report(self):
        initialize(self.root)
        folder = self.root / 'approved'; folder.mkdir()
        self.config['sessions'] = {'enabled': True, 'sources': [{'tool': 'codex', 'path': str(folder)}]}
        write_json(self.root / '.brain/config.json', self.config)
        received = []
        def deliver(root, config, report, day):
            received.append(report.read_text())
            return {'state': 'disabled'}
        with patch('workbrain.notifications.deliver', deliver):
            self.assertEqual(main(['--root', str(self.root), 'morning']), 0)
        self.assertEqual(len(received), 1)
        self.assertIn(continuity.START, received[0])
        self.assertIn('Discovery errors: 0', received[0])
