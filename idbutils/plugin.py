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


class PluginManager():
    """Loads python file based plugins."""

    _plugins_classes = {}

    def __init__(self, plugin_dir, plugin_dict):
        """Load python file based plugins from plugin_dir."""
        logger.info("Loading plugins from %s", plugin_dir)
        self.plugins = {}
        self._load_all(plugin_dir, plugin_dict)

    def _enumerate_plugins(self, plugin_dir):
        plugins = {}
        for filename in os.listdir(plugin_dir):
            found = re.match(r"(\S+)_plugin.py", filename)
            if found:
                plugins[found.group(1)] = plugin_dir + os.sep + filename
        return plugins

    def _load_class(self, name, plugin_dict):
        def _class_exec(namespace):
            namespace.update(plugin_dict)
        logger.debug("Loading plugin %s", name)
        plugin_module_name = f'{name}_plugin'
        plugin_module = importlib.import_module(plugin_module_name)
        plugin_class = getattr(plugin_module, name)
        self._plugins_classes[name] = types.new_class(name, bases=(plugin_class,), exec_body=_class_exec)
        logger.debug("Loaded plugin %s: %s", name, self._plugins_classes[name])

    def _load(self, name, plugin_dict):
        if name not in self._plugins_classes:
            self._load_class(name, plugin_dict)
        plugin_type = self._plugins_classes[name]._type
        if plugin_type not in self.plugins:
            self.plugins[plugin_type] = {}
        if name not in self.plugins[plugin_type]:
            self.plugins[plugin_type][name] = self._plugins_classes[name]()
            logger.debug("Instantiated %s plugin %s: %r", plugin_type, name, self.plugins[plugin_type][name])

    def _load_all(self, plugin_dir, plugin_dict):
        logger.debug("Loading plugins from %s ", plugin_dir)
        sys.path.append(plugin_dir)
        for plugin, path in self._enumerate_plugins(plugin_dir).items():
            self._load(plugin, plugin_dict)
