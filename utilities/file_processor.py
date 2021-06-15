"""Class for finding files that match a regex."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"


import logging
import os
import re
import datetime


class FileProcessor(object):
    """Class for finding files that match a regex."""

    logger = logging.getLogger(__file__)

    @classmethod
    def __regex_matches_file(cls, file, file_regex):
        return re.search(file_regex, file)

    @classmethod
    def match_file(cls, input_file, file_regex):
        """Test if a file matches a regex."""
        cls.logger.info("Matching file: %s", input_file)
        if cls.__regex_matches_file(input_file, file_regex):
            return [input_file]
        return []

    @classmethod
    def __file_newer_than(cls, file, timestamp):
        file_time = datetime.datetime.fromtimestamp(os.stat(file).st_mtime)
        cls.logger.debug("Is file %s newer? (%s vs %s)", file, file_time, timestamp)
        return file_time > timestamp

    @classmethod
    def dir_to_files(cls, input_dir, file_regex, latest=False, recursive=False):
        """Search a directory, possibly recursively, and return a list of all files matching a regex."""
        file_names = []
        latest_threshold = datetime.datetime.now() - datetime.timedelta(days=1)
        if latest:
            cls.logger.info("Reading directory: %s looking for files matching %s and created after %s", input_dir, file_regex, latest_threshold)
        else:
            cls.logger.info("Reading directory: %s looking for files matching %s", input_dir, file_regex)
        for file in os.listdir(input_dir):
            file_with_path = input_dir + "/" + file
            if recursive and os.path.isdir(file_with_path):
                file_names = file_names + cls.dir_to_files(file_with_path, file_regex, latest)
            elif cls.__regex_matches_file(file, file_regex) and (not latest or cls.__file_newer_than(file_with_path, latest_threshold)):
                file_names.append(file_with_path)
        return file_names
