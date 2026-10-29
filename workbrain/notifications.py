"""Optional argv adapter; stable request receipts across ambiguous retries.

The configured receiver must deduplicate request_id. Brain never treats an
accepted request as proof that a person read it or that work was completed.
"""
import datetime as dt
import hashlib
import json
import subprocess

from .storage import BrainError, write_json


def deliver(root, config, report, day):
    setting = config.get('notifications', {})
    if not setting.get('enabled', False):
        return {'state': 'disabled'}
    folder = root / '.brain/delivery'
    receipt = folder / (day + '.json')
    saved = json.loads(receipt.read_text()) if receipt.exists() else None
    command = setting['command']
    adapter = hashlib.sha256(json.dumps(command).encode()).hexdigest()
    if saved and saved['adapter_sha256'] != adapter:
        raise BrainError('Notification adapter changed for an existing receipt; reconcile delivery first.')
    if saved and saved.get('accepted'):
        return {'state': 'already_accepted', 'request_id': saved['request']['request_id']}
    if not saved:
        scope = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
        content = report.read_text()
        request = {'request_id': f'brain-{scope}-{day}', 'date': day,
                   'kind': 'daily_briefing', 'text': content}
        saved = {'request': request, 'adapter_sha256': adapter,
                 'report_sha256': hashlib.sha256(content.encode()).hexdigest(),
                 'attempted_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'accepted': False}
        write_json(receipt, saved)  # Persist exact payload before any side effect.
    try:
        result = subprocess.run(command, input=json.dumps(saved['request']),
                                capture_output=True, text=True, timeout=30, check=True, cwd=root)
        reply = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        raise BrainError('Notification failed or was not acknowledged; retry uses the saved request. Adapter output withheld.') from None
    if reply.get('accepted') is not True or reply.get('request_id') != saved['request']['request_id']:
        raise BrainError('Notification acknowledgement does not match the saved request.')
    saved.update(accepted=True, accepted_at=dt.datetime.now(dt.timezone.utc).isoformat())
    write_json(receipt, saved)
    return {'state': 'accepted', 'request_id': saved['request']['request_id']}
