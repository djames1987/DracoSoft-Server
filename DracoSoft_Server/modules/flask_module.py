import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging
from flask import Flask, Blueprint
from werkzeug.serving import make_server
import threading
import time

from DracoSoft_Server.core.baseModule import BaseModule, ModuleInfo, ModuleState
from DracoSoft_Server.core.moduleEventSystem import Event, EventTypes, EventPriority


class FlaskAppManager:
    """Manages a single Flask application instance."""

    def __init__(self, name: str, port: int, logger: logging.Logger):
        self.name = name
        self.port = port
        self.logger = logger
        self.app = Flask(name)
        self.server = None
        self.thread = None
        self._is_running = False
        self.blueprints: Dict[str, Blueprint] = {}

    def add_blueprint(self, blueprint: Blueprint, url_prefix: str = None) -> None:
        """Register a blueprint with this Flask app."""
        self.blueprints[blueprint.name] = blueprint
        self.app.register_blueprint(blueprint, url_prefix=url_prefix)
        self.logger.info(f"Registered blueprint '{blueprint.name}' for app '{self.name}'")

    def remove_blueprint(self, blueprint_name: str) -> None:
        """Remove a blueprint from this Flask app."""
        if blueprint_name in self.blueprints:
            # Flask doesn't support unregistering blueprints, so we'll need to recreate the app
            self.app = Flask(self.name)
            for name, bp in self.blueprints.items():
                if name != blueprint_name:
                    self.app.register_blueprint(bp)
            del self.blueprints[blueprint_name]
            self.logger.info(f"Removed blueprint '{blueprint_name}' from app '{self.name}'")

    def start(self) -> bool:
        """Start the Flask application in a separate thread."""
        try:
            if self._is_running and self.thread and self.thread.is_alive():
                self.logger.debug(f"App '{self.name}' is already running")
                return True

            # Stop any existing server/thread
            self.stop()

            self.server = make_server('0.0.0.0', self.port, self.app)
            self.thread = threading.Thread(target=self.server.serve_forever)
            self.thread.daemon = True
            self.thread.start()

            # Give the server a moment to start
            time.sleep(0.5)

            if self.thread.is_alive():
                self._is_running = True
                self.logger.info(f"Started Flask app '{self.name}' on port {self.port}")
                return True
            else:
                self.logger.error(f"Failed to start Flask app '{self.name}' - thread died immediately")
                return False

        except Exception as e:
            self.logger.error(f"Error starting Flask app '{self.name}': {e}")
            self._is_running = False
            self.thread = None
            self.server = None
            return False

    def stop(self) -> None:
        """Stop the Flask application."""
        try:
            if self.server:
                self.server.shutdown()
            if self.thread and self.thread.is_alive():
                self.thread.join(timeout=5.0)  # Wait up to 5 seconds for the thread to finish
                if self.thread.is_alive():
                    self.logger.warning(f"Thread for app '{self.name}' didn't stop cleanly")
            self._is_running = False
            self.thread = None
            self.server = None
            self.logger.info(f"Stopped Flask app '{self.name}'")
        except Exception as e:
            self.logger.error(f"Error stopping Flask app '{self.name}': {e}")
            self._is_running = False
            self.thread = None
            self.server = None

    @property
    def is_running(self) -> bool:
        return self._is_running and self.thread and self.thread.is_alive()


class FlaskModule(BaseModule):
    """
    Enhanced Flask module that supports multiple Flask applications.
    Each application can have its own port, blueprints, and configuration.
    """

    def __init__(self, server):
        super().__init__(server)
        self.module_info = ModuleInfo(
            name="Flask",
            version="1.1.0",
            description="Multi-app Flask server manager",
            author="DracoSoft",
            dependencies=[]
        )

        self.apps: Dict[str, FlaskAppManager] = {}
        self.default_port = 5000
        self._health_check_task: Optional[asyncio.Task] = None

    async def load(self) -> bool:
        """Load the Flask module."""
        try:
            # Get configuration
            self.default_port = self.config.get('default_port', 5000)

            # Register event handlers
            self.register_event_handler(
                EventTypes.CLIENT_MESSAGE.value,
                self._handle_client_message,
                EventPriority.NORMAL
            )

            self.state = ModuleState.LOADED
            self.logger.info("Flask module loaded successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to load Flask module: {e}")
            self.state = ModuleState.ERROR
            return False

    def create_app(self, name: str, port: Optional[int] = None) -> FlaskAppManager:
        """Create a new Flask application instance."""
        if name in self.apps:
            raise ValueError(f"App '{name}' already exists")

        # Find available port if none specified
        if port is None:
            port = self._find_available_port()

        app_manager = FlaskAppManager(name, port, self.logger)
        self.apps[name] = app_manager
        self.logger.info(f"Created Flask app '{name}' on port {port}")
        return app_manager

    def _find_available_port(self) -> int:
        """Find an available port starting from default_port."""
        used_ports = {app.port for app in self.apps.values()}
        port = self.default_port
        while port in used_ports:
            port += 1
        return port

    def get_app(self, name: str) -> Optional[FlaskAppManager]:
        """Get a Flask application by name."""
        return self.apps.get(name)

    async def enable(self) -> bool:
        """Enable the Flask module and start all applications."""
        try:
            if not await self.validate_dependencies():
                return False

            # Create and start system app if configured
            if self.config.get('apps', {}).get('system', {}).get('enabled', True):
                system_app = self.create_app('system', self.config.get('apps', {}).get('system', {}).get('port', 5001))
                if not system_app.start():
                    self.logger.error("Failed to start system app")
                    return False

            # Start all registered apps
            for app_name, app in self.apps.items():
                self.logger.info(f"Starting Flask app '{app_name}'")
                if not app.start():
                    self.logger.error(f"Failed to start app '{app_name}'")
                    return False
                else:
                    self.logger.info(f"Successfully started app '{app_name}'")

            # Start health check task
            self._health_check_task = asyncio.create_task(self._health_check_loop())

            self.state = ModuleState.ENABLED
            self.logger.info("Flask module enabled")
            return True

        except Exception as e:
            self.logger.error(f"Failed to enable Flask module: {e}")
            return False

    async def disable(self) -> bool:
        """Disable the Flask module and stop all applications."""
        try:
            if self._health_check_task:
                self._health_check_task.cancel()

            for app in self.apps.values():
                app.stop()

            self.state = ModuleState.DISABLED
            self.logger.info("Flask module disabled")
            return True

        except Exception as e:
            self.logger.error(f"Failed to disable Flask module: {e}")
            return False

    async def unload(self) -> bool:
        """Unload the Flask module."""
        try:
            if self.is_enabled:
                await self.disable()

            self.apps.clear()
            self.state = ModuleState.UNLOADED
            self.logger.info("Flask module unloaded")
            return True

        except Exception as e:
            self.logger.error(f"Failed to unload Flask module: {e}")
            return False

    async def _health_check_loop(self) -> None:
        """Monitor the health of all Flask applications."""
        while True:
            try:
                await asyncio.sleep(30)  # Check every 30 seconds
                for app in self.apps.values():
                    if not app.is_running:
                        self.logger.warning(f"App '{app.name}' is not running, attempting restart")
                        app.start()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in health check: {e}")

    def get_status(self) -> Dict[str, Any]:
        """Get module status and information."""
        return {
            'name': self.module_info.name,
            'version': self.module_info.version,
            'state': self.state.value,
            'enabled': self.is_enabled,
            'loaded': self.is_loaded,
            'dependencies': self.module_info.dependencies,
            'description': self.module_info.description,
            'author': self.module_info.author,
            'apps': {
                name: {
                    'running': app.is_running,
                    'port': app.port,
                    'blueprints': list(app.blueprints.keys())
                }
                for name, app in self.apps.items()
            }
        }

    async def _handle_client_message(self, event: Event) -> None:
        """Handle client messages."""
        pass  # Implement if needed