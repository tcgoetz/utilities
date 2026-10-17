"""Objects for implementing DBs and DB objects."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"

import os
import logging
import types

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

from idbutils import native_ops
from idbutils.db_attributes import DbAttributesObject


logger = logging.getLogger(__name__)


class DbParams():
    """Holds parameters for attaching to a database."""

    def __init__(self, **kwargs):
        """Return a DbParams instance with passed in kwargs as attributes."""
        if 'db_type' not in kwargs:
            raise Exception('db_type is a required parameter')
        vars(self).update(kwargs)

    def __repr__(self):
        """Return a string representation of a DbParams instance."""
        return f'<{self.__class__.__name__}() {repr(vars(self))}'

    def __str__(self):
        return self.__repr__()


class DB():
    """Object representing a database."""

    _db_classes = {}

    def __init__(self, db_params, debug_level=0):
        """
        Return an instance a database access class.

        Parameters:
        ----------
            db_params (dict): config data for accessing the database
            debug_level (int): 0 is no logging, higher is more logging

        """
        logger.debug("%s: %r debug: %s ", self.__class__.__name__, db_params, debug_level)
        if debug_level > 0:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
        self.db_params = db_params
        self.real_sqlite_path = None
        if native_ops.capturing() and db_params.db_type == 'sqlite':
            self.real_sqlite_path = self._sqlite_path(db_params)
            url = f'sqlite:///{native_ops.scratch_dir()}/{self.db_name}.db'
        else:
            url = getattr(self, f'_{db_params.db_type}_url')(self.db_params)
        if db_params.db_type == 'postgresql':
            # Each idbutils.DB instance maps to its own PostgreSQL schema inside a
            # single shared database. db_name (e.g. 'garmin', 'garmin_activities')
            # selects the schema; ORM tables are declared without an explicit
            # schema, so we bind search_path on the engine and create the schema
            # first if it doesn't exist.
            schema = self.db_name
            self.engine = create_engine(
                url,
                echo=(debug_level > 1),
                connect_args={'options': f'-csearch_path={schema}'},
            )
            with self.engine.begin() as conn:
                conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
        else:
            self.engine = create_engine(url, echo=(debug_level > 1))
        if self.real_sqlite_path is not None:
            event.listen(self.engine, 'connect', self.__scratch_pragmas)
        with native_ops.suspend_capture():
            self.Base.metadata.create_all(self.engine)
            self.attributes = self._DbAttributes()
            # now we can do checks
            self.attributes.version_check(self, self.db_version)
            # and last setup tables
            for table in self.db_tables.values():
                self.init_table(table)

    @staticmethod
    def __scratch_pragmas(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute('PRAGMA synchronous=OFF')
        cursor.execute('PRAGMA journal_mode=MEMORY')
        cursor.close()

    @classmethod
    def add_table(cls, table):
        """Add a table to the list of tables in this database."""
        cls.db_tables[table.__name__] = table

    def init_table(self, table):
        """Initialize a table for this database."""
        logger.debug("%s: initializing table %s", self.__class__.__name__, table)
        table.setup(self)
        self.attributes.table_version_check(self, table)
        self.attributes.update_table_units(self, table)
        if not self.attributes.view_version_check(self, table):
            table.delete_view(self)

    @classmethod
    def _sqlite_path(cls, db_params):
        return f'{db_params.db_path}/{cls.db_name}.db'

    @classmethod
    def _sqlite_url(cls, db_params):
        return 'sqlite:///' + cls._sqlite_path(db_params)

    @classmethod
    def _sqlite_delete(cls, db_params):
        filename = cls._sqlite_path(db_params)
        try:
            os.remove(filename)
            logger.info('%s removed', filename)
        except Exception:
            logger.warning('%s not removed', filename)

    @classmethod
    def _mysql_url(cls, db_params):
        return f'mysql+pymysql://{db_params.db_username}:{db_params.db_password}@{db_params.db_host}/{cls.db_name}'

    @classmethod
    def _postgresql_url(cls, db_params):
        port = getattr(db_params, 'db_port', None) or 5432
        return (
            f'postgresql+psycopg2://{db_params.db_username}:{db_params.db_password}'
            f'@{db_params.db_host}:{port}/{db_params.pg_database}'
        )

    @classmethod
    def _postgresql_delete(cls, db_params):
        engine = create_engine(cls._postgresql_url(db_params))
        try:
            with engine.begin() as conn:
                conn.execute(text(f'DROP SCHEMA IF EXISTS "{cls.db_name}" CASCADE'))
            logger.info('postgres schema %s dropped', cls.db_name)
        except Exception as e:
            logger.warning('postgres schema %s not dropped: %s', cls.db_name, e)
        finally:
            engine.dispose()

    def managed_session(self):
        """Return a session with automatic commit, rollback, and cleanup."""
        if native_ops.captures_sessions():
            return native_ops.capture_session(self)
        return sessionmaker(self.engine, expire_on_commit=False, info=native_ops.session_info(self)).begin()

    @classmethod
    def create(cls, name, version, doc=None):
        """Create a dynamic database class."""
        def class_exec(namespace):
            namespace['db_name'] = name
            if doc:
                namespace['__doc__'] = doc
            namespace['db_version'] = int(version)
            namespace['db_tables'] = {}
            base = declarative_base()
            namespace['Base'] = base
            namespace['_DbAttributes'] = types.new_class('_DbAttributes', bases=(base, DbAttributesObject))
        logger.debug("Creating DB class %s version %d", name, version)
        db_class = types.new_class(name + "Db", bases=(DB,), exec_body=class_exec)
        DB._db_classes[name] = db_class
        return db_class

    @classmethod
    def class_for_name(cls, db_name):
        """Return the database class created with a name."""
        return DB._db_classes[db_name]

    @classmethod
    def delete_db(cls, db_params):
        """Delete a database."""
        delete_func_str = f'_{db_params.db_type}_delete'
        logger.info('Deleting db with %s', delete_func_str)
        delete_func = getattr(cls, delete_func_str)
        delete_func(db_params)

    def __repr__(self):
        """Return a string representation of a DB instance."""
        return f'<{self.__class__.__name__}() {repr(self.db_params)}'

    def __str__(self):
        return self.__repr__()
