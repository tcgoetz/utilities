"""Base classes for plugins."""

__author__ = "Tom Goetz"
__copyright__ = "Copyright Tom Goetz"
__license__ = "GPL"

import os
import sys
import re
import importlib
import types
import logging


logger = logging.getLogger(__file__)


class Plugin():
    """Base class for a loadable module."""


class PluginManager():
    """Loads python file based plugins."""

    def __init__(self, plugin_dir, plugin_base, plugin_dict):
        """Load python file based plugins from plugin_dir."""
        logger.info("Loading plugins from %s", plugin_dir)
        self.plugins = {}
        self.plugins_classes = {}
        self._load_all(plugin_dir, plugin_base, plugin_dict)

    def _enumerate_plugins(self, plugin_dir):
        plugins = {}
        for filename in os.listdir(plugin_dir):
            logger.info("Possible plugin %s", filename)
            found = re.match(r"(\S+)_plugin.py", filename)
            if found:
                plugins[found.group(1)] = plugin_dir + os.sep + filename
        return plugins

    def _load(self, name, path, plugin_base, plugin_dict):
        def _class_exec(namespace):
            namespace.update(plugin_dict)
        logger.info("Loading plugin %s based on %s from %s", name, plugin_base, path)
        plugin_module_name = f'{name}_plugin'
        plugin_module = importlib.import_module(plugin_module_name)
        plugin_class = getattr(plugin_module, name)
        self.plugins_classes[name] = types.new_class(name, bases=(plugin_base, plugin_class), exec_body=_class_exec)
        logger.info("Loaded plugin %s: %s", name, self.plugins_classes[name])
        self.plugins[name] = self.plugins_classes[name]()
        logger.info("Instantiated plugin %s: %s", name, self.plugins[name])

    def _load_all(self, plugin_dir, plugin_base, plugin_dict):
        sys.path.append(plugin_dir)
        for plugin, path in self._enumerate_plugins(plugin_dir).items():
            self._load(plugin, path, plugin_base, plugin_dict)
