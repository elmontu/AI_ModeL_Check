"""Durable local metadata-event deduplication, not an independent witness.

The trusted service authorizes outbox delivery before calling this receiver.
Applying the local count projection and retaining its receipt are one SQLite
transaction. A repeated event returns that same receipt; this does not establish
exactly-once external delivery, whole-store rollback protection or clearance.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import secrets
import sqlite3
import stat

from .contracts import (FLAGS, RegistryContractError, canonical_bytes, digest, hex_id,
                        integer, strict_json, validate_outbox_event)

MAX_EVENTS = 1024
MAX_DATABASE_BYTES = 16 * 1024 * 1024
_DATABASE = 'receiver.sqlite'
_SCHEMA_ID = 'mra-fixture-event-receiver/v1'
_ZERO = '0' * 64
_SCHEMA = (
    'CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL) STRICT',
    '''CREATE TABLE events (sequence INTEGER PRIMARY KEY, store_id TEXT NOT NULL,
       event_id TEXT NOT NULL, event_json TEXT NOT NULL, receipt_json TEXT NOT NULL,
       chain_sha256 TEXT NOT NULL, UNIQUE(store_id,event_id)) STRICT''',
)


class ReceiverError(ValueError):
    """Malformed local fixture event or guard."""


class ReceiverConflict(ReceiverError):
    """Event identity was reused with different bytes, or capacity was reached."""


class ReceiverUnavailable(RuntimeError):
    """Existing receiver state or current trusted time cannot be established."""


def _unavailable():
    raise ReceiverUnavailable('Local fixture receiver unavailable')


def _identity(info):
    return info.st_dev, info.st_ino


def _unsafe(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def _directories(path):
    if '..' in path.parts or str(path).startswith(('//', '\\\\')):
        _unavailable()
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        if _unsafe(info) or not stat.S_ISDIR(info.st_mode):
            _unavailable()


def _decode(text):
    raw = text.encode('ascii')
    value = strict_json(raw)
    if canonical_bytes(value) != raw:
        _unavailable()
    return value


class FixtureEventReceiver:
    """Explicit fresh creation and identity-pinned reopening; no repair or delete."""

    def __init__(self, root, expected_receiver_id):
        try:
            self._receiver_id = hex_id(expected_receiver_id)
            self._root = Path(root).absolute()
            self._path = self._root / _DATABASE
            _directories(self._root)
            self._root_identity = _identity(self._root.lstat())
            self._db_identity = _identity(self._path.lstat())
            with self._connect() as db:
                db.execute('BEGIN')
                self._validate(db)
                self._paths()
                db.rollback()
        except (OSError, TypeError, ValueError):
            raise ReceiverUnavailable('Local fixture receiver unavailable') from None

    @property
    def root(self):
        return self._root

    @property
    def receiver_id(self):
        return self._receiver_id

    @classmethod
    def create(cls, root):
        try:
            root = Path(root).absolute()
            if '..' in root.parts:
                _unavailable()
            _directories(root.parent)
            root.mkdir(exist_ok=False)
            _directories(root)
            path = root / _DATABASE
            with path.open('xb'):
                pass
            receiver_id = secrets.token_hex(16)
            db = sqlite3.connect(path, timeout=1, isolation_level=None)
            try:
                db.enable_load_extension(False)
                db.execute('PRAGMA trusted_schema=OFF')
                db.execute('PRAGMA page_size=4096')
                db.execute('PRAGMA journal_mode=DELETE')
                db.execute('PRAGMA synchronous=FULL')
                db.execute('PRAGMA max_page_count=4096')
                db.execute('BEGIN IMMEDIATE')
                for sql in _SCHEMA:
                    db.execute(sql)
                db.executemany('INSERT INTO meta VALUES(?,?)', (
                    ('schema', _SCHEMA_ID), ('receiver_id', receiver_id),
                    ('last_clock', '0'), ('event_count', '0'), ('head_sha256', _ZERO)))
                db.commit()
            finally:
                db.close()
            return cls(root, receiver_id)
        except (OSError, sqlite3.Error, TypeError, ValueError):
            raise ReceiverUnavailable('Local fixture receiver creation unavailable') from None

    @classmethod
    def open(cls, root, expected_receiver_id):
        return cls(root, expected_receiver_id)

    def _paths(self):
        try:
            _directories(self.root)
            if _identity(self.root.lstat()) != self._root_identity:
                _unavailable()
            info = self._path.lstat()
            if (_unsafe(info) or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or _identity(info) != self._db_identity or not 1 <= info.st_size <= MAX_DATABASE_BYTES):
                _unavailable()
            for suffix in ('-journal', '-wal', '-shm'):
                try:
                    info = self._path.with_name(_DATABASE + suffix).lstat()
                except FileNotFoundError:
                    continue
                if (suffix != '-journal' or _unsafe(info) or not stat.S_ISREG(info.st_mode)
                        or info.st_nlink != 1 or info.st_size > MAX_DATABASE_BYTES + 65536):
                    _unavailable()
        except OSError:
            raise ReceiverUnavailable('Local fixture receiver filesystem unavailable') from None

    @contextmanager
    def _connect(self):
        db = None
        try:
            self._paths()
            db = sqlite3.connect(self._path.as_uri() + '?mode=rw', uri=True, timeout=1, isolation_level=None)
            db.row_factory = sqlite3.Row
            db.enable_load_extension(False)
            db.execute('PRAGMA trusted_schema=OFF')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA max_page_count=4096')
            if db.execute('PRAGMA journal_mode').fetchone()[0] != 'delete':
                _unavailable()
            self._paths()
            yield db
        except sqlite3.Error:
            raise ReceiverUnavailable('Local fixture receiver database unavailable') from None
        finally:
            if db is not None:
                db.close()

    def _receipt(self, event, sequence, now):
        return {'schema': 'mra-fixture-registry-receiver/v1', 'receiver_id': self.receiver_id,
                'store_id': event['store_id'], 'event_id': event['event_id'], 'event_sha256': digest(event),
                'applied_sequence': sequence, 'applied_at': now, 'independent_witness': False, **FLAGS}

    def _validate(self, db):
        try:
            schema = db.execute("SELECT name,type,sql FROM sqlite_schema WHERE name NOT LIKE 'sqlite_%'").fetchall()
            if (len(schema) != 2 or {row['name'] for row in schema} != {'meta', 'events'}
                    or any(row['type'] != 'table' for row in schema)
                    or {row['sql'] for row in schema} != set(_SCHEMA)):
                _unavailable()
            if (db.execute('PRAGMA page_size').fetchone()[0] != 4096
                    or db.execute('PRAGMA page_count').fetchone()[0] > 4096
                    or [row[0] for row in db.execute('PRAGMA quick_check')] != ['ok']):
                _unavailable()
            meta = dict(db.execute('SELECT key,value FROM meta'))
            if (set(meta) != {'schema', 'receiver_id', 'last_clock', 'event_count', 'head_sha256'}
                    or meta['schema'] != _SCHEMA_ID or meta['receiver_id'] != self.receiver_id):
                _unavailable()
            last = integer(int(meta['last_clock']))
            count = integer(int(meta['event_count']), maximum=MAX_EVENTS)
            if str(last) != meta['last_clock'] or str(count) != meta['event_count']:
                _unavailable()
            rows = db.execute('SELECT * FROM events ORDER BY sequence LIMIT ?', (MAX_EVENTS + 1,)).fetchall()
            if len(rows) != count:
                _unavailable()
            head, previous_time, receipts = _ZERO, 0, []
            for index, row in enumerate(rows, 1):
                event = validate_outbox_event(_decode(row['event_json']))
                receipt = _decode(row['receipt_json'])
                received = integer(receipt['applied_at'])
                expected = self._receipt(event, index, received)
                if (row['sequence'] != index or row['store_id'] != event['store_id']
                        or row['event_id'] != event['event_id'] or not previous_time <= received <= last
                        or canonical_bytes(receipt) != canonical_bytes(expected)):
                    _unavailable()
                head = digest({'previous_sha256': head, 'receipt': receipt})
                if row['chain_sha256'] != head:
                    _unavailable()
                previous_time = received
                receipts.append(receipt)
            if meta['head_sha256'] != head:
                _unavailable()
            return {'count': count, 'head': head, 'receipts': receipts}
        except (ValueError, TypeError, KeyError, UnicodeError, OverflowError, IndexError):
            raise ReceiverUnavailable('Local fixture receiver state rejected') from None

    @staticmethod
    def _clock(db, guard):
        try:
            now = integer(guard())
        except RegistryContractError:
            raise ReceiverUnavailable('Local fixture receiver clock rejected') from None
        previous = int(db.execute("SELECT value FROM meta WHERE key='last_clock'").fetchone()[0])
        if now < previous:
            raise ReceiverUnavailable('Local fixture receiver clock moved backwards')
        db.execute("UPDATE meta SET value=? WHERE key='last_clock'", (str(now),))
        return now

    @contextmanager
    def _transaction(self, guard):
        if not callable(guard):
            raise ReceiverError('A trusted current authorization/time guard is required')
        with self._connect() as db:
            try:
                db.execute('BEGIN IMMEDIATE')
                state = self._validate(db)
                now = self._clock(db, guard)
                finalizers = []
                yield db, state, now, finalizers
                self._validate(db)  # Expensive replay precedes the final current guard.
                self._paths()
                final = self._clock(db, guard)
                for finalize in finalizers:
                    finalize(final)
                self._paths()
                db.commit()
            except BaseException:
                if db.in_transaction:
                    db.rollback()
                raise

    def receive(self, event, *, guard):
        """Apply a count projection once; exact repeats return the original receipt."""
        try:
            event = validate_outbox_event(event)  # Own input before any guard callback.
        except (ValueError, TypeError):
            raise ReceiverError('Local fixture event rejected') from None
        encoded = canonical_bytes(event).decode('ascii')
        with self._transaction(guard) as (db, state, now, finalizers):
            existing = db.execute('SELECT event_json,receipt_json FROM events WHERE store_id=? AND event_id=?',
                                  (event['store_id'], event['event_id'])).fetchone()
            if existing is not None:
                if existing['event_json'] != encoded:
                    raise ReceiverConflict('Event identity already binds different bytes')
                receipt = _decode(existing['receipt_json'])
            else:
                if state['count'] >= MAX_EVENTS:
                    raise ReceiverConflict('Local receiver capacity reached; events are retained')
                sequence = state['count'] + 1
                receipt = self._receipt(event, sequence, now)
                head = digest({'previous_sha256': state['head'], 'receipt': receipt})
                db.execute('INSERT INTO events VALUES(?,?,?,?,?,?)', (sequence, event['store_id'],
                    event['event_id'], encoded, canonical_bytes(receipt).decode('ascii'), head))
                db.execute("UPDATE meta SET value=? WHERE key='event_count'", (str(sequence),))
                db.execute("UPDATE meta SET value=? WHERE key='head_sha256'", (head,))
                def finalize(final):
                    receipt['applied_at'] = final
                    head = digest({'previous_sha256': state['head'], 'receipt': receipt})
                    db.execute('UPDATE events SET receipt_json=?,chain_sha256=? WHERE sequence=?',
                               (canonical_bytes(receipt).decode('ascii'), head, sequence))
                    db.execute("UPDATE meta SET value=? WHERE key='head_sha256'", (head,))
                finalizers.append(finalize)
        return receipt

    def snapshot(self, *, guard):
        with self._transaction(guard) as (_db, state, _now, _finalizers):
            result = {'schema': 'mra-fixture-receiver-state/v1', 'receiver_id': self.receiver_id,
                      'applied_events': state['count'], 'head_sha256': state['head'],
                      'receipts': state['receipts'], 'independent_witness': False, **FLAGS}
        return result
