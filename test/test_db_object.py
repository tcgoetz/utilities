"""Test db_object."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"


import datetime
import unittest
import logging
import tempfile
from sqlalchemy import DateTime, Integer, String

import idbutils

root_logger = logging.getLogger()
root_logger.addHandler(logging.FileHandler('db_object.log', 'w'))
root_logger.setLevel(logging.DEBUG)

logger = logging.getLogger(__name__)


class TestActivitiesDb(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        temp_dir = tempfile.mkdtemp()
        cls.test_db_params = idbutils.DbParams(**{'db_type' : 'sqlite', 'db_path': temp_dir})
        logger.info("test_db_params %r", cls.test_db_params)
        cls.TestDB = idbutils.DB.create('test', 1)
        _cols = {
            'activity_id': {'args': [String], 'kwargs': {'primary_key': True}},
            'record': {'args': [Integer]}
        }
        # _single_pk = ("activity_id")
        cls.table_single_pk = idbutils.DbObject.create("test_1k", cls.TestDB, 1, cols=_cols)
        _double_pk = ("activity_id", "record")
        cls.table_double_pk = idbutils.DbObject.create("test_2pk", cls.TestDB, 1, _double_pk, _cols)
        _timed_cols = {
            'id': {'args': [Integer], 'kwargs': {'primary_key': True}},
            'timestamp': {'args': [DateTime]}
        }
        cls.table_timed = idbutils.DbObject.create("test_timed", cls.TestDB, 1, cols=_timed_cols, vars={'__time_col_name__': 'timestamp'})
        cls.test_db = cls.TestDB(cls.test_db_params)

    def test_exists_not_present(self):
        data = {
            'activity_id': 0,
            'record': 0
        }
        self.assertFalse(self.table_single_pk.exists(self.test_db, data))
        self.assertFalse(self.table_double_pk.exists(self.test_db, data))

    def test_exists_other_record_of_same_activity(self):
        self.table_double_pk.add(self.test_db, {'activity_id': 2, 'record': 0})
        self.assertFalse(self.table_double_pk.exists(self.test_db, {'activity_id': 2, 'record': 1}))

    def test_exists_present_1pk(self):
        data = {
            'activity_id': 1,
            'record': 1
        }
        self.table_single_pk.add(self.test_db, data)
        self.assertTrue(self.table_single_pk.exists(self.test_db, data))

    def test_exists_present_2pk(self):
        data = {
            'activity_id': 0,
            'record': 0
        }
        self.table_double_pk.add(self.test_db, data)
        self.assertTrue(self.table_double_pk.exists(self.test_db, data))

    def test_years_and_months_leave_out_rows_without_a_time(self):
        self.table_timed.add(self.test_db, {'id': 1, 'timestamp': datetime.datetime(2026, 5, 1)})
        self.table_timed.add(self.test_db, {'id': 2, 'timestamp': None})
        self.assertEqual(self.table_timed.get_years(self.test_db), [2026])
        self.assertEqual(self.table_timed.get_months(self.test_db, 2026), [5])

    def test_time_arithmetic_on_seconds_since_midnight(self):
        seconds = self.table_timed._secs_from_time(datetime.time(2, 30))
        with self.test_db.managed_session() as session:
            self.assertEqual(session.query(self.table_timed._time_from_secs(seconds / 7)).scalar(), datetime.time(0, 21, 25))
            self.assertEqual(session.query(seconds * 2).scalar(), 18000)


if __name__ == '__main__':
    unittest.main(verbosity=2)
