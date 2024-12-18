import asyncio
import logging
import time
from pathlib import Path
from typing import Dict, Set, Callable, Union

import yaml
from watchdog.events import FileSystemEventHandler, FileModifiedEvent, FileCreatedEvent
from watchdog.observers import Observer


class ConfigFileEventHandler(FileSystemEventHandler):
    """
    Handles file system events for configuration files.
    Implements debouncing to prevent multiple rapid reloads.
    """

    def __init__(self, callback: Callable[[Path], None], debounce_seconds: float = 1.0):
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.last_modified: Dict[str, float] = {}
        self.logger = logging.getLogger(__name__)

    def on_modified(self, event):
        if not isinstance(event, FileModifiedEvent):
            return

        if not event.src_path.endswith('.yaml'):
            return

        current_time = time.time()
        last_modified = self.last_modified.get(event.src_path, 0)

        if current_time - last_modified > self.debounce_seconds:
            self.last_modified[event.src_path] = current_time
            self.callback(Path(event.src_path))

    def on_created(self, event):
        if not isinstance(event, FileCreatedEvent):
            return

        if not event.src_path.endswith('.yaml'):
            return

        self.callback(Path(event.src_path))


class ConfigurationWatcher:
    """
    Watches configuration files for changes and manages automatic reloading.
    """

    def __init__(self, config_dirs: Union[str, Path, list[Union[str, Path]]]):
        self.logger = logging.getLogger(__name__)
        self.observer = Observer()
        self.watch_paths: Set[Path] = set()
        self.callbacks: Dict[Path, Set[Callable]] = {}
        self.running = False

        # Convert input to list of Paths
        if isinstance(config_dirs, (str, Path)):
            config_dirs = [config_dirs]
        self.config_dirs = [Path(d) for d in config_dirs]

        # Initialize file event handler
        self.event_handler = ConfigFileEventHandler(
            callback=self._handle_config_change,
            debounce_seconds=1.0
        )

    async def start(self):
        """Start watching configuration files."""
        if self.running:
            return

        self.running = True

        # Set up watches for all config directories
        for config_dir in self.config_dirs:
            if not config_dir.exists():
                self.logger.warning(f"Config directory does not exist: {config_dir}")
                continue

            self.observer.schedule(
                self.event_handler,
                str(config_dir),
                recursive=True
            )
            self.watch_paths.add(config_dir)
            self.logger.info(f"Watching config directory: {config_dir}")

        # Start the observer in a separate thread
        self.observer.start()
        self.logger.info("Configuration watcher started")

    async def stop(self):
        """Stop watching configuration files."""
        if not self.running:
            return

        self.running = False
        self.observer.stop()
        self.observer.join()
        self.logger.info("Configuration watcher stopped")

    def register_callback(self, config_path: Union[str, Path], callback: Callable):
        """
        Register a callback function to be called when a configuration file changes.
        The callback receives the path to the changed file.
        """
        config_path = Path(config_path)

        if config_path not in self.callbacks:
            self.callbacks[config_path] = set()

        self.callbacks[config_path].add(callback)
        self.logger.debug(f"Registered callback for {config_path}")

    def unregister_callback(self, config_path: Union[str, Path], callback: Callable):
        """Remove a callback function for a configuration file."""
        config_path = Path(config_path)

        if config_path in self.callbacks:
            self.callbacks[config_path].discard(callback)
            if not self.callbacks[config_path]:
                del self.callbacks[config_path]
            self.logger.debug(f"Unregistered callback for {config_path}")

    def _handle_config_change(self, file_path: Path):
        """Handle configuration file changes and notify registered callbacks."""
        try:
            # Verify it's a YAML file
            if not file_path.suffix == '.yaml':
                return

            # Read the new configuration
            with open(file_path, 'r') as f:
                new_config = yaml.safe_load(f)

            # Find and notify relevant callbacks
            matched_callbacks = set()

            # Exact path matches
            if file_path in self.callbacks:
                matched_callbacks.update(self.callbacks[file_path])

            # Parent directory matches (for watching entire directories)
            for watched_path in self.callbacks:
                if watched_path.is_dir() and file_path.is_relative_to(watched_path):
                    matched_callbacks.update(self.callbacks[watched_path])

            # Notify callbacks
            for callback in matched_callbacks:
                try:
                    callback(file_path, new_config)
                except Exception as e:
                    self.logger.error(f"Error in callback for {file_path}: {e}")

            self.logger.info(f"Configuration reloaded: {file_path}")

        except Exception as e:
            self.logger.error(f"Error handling config change for {file_path}: {e}")


class AutoReloadConfigManager:
    """
    Extension of ConfigurationManager that automatically reloads changed configurations.
    """

    def __init__(self, config_manager, config_watcher: ConfigurationWatcher):
        self.config_manager = config_manager
        self.config_watcher = config_watcher
        self.logger = logging.getLogger(__name__)

    async def start(self):
        """Start watching configurations for changes."""
        # Register callbacks for all configuration directories
        for scope_dir in self.config_manager.config_dirs.values():
            self.config_watcher.register_callback(
                scope_dir,
                self._handle_config_reload
            )

        await self.config_watcher.start()

    async def stop(self):
        """Stop watching configurations."""
        await self.config_watcher.stop()

    def _handle_config_reload(self, file_path: Path, new_config: dict):
        """Handle configuration reload events."""
        try:
            # Determine configuration name and scope
            relative_path = None
            config_scope = None

            for scope, dir_path in self.config_manager.config_dirs.items():
                if file_path.is_relative_to(dir_path):
                    relative_path = file_path.relative_to(dir_path)
                    config_scope = scope
                    break

            if not relative_path or not config_scope:
                return

            config_name = relative_path.stem

            # Validate and update configuration
            schema_name = config_name  # Assuming schema name matches config name

            if schema_name in self.config_manager.schema_registry:
                self.config_manager._validate_config(
                    new_config,
                    self.config_manager.schema_registry[schema_name]
                )

            # Update the configuration
            self.config_manager.configs[config_name] = new_config

            self.logger.info(
                f"Configuration {config_name} automatically reloaded from {file_path}"
            )

        except Exception as e:
            self.logger.error(f"Error reloading configuration {file_path}: {e}")


# Example usage
async def example_usage():
    from config_yaml_system import ConfigurationManager

    # Initialize configuration manager and watcher
    config_manager = ConfigurationManager("./config")
    config_watcher = ConfigurationWatcher(config_manager.config_dirs.values())
    auto_reload_manager = AutoReloadConfigManager(config_manager, config_watcher)

    # Start watching configurations
    await auto_reload_manager.start()

    try:
        # Your server code here
        while True:
            await asyncio.sleep(1)
    finally:
        await auto_reload_manager.stop()


if __name__ == "__main__":
    asyncio.run(example_usage())