import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class EventPriority(Enum):
    """Priority levels for event handlers."""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Event:
    """Base class for all events."""
    event_type: str
    source: str  # Source module name
    timestamp: datetime = field(default_factory=datetime.now)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    data: Dict[str, Any] = field(default_factory=dict)
    propagating: bool = True  # Whether the event should continue propagating

    def stop_propagation(self):
        """Stop the event from being handled by other handlers."""
        self.propagating = False


@dataclass
class EventHandler:
    """Represents an event handler with its callback and metadata."""
    callback: Callable
    priority: EventPriority
    module_name: str
    filter_condition: Optional[Callable[[Event], bool]] = None


class EventManager:
    """
    Manages event registration, dispatch, and handling for inter-module communication.
    """

    def __init__(self):
        self.handlers: Dict[str, List[EventHandler]] = {}
        self.logger = logging.getLogger(__name__)
        self._event_queue: asyncio.Queue[Event] = asyncio.Queue()
        self.running: bool = False
        self._processor_task: Optional[asyncio.Task] = None
        self._history: List[Event] = []
        self._history_limit = 1000  # Keep last 1000 events

    def register_handler(self,
                         event_type: str,
                         callback: Callable,
                         module_name: str,
                         priority: EventPriority = EventPriority.NORMAL,
                         filter_condition: Optional[Callable[[Event], bool]] = None) -> None:
        """Register an event handler."""
        if event_type not in self.handlers:
            self.handlers[event_type] = []

        handler = EventHandler(callback, priority, module_name, filter_condition)
        self.handlers[event_type].append(handler)

        # Sort handlers by priority (highest first)
        self.handlers[event_type].sort(key=lambda h: h.priority.value, reverse=True)

        self.logger.debug(
            f"Registered handler for {event_type} from {module_name} "
            f"with priority {priority.name}"
        )

    def unregister_handler(self, event_type: str, module_name: str) -> None:
        """Unregister all handlers for a module for a specific event type."""
        if event_type in self.handlers:
            self.handlers[event_type] = [
                h for h in self.handlers[event_type]
                if h.module_name != module_name
            ]
            self.logger.debug(
                f"Unregistered handlers for {event_type} from {module_name}"
            )

    def unregister_all_handlers(self, module_name: str) -> None:
        """Unregister all handlers for a module."""
        for event_type in self.handlers:
            self.unregister_handler(event_type, module_name)

    async def emit(self, event: Event) -> None:
        """Emit an event for processing."""
        await self._event_queue.put(event)
        self.logger.debug(
            f"Event {event.event_type} queued from {event.source}"
        )

    async def emit_and_wait(self, event: Event, timeout: Optional[float] = None) -> bool:
        """
        Emit an event and wait for it to be processed.
        Returns True if processed within timeout, False otherwise.
        """
        processed = asyncio.Event()
        event.data['_completion_event'] = processed

        await self._event_queue.put(event)

        try:
            await asyncio.wait_for(processed.wait(), timeout)
            return True
        except asyncio.TimeoutError:
            return False

    async def _process_event(self, event: Event) -> None:
        """Process a single event by calling all relevant handlers."""
        if event.event_type not in self.handlers:
            return

        for handler in self.handlers[event.event_type]:
            if not event.propagating:
                break

            # Check filter condition if present
            if handler.filter_condition and not handler.filter_condition(event):
                continue

            try:
                if asyncio.iscoroutinefunction(handler.callback):
                    await handler.callback(event)
                else:
                    handler.callback(event)
            except Exception as e:
                self.logger.error(
                    f"Error in handler {handler.module_name} "
                    f"for event {event.event_type}: {e}"
                )

        # Add to history
        self._history.append(event)
        if len(self._history) > self._history_limit:
            self._history.pop(0)

        # Signal completion if this is a waited event
        completion_event = event.data.get('_completion_event')
        if completion_event:
            completion_event.set()

    async def _event_processor(self) -> None:
        """Main event processing loop."""
        self.logger.info("Event processor started")

        while self.running:
            try:
                event = await self._event_queue.get()
                await self._process_event(event)
                self._event_queue.task_done()
            except Exception as e:
                self.logger.error(f"Error processing event: {e}")

    async def start(self) -> None:
        """Start the event processing system."""
        if self.running:
            return

        self.running = True
        self._processor_task = asyncio.create_task(self._event_processor())
        self.logger.info("Event system started")

    async def stop(self) -> None:
        """Stop the event processing system."""
        if not self.running:
            return

        self.running = False

        # Process remaining events
        while not self._event_queue.empty():
            event = await self._event_queue.get()
            await self._process_event(event)
            self._event_queue.task_done()

        if self._processor_task:
            self._processor_task.cancel()
            try:
                await self._processor_task
            except asyncio.CancelledError:
                pass

        self.logger.info("Event system stopped")

    def get_event_history(self,
                          event_type: Optional[str] = None,
                          source: Optional[str] = None,
                          limit: int = 100) -> List[Event]:
        """Get event history with optional filtering."""
        filtered_history = self._history

        if event_type:
            filtered_history = [
                e for e in filtered_history
                if e.event_type == event_type
            ]

        if source:
            filtered_history = [
                e for e in filtered_history
                if e.source == source
            ]

        return filtered_history[-limit:]


class EventTypes(Enum):
    """Common event types used in the game server."""
    # Server events
    SERVER_STARTED = "server:started"
    SERVER_STOPPED = "server:stopped"

    # Client events
    CLIENT_CONNECTED = "client:connected"
    CLIENT_DISCONNECTED = "client:disconnected"
    CLIENT_MESSAGE = "client:message"

    # Room events
    ROOM_CREATED = "room:created"
    ROOM_DELETED = "room:deleted"
    ROOM_JOINED = "room:joined"
    ROOM_LEFT = "room:left"

    # Game events
    GAME_STARTED = "game:started"
    GAME_ENDED = "game:ended"
    GAME_STATE_UPDATED = "game:state_updated"

    # Module events
    MODULE_LOADED = "module:loaded"
    MODULE_UNLOADED = "module:unloaded"
    MODULE_ENABLED = "module:enabled"
    MODULE_DISABLED = "module:disabled"


# Example usage and helper functions
async def example_usage():
    # Create event manager
    event_manager = EventManager()

    # Example module registration
    async def handle_client_connected(event: Event):
        print(f"Client connected: {event.data.get('client_id')}")

    event_manager.register_handler(
        EventTypes.CLIENT_CONNECTED.value,
        handle_client_connected,
        "example_module",
        EventPriority.HIGH
    )

    # Start event system
    await event_manager.start()

    # Emit example event
    client_connected_event = Event(
        EventTypes.CLIENT_CONNECTED.value,
        "connection_manager",
        data={"client_id": "123"}
    )

    await event_manager.emit(client_connected_event)

    # Stop event system
    await event_manager.stop()


if __name__ == "__main__":
    asyncio.run(example_usage())