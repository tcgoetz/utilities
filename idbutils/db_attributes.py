"""Class for database attributes including versioning."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"


from idbutils.key_value import KeyValueObject


class DbAttributesObject(KeyValueObject):
    """Class for managing databse attributes including versioning."""

    __tablename__ = '_attributes'
    __db_version_key = 'db.version'

    @classmethod
    def __version_check_key(cls, db, version_key, version_number):
        cls.set_if_unset(db, version_key, version_number)
        return cls.get_int(db, version_key)

    def version_check(self, db, version_number):
        """Check if the databse version in the database is the same as in the code."""
        self.version = self.__version_check_key(db, self.__db_version_key, version_number)
        if self.version != version_number:
            raise RuntimeError("DB: %s version mismatch. The DB schema has been updated. Please rebuild the %s DB. (%s vs %s)" %
                               (db.db_name, db.db_name, self.version, version_number))

    @classmethod
    def table_version_check(cls, db, table_object):
        """Check if the table version in the database is the same as in the code."""
        table_version = cls.__version_check_key(db, table_object.__tablename__ + '.version', table_object.table_version)
        if table_version != table_object.table_version:
            raise RuntimeError("DB: %s table %s version mismatch. The DB schema has been updated. Please rebuild the %s DB. (%s vs %s)" %
                               (db.db_name, table_object.__tablename__, db.db_name, table_version, table_object.table_version))

    def view_version_check(self, db, table_object):
        """Check if the view version in the database is the same as in the code."""
        if hasattr(table_object, 'view_version'):
            self.version = self.__version_check_key(db, table_object.__tablename__ + '.view_version', table_object.view_version)
            return self.version == table_object.view_version
        return True

    @classmethod
    def update_table_units(cls, db, table_object):
        """Update the units for the table columns in the database."""
        if hasattr(table_object, '_col_units'):
            for colname, units in table_object._col_units.items():
                cls.set_if_unset(db, f'{table_object.__tablename__}.{colname}.units', units)
