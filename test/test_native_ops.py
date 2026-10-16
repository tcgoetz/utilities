"""Test that batched native writes leave the same rows as the ORM read-then-write path."""

__author__ = "Philippe Auriach"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"


import datetime
import random
import sqlite3
import tempfile
import unittest
from unittest import mock

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Time

import idbutils
from idbutils import native_ops


class TestNativeOps(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.TestDB = idbutils.DB.create('native_ops_test', 1)
        _cols = {
            'id': {'args': [Integer], 'kwargs': {'primary_key': True}},
            'timestamp': {'args': [DateTime]},
            'name': {'args': [String]},
            'value': {'args': [Float]},
            'count': {'args': [Integer]},
            'flag': {'args': [Boolean]},
            'duration': {'args': [Time], 'kwargs': {'nullable': False, 'default': datetime.time.min}},
        }
        cls.single_pk = idbutils.DbObject.create('native_1pk', cls.TestDB, 1, cols=_cols)
        _two_pk_cols = {
            'timestamp': {'args': [DateTime]},
            'kind': {'args': [String]},
            'value': {'args': [Float]},
            'duration': {'args': [Time], 'kwargs': {'nullable': False, 'default': datetime.time.min}},
        }
        cls.double_pk = idbutils.DbObject.create('native_2pk', cls.TestDB, 1, ('timestamp', 'kind'), _two_pk_cols)
        cls.key_value = type('NativeKeyValue', (cls.TestDB.Base, idbutils.KeyValueObject), {'__tablename__': 'native_kv', 'db': cls.TestDB, 'table_version': 1})

    def __db(self):
        return self.TestDB(idbutils.DbParams(db_type='sqlite', db_path=tempfile.mkdtemp()))

    @classmethod
    def __rows(cls, db):
        connection = sqlite3.connect(cls.TestDB._sqlite_path(db.db_params))
        try:
            return {table: connection.execute(f'SELECT * FROM {table} ORDER BY 1, 2').fetchall() for table in ('native_1pk', 'native_2pk', 'native_kv')}
        finally:
            connection.close()

    @classmethod
    def __random_ops(cls, seed, count):
        rng = random.Random(seed)
        start = datetime.datetime(2026, 1, 1)
        ops = []
        for _ in range(count):
            ignore_none, ignore_zero = rng.choice([(True, False), (True, False), (True, True), (False, False), (False, True)])
            choice = rng.random()
            if choice < 0.5:
                values = {'id': rng.randrange(8)}
                for name, candidates in (('timestamp', [None, start, start + datetime.timedelta(hours=rng.randrange(5))]),
                                         ('name', [None, '', 'a', "it's"]), ('value', [None, 0.0, 1.5, -2.0]), ('count', [None, 0, 3]),
                                         ('flag', [None, False, True]), ('duration', [None, datetime.time(0, rng.randrange(3))])):
                    if rng.random() < 0.6:
                        values[name] = rng.choice(candidates)
                if not ignore_none and values.get('duration', 0) is None:
                    del values['duration']
                table = cls.single_pk
            elif choice < 0.85:
                values = {'timestamp': start + datetime.timedelta(minutes=rng.randrange(4)), 'kind': rng.choice(['x', 'y'])}
                if rng.random() < 0.7:
                    values['value'] = rng.choice([None, 0.0, 2.5])
                if rng.random() < 0.5:
                    values['duration'] = datetime.time(0, 0, rng.randrange(3))
                table = cls.double_pk
            else:
                ops.append(('newer', rng.choice(['k1', 'k2']), rng.randrange(100), start + datetime.timedelta(seconds=rng.randrange(50))))
                continue
            ops.append((rng.choice(['upsert', 'upsert', 'upsert', 'create', 'get_update', 'exists_add']), table, values, ignore_none, ignore_zero))
        return ops

    def __apply(self, db, ops, per_session):
        for start in range(0, len(ops), per_session):
            with db.managed_session() as session:
                for op in ops[start:start + per_session]:
                    if op[0] == 'newer':
                        self.key_value.s_set_newer(session, op[1], op[2], op[3])
                        continue
                    kind, table, values, ignore_none, ignore_zero = op
                    if kind == 'upsert':
                        table.s_insert_or_update(session, values, ignore_none, ignore_zero)
                    elif kind == 'create':
                        table.s_find_or_create(session, values)
                    elif kind == 'exists_add':
                        if not table.s_exists(session, values):
                            session.add(table(**values))
                    elif table is self.single_pk:
                        current = table.s_get(session, values['id'])
                        if current:
                            current.update_from_dict(values, ignore_none=True, ignore_zero=True)
                        else:
                            session.add(table(**values))

    def test_same_rows_as_orm_path(self):
        for seed in range(6):
            ops = self.__random_ops(seed, 400)
            orm_db = self.__db()
            with mock.patch.object(native_ops, '_enqueue', return_value=False):
                self.__apply(orm_db, ops, per_session=25)
            native_db = self.__db()
            self.__apply(native_db, ops, per_session=25)
            self.assertEqual(self.__rows(orm_db), self.__rows(native_db), f'seed {seed}')

    def test_sql_expression_values(self):
        values = {'id': 1, 'count': 2, 'duration': self.single_pk._time_from_secs(self.single_pk._secs_from_time(datetime.time(0, 7)) / 7)}
        orm_db = self.__db()
        with mock.patch.object(native_ops, '_enqueue', return_value=False):
            with orm_db.managed_session() as session:
                self.single_pk.s_insert_or_update(session, values)
        native_db = self.__db()
        with native_db.managed_session() as session:
            self.single_pk.s_insert_or_update(session, values)
        self.assertEqual(self.__rows(orm_db), self.__rows(native_db))

    def test_rows_are_written_in_batches(self):
        db = self.__db()
        with db.managed_session() as session:
            for index in range(50):
                self.single_pk.s_insert_or_update(session, {'id': index, 'count': index})
            self.assertEqual(len(native_ops._batches(session.info['idbutils_ops'])), 1)
            self.assertEqual(session.query(self.single_pk).count(), 50)


if __name__ == '__main__':
    unittest.main(verbosity=2)
