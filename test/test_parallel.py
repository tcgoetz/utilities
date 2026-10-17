"""Test that importing items on worker processes leaves the same rows as importing them one after the other."""

__author__ = "Philippe Auriach"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"


import sqlite3
import tempfile
import unittest

from sqlalchemy import Integer, String

import idbutils
from idbutils import parallel


TestDB = idbutils.DB.create('parallel_test', 1)
Items = idbutils.DbObject.create('items', TestDB, 1, cols={
    'id': {'args': [Integer], 'kwargs': {'primary_key': True}},
    'name': {'args': [String]},
    'last_item': {'args': [Integer]},
}, vars={'__get_col_name__': 'id'})

FAILING_ITEM = 17
SHARED_ROWS = 4


def make_handler(db_params):
    return TestDB(db_params)


def import_item(db, item):
    if item == FAILING_ITEM:
        raise ValueError(f'item {item} can not be imported')
    with db.managed_session() as session:
        Items.s_insert_or_update(session, {'id': item, 'name': f'item {item}'})
        # every item also writes a row that other items write, the last item has to win
        Items.s_insert_or_update(session, {'id': 1000 + item % SHARED_ROWS, 'last_item': item})
        if Items.s_get(session, 1000 + item % SHARED_ROWS).last_item != item:
            raise AssertionError('a write of this item is not visible to its own reads')
    return item * 2


class TestParallel(unittest.TestCase):

    def tearDown(self):
        parallel.shutdown()
        parallel.set_workers(1)

    @staticmethod
    def __rows(db_params):
        connection = sqlite3.connect(TestDB._sqlite_path(db_params))
        try:
            return connection.execute('SELECT * FROM items ORDER BY id').fetchall()
        finally:
            connection.close()

    def test_same_rows_and_results_as_a_sequential_import(self):
        items = list(range(1, 61))
        sequential_params = idbutils.DbParams(db_type='sqlite', db_path=tempfile.mkdtemp())
        sequential_db = TestDB(sequential_params)
        expected = []
        for item in items:
            try:
                expected.append((item, import_item(sequential_db, item), False))
            except ValueError:
                expected.append((item, None, True))

        parallel_params = idbutils.DbParams(db_type='sqlite', db_path=tempfile.mkdtemp())
        parallel.set_workers(3)
        workers = parallel.workers_for(parallel_params, len(items))
        self.assertEqual(workers, 3)
        results = []
        parallel.import_items(parallel_params, items, workers, make_handler, (parallel_params,), import_item,
                              lambda item, result, error: results.append((item, result, error is not None)), simple_label='Importing test items')

        self.assertEqual(results, expected)
        self.assertEqual(self.__rows(parallel_params), self.__rows(sequential_params))

    def test_one_worker_for_few_items_or_another_database_type(self):
        parallel.set_workers(4)
        self.assertEqual(parallel.workers_for(idbutils.DbParams(db_type='sqlite', db_path=tempfile.mkdtemp()), 3), 1)
        self.assertEqual(parallel.workers_for(idbutils.DbParams(db_type='postgresql'), 1000), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
