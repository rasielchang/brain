"""Opt-in scan orchestration and deterministic coverage on current reports."""
import datetime as dt
import json
from zoneinfo import ZoneInfo

from . import sessions
from .storage import BrainError, atomic_write

START = '<!-- brain-session-scan:start -->'
END = '<!-- brain-session-scan:end -->'


def scan(root, config):
    setting = config.get('sessions', {})
    if not setting.get('enabled', False):
        return None
    data = sessions.scan(setting['sources'], root / '.brain/sessions', root)
    return sessions.review_packet(sessions.metadata_only(data))


def coverage(packet, day, timezone='UTC', not_before=None):
    stamp = dt.datetime.fromisoformat(packet['snapshot_at'])
    if stamp.tzinfo is None or stamp.astimezone(ZoneInfo(timezone)).date().isoformat() != day:
        raise BrainError('Session scan is not from the report date; scan again.')
    if not_before is not None and stamp.timestamp() < not_before:
        raise BrainError('Session scan predates this run; scan again.')
    counts, pending = packet['coverage'], packet['pending']
    lines = [START, '## Session review coverage', '', f"Scan: {stamp.isoformat()}",
             f"- Readable: {counts.get('read', 0)}; unavailable: {counts.get('unavailable', 0)}.",
             f"- Pending: new {pending.get('new', 0)}, updated {pending.get('updated', 0)}, "
             f"historical {pending.get('historical', 0)}, needs context {pending.get('needs_context', 0)}.",
             f"- Discovery errors: {counts.get('discovery_errors', 0)}; malformed records: {counts.get('malformed_lines', 0)}.",
             '- Inventory is not semantic review. Missing or unreviewed sources do not establish completion.', '', END]
    return '\n'.join(lines)


def attach(path, packet, day, timezone='UTC', not_before=None):
    content = path.read_text()
    if not content.startswith('# Today · ' + day + '\n'):
        raise BrainError('Report title/date does not match current scan.')
    block = coverage(packet, day, timezone, not_before)
    if START in content or END in content:
        if content.count(START) != 1 or content.count(END) != 1 or content.index(START) > content.index(END):
            raise BrainError('Ambiguous session coverage markers; report kept.')
        content = content[:content.index(START)] + block + content[content.index(END) + len(END):]
    else:
        content = content.rstrip() + '\n\n' + block + '\n'
    atomic_write(path, content)


def validate_today(content, config, day):
    if not content.startswith('# Today · ' + day + '\n') or len(content.strip()) < 200:
        raise BrainError('Daily report has an invalid title/date or insufficient content.')
    if day in config.get('non_working_dates', []):
        return
    weekday = dt.date.fromisoformat(day).isoweekday()
    names = [r['name'] for r in config.get('routines', [])
             if weekday in r.get('weekdays', []) and day >= r.get('start_on', '')]
    focus = config.get('weekly_focus', {}).get(str(weekday), [])
    names += [p['name'] for p in config['projects'] if p['id'] in focus
              and p.get('active', True) and p.get('status') not in ('paused', 'waiting_customer')]
    if any(name.casefold() not in content.casefold() for name in names):
        raise BrainError('Daily report omitted a scheduled routine or focus project; previous report kept.')
