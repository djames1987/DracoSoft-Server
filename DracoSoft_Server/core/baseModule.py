import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from .core_server import CoreServer
from .moduleEventSystem import EventPriority


class ModuleState(Enum):
    UNLOADED = "unloaded"
    LOADED = "loaded"
    ENABLED = "enabled"
    DISABLED = "disabled"
    ERROR = "error"


@dataclass
class ModuleInfo:
    name: str
    version: str
    description: str
    author: str
    dependencies: list[str]


class BaseModule(ABC):
    def __init__(self, server: 'CoreServer'):
        self.server = server
        self.logger = logging.getLogger(f"module.{self.__class__.__name__}")
        self.state = ModuleState.UNLOADED
        self.config: Dict[str, Any] = {}

        self.module_info = ModuleInfo(
            name=self.__class__.__name__,
            version="0.1.0",
            description="Base module implementation",
            author="Unknown",
            dependencies=[]
        )

    @abstractmethod
    async def load(self) -> bool:
        """
        Load the module and its resources.
        Returns True if loading was successful, False otherwise.
        """
        pass

    @abstractmethod
    async def unload(self) -> bool:
        """
        Unload the module and cleanup resources.
        Returns True if unloading was successful, False otherwise.
        """
        pass

    @abstractmethod
    async def enable(self) -> bool:
        """
        Enable the module functionality.
        Returns True if enabling was successful, False otherwise.
        """
        pass

    @abstractmethod
    async def disable(self) -> bool:
        """
        Disable the module functionality.
        Returns True if disabling was successful, False otherwise.
        """
        pass

    async def reload(self) -> bool:
        """Reload the module by unloading and loading it again."""
        if await self.unload():
            return await self.load()
        return False

    def configure(self, config: Dict[str, Any]) -> None:
        """Configure the module with the provided settings."""
        self.config = config
        self.logger.info(f"Module {self.module_info.name} configured with: {config}")

    @property
    def is_enabled(self) -> bool:
        """Check if the module is currently enabled."""
        return self.state == ModuleState.ENABLED

    @property
    def is_loaded(self) -> bool:
        """Check if the module is currently loaded."""
        return self.state in [ModuleState.LOADED, ModuleState.ENABLED]

    async def handle_server_event(self, event_type: str, data: Any) -> None:
        """
        Handle events from the server.
        Override this method to handle specific server events.
        """
        pass

    async def handle_client_message(self, client_id: str, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Handle messages from clients.
        Override this method to handle specific client messages.
        Returns a response message if needed.
        """
        return None

    def register_event_handler(self, event_type: str, handler, priority: EventPriority = EventPriority.NORMAL) -> None:
        """Register an event handler for specific event types."""
        if hasattr(self.server, 'event_handlers'):
            if event_type not in self.server.event_handlers:
                self.server.event_handlers[event_type] = set()
            self.server.event_handlers[event_type].add((handler, priority))
            self.logger.debug(f"Registered handler for event type: {event_type} with priority: {priority.name}")

    def unregister_event_handler(self, event_type: str, handler) -> None:
        """Unregister an event handler."""
        if hasattr(self.server, 'event_handlers'):
            if event_type in self.server.event_handlers:
                self.server.event_handlers[event_type].discard(handler)
                self.logger.debug(f"Unregistered handler for event type: {event_type}")

    async def validate_dependencies(self) -> bool:
        """
        Validate that all required dependencies are available and enabled.
        Returns True if all dependencies are satisfied.
        """
        try:
            for dependency in self.module_info.dependencies:
                if dependency not in self.server.module_manager.modules:
                    self.logger.error(f"Missing required dependency: {dependency}")
                    return False

                dep_module = self.server.module_manager.modules[dependency]
                if not dep_module.is_enabled:
                    self.logger.error(f"Required dependency not enabled: {dependency}")
                    return False

                self.logger.debug(f"Validated dependency: {dependency}")

            self.logger.info("All dependencies validated successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error validating dependencies: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the module."""
        return {
            "name": self.module_info.name,
            "version": self.module_info.version,
            "state": self.state.value,
            "enabled": self.is_enabled,
            "loaded": self.is_loaded,
            "dependencies": self.module_info.dependencies,
            "description": self.module_info.description,
            "author": self.module_info.author
        }

    def __str__(self) -> str:
        """String representation of the module."""
        return f"{self.module_info.name} v{self.module_info.version} ({self.state.value})"
