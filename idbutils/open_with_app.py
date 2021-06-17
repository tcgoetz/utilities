"""Open a file with an application."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"

import sys
import subprocess


class OpenWithApp():
    """Class that opens a file with an application regardsless of platform."""

    @classmethod
    def open_on_darwin(cls, app_name, filename):
        """Open a file with a MacOS application."""
        subprocess.run(['open', '-a', app_name, '--args', filename], check=True)

    @classmethod
    def open_on_darwin_with_applescript(cls, app_name, scriptlet):
        """Open a file with a MacOS application using applescript."""
        applescript = f'tell application "{app_name}" to {scriptlet}'
        subprocess.run(['osascript', '-e', applescript], check=True)

    @classmethod
    def open_on_linux(cls, app_name, filename):
        """Open a file with MacOS application."""
        subprocess.run(['start', '-n', app_name, '--args', filename], check=True)

    @classmethod
    def open(cls, filename):
        """Open a file with application."""
        handler_name = '_open_on_' + sys.platform
        function = getattr(cls, handler_name, None)
        if function is not None:
            return function(filename)
        raise Exception(f'No opener {handler_name} for platform {sys.platform}')
