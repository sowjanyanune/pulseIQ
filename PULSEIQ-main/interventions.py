"""Session-owned actions with append-only revision history."""
from copy import deepcopy
from datetime import date, datetime, timezone
import uuid
import pandas as pd

STATUSES = ['Planned', 'In progress', 'Reviewed', 'Closed']
ACTION_COLUMNS = ['intervention_id', 'student_id', 'owner_alias', 'action', 'rationale',
                  'created_at', 'updated_at', 'due_date', 'status', 'review_note']
HISTORY_COLUMNS = ['intervention_id', 'event', 'at'] + ACTION_COLUMNS[1:]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _validate(owner_alias, action, due_date, status, review_note):
    if not owner_alias.strip() or not action.strip():
        raise ValueError('Provide an owner alias and an action.')
    if len(owner_alias) > 80 or len(action) > 2000 or len(review_note) > 2000:
        raise ValueError('Owner limit is 80 characters; actions and notes are limited to 2,000.')
    if status not in STATUSES:
        raise ValueError('Select a valid action status.')
    date.fromisoformat(str(due_date))
    if status in ['Reviewed', 'Closed'] and not review_note.strip():
        raise ValueError('Reviewed and Closed actions need a review note.')


def create_action(actions, history, *, student_id, owner_alias, action, due_date, rationale=''):
    _validate(owner_alias, action, due_date, 'Planned', '')
    stamp = _now()
    record = dict(intervention_id=uuid.uuid4().hex[:12], student_id=str(student_id),
                  owner_alias=owner_alias.strip(), action=action.strip(), rationale=rationale.strip(),
                  created_at=stamp, updated_at=stamp, due_date=str(due_date), status='Planned', review_note='')
    return actions + [record], history + [dict(event='Created', at=stamp, **deepcopy(record))]


def update_action(actions, history, intervention_id, *, owner_alias, action, due_date, status, review_note):
    _validate(owner_alias, action, due_date, status, review_note)
    updated = deepcopy(actions)
    for record in updated:
        if record['intervention_id'] == intervention_id:
            old = record['status']
            record.update(owner_alias=owner_alias.strip(), action=action.strip(), due_date=str(due_date),
                          status=status, review_note=review_note.strip(), updated_at=_now())
            reopened = old in ('Reviewed', 'Closed') and status in ('Planned', 'In progress')
            event = 'Reopened' if reopened else 'Updated'
            return updated, history + [dict(event=event, at=record['updated_at'], **deepcopy(record))]
    raise ValueError('Action not found in this session.')


def action_frame(actions):
    return pd.DataFrame(actions, columns=ACTION_COLUMNS)


def history_frame(history):
    return pd.DataFrame(history, columns=HISTORY_COLUMNS)
