import logging
from importlib import import_module
from argparse import ArgumentParser
from typing import Dict

logger = logging.getLogger(__name__)


class Plugin:
    """Registry for user-defined plot plugins.

    Each plugin module must expose two callables:
        load(parser: ArgumentParser) -> None
            Register any CLI arguments the plugin needs.
        main(*args) -> None
            Execute the plugin (called after the chart is set up).

    Usage::

        plugin = Plugin()
        plugin.register(config.PLOT_PLUGINS, parser)
        plugin.run(plotter, df)
    """

    def __init__(self):
        self.plugins: list = []

    def register(self, plugins: Dict, parser: ArgumentParser) -> None:
        """Load and register plugins from a config dict.

        Skips plugins that cannot be imported or are missing required
        callables, logging a warning instead of crashing.
        """
        for name, cfg in plugins.items():
            module_name = cfg.get("name", name)
            try:
                instance = import_module(f"plugin.{module_name}")
            except ImportError as exc:
                logger.warning("Plugin '%s' could not be imported: %s", module_name, exc)
                continue

            for required in ("load", "main"):
                if not callable(getattr(instance, required, None)):
                    logger.warning(
                        "Plugin '%s' is missing required callable '%s' — skipped.",
                        module_name,
                        required,
                    )
                    break
            else:
                try:
                    instance.load(parser)
                except Exception as exc:
                    logger.warning("Plugin '%s' load() raised an error: %s", module_name, exc)
                    continue
                self.plugins.append(instance)

    def run(self, *args) -> None:
        """Execute all registered plugins, logging failures without crashing."""
        for plugin in self.plugins:
            try:
                plugin.main(*args)
            except Exception as exc:
                logger.warning("Plugin '%s' main() raised an error: %s", plugin.__name__, exc)
