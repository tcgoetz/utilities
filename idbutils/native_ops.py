"""Batched native SQL writes for DbObject tables, with an operation log that can be replayed by another process."""

__author__ = "Philippe Auriach"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"

import contextlib
import logging
import os
import shutil
import sqlite3
import tempfile

from sqlalchemy import event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session
from sqlalchemy.sql import ClauseElement


logger = logging.getLogger(__name__)

_OPS = 'idbutils_ops'
_LOG = 'idbutils_log'
_UPDATED = 'idbutils_updated'
_DB = 'idbutils_db'

_UPSERT = 'upsert'
_UPSERT_FLAGS = 'upsert_flags'
_IGNORE = 'ignore'
_NEWER = 'newer'

_plans = {}


def _quote(name):
    return '"' + name.replace('"', '""') + '"'


def _literal(value):
    if isinstance(value, bool):
        return str(int(value))
    if isinstance(value, (int, float)):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


class _TablePlan():
    """Pre-computed SQL and value converters for one table on one dialect."""

    def __init__(self, cls, dialect):
        table = cls.__table__
        self.cls = cls
        self.table = _quote(table.name)
        self.cols = [col.name for col in table.columns]
        self.count = len(self.cols)
        self.index = {name: index for index, name in enumerate(self.cols)}
        self.pk = [col.name for col in table.primary_key.columns]
        self.pk_indexes = [self.index[name] for name in self.pk]
        self.updated = [index for index in range(self.count) if index not in self.pk_indexes]
        self.processors = []
        self.defaults = {}
        for index, col in enumerate(table.columns):
            processor = col.type._cached_bind_processor(dialect)
            if processor is not None:
                self.processors.append((index, processor))
            if col.default is not None:
                default = col.default.arg
                self.defaults[index] = _literal(processor(default) if processor is not None else default)
        self._sql = {}

    @classmethod
    def supported(cls, db_object_cls, dialect):
        """Return True if every write to the table can be expressed as a native statement."""
        if dialect.name != 'sqlite' or sqlite3.sqlite_version_info < (3, 24):
            return False
        table = db_object_cls.__table__
        if not len(table.primary_key.columns):
            return False
        mapper = db_object_cls.__mapper__
        for col in table.columns:
            if col.server_default is not None or col.onupdate is not None or col.server_onupdate is not None:
                return False
            if col.default is not None and not col.default.is_scalar:
                return False
            if mapper.get_property_by_column(col).key != col.name:
                return False
        return True

    def sql(self, kind):
        """Return the statement for a kind of write."""
        if kind not in self._sql:
            self._sql[kind] = self.__build_sql(kind)
        return self._sql[kind]

    def __build_sql(self, kind):
        names = ', '.join(_quote(name) for name in self.cols)
        values = ', '.join(f'COALESCE(?{index + 1}, {self.defaults[index]})' if index in self.defaults else f'?{index + 1}'
                           for index in range(self.count))
        target = ', '.join(_quote(name) for name in self.pk)
        insert = f'INSERT INTO {self.table} ({names}) VALUES ({values}) ON CONFLICT ({target}) DO '
        if kind == _IGNORE or not self.updated:
            return insert + 'NOTHING'
        if kind == _UPSERT_FLAGS:
            sets = [f'{_quote(self.cols[index])} = CASE WHEN ?{self.count + position + 1} THEN ?{index + 1} ELSE {_quote(self.cols[index])} END'
                    for position, index in enumerate(self.updated)]
        else:
            sets = [f'{_quote(self.cols[index])} = COALESCE(?{index + 1}, {_quote(self.cols[index])})' for index in self.updated]
        statement = insert + 'UPDATE SET ' + ', '.join(sets)
        if kind == _NEWER:
            statement += f' WHERE {self.table}."timestamp" < excluded."timestamp"'
        return statement

    def convert(self, row):
        """Convert Python values to what the driver stores, in place."""
        for index, processor in self.processors:
            if row[index] is not None:
                row[index] = processor(row[index])
        return row

    def row(self, values_dict):
        """Return a driver ready row holding the dict's values for the table's columns."""
        row = [None] * self.count
        index_for = self.index
        for key, value in values_dict.items():
            index = index_for.get(key)
            if index is not None:
                row[index] = value
        return tuple(self.convert(row))

    def row_with_flags(self, values_dict, ignore_none, ignore_zero):
        """Return a driver ready row followed by one 'update this column' flag per non key column."""
        row = [None] * self.count
        flags = [0] * self.count
        index_for = self.index
        for key, value in values_dict.items():
            index = index_for.get(key)
            if index is not None:
                row[index] = value
                if (not ignore_none or value is not None) and (not ignore_zero or value != 0):
                    flags[index] = 1
        return tuple(self.convert(row) + [flags[index] for index in self.updated])


def _plan(session, cls):
    dialect = session.get_bind().dialect
    key = (cls, dialect.name)
    if key not in _plans:
        _plans[key] = _TablePlan(cls, dialect) if _TablePlan.supported(cls, dialect) else None
    return _plans[key]


def _enqueue(session, cls, values_dict, kind, ignore_none=True, ignore_zero=False):
    plan = _plan(session, cls)
    if plan is None:
        return False
    for name in plan.pk:
        if values_dict.get(name) is None:
            return False
    if any(isinstance(value, ClauseElement) for value in values_dict.values()):
        return False
    # ORM changes made before this write have to reach the database before it does
    if not session._is_clean():
        session.flush()
    if kind == _UPSERT_FLAGS:
        row = plan.row_with_flags(values_dict, ignore_none, ignore_zero)
    else:
        row = plan.row(values_dict)
    session.info.setdefault(_OPS, []).append((plan, kind, row))
    return True


def upsert(session, cls, values_dict, ignore_none=True, ignore_zero=False):
    """Queue an insert-or-update of a row. Returns False if the table needs the ORM path."""
    kind = _UPSERT if ignore_none and not ignore_zero else _UPSERT_FLAGS
    return _enqueue(session, cls, values_dict, kind, ignore_none, ignore_zero)


def upsert_newer(session, cls, values_dict):
    """Queue an insert-or-update of a row that only updates when the new timestamp is later than the stored one."""
    return _enqueue(session, cls, values_dict, _NEWER)


def insert_ignore(session, cls, values_dict):
    """Queue an insert of a row that is skipped when the row already exists."""
    return _enqueue(session, cls, values_dict, _IGNORE)


def _batches(ops):
    batches = []
    current = None
    for plan, kind, row in ops:
        if current is None or current[0] is not plan or current[1] != kind:
            current = (plan, kind, [])
            batches.append(current)
        current[2].append(row)
    return batches


def flush(session, execute=True):
    """Write the queued rows of a session, one executemany per run of rows for the same table and kind."""
    ops = session.info.get(_OPS)
    if not ops:
        return
    session.info[_OPS] = []
    batches = _batches(ops)
    log = session.info.get(_LOG)
    if log is not None:
        log.extend((plan.sql(kind), rows) for plan, kind, rows in batches)
    if execute:
        connection = session.connection()
        for plan, kind, rows in batches:
            if log is not None:
                _seed_scratch(session, plan, list({tuple(row[index] for index in plan.pk_indexes) for row in rows}))
            connection.exec_driver_sql(plan.sql(kind), rows)
        if len(session.identity_map):
            written = {plan.cls for plan, _, _ in batches}
            for instance in list(session.identity_map.values()):
                if type(instance) in written:
                    session.expire(instance)


@event.listens_for(Session, 'do_orm_execute')
def _before_execute(orm_execute_state):
    if orm_execute_state.session.info.get(_OPS):
        flush(orm_execute_state.session)


@event.listens_for(Session, 'before_flush')
def _before_flush(session, flush_context, instances):
    if session.info.get(_OPS):
        flush(session)
    if session.info.get(_LOG) is not None:
        session.info[_UPDATED] = _orm_updates(session)


@event.listens_for(Session, 'after_flush')
def _after_flush(session, flush_context):
    if session.info.get(_LOG) is not None:
        _log_orm_updates(session, session.info.pop(_UPDATED, []))
        _log_orm_inserts(session)


@event.listens_for(Session, 'before_commit')
def _before_commit(session):
    if session.info.get(_OPS):
        flush(session)


#
# Capture: a worker process runs the unmodified import code against an empty scratch database and logs its writes
# instead of committing them. Another process replays the log on the real database.
#

class _Capture():

    def __init__(self):
        self.scratch_dir = tempfile.mkdtemp(prefix='idbutils_scratch_')
        self.batches = []
        self.suspended = 0
        self.readers = {}

    def reader(self, path):
        if path not in self.readers and os.path.isfile(path):
            self.readers[path] = sqlite3.connect(f'file:{path}?mode=ro', uri=True, timeout=60)
        return self.readers.get(path)

    def close_readers(self):
        for reader in self.readers.values():
            reader.close()
        self.readers = {}


_capture = None


def start_capture():
    """Make this process log database writes instead of applying them."""
    global _capture
    _capture = _Capture()


def stop_capture():
    """Return this process to writing to the real database."""
    global _capture
    if _capture is not None:
        _capture.close_readers()
        shutil.rmtree(_capture.scratch_dir, ignore_errors=True)
    _capture = None


def close_readers():
    """Close the connections to the real databases, they are reopened when needed."""
    _capture.close_readers()


def capturing():
    """Return True if this process logs database writes."""
    return _capture is not None


def scratch_dir():
    """Return the directory that holds the scratch databases of this process."""
    return _capture.scratch_dir


@contextlib.contextmanager
def suspend_capture():
    """Let sessions opened in this context commit to the scratch database without being logged."""
    if _capture is None:
        yield
        return
    _capture.suspended += 1
    try:
        yield
    finally:
        _capture.suspended -= 1


def take_captured():
    """Return and clear the writes logged since the last call as a list of (db name, statement, rows)."""
    batches = _capture.batches
    _capture.batches = []
    return batches


def session_info(db):
    """Return the info dict for a new session on a database."""
    return {_DB: db}


def captures_sessions():
    """Return True if sessions opened now have to be logged."""
    return _capture is not None and not _capture.suspended


@contextlib.contextmanager
def capture_session(db):
    """Return a session whose writes are logged and then rolled back."""
    session = Session(db.engine, expire_on_commit=False, info={_DB: db, _LOG: []})
    try:
        yield session
        session.flush()
        flush(session, execute=False)
        _capture.batches.extend((db.db_name, statement, rows) for statement, rows in session.info[_LOG])
    finally:
        session.rollback()
        session.close()


def _log_plan(session, cls):
    plan = _plan(session, cls)
    if plan is None:
        raise RuntimeError(f'{cls.__name__} can not be written by a parallel import')
    return plan


def _orm_updates(session):
    if session.deleted:
        raise RuntimeError('Deletes can not be done by a parallel import')
    updates = []
    for instance in session.dirty:
        if session.is_modified(instance):
            plan = _log_plan(session, type(instance))
            state = sa_inspect(instance)
            updates.append((instance, plan, [name for name in plan.cols if name in plan.pk or state.attrs[name].history.has_changes()]))
    return updates


def _log_orm_updates(session, updates):
    log = session.info[_LOG]
    for instance, plan, names in updates:
        log.append((plan.sql(_UPSERT_FLAGS), [plan.row_with_flags({name: getattr(instance, name) for name in names}, False, False)]))


def _log_orm_inserts(session):
    log = session.info[_LOG]
    for instance in session.new:
        plan = _log_plan(session, type(instance))
        log.append((plan.sql(_IGNORE), [plan.row({name: getattr(instance, name) for name in plan.cols})]))


def _real_rows(session, plan, keys):
    """Return the rows of a capture session's real database for a list of driver ready primary keys."""
    reader = _capture.reader(session.info[_DB].real_sqlite_path)
    if reader is None:
        return []
    names = ', '.join(_quote(name) for name in plan.cols)
    target = ', '.join(_quote(name) for name in plan.pk)
    per_query = 900 // len(plan.pk)
    rows = []
    try:
        for start in range(0, len(keys), per_query):
            chunk = keys[start:start + per_query]
            marks = ', '.join(['(' + ', '.join('?' * len(plan.pk)) + ')'] * len(chunk))
            rows += reader.execute(f'SELECT {names} FROM {plan.table} WHERE ({target}) IN (VALUES {marks})',
                                   [value for key in chunk for value in key]).fetchall()
    except sqlite3.OperationalError as error:
        if 'no such table' not in str(error):
            raise
        return []
    return rows


def _seed_scratch(session, plan, keys):
    """Copy rows from the real database into the scratch database so that writes and reads start from the real state."""
    rows = _real_rows(session, plan, keys)
    if rows:
        names = ', '.join(_quote(name) for name in plan.cols)
        marks = ', '.join('?' * plan.count)
        session.connection().exec_driver_sql(f'INSERT OR IGNORE INTO {plan.table} ({names}) VALUES ({marks})', [tuple(row) for row in rows])
    return rows


def _driver_key(session, cls, pk_values):
    plan = _plan(session, cls) if session.info.get(_LOG) is not None else None
    if plan is None:
        return None, None
    row = plan.row(dict(zip(plan.pk, pk_values)))
    return plan, tuple(row[index] for index in plan.pk_indexes)


def exists_in_real_db(session, cls, pk_values):
    """Return True if a capture session's real database already holds the row."""
    plan, key = _driver_key(session, cls, pk_values)
    return plan is not None and bool(_real_rows(session, plan, [key]))


def read_through(session, cls, pk_values):
    """Copy a row from the real database into a capture session's scratch database. Returns True if the row exists."""
    plan, key = _driver_key(session, cls, pk_values)
    return plan is not None and bool(_seed_scratch(session, plan, [key]))
