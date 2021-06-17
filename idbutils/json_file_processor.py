"""Class for parsing JSON formatted health data into a database."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"

import json
import logging
import traceback
from tqdm import tqdm
import dateutil.parser

from idbutils.file_processor import FileProcessor
from idbutils.conversions import epoch_ms_to_dt


class JsonFileProcessor(object):
    """Class for parsing JSON formatted health data into a database."""

    logger = logging.getLogger()
    conversions = None

    def __init__(self, file_regex, input_file=None, input_dir=None, latest=True, debug=False, recursive=False):
        """
        Return an instance of JsonFileProcessor.

        Parameters:
        ----------
            file_regex (string): only process files that match this regex
            input_file (string): file (full path) to check for data
            input_dir (string): directory (full path) to check for data files
            latest (Boolean): check for latest files only
            debug (Boolean): enable debug logging
            recursive (Boolean): check the search directory recursively

        """
        self.debug = debug
        if input_file:
            self.file_names = FileProcessor.match_file(input_file, file_regex)
            self.logger.info("Found %d json files for %s in %s", self.file_count(), file_regex, input_file)
        if input_dir:
            self.file_names = FileProcessor.dir_to_files(input_dir, file_regex, latest, recursive)
            self.logger.info("Found %d json files for %s in %s", self.file_count(), file_regex, input_dir)
        self.total_updates = 0

    def _parse_date(self, date_str):
        """Return a datetime object for the given date string."""
        # Try parsing the date as an epoch first
        try:
            return epoch_ms_to_dt(date_str)
        except Exception:
            try:
                return dateutil.parser.parse(date_str)
            except Exception as e:
                self.logger.info("Failed to parse date %s: %s", date_str, e)

    def file_count(self):
        """Return the number of files that will be proccessed."""
        return len(self.file_names)

    def __parse_file(self, filename):
        def parser(entry):
            for (conversion_key, conversion_func) in self.conversions.items():
                entry_value = entry.get(conversion_key)
                if entry_value is not None:
                    entry[conversion_key] = conversion_func(entry_value)
            return entry
        with open(filename) as file:
            return json.load(file, object_hook=parser)

    def _get_field(self, json, fieldname, format_func=str):
        try:
            data = json[fieldname]
            if data is not None:
                return format_func(data)
        except KeyError as e:
            self.logger.debug("JSON %s not found in %r: %s", fieldname, json, e)

    def _get_field_obj(self, json, fieldname, format_func):
        try:
            data = json[fieldname]
            return format_func(data)
        except KeyError as e:
            self.logger.debug("JSON %s not found in %r: %s", fieldname, json, e)

    def _save_json_file(self, json_full_filname, json_data):
        def __convert_to_json(object):
            return str(object)
        with open(json_full_filname, 'w') as file:
            self.logger.info("_save_json_file: %s", json_full_filname)
            file.write(json.dumps(json_data, default=__convert_to_json))

    def _process_json(self, json_data):
        """Implement this function in a subclass to handle saving a JSON blob to a DB."""
        return 0

    def _call_process_func(self, name, sub_name, id, json_data):
        """Call a JSON data processor function given it's base name."""
        process_function = '_process_' + name
        try:
            function = getattr(self, process_function, None)
            if function is not None:
                function(sub_name, id, json_data)
            else:
                self.logger.warning("No handler %s from %s %s", process_function, id, self.__class__.__name__)
        except Exception as e:
            self.logger.error("Exception in %s from %s %s: %s", process_function, id, self.__class__.__name__, e)

    def _process_files(self):
        self.logger.info("Processing %d json files", self.file_count())
        for file_name in tqdm(self.file_names, unit='files'):
            try:
                json_data = self.__parse_file(file_name)
                updates = self._process_json(json_data)
                if updates > 0:
                    self.logger.info("DB updated with %d entries from %s", updates, file_name)
                    self.total_updates += updates
                else:
                    self.logger.warning("No data saved for %s", file_name)
            except Exception:
                self.logger.error("Failed to parse %s: %s", file_name, traceback.format_exc())
        self.logger.info("DB updated with %d entries from %d files.", self.total_updates, self.file_count())

    def process(self):
        """Import files into the database."""
        self._process_files()
