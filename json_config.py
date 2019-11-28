"""Class that loads a JSON config file."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"


import json
import dateutil.parser


class JsonConfig(object):
    """Class that loads a JSON config file."""

    def __init__(self, filename):
        """Return a new JsonConfig instance."""
        def parser(entry):
            for (entry_key, entry_value) in entry.items():
                if str(entry_key).endswith('_date'):
                    entry[entry_key] = dateutil.parser.parse(entry_value).date()
            return entry
        with open(filename) as file:
            self.config = json.load(file, object_hook=parser)

    def get_datetime(self, node):
        """Return a datetime.datetime object created from a date string."""
        return dateutil.parser.parse(node)

    def get_date(self, node):
        """Return a datetime.time object created from a date string."""
        return self.get_datetime(node).date()
