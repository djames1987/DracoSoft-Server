import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Any

from DracoSoft_Server.core.baseModule import BaseModule, ModuleInfo, ModuleState
from DracoSoft_Server.core.moduleEventSystem import Event, EventTypes, EventPriority


@dataclass
class ClientSession:
    """Represents a connected client's session."""
    client_id: str
    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    address: str
    connected_at: float
    last_activity: float
    authenticated: bool = False
    attributes: Dict[str, Any] = None

    def __post_init__(self):
        if self.attributes is None:
            self.attributes = {}


class NetworkModule(BaseModule):
    """
    Handles all network-related operations including client connections,
    message processing, and network-level protocol handling.
    """

    def __init__(self, server):
        super().__init__(server)
        self.module_info = ModuleInfo(
            name="Network",
            version="1.0.0",
            description="Handles network communication and client connections",
            author="DracoSoft",
            dependencies=[]
        )

        self.clients: Dict[str, ClientSession] = {}
        self._server: Optional[asyncio.Server] = None
        self._client_handlers: Dict[str, asyncio.Task] = {}
        self._MAX_MESSAGE_SIZE = 1048576  # 1MB
        self._cleanup_task: Optional[asyncio.Task] = None

    async def load(self) -> bool:
        """Load the network module."""
        try:
            # Register event handlers
            self.server.event_manager.register_handler(
                EventTypes.CLIENT_CONNECTED.value,
                self._handle_client_connected,
                EventPriority.HIGH
            )
            self.server.event_manager.register_handler(
                EventTypes.CLIENT_DISCONNECTED.value,
                self._handle_client_disconnected,
                EventPriority.HIGH
            )
            self.server.event_manager.register_handler(
                EventTypes.CLIENT_MESSAGE.value,
                self._handle_client_message,
                EventPriority.NORMAL
            )

            self.state = ModuleState.LOADED
            self.logger.info("Network module loaded successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to load network module: {e}")
            self.state = ModuleState.ERROR
            return False

    async def unload(self) -> bool:
        """Unload the network module and cleanup resources."""
        try:
            if self.is_enabled:
                await self.disable()

            # Unregister event handlers
            self.server.event_manager.unregister_all_handlers(self.module_info.name)

            self.state = ModuleState.UNLOADED
            self.logger.info("Network module unloaded")
            return True

        except Exception as e:
            self.logger.error(f"Failed to unload network module: {e}")
            return False

    async def enable(self) -> bool:
        """Enable the network module and start listening for connections."""
        try:
            # Get network configuration
            host = self.config.get('host', '0.0.0.0')
            port = self.config.get('port', 8889)

            # Start server
            self._server = await asyncio.start_server(
                self._handle_client_connection,
                host,
                port
            )

            # Start the server in the background
            asyncio.create_task(self._server.serve_forever())

            # Start cleanup task
            self._cleanup_task = asyncio.create_task(self._cleanup_inactive_clients())

            self.state = ModuleState.ENABLED
            self.logger.info(f"Network module enabled and listening on {host}:{port}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to enable network module: {e}")
            self.state = ModuleState.ERROR
            return False

    async def disable(self) -> bool:
        """Disable the network module and close all connections."""
        try:
            # Stop cleanup task
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass

            # Close server
            if self._server:
                self._server.close()
                await self._server.wait_closed()
                self._server = None

            # Disconnect all clients
            for client_id in list(self.clients.keys()):
                await self._disconnect_client(client_id)

            self.state = ModuleState.DISABLED
            self.logger.info("Network module disabled")
            return True

        except Exception as e:
            self.logger.error(f"Failed to disable network module: {e}")
            return False

    async def _handle_client_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle new client connections."""
        client_addr = writer.get_extra_info('peername')
        client_id = f"{client_addr[0]}:{client_addr[1]}"

        try:
            # Create client session
            session = ClientSession(
                client_id=client_id,
                reader=reader,
                writer=writer,
                address=f"{client_addr[0]}:{client_addr[1]}",
                connected_at=asyncio.get_event_loop().time(),
                last_activity=asyncio.get_event_loop().time()
            )

            self.clients[client_id] = session

            # Emit client connected event
            await self.server.event_manager.emit(Event(
                event_type=EventTypes.CLIENT_CONNECTED.value,
                source=self.module_info.name,
                data={'client_id': client_id, 'address': session.address}
            ))

            # Start message handler for this client
            self._client_handlers[client_id] = asyncio.create_task(
                self._handle_client_messages(client_id)
            )

            self.logger.info(f"Client connected: {client_id}")

        except Exception as e:
            self.logger.error(f"Error handling client connection: {e}")
            writer.close()
            try:
                await writer.wait_closed()
            except:
                pass

    async def _handle_client_messages(self, client_id: str):
        """Handle messages from a connected client."""
        session = self.clients.get(client_id)
        if not session:
            return

        while True:
            try:
                # Read message length (4 bytes)
                length_bytes = await session.reader.readexactly(4)
                message_length = int.from_bytes(length_bytes, 'big')

                if message_length <= 0 or message_length > self._MAX_MESSAGE_SIZE:
                    self.logger.warning(f"Invalid message length from {client_id}: {message_length}")
                    continue

                # Read message data
                message_data = await session.reader.readexactly(message_length)
                session.last_activity = asyncio.get_event_loop().time()

                try:
                    message = json.loads(message_data.decode('utf-8'))

                    # Handle special messages
                    msg_type = message.get('type', '')

                    if msg_type == 'ping':
                        await self.send_message(client_id, {
                            'type': 'pong',
                            'timestamp': datetime.now().isoformat()
                        })
                        continue

                    # Emit message event for other modules to handle
                    await self.server.event_manager.emit(Event(
                        event_type=EventTypes.CLIENT_MESSAGE.value,
                        source=self.module_info.name,
                        data={
                            'client_id': client_id,
                            'message': message,
                            'authenticated': session.authenticated
                        }
                    ))

                except json.JSONDecodeError:
                    if len(message_data.strip()) > 2:
                        self.logger.warning(f"Invalid JSON from {client_id}")

            except asyncio.IncompleteReadError:
                break
            except ConnectionError:
                break
            except Exception as e:
                self.logger.error(f"Error handling messages from {client_id}: {e}")
                break

        # Clean up when loop exits
        await self._disconnect_client(client_id)

    async def send_message(self, client_id: str, message: dict) -> bool:
        """Send a message to a specific client."""
        session = self.clients.get(client_id)
        if not session:
            return False

        try:
            # Ensure message has a timestamp
            if 'timestamp' not in message:
                message['timestamp'] = datetime.now().isoformat()

            # Serialize message
            message_data = json.dumps(message).encode('utf-8')
            message_length = len(message_data)

            if message_length > self._MAX_MESSAGE_SIZE:
                self.logger.error(f"Message too large for {client_id}: {message_length} bytes")
                return False

            # Send length prefix and message
            session.writer.write(message_length.to_bytes(4, 'big'))
            session.writer.write(message_data)
            await session.writer.drain()
            return True

        except Exception as e:
            self.logger.error(f"Error sending message to {client_id}: {e}")
            await self._disconnect_client(client_id)
            return False

    async def broadcast_message(self, message: dict, exclude_client: Optional[str] = None):
        """Broadcast a message to all connected clients."""
        for client_id in list(self.clients.keys()):
            if client_id != exclude_client:
                await self.send_message(client_id, message)

    async def _disconnect_client(self, client_id: str):
        """Disconnect a client and cleanup their session."""
        session = self.clients.get(client_id)
        if not session:
            return

        try:
            # Cancel message handler task
            if client_id in self._client_handlers:
                self._client_handlers[client_id].cancel()
                del self._client_handlers[client_id]

            # Close connection
            session.writer.close()
            try:
                await session.writer.wait_closed()
            except:
                pass

            # Remove session
            del self.clients[client_id]

            # Emit disconnected event
            await self.server.event_manager.emit(Event(
                event_type=EventTypes.CLIENT_DISCONNECTED.value,
                source=self.module_info.name,
                data={'client_id': client_id, 'address': session.address}
            ))

            self.logger.info(f"Client disconnected: {client_id}")

        except Exception as e:
            self.logger.error(f"Error disconnecting client {client_id}: {e}")

    async def _cleanup_inactive_clients(self):
        """Periodically clean up inactive client connections."""
        while self.is_enabled:
            try:
                current_time = asyncio.get_event_loop().time()
                timeout = self.config.get('client_timeout', 300)  # 5 minutes default

                for client_id, session in list(self.clients.items()):
                    if current_time - session.last_activity > timeout:
                        self.logger.info(f"Disconnecting inactive client: {client_id}")
                        await self._disconnect_client(client_id)

            except Exception as e:
                self.logger.error(f"Error in cleanup task: {e}")

            await asyncio.sleep(60)  # Run cleanup every minute

    async def _handle_client_connected(self, event: Event):
        """Handle client connected event."""
        client_id = event.data.get('client_id')
        if client_id in self.clients:
            self.logger.info(f"Client {client_id} connected and registered")

    async def _handle_client_disconnected(self, event: Event):
        """Handle client disconnected event."""
        client_id = event.data.get('client_id')
        if client_id in self.clients:
            await self._disconnect_client(client_id)

    async def _handle_client_message(self, event: Event):
        """Handle processed client messages."""
        # This method can be used to handle any network-specific message processing
        # For example, implementing rate limiting or message validation
        pass

    def set_client_authenticated(self, client_id: str, authenticated: bool = True):
        """Set the authentication status of a client."""
        if client_id in self.clients:
            self.clients[client_id].authenticated = authenticated

    def is_client_authenticated(self, client_id: str) -> bool:
        """Check if a client is authenticated."""
        return self.clients.get(client_id, ClientSession(
            client_id="", reader=None, writer=None, address="",
            connected_at=0, last_activity=0
        )).authenticated

    def get_client_count(self) -> int:
        """Get the number of connected clients."""
        return len(self.clients)

    def get_client_info(self, client_id: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific client."""
        session = self.clients.get(client_id)
        if not session:
            return None

        return {
            'client_id': session.client_id,
            'address': session.address,
            'connected_at': session.connected_at,
            'last_activity': session.last_activity,
            'authenticated': session.authenticated,
            'attributes': session.attributes
        }