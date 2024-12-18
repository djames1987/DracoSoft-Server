import asyncio
import logging
import uuid
from abc import ABC
from typing import Dict, Optional


class CoreServer(ABC):
    """
    Abstract base class for the modular game server.
    Provides core functionality and defines the interface for game-specific implementations.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 8888):
        self.host = host
        self.port = port
        self.clients: Dict[str, asyncio.StreamWriter] = {}
        self.modules: Dict[str, object] = {}
        self.running: bool = False

        # Set up logging
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.INFO)

    async def start(self):
        """Start the game server."""
        self.running = True
        server = await asyncio.start_server(
            self.handle_client_connection, self.host, self.port
        )
        self.logger.info(f"Server started on {self.host}:{self.port}")

        async with server:
            await server.serve_forever()

    async def handle_client_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle new client connections."""
        client_id = str(uuid.uuid4())
        self.clients[client_id] = writer

        self.logger.info(f"New client connected: {client_id}")

        try:
            while self.running:
                data = await reader.read(8192)
                if not data:
                    break

                await self.handle_message(client_id, data)
        except Exception as e:
            self.logger.error(f"Error handling client {client_id}: {e}")
        finally:
            await self.disconnect_client(client_id)

    async def disconnect_client(self, client_id: str):
        """Handle client disconnection."""
        if client_id in self.clients:
            writer = self.clients[client_id]
            try:
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                self.logger.error(f"Error closing connection for client {client_id}: {e}")

            del self.clients[client_id]
            self.logger.info(f"Client disconnected: {client_id}")

    #@abstractmethod
    async def handle_message(self, client_id: str, data: bytes):
        """
        Abstract method to handle incoming messages.
        Must be implemented by specific game servers.
        """
        pass

    async def broadcast(self, message: bytes, exclude: Optional[str] = None):
        """Broadcast a message to all connected clients."""
        for client_id, writer in self.clients.items():
            if client_id != exclude:
                try:
                    writer.write(message)
                    await writer.drain()
                except Exception as e:
                    self.logger.error(f"Error broadcasting to client {client_id}: {e}")

    def register_module(self, module_name: str, module_instance: object):
        """Register a new module with the server."""
        self.modules[module_name] = module_instance
        self.logger.info(f"Registered module: {module_name}")

    def unregister_module(self, module_name: str):
        """Unregister a module from the server."""
        if module_name in self.modules:
            del self.modules[module_name]
            self.logger.info(f"Unregistered module: {module_name}")