import importlib.util
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Type

import yaml

from .baseModule import BaseModule


class ModuleManager:
    def __init__(self, server):
        self.server = server
        self.modules: Dict[str, BaseModule] = {}
        self.module_classes: Dict[str, Type[BaseModule]] = {}
        self.logger = logging.getLogger(__name__)

        # Get the absolute path to the modules directory
        self.modules_dir = Path(__file__).parent.parent / "modules"
        self.logger.info(f"ModuleManager initializing with modules directory: {self.modules_dir}")

        # Create modules directory if it doesn't exist
        self.modules_dir.mkdir(parents=True, exist_ok=True)

        # Load module configurations
        self.config_path = Path(__file__).parent.parent / "config" / "modules.yaml"
        self.logger.info(f"Loading module configs from: {self.config_path}")
        self.module_configs = self._load_module_configs()

    def _load_module_configs(self) -> Dict:
        """Load module configurations from YAML file."""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    return yaml.safe_load(f)
            return {}
        except Exception as e:
            self.logger.error(f"Error loading module configs: {e}")
            return {}

    async def discover_modules(self) -> List[str]:
        """Discover available modules in the modules directory."""
        discovered_modules = []

        self.logger.info(f"Searching for modules in: {self.modules_dir}")

        if not self.modules_dir.exists():
            self.logger.error(f"Modules directory does not exist: {self.modules_dir}")
            return discovered_modules

        for file_path in self.modules_dir.glob("*.py"):
            if file_path.name.startswith('_'):
                continue

            module_name = file_path.stem
            self.logger.debug(f"Found potential module file: {file_path}")

            try:
                module_class = self._load_module_class(module_name)
                if module_class:
                    self.module_classes[module_name] = module_class
                    discovered_modules.append(module_name)
                    self.logger.info(f"Successfully loaded module class: {module_name}")
                else:
                    self.logger.warning(f"No valid module class found in {file_path}")
            except Exception as e:
                self.logger.error(f"Error loading module {module_name}: {e}", exc_info=True)

        return discovered_modules

    def _load_module_class(self, module_name: str) -> Optional[Type[BaseModule]]:
        """Load a module class from file."""
        try:
            module_path = self.modules_dir / f"{module_name}.py"
            self.logger.debug(f"Attempting to load module from: {module_path}")

            if not module_path.exists():
                self.logger.error(f"Module file does not exist: {module_path}")
                return None

            spec = importlib.util.spec_from_file_location(module_name, str(module_path))
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                # Find the module class that inherits from BaseModule
                for item in dir(module):
                    obj = getattr(module, item)
                    if (isinstance(obj, type) and
                            issubclass(obj, BaseModule) and
                            obj != BaseModule):
                        self.logger.info(f"Found valid module class {obj.__name__} in {module_name}")
                        return obj

            self.logger.warning(f"No valid module class found in {module_name}")
            return None

        except Exception as e:
            self.logger.error(f"Error loading module class {module_name}: {e}", exc_info=True)
            return None

    async def load_module(self, module_name: str) -> bool:
        """
        Load and initialize a module.
        Returns True if successful, False otherwise.
        """
        if module_name in self.modules:
            self.logger.warning(f"Module {module_name} is already loaded")
            return False

        if module_name not in self.module_classes:
            self.logger.error(f"Module class {module_name} not found")
            return False

        try:
            self.logger.debug(f"Loading module {module_name}")
            self.logger.debug(f"Module class: {self.module_classes.get(module_name)}")
            # Create module instance
            module_class = self.module_classes[module_name]
            module_instance = module_class(self.server)

            # Apply configuration if available
            if module_name in self.module_configs:
                module_instance.configure(self.module_configs[module_name])

            # Load the module
            if await module_instance.load():
                self.modules[module_name] = module_instance
                self.logger.info(f"Successfully loaded module: {module_name}")
                return True

        except Exception as e:
            self.logger.error(f"Error loading module {module_name}: {e}")
        return False

    async def unload_module(self, module_name: str) -> bool:
        """
        Unload a module and cleanup its resources.
        Returns True if successful, False otherwise.
        """
        if module_name not in self.modules:
            self.logger.warning(f"Module {module_name} is not loaded")
            return False

        try:
            module = self.modules[module_name]

            # Check for dependent modules
            for other_module in self.modules.values():
                if module_name in other_module.module_info.dependencies:
                    if other_module.is_enabled:
                        self.logger.error(
                            f"Cannot unload {module_name}: Required by {other_module.module_info.name}"
                        )
                        return False

            # Disable if enabled
            if module.is_enabled:
                await module.disable()

            # Unload the module
            if await module.unload():
                del self.modules[module_name]
                self.logger.info(f"Successfully unloaded module: {module_name}")
                return True

        except Exception as e:
            self.logger.error(f"Error unloading module {module_name}: {e}")
        return False

    async def enable_module(self, module_name: str) -> bool:
        """
        Enable a loaded module.
        Returns True if successful, False otherwise.
        """
        if module_name not in self.modules:
            self.logger.error(f"Module {module_name} is not loaded")
            return False

        try:
            module = self.modules[module_name]

            # Check dependencies
            if not await module.validate_dependencies():
                self.logger.error(f"Module {module_name} dependencies not satisfied")
                return False

            # Enable the module
            if await module.enable():
                self.logger.info(f"Successfully enabled module: {module_name}")
                return True

        except Exception as e:
            self.logger.error(f"Error enabling module {module_name}: {e}")
        return False

    async def disable_module(self, module_name: str) -> bool:
        """
        Disable a loaded module.
        Returns True if successful, False otherwise.
        """
        if module_name not in self.modules:
            self.logger.error(f"Module {module_name} is not loaded")
            return False

        try:
            module = self.modules[module_name]

            # Check for dependent modules
            for other_module in self.modules.values():
                if (module_name in other_module.module_info.dependencies and
                        other_module.is_enabled):
                    self.logger.error(
                        f"Cannot disable {module_name}: Required by {other_module.module_info.name}"
                    )
                    return False

            # Disable the module
            if await module.disable():
                self.logger.info(f"Successfully disabled module: {module_name}")
                return True

        except Exception as e:
            self.logger.error(f"Error disabling module {module_name}: {e}")
        return False

    def get_module_status(self, module_name: str) -> Optional[Dict]:
        """Get the current status of a module."""
        if module_name in self.modules:
            return self.modules[module_name].get_status()
        return None

    def get_all_modules_status(self) -> Dict[str, Dict]:
        """Get the status of all loaded modules."""
        return {name: module.get_status() for name, module in self.modules.items()}

    async def reload_module(self, module_name: str) -> bool:
        """
        Reload a module by unloading and loading it again.
        Returns True if successful, False otherwise.
        """
        if await self.unload_module(module_name):
            return await self.load_module(module_name)
        return False

    async def load_all_modules(self) -> Dict[str, bool]:
        """
        Attempt to load all discovered modules.
        Returns a dictionary of module names and their load status.
        """
        results = {}
        discovered = await self.discover_modules()

        for module_name in discovered:
            results[module_name] = await self.load_module(module_name)

        return results

    async def shutdown(self):
        """Gracefully shutdown all modules."""
        for module_name in list(self.modules.keys()):
            await self.unload_module(module_name)