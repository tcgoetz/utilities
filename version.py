"""Version information for the application."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"

import sys
import logging


logger = logging.getLogger(__file__)


def to_string(version_info, prerelease=False):
    """Return a version string for a version tuple."""
    return '.'.join(str(digit) for digit in version_info) + ' pre' if prerelease else ''


def display(program, version):
    """Print version information for the script."""
    print('%s %s' % (program, version))


def log(program, version):
    """Print version information for the script."""
    logger.info('%s %s', program, version)


def python_version_check(program, required, tested):
    """Validate the Python version requirements."""
    if sys.version_info < required:
        raise Exception(f'{program} requires Python {to_string(required)} or greater')
    if sys.version_info != tested:
        logger.info('%s has been tested on Python %s', program, to_string(tested))
