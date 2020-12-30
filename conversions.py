"""Methods for converting metrics from one representation to another."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"


import datetime


def epoch_ms_to_dt(epoch_ms):
    """Convert milliseconds since the epoch to a datetime object."""
    return datetime.datetime.fromtimestamp(epoch_ms / 1000.0)
