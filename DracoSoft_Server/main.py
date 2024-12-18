import asyncio
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from DracoSoft_Server.core.config_yaml_system import ConfigurationManager, ConfigurationScope
from DracoSoft_Server.core.core_server import CoreServer
from DracoSoft_Server.core.moduleEventSystem import EventManager
from DracoSoft_Server.core.moduleManager import ModuleManager

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))


class DracoSoftServer(CoreServer):
    """Main server implementation for DracoSoft game server framework."""

    def __init__(self, config_path: str):
        # Load configurations
        self.config_manager = ConfigurationManager(config_path)
        self.server_config = self.config_manager.load_config("server", ConfigurationScope.SERVER)
        self.main_config = self.config_manager.load_config("main", ConfigurationScope.SERVER)

        if not self.main_config:
            raise RuntimeError("Main configuration not found")

        super().__init__()

        # Initialize components
        self.event_manager = EventManager()
        self.module_manager = ModuleManager(self)
        self._server = None

        # Setup logging
        log_config = self.server_config.get('logging', {})
        self.setup_logging(log_config)
        self.logger = logging.getLogger(__name__)

        # Create required directories
        self.create_directories()

    def create_directories(self) -> None:
        """Create required directories from configuration."""
        dir_config = self.main_config.get('directories', {})
        base_path = Path.cwd()

        for dir_name, dir_path in dir_config.items():
            full_path = base_path / dir_path
            full_path.mkdir(parents=True, exist_ok=True)
            self.logger.debug(f"Ensured directory exists: {full_path}")

    def setup_logging(self, log_config: dict) -> None:
        """Setup logging configuration."""
        try:
            log_level = getattr(logging, log_config.get('level', 'INFO'))
            log_format = log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s')

            # Get log directory from main config
            log_dir = self.main_config.get('directories', {}).get('logs', 'logs')
            os.makedirs(log_dir, exist_ok=True)

            # Setup log file
            log_file = log_config.get('file')
            if log_file:
                # Add timestamp to log filename
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                log_filename = os.path.splitext(log_file)
                log_file = Path(log_dir) / f"{log_filename[0]}_{timestamp}{log_filename[1]}"

            # Configure logging
            handlers = [logging.StreamHandler()]
            if log_file:
                handlers.append(logging.FileHandler(log_file))

            logging.basicConfig(
                level=log_level,
                format=log_format,
                handlers=handlers
            )

            self.logger = logging.getLogger(__name__)
            self.logger.setLevel(log_level)
            self.logger.info("Logging system initialized")

        except Exception as e:
            print(f"Error setting up logging: {e}")
            logging.basicConfig(
                level=logging.INFO,
                format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            self.logger = logging.getLogger(__name__)
            self.logger.error(f"Failed to configure logging: {e}")

    async def start_server(self):
        """Start the server and initialize all components."""
        try:
            # Start event system
            await self.event_manager.start()
            self.logger.info("Event system started")

            # Discover available modules
            discovered_modules = await self.module_manager.discover_modules()
            self.logger.info(f"Discovered modules: {discovered_modules}")

            # Get module configuration
            module_config = self.main_config.get('modules', {})
            module_mapping = module_config.get('mapping', {})
            load_order = module_config.get('load_order', [])

            # Load modules in order
            for module_base in load_order:
                module_name = module_mapping.get(module_base)
                if not module_name:
                    self.logger.warning(f"No mapping found for module: {module_base}")
                    continue

                if module_name not in discovered_modules:
                    self.logger.error(f"Required module not found: {module_name}")
                    continue

                self.logger.info(f"Loading module: {module_name}")
                if not await self.module_manager.load_module(module_name):
                    raise RuntimeError(f"Failed to load {module_name}")

                self.logger.info(f"Enabling module: {module_name}")
                if not await self.module_manager.enable_module(module_name):
                    raise RuntimeError(f"Failed to enable {module_name}")

            self.running = True
            self.logger.info("Server started successfully")

        except Exception as e:
            self.logger.error(f"Failed to start server: {e}")
            await self.shutdown()
            raise

    async def shutdown(self):
        """Shutdown the server and cleanup resources."""
        if not self.running:
            return

        try:
            self.logger.info("Beginning server shutdown...")

            # Stop event system
            await self.event_manager.stop()

            # Get shutdown order from config
            shutdown_order = self.main_config.get('modules', {}).get('shutdown_order', [])

            # Shutdown modules in configured order
            for module_name in shutdown_order:
                if module_name in self.module_manager.modules:
                    module = self.module_manager.modules[module_name]
                    try:
                        if module.is_enabled:
                            self.logger.info(f"Disabling module: {module_name}")
                            await module.disable()
                        self.logger.info(f"Unloading module: {module_name}")
                        await self.module_manager.unload_module(module_name)
                    except Exception as e:
                        self.logger.error(f"Error shutting down {module_name}: {e}")

            self.running = False
            self.logger.info("Server shutdown complete")

        except Exception as e:
            self.logger.error(f"Error during shutdown: {e}")


async def main():
    """Main entry point for the server."""
    config_base = Path("config")
    server = DracoSoftServer(str(config_base))

    try:
        await server.start_server()

        # Get tick rate from config
        tick_rate = server.main_config.get('server', {}).get('tick_rate', 1)

        # Keep the server running until interrupted
        while server.running:
            await asyncio.sleep(tick_rate)

    except KeyboardInterrupt:
        logging.info("Server shutdown requested")
    except Exception as e:
        logging.error(f"Server error: {e}")
    finally:
        await server.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
