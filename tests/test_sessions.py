#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from datetime import datetime, timezone

from workbrain import sessions as scan
from workbrain import continuity as report
from workbrain.storage import BrainError


def event(text):
    return json.dumps({'type': 'event_msg', 'timestamp': '2020-01-01T00:00:00Z',
                       'payload': {'type': 'agent_message', 'message': text, 'phase': 'final_answer'}}) + '\n'


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / '.codex/sessions').mkdir(parents=True)
        (self.root / '.claude/projects/project').mkdir(parents=True)
        self.addCleanup(self.tmp.cleanup)

    def transcript(self, identity, source='cli'):
        p = self.root / '.codex/sessions/2020/01/01' / (identity + '.jsonl')
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({'type': 'session_meta', 'payload': {
            'id': identity, 'source': source, 'cwd': '/same-project'}}) + '\n' + event('Draft ready; integration remains.'))
        return p

    def run_scan(self):
        return scan.scan([{'tool': 'codex', 'path': str(self.root / '.codex/sessions')},
                          {'tool': 'claude', 'path': str(self.root / '.claude/projects/project')}],
                         self.root / 'state', self.root)

    def test_old_closed_sessions_same_cwd_and_review_persistence(self):
        self.transcript('one'); self.transcript('two')
        self.transcript('child', {'subagent': {}})
        first = self.run_scan()
        self.assertEqual(set(first['sessions']), {'codex:one', 'codex:two'})
        second = self.run_scan()
        self.assertEqual(second['coverage']['changed'], 0)
        self.assertEqual(second['coverage']['needs_review'], 2)
        self.assertNotIn('completed', second['sessions']['codex:one'])

    def test_live_partial_record_then_missing_file(self):
        path = self.transcript('one')
        a = self.run_scan()['sessions']['codex:one']
        with path.open('a') as f:
            f.write(event('New outcome').rstrip('\n'))
        b = self.run_scan()['sessions']['codex:one']
        self.assertEqual(a['digest'], b['digest'])
        with path.open('a') as f:
            f.write('\n')
        c = self.run_scan()['sessions']['codex:one']
        self.assertNotEqual(a['digest'], c['digest'])
        path.unlink()
        missing = self.run_scan()['sessions']['codex:one']
        self.assertEqual(missing['read_status'], 'unavailable')
        self.assertEqual(missing['digest'], c['digest'])

    def test_claude_cwd_survives_unchanged_scan_and_cache_has_no_text(self):
        p = self.root / '.claude/projects/project/parent.jsonl'
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({'type': 'user', 'sessionId': 'parent', 'cwd': '/project',
                                'timestamp': '2020-01-01T00:00:00Z',
                                'message': {'role': 'user', 'content': 'private conversation'}}) + '\n')
        self.run_scan()
        second = self.run_scan()
        self.assertEqual(second['sessions']['claude:parent']['cwd'], '/project')
        for path in (self.root / 'state').glob('*.json'):
            text = path.read_text()
            self.assertNotIn('private conversation', text)
            self.assertNotIn('excerpt', text)

    def review(self, key, disposition='reference'):
        inventory = json.loads((self.root / 'state/inventory.json').read_text())
        s = inventory['sessions'][key]
        return {'session': key, 'digest': s['digest'], 'source_revision': s['source_revision'],
                'disposition': disposition, 'note': 'Reviewed fixture conversation; no task inferred.'}

    def packet(self):
        return json.loads((self.root / 'state/review-packet.json').read_text())

    def test_new_finished_session_discovered_without_a_window_and_never_auto_completed(self):
        self.transcript('old'); self.run_scan()
        self.transcript('new'); self.run_scan(); self.run_scan()
        rows = self.packet()['review_queue']
        self.assertEqual(next(r for r in rows if r['key'] == 'codex:new')['reason'], 'new')
        self.assertNotIn('completed', next(r for r in rows if r['key'] == 'codex:new'))

    def test_exact_review_and_tool_only_update_requires_another_review(self):
        p = self.transcript('one'); self.run_scan()
        receipt = self.review('codex:one')
        scan.apply_reviews(self.root / 'state', [receipt], self.root)
        self.assertEqual(self.run_scan()['coverage']['needs_review'], 0)
        with p.open('a') as f:
            f.write(json.dumps({'type': 'response_item', 'payload': {
                'type': 'function_call_output', 'output': 'New build evidence'}}) + '\n')
        self.assertEqual(self.run_scan()['coverage']['needs_review'], 1)
        self.assertEqual(self.packet()['review_queue'][0]['reason'], 'updated')
        before = (self.root / 'state/reviews.json').read_bytes()
        with self.assertRaises(ValueError):
            scan.apply_reviews(self.root / 'state', [receipt], self.root)
        self.assertEqual((self.root / 'state/reviews.json').read_bytes(), before)

    def test_ambiguous_content_stays_in_queue_and_missing_cannot_be_reviewed(self):
        p = self.transcript('one'); self.run_scan()
        scan.apply_reviews(self.root / 'state', [self.review('codex:one', 'needs_context')], self.root)
        self.run_scan()
        self.assertEqual(self.packet()['review_queue'][0]['reason'], 'needs_context')
        receipt = self.review('codex:one'); p.unlink(); self.run_scan()
        with self.assertRaises(ValueError):
            scan.apply_reviews(self.root / 'state', [receipt], self.root)
        self.assertEqual(len(self.packet()['unavailable_sources']), 1)

    def test_report_coverage_idempotent_and_rejects_stale_day(self):
        self.transcript('one'); self.run_scan()
        packet = self.packet(); day = datetime.now(timezone.utc).date().isoformat()
        p = self.root / 'briefing.md'; p.write_text('# Today · ' + day + '\n\nWork\n')
        report.attach(p, packet, day); before = p.read_bytes(); report.attach(p, packet, day)
        self.assertEqual(p.read_bytes(), before)
        self.assertEqual(p.read_text().count(report.START), 1)
        self.assertIn('historical 1', p.read_text())
        packet['snapshot_at'] = '2020-01-01T00:00:00+00:00'
        with self.assertRaises(BrainError):
            report.attach(p, packet, day)
        self.assertEqual(p.read_bytes(), before)

    def test_missing_source_directory_is_reported(self):
        (self.root / '.claude/projects/project').rmdir()
        data = self.run_scan()
        self.assertGreater(data['coverage']['discovery_errors'], 0)
        self.assertIn('SourceDirectoryMissing', [e['error'] for e in data['errors']])

    def test_malformed_record_cannot_be_acknowledged_as_reviewed(self):
        p = self.transcript('one')
        with p.open('a') as f:
            f.write('{broken record}\n')
        data = self.run_scan()
        self.assertEqual(data['coverage']['malformed_lines'], 1)
        with self.assertRaises(ValueError):
            scan.apply_reviews(self.root / 'state', [self.review('codex:one')], self.root)


    def test_live_change_after_scan_rejects_receipt_without_partial_batch_write(self):
        path = self.transcript('one'); self.run_scan()
        receipt = self.review('codex:one')
        with path.open('a') as stream:
            stream.write(event('Fresh outcome after inventory'))
        with self.assertRaisesRegex(ValueError, 'source changed after scan'):
            scan.apply_reviews(self.root / 'state', [receipt], self.root)
        self.assertFalse((self.root / 'state/reviews.json').exists())

    def test_work_card_must_reference_exact_session(self):
        self.transcript('one'); self.run_scan()
        card = self.root / 'projects/example/work-items/task.json'
        card.parent.mkdir(parents=True)
        request = self.review('codex:one', 'pending')
        request['work_item'] = 'projects/example/work-items/task.json'
        card.write_text(json.dumps({'resume': {'tool': 'codex', 'thread_id': 'other'}}))
        with self.assertRaisesRegex(ValueError, 'exact session'):
            scan.apply_reviews(self.root / 'state', [request], self.root)
        self.assertFalse((self.root / 'state/reviews.json').exists())
        card.write_text(json.dumps({'resume': {'tool': 'codex', 'thread_id': 'one'}}))
        scan.apply_reviews(self.root / 'state', [request], self.root)
        self.assertEqual(self.run_scan()['coverage']['needs_review'], 0)


if __name__ == '__main__':
    unittest.main()
