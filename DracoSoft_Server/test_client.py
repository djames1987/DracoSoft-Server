import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class NetworkClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 8889):
        self.host = host
        self.port = port
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self.session_token: Optional[str] = None
        self._connected = False
        self.logger = logging.getLogger(self.__class__.__name__)
        self._MAX_MESSAGE_SIZE = 1048576  # 1MB

    async def connect(self) -> bool:
        """Connect to the server with improved error handling."""
        try:
            self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
            self._connected = True
            self.logger.info(f"Connected to server at {self.host}:{self.port}")

            # Clear any initial connection data
            try:
                self.writer.set_write_buffer_limits(high=self._MAX_MESSAGE_SIZE)
                await self.writer.drain()
            except Exception as e:
                self.logger.debug(f"Error clearing initial connection state: {e}")

            return True

        except ConnectionRefusedError:
            self.logger.error("Connection refused by server")
            self._connected = False
            return False
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            self._connected = False
            return False

    async def disconnect(self):
        """Disconnect from the server."""
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
                self._connected = False
                self.logger.info("Disconnected from server")
            except Exception as e:
                self.logger.error(f"Error during disconnect: {e}")

    async def send_message(self, message: Dict[str, Any]) -> bool:
        """Send a message with improved error handling and validation."""
        if not self._connected:
            self.logger.error("Not connected to server")
            return False

        try:
            # Add timestamp and token
            if 'timestamp' not in message:
                message['timestamp'] = datetime.now().isoformat()
            if self.session_token and message.get('type') != 'auth':
                message['token'] = self.session_token

            # Serialize and validate message size
            message_data = json.dumps(message).encode('utf-8')
            if len(message_data) > self._MAX_MESSAGE_SIZE:
                self.logger.error("Message too large")
                return False

            # Send message length and data
            self.writer.write(len(message_data).to_bytes(4, 'big'))
            self.writer.write(message_data)
            await self.writer.drain()
            return True

        except ConnectionError:
            self.logger.error("Connection lost while sending message")
            self._connected = False
            return False
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")
            return False

    async def receive_message(self, timeout: float = 5.0) -> Optional[Dict[str, Any]]:
        """Receive a message with improved timeout handling."""
        if not self._connected:
            print("Not connected to server")
            return None

        try:
            # Read message length with timeout
            length_bytes = await asyncio.wait_for(
                self.reader.readexactly(4),
                timeout=timeout
            )
            message_length = int.from_bytes(length_bytes, 'big')

            if message_length <= 0 or message_length > 1048576:  # Max 1MB
                print(f"Invalid message length: {message_length}")
                return None

            # Read message data with timeout
            message_data = await asyncio.wait_for(
                self.reader.readexactly(message_length),
                timeout=timeout
            )

            try:
                response = json.loads(message_data.decode('utf-8'))
                return response
            except json.JSONDecodeError:
                print("Received invalid JSON from server")
                return None

        except asyncio.TimeoutError:
            print(f"Server did not respond within {timeout} seconds")
            return None
        except ConnectionError:
            print("Connection lost while waiting for response")
            self._connected = False
            return None
        except Exception as e:
            print(f"Error receiving message: {e}")
            return None

    @property
    def is_connected(self) -> bool:
        """Check if client is currently connected."""
        return self._connected

    def handle_auth_response(self, response: Dict[str, Any]) -> bool:
        """Handle authentication response from server."""
        if response and response.get('success'):
            self.session_token = response.get('token')
            return True
        return False

class InteractiveClient(NetworkClient):
    def __init__(self, host: str = "127.0.0.1", port: int = 8889):
        super().__init__(host, port)
        self.running = True

    async def register_user(self):
        """Interactive user registration with better error handling."""
        try:
            print("\n=== User Registration ===")
            username = input("Enter username: ")
            password = input("Enter password: ")
            email = input("Enter email: ")

            message = {
                "type": "auth",
                "action": "register",
                "username": username,
                "password": password,
                "email": email
            }

            if await self.send_message(message):
                response = await self.receive_message(timeout=10.0)  # Increased timeout
                if response is None:
                    print("No response received from server - registration status unknown")
                    return False

                if response.get('success'):
                    self.session_token = response.get('token')
                    print(f"Successfully registered user: {username}")
                    print(f"Session token: {self.session_token}")
                    return True
                else:
                    print(f"Registration failed: {response.get('message', 'Unknown error')}")
                    return False
            else:
                print("Failed to send registration request")
                return False

        except Exception as e:
            print(f"Error during registration: {e}")
            return False

    async def login(self):
        """Interactive user login."""
        print("\n=== User Login ===")
        username = input("Enter username: ")
        password = input("Enter password: ")

        message = {
            "type": "auth",
            "action": "login",
            "username": username,
            "password": password
        }

        if await self.send_message(message):
            response = await self.receive_message()
            if self.handle_auth_response(response):
                print(f"Successfully logged in as: {username}")
            else:
                print(f"Failed to login: {response.get('message', 'Unknown error')}")
        else:
            print("Failed to send login request")

    async def chat(self):
        """Send a chat message."""
        if not self.session_token:
            print("You must be logged in to send chat messages")
            return

        print("\n=== Send Chat Message ===")
        message = input("Enter your message: ")

        if await self.send_message({
            "type": "chat",
            "content": message
        }):
            print("Message sent")
        else:
            print("Failed to send message")

    async def ping(self):
        """Send a ping message."""
        if await self.send_message({"type": "ping"}):
            response = await self.receive_message()
            if response and response.get('type') == 'pong':
                print("Received pong response")
            else:
                print("No valid pong response received")
        else:
            print("Failed to send ping")

    async def show_menu(self):
        """Display interactive menu."""
        while self.running and self.is_connected:
            print("\n=== Test Client Menu ===")
            print("1. Register new user")
            print("2. Login")
            print("3. Send chat message")
            print("4. Send ping")
            print("5. Quit")

            try:
                choice = input("\nEnter your choice (1-5): ")

                if choice == "1":
                    await self.register_user()
                elif choice == "2":
                    await self.login()
                elif choice == "3":
                    await self.chat()
                elif choice == "4":
                    await self.ping()
                elif choice == "5":
                    self.running = False
                else:
                    print("Invalid choice. Please try again.")
            except Exception as e:
                print(f"Error processing command: {e}")


async def main():
    client = InteractiveClient()

    try:
        if await client.connect():
            await client.show_menu()
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())