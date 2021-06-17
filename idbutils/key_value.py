"""Objects for implementing key-value database objects."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"


import datetime
import logging
from sqlalchemy import Column, String, DateTime

from idbutils import db_object


class KeyValueObject(db_object.DbObject):
    """Base class for implementing key-value databse objects."""

    logger = logging.getLogger(__name__)

    timestamp = Column(DateTime)
    key = Column(String, primary_key=True)
    value = Column(String)

    @classmethod
    def set(cls, db, key, value, timestamp=datetime.datetime.now()):
        """Set a key-value pair in the database."""
        cls.insert_or_update(db, {'timestamp' : timestamp, 'key' : key, 'value' : str(value)})

    @classmethod
    def s_set_newer(cls, session, key, value, timestamp=datetime.datetime.now()):
        """Set a key-value pair in the database if the timestamp is newer than the one in the database."""
        item = cls.s_get(session, key)
        if item is None or item.timestamp < timestamp:
            cls.s_insert_or_update(session, {'timestamp' : timestamp, 'key' : key, 'value' : str(value)})

    @classmethod
    def set_newer(cls, db, key, value, timestamp=datetime.datetime.now()):
        """Set a key-value pair in the database if the timestamp is newer than the one in the database."""
        with db.managed_session() as session:
            cls.s_set_newer(session, key, value, timestamp)

    @classmethod
    def set_if_unset(cls, db, key, value, timestamp=datetime.datetime.now()):
        """Set a key-value pair in the database if the key does not exist in the database."""
        cls.logger.debug("%s::set_if_unset {%s : %s}", cls.__name__, key, value)
        return cls.find_or_create(db, {'timestamp' : timestamp, 'key' : key, 'value' : str(value)})

    @classmethod
    def s_get_from_dict(cls, session, values_dict):
        """Return a single activity instance for the given id."""
        return cls.s_get(session, values_dict['key'])

    @classmethod
    def get_type(cls, db, type_func, key, default=None):
        """Get a key-integer pair from the database."""
        instance = cls.get(db, key)
        if instance is not None:
            if instance.value is not None:
                try:
                    return type_func(instance.value)
                except Exception as e:
                    cls.logger.error("Failed to convert value from %r: %s", instance, e)
            else:
                return None
        return default

    @classmethod
    def get_string(cls, db, key, default=None):
        """Get a string from the database."""
        return cls.get_type(db, str, key, default)

    @classmethod
    def get_int(cls, db, key, default=None):
        """Get a integer from the database."""
        return cls.get_type(db, int, key, default)

    @classmethod
    def get_float(cls, db, key, default=None):
        """Get a float from the database."""
        return cls.get_type(db, float, key, default)

    @classmethod
    def get_time(cls, db, key, default=None):
        """Get a time from the database."""
        def _convert(value):
            return datetime.datetime.strptime(value, "%H:%M:%S").time()
        return cls.get_type(db, _convert, key, default)
