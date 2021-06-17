"""Test db_object."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"


import unittest
import logging
import tempfile
from sqlalchemy import Integer, String

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
        cls.test_db = cls.TestDB(cls.test_db_params)

    def test_exists_not_present(self):
        data = {
            'activity_id': 0,
            'record': 0
        }
        self.assertFalse(self.table_single_pk.exists(self.test_db, data))
        self.assertFalse(self.table_double_pk.exists(self.test_db, data))

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


if __name__ == '__main__':
    unittest.main(verbosity=2)
