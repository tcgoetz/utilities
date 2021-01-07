"""Objects for creating a database and database tables dynamically."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"

import types
import logging
from sqlalchemy import Column
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import PrimaryKeyConstraint

from utilities.db import DB
from utilities.db_object import DBObject
from utilities.db_version import DbVersionObject


logger = logging.getLogger(__file__)


class DynamicDb(DB):
    """Object representing a database for storing health data from a Garmin device."""

    @classmethod
    def Create(cls, name, version, doc=None):
        """Create a dynamic database class."""
        def class_exec(namespace):
            namespace['db_name'] = name
            if doc:
                namespace['__doc__'] = doc
            namespace['db_version'] = int(version)
            namespace['db_tables'] = []
            base = declarative_base()
            namespace['Base'] = base
            namespace['_DbVersion'] = types.new_class('_DbVersion', bases=(base, DbVersionObject))
        logger.info("Creating DB class %s version %d", name, version)
        return types.new_class(name + "Db", bases=(DB,), exec_body=class_exec)

    @classmethod
    def CreateTable(cls, name, db, version, pk=None, cols={}, base=DBObject):
        """Create a tables in a dynamic database class."""
        def class_exec(namespace):
            namespace['__tablename__'] = name
            namespace['db'] = db
            namespace['table_version'] = int(version)
            if pk:
                namespace['__table_args__'] = (PrimaryKeyConstraint(*pk),)
            for colname, coltype in cols.items():
                namespace[colname] = Column(coltype)
        logger.info("Creating table class %s version %d in db %s", name, version, db)
        return types.new_class(name, bases=(db.Base, base), exec_body=class_exec)
