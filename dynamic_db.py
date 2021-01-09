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
            namespace['db_tables'] = {}
            base = declarative_base()
            namespace['Base'] = base
            namespace['_DbVersion'] = types.new_class('_DbVersion', bases=(base, DbVersionObject))
        logger.debug("Creating DB class %s version %d", name, version)
        return types.new_class(name + "Db", bases=(DB,), exec_body=class_exec)

    @classmethod
    def CreateTable(cls, name, db_class, version, pk=None, cols={}, base=DBObject, doc=None, create_view=None, vars={}):
        """Create a table in a dynamic database class."""
        def class_exec(namespace):
            if doc:
                namespace['__doc__'] = doc
            namespace['__tablename__'] = name
            namespace['db'] = db_class
            namespace['table_version'] = int(version)
            if pk:
                namespace['__table_args__'] = (PrimaryKeyConstraint(*pk),)
            for colname, colargs in cols.items():
                namespace[colname] = Column(*colargs.get('args', []), **colargs.get('kwargs', {}))
            if create_view:
                namespace['create_view'] = create_view
            namespace.update(vars)
        logger.debug("Creating table class %s version %d cols %r in db %s", name, version, cols, db_class)
        return types.new_class(name, bases=(db_class.Base, base), exec_body=class_exec)

    @classmethod
    def ActivateTable(cls, db, table_class):
        """Activate a table in a dynamic database class."""
        logger.debug("Activating table class %s in db %s", table_class, db)
        db.init_table(table_class)
