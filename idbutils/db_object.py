"""Objects for implementing DBs and DB objects."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"

import types
import logging
import datetime

from sqlalchemy import func, desc, extract, and_, literal_column
from sqlalchemy.orm import synonym, Query
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm.attributes import set_attribute
from sqlalchemy.ext.hybrid import hybrid_method
from sqlalchemy import DateTime, Date, Time, PrimaryKeyConstraint, Column

from idbutils.list_and_dict import filter_dict_by_list
from idbutils.db_exception import DbException

logger = logging.getLogger(__name__)


class DbViewException(DbException):
    """Exceptions encountered while managing DB views."""


class DbObject():
    """Base class for implementing database table objects."""

    db = None
    db_views = []

    @classmethod
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, 'db') and cls.db is not None:
            cls.db.add_table(cls)

    @classmethod
    def create(cls, name, db_class, version, pk=None, cols={}, base=None, doc=None, create_view=None, inherited_create_view=None, view_version=None, vars={}):
        """Create a table in a dynamic database class."""
        def class_exec(namespace):
            if doc:
                namespace['__doc__'] = doc
            namespace['__tablename__'] = name
            namespace['db'] = db_class
            namespace['table_version'] = int(version)
            if view_version:
                namespace['view_version'] = int(view_version)
            if pk:
                namespace['__table_args__'] = (PrimaryKeyConstraint(*pk),)
            namespace['_col_units'] = {}
            for colname, colargs in cols.items():
                namespace[colname] = Column(*colargs.get('args', []), **colargs.get('kwargs', {}))
                if 'units' in colargs:
                    namespace['_col_units'][colname] = colargs['units']
            if create_view:
                namespace['create_view'] = create_view
            namespace.update(vars)
        if not base:
            base = DbObject
        logger.info("Creating table class %s base %r version %d cols %r in db %s", name, base, version, cols, db_class)
        return types.new_class(name, bases=(db_class.Base, base), exec_body=class_exec)

    @classmethod
    def setup(cls, db):
        """Initialize per table data."""
        if not hasattr(cls, 'time_col_name'):
            cls.__setup_table_vars()
        if hasattr(cls, 'create_view'):
            cls.create_view(db)

    @classmethod
    def __setup_table_vars(cls):
        cls.col_names = [col.name for col in cls.__table__.columns]
        cls.primary_key_cols = []
        cls.time_col_name = None
        for col in cls.__table__._columns:
            if col.primary_key:
                logger.debug("Found primary key column %s for table %s", col.name, cls.__name__)
                cls.primary_key_cols.append(col.name)
                cls.get_col_name = col.name
                if isinstance(col.type, DateTime) or isinstance(col.type, Date) or isinstance(col.type, Time):
                    logger.debug("Found primary key time_col_name %s for table %s", col.name, cls.__name__)
                    cls.time_col_name = col.name
        if cls.time_col_name is None:
            for col in cls.__table__._columns:
                if isinstance(col.type, DateTime) or isinstance(col.type, Date) or isinstance(col.type, Time):
                    logger.info("Found time_col_name %s for table %s", col.name, cls.__name__)
                    cls.time_col_name = col.name
                    break
        if cls.time_col_name is not None:
            cls.time_col = synonym(cls.time_col_name)

    @classmethod
    def _col_from_name(cls, name):
        for col in cls.__table__.columns:
            if col.name == name:
                return col

    @classmethod
    def round_ext_col(cls, table, col_name, alt_col_name=None, places=1):
        """Return a SQL phrase for rounding and optionally aliasing a column from another table."""
        return literal_column(f'ROUND({table.__tablename__ + "." + col_name}, {places}) AS {alt_col_name if alt_col_name else col_name} ')

    @classmethod
    def round_col(cls, col_name, alt_col_name=None, places=1):
        """Return a SQL phrase for rounding and optionally aliasing a column in this table."""
        return cls.round_ext_col(cls, col_name, alt_col_name, places)

    @classmethod
    def round_col_txt(cls, col_name, alt_col_name=None, places=1):
        """Return a SQL phrase for rounding and optionally aliasing a column."""
        return literal_column(f'ROUND({col_name}, {places}) AS {alt_col_name if alt_col_name else col_name} ')

    @declared_attr
    def col_count(cls):
        """Return the number of columns in database object class."""
        if hasattr(cls, '__table__'):
            return len(cls.__table__.columns)

    @hybrid_method
    def during(self, start_ts, end_ts):
        """Return True if the databse object's timestamp is between the given times."""
        return self.time_col >= start_ts and self.time_col < end_ts

    @during.expression
    def during(cls, start_ts, end_ts):
        """Return True if the databse object's timestamp is between the given times."""
        return and_(cls.time_col >= start_ts, cls.time_col < end_ts)

    @hybrid_method
    def after(self, start_ts):
        """Return True if the databse object's timestamp is after the given time."""
        if start_ts is not None:
            return self.time_col >= start_ts

    @after.expression
    def after(cls, start_ts):
        """Return True if the databse object's timestamp is after the given time."""
        return cls.time_col >= start_ts

    @hybrid_method
    def before(self, end_ts):
        """Return True if the databse object's timestamp is before the given time."""
        return self.time_col < end_ts

    @before.expression
    def before(cls, end_ts):
        """Return True if the databse object's timestamp is before the given time."""
        return cls.time_col < end_ts

    @classmethod
    def _get_default_view_name(cls):
        return cls.__tablename__ + '_view'

    def update_from_dict(self, values_dict, ignore_none=False, ignore_zero=False):
        """Update a DB object instance from values in a dict by matching the dict keys to DB object attributes."""
        for key, value in values_dict.items():
            if (not ignore_none or value is not None) and (not ignore_zero or value != 0) and key in self.col_names:
                set_attribute(self, key, value)
        return self

    @classmethod
    def __delete_view(cls, db, view_name):
        """Delete a database view with name view_name."""
        with db.managed_session() as session:
            session.execute('DROP VIEW IF EXISTS ' + view_name)

    @classmethod
    def delete_view(cls, db, view_name=None):
        """Delete a database view with name view_name."""
        if view_name is None:
            view_name = cls._get_default_view_name()
        logger.info("Deleted join view %s", view_name)
        cls.__delete_view(db, view_name)

    @classmethod
    def __create_view_if_not_exists(cls, session, view_name, query_str):
        result = session.execute('CREATE VIEW IF NOT EXISTS ' + view_name + ' AS ' + query_str)
        logger.debug("Created join view %s using query %s: %r", view_name, query_str, result)

    @classmethod
    def create_view_if_doesnt_exist(cls, db, view_name, query_str):
        """Create a database view named view_name if ti doesn't already exist."""
        with db.managed_session() as session:
            cls.__create_view_if_not_exists(session, view_name, query_str)

    @classmethod
    def create_join_view(cls, db, view_name, selectable, join_table, filter_by=None, order_by=None):
        """Create a database view named view_name if it doesn't already exist."""
        with db.managed_session() as session:
            try:
                query = Query(selectable, session=session).join(join_table)
                if filter_by is not None:
                    query = query.filter(filter_by)
                if order_by is not None:
                    query = query.order_by(order_by)
                cls.__create_view_if_not_exists(session, view_name, str(query))
            except Exception as e:
                raise DbViewException(f"Failed to create DB view {view_name} with table {join_table}", e)

    @classmethod
    def create_multi_join_view(cls, db, view_name, selectable, joins, order_by=None):
        """Create a database view named view_name if it doesn't already exist."""
        with db.managed_session() as session:
            query = Query(selectable, session=session)
            for (join_table, join_clause) in joins:
                query = query.join(join_table, join_clause)
            if order_by is not None:
                query = query.order_by(order_by)
            cls.__create_view_if_not_exists(session, view_name, str(query))

    @classmethod
    def _create_view_from_selectable(cls, db, view_name, selectable, order_by):
        with db.managed_session() as session:
            query = Query(selectable, session=session).order_by(order_by)
            cls.__create_view_if_not_exists(session, view_name, str(query))

    @classmethod
    def intersection(cls, values_dict):
        """Return the dict elements whose keys are column names."""
        return filter_dict_by_list(values_dict, cls.col_names)

    @classmethod
    def s_exists(cls, session, values_dict):
        """Return if a matching record exists in the database."""
        query = session.query(cls)
        for pk_col_name in cls.primary_key_cols:
            query = query.filter(cls._col_from_name(pk_col_name) == values_dict[pk_col_name])
        return session.query(query.exists()).scalar()

    @classmethod
    def exists(cls, db, values_dict):
        """Return if a matching record exists in the database."""
        with db.managed_session() as session:
            return cls.s_exists(session, values_dict)

    @classmethod
    def add(cls, db, values_dict):
        """Add values to the table."""
        with db.managed_session() as session:
            return session.add(cls(**values_dict))

    @classmethod
    def s_get(cls, session, instance_id, default=None):
        """Return a single instance for the given id."""
        instance = session.query(cls).get(instance_id)
        if instance is None:
            return default
        return instance

    @classmethod
    def get(cls, db, instance_id, default=None):
        """Return a single instance for the given id."""
        with db.managed_session() as session:
            return cls.s_get(session, instance_id, default)

    @classmethod
    def s_get_from_dict(cls, session, values_dict):
        """Return a single activity instance for the given id."""
        return cls.s_get(session, values_dict[cls.get_col_name])

    @classmethod
    def s_find_match(cls, session, match_dict):
        """Find a table row that matches the values in the match_dict."""
        query = session.query(cls)
        for col, value in match_dict.items():
            query = query.filter(col == value)
        return query.one_or_none()

    @classmethod
    def s_find_id(cls, session, match_dict):
        """Return the id for a table row that matched the values in the match_dict."""
        return cls.s_find_match(session, match_dict).id

    @classmethod
    def find_id(cls, db, values_dict):
        """Return the id for a table row that matched the values in the values_dict."""
        with db.managed_session() as session:
            return cls.s_find_id(session, values_dict)

    @classmethod
    def s_find_or_create(cls, session, values_dict, ignore_none=True, ignore_zero=False):
        """Create a database record with the passed in data if it doesn't exist."""
        instance = cls.s_get_from_dict(session, values_dict)
        if not instance:
            session.add(cls(**values_dict))

    @classmethod
    def find_or_create(cls, db, values_dict, ignore_none=False):
        """Create a database record with the passed in data if it doesn't exist."""
        with db.managed_session() as session:
            cls.s_find_or_create(session, values_dict, ignore_none)

    @classmethod
    def s_insert_or_update(cls, session, values_dict, ignore_none=True, ignore_zero=False):
        """Create a database record if it doesn't exist. Update it if does exist."""
        instance = cls.s_get_from_dict(session, values_dict)
        if instance:
            instance.update_from_dict(values_dict, ignore_none, ignore_zero)
        else:
            session.add(cls(**values_dict))

    @classmethod
    def insert_or_update(cls, db, values_dict, ignore_none=False):
        """Create a database record if it doesn't exist. Update it if does exist."""
        with db.managed_session() as session:
            cls.s_insert_or_update(session, values_dict, ignore_none)

    @classmethod
    def _secs_from_time(cls, col):
        return func.strftime('%s', col) - func.strftime('%s', '00:00')

    @classmethod
    def _time_from_secs(cls, value):
        return func.time(value, 'unixepoch')

    @classmethod
    def _row_to_int(cls, row):
        return int(row[0])

    @classmethod
    def _row_to_int_not_none(cls, row):
        if row[0] is not None:
            return cls._row_to_int(row)

    @classmethod
    def _rows_to_ints(cls, rows):
        return [cls._row_to_int(row) for row in rows]

    @classmethod
    def _rows_to_ints_not_none(cls, rows):
        return [cls._row_to_int_not_none(row) for row in rows]

    @classmethod
    def _row_to_month(cls, row):
        return datetime.date(1900, row, 1).strftime("%b")

    @classmethod
    def _rows_to_months(cls, rows):
        return [cls._row_to_month(row) for row in rows]

    @classmethod
    def get_years(cls, db):
        """Return a list of the unique years present in the time column."""
        with db.managed_session() as session:
            return cls._rows_to_ints_not_none(session.query(extract('year', cls.time_col)).distinct().all())

    @classmethod
    def s_get_months(cls, session, year):
        """Return a list of months as indexes, for the given year, present in the table."""
        return cls._rows_to_ints_not_none(session.query(extract('month', cls.time_col)).filter(extract('year', cls.time_col) == str(year)).distinct().all())

    @classmethod
    def get_months(cls, db, year):
        """Return a list of months as indexes, for the given year, present in the table."""
        with db.managed_session() as session:
            return cls.s_get_months(session, year)

    @classmethod
    def get_month_names(cls, db, year):
        """Return the names of months present in the table for the given year."""
        return cls._rows_to_months(cls.get_months(db, year))

    @classmethod
    def s_get_days(cls, session, year):
        """Return a list of days as indexes, for the given year, present in the table."""
        return cls._rows_to_ints(session.query(func.strftime("%j", cls.time_col)).filter(extract('year', cls.time_col) == str(year)).distinct().all())

    @classmethod
    def get_days(cls, db, year):
        """Return a list of days as indexes, for the given year, present in the table."""
        with db.managed_session() as session:
            return cls.s_get_days(session, year)

    @classmethod
    def _s_query(cls, session, selectable, order_by=None, start_ts=None, end_ts=None, ignore_le_zero_col=None):
        query = session.query(selectable)
        if order_by is not None:
            query = query.order_by(order_by)
        if start_ts is not None and end_ts is not None:
            query = query.filter(cls.during(start_ts, end_ts))
        elif start_ts is not None:
            query = query.filter(cls.after(start_ts))
        elif end_ts is not None:
            query = query.filter(cls.before(end_ts))
        if ignore_le_zero_col is not None:
            query = query.filter(ignore_le_zero_col > 0)
        return query

    @classmethod
    def get_all(cls, db):
        """Return all DB records in the table."""
        with db.managed_session() as session:
            return session.query(cls).all()

    @classmethod
    def s_get_for_period_where(cls, session, start_ts, end_ts, selectable=None, where=None):
        """Return all DB records matching the selection criteria."""
        if selectable is None:
            selectable = cls
        query = cls._s_query(session, selectable, cls.time_col, start_ts, end_ts)
        if where is not None:
            query = query.filter(where)
        return query.all()

    @classmethod
    def get_for_period_where(cls, db, start_ts, end_ts, selectable=None, where=None):
        """Return all DB records matching the selection criteria."""
        with db.managed_session() as session:
            return cls.s_get_for_period_where(session, start_ts, end_ts, selectable, where)

    @classmethod
    def s_get_for_period(cls, session, start_ts, end_ts, selectable=None, not_none_col=None):
        """Return all DB records matching the selection criteria."""
        if selectable is None:
            selectable = cls
        query = cls._s_query(session, selectable, cls.time_col, start_ts, end_ts)
        if not_none_col is not None:
            # filter does not use 'is not None'
            query = query.filter(not_none_col != None)  # noqa
        return query.all()

    @classmethod
    def get_for_period(cls, db, start_ts, end_ts, selectable=None, not_none_col=None):
        """Return all DB records matching the selection criteria."""
        with db.managed_session() as session:
            return cls.s_get_for_period(session, start_ts, end_ts, selectable, not_none_col)

    @classmethod
    def _get_for_day(cls, db, day_date, selectable=None, not_none_col=None):
        """Return the values from a column for a given day."""
        start_ts = datetime.datetime.combine(day_date, datetime.time.min)
        end_ts = start_ts + datetime.timedelta(1)
        return cls.s_get_for_period(db, start_ts, end_ts, selectable, not_none_col)

    @classmethod
    def get_for_day(cls, db, selectable, day_date, not_none_col=None):
        """Return the values from a column for a given day."""
        start_ts = datetime.datetime.combine(day_date, datetime.time.min)
        end_ts = start_ts + datetime.timedelta(1)
        return cls.get_for_period(db, start_ts, end_ts, selectable, not_none_col)

    @classmethod
    def get_col_values(cls, db, get_col, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the values from a column possibly filtered by time period."""
        with db.managed_session() as session:
            return cls._s_query(session, get_col, cls.time_col, start_ts, end_ts, ignore_le_zero).filter(match_col == match_value).all()

    @classmethod
    def _s_get_col_func_query(cls, session, col, func, start_ts=None, end_ts=None, ignore_le_zero=False):
        return cls._s_query(session, func(col), None, start_ts, end_ts, col if ignore_le_zero else None)

    @classmethod
    def get_col_distinct(cls, db, col, start_ts=None, end_ts=None):
        """Return the set of distinct value from a column possibly filtered by time period."""
        with db.managed_session() as session:
            return [row[0] for row in cls._s_get_col_func_query(session, col, func.distinct, start_ts, end_ts).all()]

    @classmethod
    def s_get_col_avg(cls, session, col, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the average value of a column filtered by criteria."""
        return cls._s_get_col_func_query(session, col, func.avg, start_ts, end_ts, col if ignore_le_zero else None).scalar()

    @classmethod
    def get_col_avg(cls, db, col, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the average value of a column filtered by criteria."""
        with db.managed_session() as session:
            return cls.s_get_col_avg(session, col, start_ts, end_ts, ignore_le_zero)

    @classmethod
    def s_get_col_min(cls, session, col, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the minimum value in a column filtered by criteria."""
        return cls._s_get_col_func_query(session, col, func.min, start_ts, end_ts, col if ignore_le_zero else None).scalar()

    @classmethod
    def get_col_min(cls, db, col, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the minimum value in a column filtered by criteria."""
        with db.managed_session() as session:
            return cls._s_get_col_func_query(session, col, func.min, start_ts, end_ts, col if ignore_le_zero else None).scalar()

    @classmethod
    def s_get_col_max(cls, session, col, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the maximum value in a column filtered by criteria."""
        return cls._s_get_col_func_query(session, col, func.max, start_ts, end_ts, ignore_le_zero).scalar()

    @classmethod
    def get_col_max(cls, db, col, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the maximum value in a column filtered by criteria."""
        with db.managed_session() as session:
            return cls._s_get_col_func_query(session, col, func.max, start_ts, end_ts, ignore_le_zero).scalar()

    @classmethod
    def s_get_col_sum(cls, session, col, start_ts=None, end_ts=None):
        """Return the sum of a column filtered by criteria."""
        return cls._s_get_col_func_query(session, col, func.sum, start_ts, end_ts).scalar()

    @classmethod
    def get_col_sum(cls, db, col, start_ts=None, end_ts=None):
        """Return the sum of a column filtered by criteria."""
        with db.managed_session() as session:
            return cls.s_get_col_sum(session, col, start_ts, end_ts)

    @classmethod
    def _s_get_time_col_func(cls, session, col, stat_func, start_ts=None, end_ts=None):
        result = cls._s_query(session, cls._time_from_secs(stat_func(cls._secs_from_time(col))), None, start_ts, end_ts, cls._secs_from_time(col)).scalar()
        return datetime.datetime.strptime(result, '%H:%M:%S').time() if result is not None else datetime.time.min

    @classmethod
    def _get_time_col_func(cls, db, col, stat_func, start_ts=None, end_ts=None):
        with db.managed_session() as session:
            return cls._s_get_time_col_func(session, col, stat_func, start_ts, end_ts)

    @classmethod
    def s_get_time_col_avg(cls, session, col, start_ts=None, end_ts=None):
        """Return the average value, from the time period defined by the given two datetime value, of a column, with time format."""
        return cls._s_get_time_col_func(session, col, func.avg, start_ts, end_ts)

    @classmethod
    def get_time_col_avg(cls, db, col, start_ts=None, end_ts=None):
        """Return the average value, from the time period defined by the given two datetime value, of a column, with time format."""
        return cls._get_time_col_func(db, col, func.avg, start_ts, end_ts)

    @classmethod
    def s_get_time_col_min(cls, session, col, start_ts=None, end_ts=None):
        """Return the minimum value, from the time period defined by the given two datetime value, of a column, with time format."""
        return cls._s_get_time_col_func(session, col, func.min, start_ts, end_ts)

    @classmethod
    def get_time_col_min(cls, db, col, start_ts=None, end_ts=None):
        """Return the minimum value, from the time period defined by the given two datetime value, of a column, with time format."""
        return cls._get_time_col_func(db, col, func.min, start_ts, end_ts)

    @classmethod
    def s_get_time_col_max(cls, session, col, start_ts=None, end_ts=None):
        """Return the maximum value, from the time period defined by the given two datetime value, of a column, with time format."""
        return cls._s_get_time_col_func(session, col, func.max, start_ts, end_ts)

    @classmethod
    def get_time_col_max(cls, db, col, start_ts=None, end_ts=None):
        """Return the maximum value, from the time period defined by the given two datetime value, of a column, with time format."""
        return cls._get_time_col_func(db, col, func.max, start_ts, end_ts)

    @classmethod
    def s_get_time_col_sum(cls, session, col, start_ts=None, end_ts=None):
        """Return the sum of values, from the time period defined by the given two datetime value, of a column, with time format."""
        return cls._s_get_time_col_func(session, col, func.sum, start_ts, end_ts)

    @classmethod
    def get_time_col_sum(cls, db, col, start_ts=None, end_ts=None):
        """Return the sum of values, from the time period defined by the given two datetime value, of a column, with time format."""
        return cls._get_time_col_func(db, col, func.sum, start_ts, end_ts)

    @classmethod
    def get_col_latest_where(cls, db, col, where_clauses):
        """Return the most recent value for the given column."""
        with db.managed_session() as session:
            query = session.query(col)
            for where_clause in where_clauses:
                query = query.filter(where_clause)
            return query.order_by(desc(cls.time_col)).limit(1).scalar()

    @classmethod
    def get_col_latest(cls, db, col, ignore_le_zero=False):
        """Return the most recent value for the given column."""
        with db.managed_session() as session:
            query = session.query(col)
            if ignore_le_zero:
                if col == cls.time_col:
                    query = query.filter(cls._secs_from_time(col) > 0)
                else:
                    query = query.filter(col > 0)
            return query.order_by(desc(cls.time_col)).limit(1).scalar()

    @classmethod
    def get_time_col_latest(cls, db, col):
        """Return the most recent value for the given column with time format."""
        with db.managed_session() as session:
            return session.query(col).filter(cls._secs_from_time(col) > 0).order_by(desc(cls.time_col)).limit(1).scalar()

    @classmethod
    def _s_get_col_func_of_max_per_day_for_value(cls, session, col, stat_func, start_ts, end_ts, match_col=None, match_value=None):
        max_daily_query = (
            session.query(func.max(col).label('maxes')).filter(cls.during(start_ts, end_ts)).group_by(func.strftime("%j", cls.time_col))
        )
        if match_col is not None and match_value is not None:
            max_daily_query.filter(match_col == match_value)
        return session.query(stat_func(max_daily_query.subquery().columns.maxes)).scalar()

    @classmethod
    def _get_col_func_of_max_per_day_for_value(cls, db, col, stat_func, start_ts, end_ts, match_col=None, match_value=None):
        with db.managed_session() as session:
            return cls._s_get_col_func_of_max_per_day_for_value(session, col, stat_func, start_ts, end_ts, match_col, match_value)

    @classmethod
    def get_col_sum_of_max_per_day_for_value(cls, db, col, match_col, match_value, start_ts, end_ts):
        """Return the sum of the per day maximums for the given column where match_col has value match_value."""
        return cls._get_col_func_of_max_per_day_for_value(db, col, func.sum, start_ts, end_ts, match_col, match_value)

    @classmethod
    def s_get_col_avg_of_max_per_day_for_value(cls, session, col, match_col, match_value, start_ts, end_ts):
        """Return the average of the per day maximums for the given column where match_col has value match_value."""
        return cls._s_get_col_func_of_max_per_day_for_value(session, col, func.avg, start_ts, end_ts, match_col, match_value)

    @classmethod
    def get_col_avg_of_max_per_day_for_value(cls, db, col, match_col, match_value, start_ts, end_ts):
        """Return the average of the per day maximums for the given column where match_col has value match_value."""
        return cls._get_col_func_of_max_per_day_for_value(db, col, func.avg, start_ts, end_ts, match_col, match_value)

    @classmethod
    def _s_get_col_func_of_max_per_day(cls, session, col, stat_func, start_ts, end_ts):
        return cls._s_get_col_func_of_max_per_day_for_value(session, col, func.sum, start_ts, end_ts)

    @classmethod
    def _get_col_func_of_max_per_day(cls, db, col, stat_func, start_ts, end_ts):
        return cls._get_col_func_of_max_per_day_for_value(db, col, func.sum, start_ts, end_ts)

    @classmethod
    def s_get_col_sum_of_max_per_day(cls, session, col, start_ts, end_ts):
        """Return the sum of the per day maximums for the given column."""
        return cls._s_get_col_func_of_max_per_day(session, col, func.sum, start_ts, end_ts)

    @classmethod
    def get_col_sum_of_max_per_day(cls, db, col, start_ts, end_ts):
        """Return the sum of the per day maximums for the given column."""
        return cls._get_col_func_of_max_per_day(db, col, func.sum, start_ts, end_ts)

    @classmethod
    def get_col_avg_of_max_per_day(cls, db, col, start_ts, end_ts):
        """Return the average of the per day maximums for the given column."""
        return cls._get_col_func_of_max_per_day(db, col, func.avg, start_ts, end_ts)

    @classmethod
    def get_col_min_of_max_per_day(cls, db, col, start_ts, end_ts):
        """Return the minimum of the per day maximums for the given column."""
        return cls._get_col_func_of_max_per_day(db, col, func.min, start_ts, end_ts)

    @classmethod
    def get_col_max_of_max_per_day(cls, db, col, start_ts, end_ts):
        """Return the maximum of the per day maximums for the given column."""
        return cls._get_col_func_of_max_per_day(db, col, func.max, start_ts, end_ts)

    @classmethod
    def latest_time(cls, db, not_zero_col):
        """Return the time value of the most recent entry in the table."""
        return cls.get_col_max_greater_than_value(db, cls.time_col, not_zero_col, 0)

    @classmethod
    def row_count(cls, db, col=None, col_value=None):
        """Return the number of rows, with matching column values if supplied, in the table."""
        with db.managed_session() as session:
            query = session.query(cls)
            if col is not None:
                query = query.filter(col == col_value)
            return query.count()

    @classmethod
    def s_row_count_for_period(cls, session, start_ts, end_ts):
        """Return the number of rows in the table in the period defined by the two datetimes."""
        return session.query(cls).filter(cls.time_col >= start_ts).filter(cls.time_col < end_ts).count()

    @classmethod
    def row_count_for_period(cls, db, start_ts, end_ts):
        """Return the number of rows in the table in the period defined by the two datetimes."""
        with db.managed_session() as session:
            return cls.s_row_count_for_period(session, start_ts, end_ts)

    @classmethod
    def s_row_count_for_day(cls, session, day_date):
        """Return the number of rows in the table in the given day."""
        start_ts = datetime.datetime.combine(day_date, datetime.time.min)
        end_ts = start_ts + datetime.timedelta(days=1)
        return cls.s_row_count_for_period(session, start_ts, end_ts)

    @classmethod
    def row_count_for_day(cls, db, day_date):
        """Return the number of rows in the table in the given day."""
        start_ts = datetime.datetime.combine(day_date, datetime.time.min)
        end_ts = start_ts + datetime.timedelta(days=1)
        return cls.row_count_for_period(db, start_ts, end_ts)

    @classmethod
    def _s_get_col_func_for_value(cls, session, col, stat_func, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        return cls._s_query(session, stat_func(col), None, start_ts, end_ts, col if ignore_le_zero else None).filter(match_col == match_value).scalar()

    @classmethod
    def _get_col_func_for_value(cls, db, col, stat_func, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        with db.managed_session() as session:
            return cls._s_query(session, stat_func(col), None, start_ts, end_ts, col if ignore_le_zero else None).filter(match_col == match_value).scalar()

    @classmethod
    def _get_col_sum_for_value(cls, session, col, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        return cls._s_get_col_func_for_value(session, col, func.sum, match_col, match_value, start_ts, end_ts, ignore_le_zero)

    @classmethod
    def get_col_sum_for_value(cls, db, col, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the sum of column values limited by row where match_col has match_value and are in time period defined by start_ts and end_ts."""
        return cls._get_col_func_for_value(db, col, func.sum, match_col, match_value, start_ts, end_ts, ignore_le_zero)

    @classmethod
    def s_get_col_avg_for_value(cls, session, col, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the average of column values limited by row where match_col has match_value and are in time period defined by start_ts and end_ts."""
        return cls._s_get_col_func_for_value(session, col, func.avg, match_col, match_value, start_ts, end_ts, ignore_le_zero)

    @classmethod
    def get_col_avg_for_value(cls, db, col, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the average of column values limited by row where match_col has match_value and are in time period defined by start_ts and end_ts."""
        return cls._get_col_func_for_value(db, col, func.avg, match_col, match_value, start_ts, end_ts, ignore_le_zero)

    @classmethod
    def s_get_col_min_for_value(cls, session, col, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the minimum of column values limited by row where match_col has match_value and are in time period defined by start_ts and end_ts."""
        return cls._s_get_col_func_for_value(session, col, func.min, match_col, match_value, start_ts, end_ts, ignore_le_zero)

    @classmethod
    def get_col_min_for_value(cls, db, col, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the minimum of column values limited by row where match_col has match_value and are in time period defined by start_ts and end_ts."""
        return cls._get_col_func_for_value(db, col, func.min, match_col, match_value, start_ts, end_ts, ignore_le_zero)

    @classmethod
    def s_get_col_max_for_value(cls, session, col, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the maximum of column values limited by row where match_col has match_value and are in time period defined by start_ts and end_ts."""
        return cls._s_get_col_func_for_value(session, col, func.max, match_col, match_value, start_ts, end_ts, ignore_le_zero)

    @classmethod
    def get_col_max_for_value(cls, db, col, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the maximum of column values limited by row where match_col has match_value and are in time period defined by start_ts and end_ts."""
        return cls._get_col_func_for_value(db, col, func.max, match_col, match_value, start_ts, end_ts, ignore_le_zero)

    @classmethod
    def _get_col_func_greater_than_value(cls, db, col, stat_func, match_col, match_value, start_ts=None, end_ts=None):
        with db.managed_session() as session:
            return cls._s_query(session, stat_func(col), None, start_ts, end_ts).filter(match_col > match_value).scalar()

    @classmethod
    def get_col_avg_greater_than_value(cls, db, col, match_col, match_value, start_ts=None, end_ts=None):
        """Return the average of column values limited by row where match_col is greater than match_value and are in time period defined by start_ts and end_ts."""
        return cls._get_col_func_greater_than_value(db, col, func.avg, match_col, match_value, start_ts, end_ts)

    @classmethod
    def get_col_max_greater_than_value(cls, db, col, match_col, match_value, start_ts=None, end_ts=None):
        """Return the maximum of column values limited by row where match_col is greater than match_value and are in time period defined by start_ts and end_ts."""
        return cls._get_col_func_greater_than_value(db, col, func.max, match_col, match_value, start_ts, end_ts)

    @classmethod
    def _get_col_func_less_than_value(cls, db, col, stat_func, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        with db.managed_session() as session:
            return cls._s_query(session, stat_func(col), None, start_ts, end_ts, col if ignore_le_zero else None).filter(match_col < match_value).scalar()

    @classmethod
    def get_col_avg_less_than_value(cls, db, col, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the average of column values limited by row where match_col is less than match_value and are in time period defined by start_ts and end_ts."""
        return cls._get_col_func_less_than_value(db, col, func.avg, match_col, match_value, start_ts, end_ts, ignore_le_zero)

    @classmethod
    def get_col_min_less_than_value(cls, db, col, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the minimum of column values limited by row where match_col is less than match_value and are in time period defined by start_ts and end_ts."""
        return cls._get_col_func_less_than_value(db, col, func.min, match_col, match_value, start_ts, end_ts, ignore_le_zero)

    @classmethod
    def get_col_max_less_than_value(cls, db, col, match_col, match_value, start_ts=None, end_ts=None, ignore_le_zero=False):
        """Return the maximum of column values limited by row where match_col is less than match_value and are in time period defined by start_ts and end_ts."""
        return cls._get_col_func_less_than_value(db, col, func.max, match_col, match_value, start_ts, end_ts, ignore_le_zero)

    @classmethod
    def get_daily_stats(cls, session, day_ts):
        """Return a dictionary of aggregate statistics for the given day."""
        stats = cls.get_stats(session, day_ts, day_ts + datetime.timedelta(1))
        stats['day'] = day_ts
        return stats

    @classmethod
    def get_weekly_stats(cls, session, first_day_ts):
        """Return a dictionary of aggregate statistics for the given week."""
        stats = cls.get_stats(session, first_day_ts, first_day_ts + datetime.timedelta(7))
        stats['first_day'] = first_day_ts
        return stats

    @classmethod
    def get_monthly_stats(cls, session, first_day_ts, last_day_ts):
        """Return a dictionary of aggregate statistics for the given month."""
        stats = cls.get_stats(session, first_day_ts, last_day_ts)
        stats['first_day'] = first_day_ts
        return stats

    @classmethod
    def get_yearly_stats(cls, session, year):
        """Return a dictionary of aggregate statistics for the given year."""
        first_day_ts = datetime.datetime(year, 1, 1)
        return cls.get_monthly_stats(session, first_day_ts, first_day_ts + datetime.timedelta(365))

    def __repr__(self):
        """Return a string representation of a DbObject instance."""
        classname = self.__class__.__name__
        values = {col_name : getattr(self, col_name) for col_name in self.col_names}
        return ("<%s() %r>" % (classname, values))
