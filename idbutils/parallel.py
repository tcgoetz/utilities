"""Run a file import on several processes while a single process writes the results to the database in order."""

__author__ = "Philippe Auriach"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"

import atexit
import logging
import multiprocessing
import os
import sys
import traceback
from concurrent.futures import ProcessPoolExecutor

from tqdm import tqdm

from idbutils import native_ops
from idbutils.db import DB


logger = logging.getLogger(__name__)

_MIN_ITEMS_PER_WORKER = 8
_MAX_ITEMS_PER_TASK = 16
_TASKS_PER_WORKER = 8
_ROWS_PER_COMMIT = 50000

_configured_workers = 1


def set_workers(count):
    """Set how many processes imports may use. None or 0 means one per CPU."""
    global _configured_workers
    _configured_workers = count or os.cpu_count() or 1


def workers_for(db_params, item_count):
    """Return how many worker processes to use for importing a number of items into a database."""
    if db_params.db_type != 'sqlite' or native_ops.capturing():
        return 1
    return max(1, min(_configured_workers, item_count // _MIN_ITEMS_PER_WORKER))


_pool = None
_run_count = 0

_worker_run = None
_worker_handler = None
_worker_log = []


class _LogCollector(logging.Handler):
    """Keeps what a worker logs so that it can be logged by the process that owns the log."""

    def emit(self, record):
        _worker_log.append((record.name, record.levelno, record.getMessage()))


def _start_worker():
    native_ops.start_capture()


def _collect_logging():
    for existing_logger in [logging.getLogger()] + [item for item in logging.Logger.manager.loggerDict.values() if isinstance(item, logging.Logger)]:
        for handler in list(existing_logger.handlers):
            existing_logger.removeHandler(handler)
    logging.getLogger().setLevel(logging.WARNING)
    logging.getLogger().addHandler(_LogCollector())


def _run_task(task):
    global _worker_run, _worker_handler, _worker_log
    run, make_handler, handler_args, handle_item, items = task
    if run != _worker_run:
        native_ops.close_readers()
        with native_ops.suspend_capture():
            _worker_handler = make_handler(*handler_args)
        _collect_logging()
        _worker_run = run
    results = []
    for item in items:
        result = error = None
        _worker_log = []
        try:
            result = handle_item(_worker_handler, item)
        except Exception:
            error = traceback.format_exc()
        results.append((item, native_ops.take_captured(), result, error, _worker_log))
    return results


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ProcessPoolExecutor(max_workers=_configured_workers, mp_context=multiprocessing.get_context('spawn'), initializer=_start_worker)
        atexit.register(shutdown)
    return _pool


def shutdown():
    """Stop the worker processes."""
    global _pool
    if _pool is not None:
        _pool.shutdown()
        _pool = None


class _Writer():
    """Applies logged writes to the real databases in short transactions, so that workers are never kept from reading for long."""

    def __init__(self, db_params):
        self.db_params = db_params
        self.engines = {}
        self.pending = []
        self.pending_rows = 0

    def add(self, batches):
        self.pending += batches
        self.pending_rows += sum(len(rows) for _, _, rows in batches)
        if self.pending_rows >= _ROWS_PER_COMMIT:
            self.write()

    def write(self):
        connections = {}
        try:
            for db_name, statement, rows in self.pending:
                if db_name not in connections:
                    if db_name not in self.engines:
                        self.engines[db_name] = DB.class_for_name(db_name)(self.db_params).engine
                    connections[db_name] = self.engines[db_name].connect()
                connections[db_name].exec_driver_sql(statement, rows)
            for connection in connections.values():
                connection.commit()
        finally:
            for connection in connections.values():
                connection.close()
        self.pending = []
        self.pending_rows = 0


def import_items(db_params, items, workers, make_handler, handler_args, handle_item, on_result, unit='files', simple_label=None):
    """
    Import items on worker processes and write what they produce to the database in item order.

    Each worker builds its handler with make_handler(*handler_args) and calls handle_item(handler, item) for every item it gets.
    The workers argument only decides how the items are split, the processes are shared by all imports.
    The database writes the call makes are logged instead of applied, and replayed here. Reads done by handle_item see the
    database as it was when the item started, without the writes of other items of the same run.
    on_result(item, result, error) is called in item order with what handle_item returned, or the traceback if it raised.
    Progress is shown as a bar, or as a start and an end line starting with simple_label when one is given.
    """
    global _run_count
    _run_count += 1
    per_task = max(1, min(_MAX_ITEMS_PER_TASK, len(items) // (workers * _TASKS_PER_WORKER)))
    tasks = [(_run_count, make_handler, handler_args, handle_item, items[start:start + per_task]) for start in range(0, len(items), per_task)]
    writer = _Writer(db_params)
    if simple_label:
        print(simple_label, file=sys.stderr, flush=True)
    with tqdm(total=len(items), unit=unit, disable=bool(simple_label)) as progress:
        for results in _get_pool().map(_run_task, tasks):
            for item, batches, result, error, log_records in results:
                writer.add(batches)
                for logger_name, level, message in log_records:
                    logging.getLogger(logger_name).log(level, message)
                on_result(item, result, error)
            progress.update(len(results))
    writer.write()
    if simple_label:
        print(f'{simple_label}: {len(items)} {unit} visited', file=sys.stderr, flush=True)
