"""Objects for implementing DBs and DB objects."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"

import os
import logging

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


logger = logging.getLogger(__name__)


class DbParams(object):
    """Holds parameters for attaching to a database."""

    def __init__(self, **kwargs):
        if 'db_type' not in kwargs:
            raise Exception('db_type is a required parameter')
        self.__dict__.update(kwargs)

    def __repr__(self):
        """Return a string representation of a DbParams instance."""
        return f'<{self.__class__.__name__}() {repr(self.__dict__)}'

    def __str__(self):
        return self.__repr__()


class DB(object):
    """Object representing a database."""

    def __init__(self, db_params, debug=False):
        """
        Return an instance a databse access class.

        Parameters:
            db_params (dict): config data for accessing the database
            debug (Boolean): enable debug logging

        """
        logger.info("%s: %r debug: %s ", self.__class__.__name__, db_params, debug)
        if debug > 0:
            logger.setLevel(logging.DEBUG)
        else:
            logger.setLevel(logging.INFO)
        self.db_params = db_params
        url_func = getattr(self, f'_{db_params.db_type}_url')
        self.engine = create_engine(url_func(self.db_params), echo=(debug > 1))
        self.session_maker = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.Base.metadata.create_all(self.engine)
        self.version = self._DbVersion()
        # now init this DBs tables
        for table in self.db_tables:
            table.setup(self)
        # now we can do checks
        self.version.version_check(self, self.db_version)
        for table in self.db_tables:
            self.version.table_version_check(self, table)
            if not self.version.view_version_check(self, table):
                table.delete_view(self)

    @classmethod
    def add_table(cls, table):
        cls.db_tables.append(table)

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
        except Exception:
            logger.warning('%s not removed', filename)

    @classmethod
    def _mysql_url(cls, db_params):
        return f'mysql+pymysql://{db_params.db_username}:{db_params.db_password}@{db_params.db_host}/{cls.db_name}'

    def session(self):
        """Return a databse session."""
        return self.session_maker()

    @contextmanager
    def managed_session(self):
        """Return a session with automatic commit, rollback, and cleanup."""
        session = self.session()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @classmethod
    def delete_db(cls, db_params):
        """Delete a database."""
        delete_func = getattr(cls, f'_{db_params.db_type}_delete')
        delete_func(db_params)

    def __repr__(self):
        """Return a string representation of a DB instance."""
        return f'<{self.__class__.__name__}() {repr(self.db_param)}'

    def __str__(self):
        return self.__repr__()
