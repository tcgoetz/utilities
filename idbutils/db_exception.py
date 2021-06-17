"""Exceptions encountered while interacting with a DB."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"


class DbException(Exception):
    """Base class for DB exceptions."""

    def __init__(self, message, inner_exception=None):
        """Return a DbException instance."""
        self.message = message
        self.inner_exception = inner_exception

    def __str__(self):
        """Return a string representation of a DbException instance."""
        return f'{self.message}:{self.inner_exception}'
