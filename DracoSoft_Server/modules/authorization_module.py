# modules/authorization_module.py
import asyncio
import secrets
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from DracoSoft_Server.core.baseModule import BaseModule, ModuleInfo, ModuleState
from DracoSoft_Server.core.moduleEventSystem import Event, EventTypes, EventPriority


class AuthorizationModule(BaseModule):
    def __init__(self, server):
        super().__init__(server)
        self.module_info = ModuleInfo(
            name="Authorization",
            version="1.0.0",
            description="Handles user authentication and authorization",
            author="DracoSoft",
            dependencies=['sqlite_module', 'user_management_module', 'network_module']  # Updated dependency names
        )

        self.db_module = None
        self.user_module = None
        self.network_module = None
        self.active_sessions: Dict[str, Dict[str, Any]] = {}

    async def load(self) -> bool:
        """Load the Authorization module with proper event registration."""
        try:
            # Get required modules
            self.db_module = self.server.module_manager.modules.get('sqlite_module')
            self.user_module = self.server.module_manager.modules.get('user_management_module')
            self.network_module = self.server.module_manager.modules.get('network_module')

            if not all([self.db_module, self.user_module, self.network_module]):
                missing_modules = []
                if not self.db_module:
                    missing_modules.append('sqlite_module')
                if not self.user_module:
                    missing_modules.append('user_management_module')
                if not self.network_module:
                    missing_modules.append('network_module')
                raise RuntimeError(f"Required modules not found: {', '.join(missing_modules)}")

            # Register event handlers with high priority for auth messages
            self.server.event_manager.register_handler(
                EventTypes.CLIENT_MESSAGE.value,
                self._handle_client_message,
                self.module_info.name,
                EventPriority.HIGH
            )

            self.server.event_manager.register_handler(
                EventTypes.CLIENT_DISCONNECTED.value,
                self._handle_client_disconnected,
                self.module_info.name,
                EventPriority.NORMAL
            )

            self.state = ModuleState.LOADED
            self.logger.info("Authorization module loaded successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to load Authorization module: {e}")
            self.state = ModuleState.ERROR
            return False

    async def unload(self) -> bool:
        """Unload the Authorization module and cleanup resources."""
        try:
            if self.is_enabled:
                await self.disable()

            # Clean up any remaining sessions
            for client_id in list(self.active_sessions.keys()):
                await self._remove_session(client_id)

            self.state = ModuleState.UNLOADED
            self.logger.info("Authorization module unloaded")
            return True
        except Exception as e:
            self.logger.error(f"Failed to unload Authorization module: {e}")
            return False

    async def enable(self) -> bool:
        """Enable the Authorization module."""
        try:
            # Validate dependencies
            if not await self.validate_dependencies():
                return False

            # Start session cleanup task
            asyncio.create_task(self._cleanup_expired_sessions())

            self.state = ModuleState.ENABLED
            self.logger.info("Authorization module enabled")
            return True
        except Exception as e:
            self.logger.error(f"Failed to enable Authorization module: {e}")
            return False

    async def disable(self) -> bool:
        try:
            # Close all active sessions
            for client_id in list(self.active_sessions.keys()):
                await self._remove_session(client_id)

            self.state = ModuleState.DISABLED
            self.logger.info("Authorization module disabled")
            return True
        except Exception as e:
            self.logger.error(f"Failed to disable Authorization module: {e}")
            return False

    async def _handle_client_message(self, event: Event) -> None:
        """Handle incoming client messages with improved logging."""
        try:
            message = event.data.get('message', {})
            client_id = event.data.get('client_id')

            self.logger.debug(f"Authorization module received message: {message}")

            if message.get('type') == 'auth':
                self.logger.info(f"Processing auth request from client {client_id}")
                await self._handle_auth_request(client_id, message)
            elif not self._is_authenticated(client_id):
                self.logger.warning(f"Unauthenticated request from client {client_id}")
                await self._send_auth_response(client_id, False, "Authentication required")

        except Exception as e:
            self.logger.error(f"Error handling client message: {e}", exc_info=True)
            if client_id:
                await self._send_auth_response(client_id, False, "Internal server error")

    async def _handle_client_disconnected(self, event: Event) -> None:
        """Handle client disconnection."""
        client_id = event.data.get('client_id')
        if client_id in self.active_sessions:
            await self._remove_session(client_id)

    async def _handle_auth_request(self, client_id: str, message: Dict[str, Any]) -> None:
        """Handle authentication requests with improved logging and error handling."""
        try:
            action = message.get('action')
            username = message.get('username')
            password = message.get('password')

            self.logger.info(f"Processing {action} request for user: {username}")

            if not all([action, username, password]):
                self.logger.warning(f"Missing required fields in auth request from {client_id}")
                await self._send_auth_response(client_id, False, "Missing required fields")
                return

            if action == 'register':
                email = message.get('email')
                self.logger.info(f"Processing registration for user: {username}")

                # Check if user exists
                existing_user = await self.user_module.get_user(username)
                if existing_user:
                    self.logger.warning(f"Registration failed - username already exists: {username}")
                    await self._send_auth_response(client_id, False, "Username already exists")
                    return

                # Create new user
                user_id = await self.user_module.create_user(username, password, email)
                if not user_id:
                    self.logger.error(f"Failed to create user account for: {username}")
                    await self._send_auth_response(client_id, False, "Failed to create user account")
                    return

                # Create session
                session_token = await self._create_session(user_id)
                if not session_token:
                    self.logger.error(f"Failed to create session for user: {username}")
                    await self._send_auth_response(client_id, False, "Failed to create session")
                    return

                # Store session
                self.active_sessions[client_id] = {
                    'user_id': user_id,
                    'username': username,
                    'token': session_token,
                    'expires_at': datetime.now() + timedelta(hours=24)
                }

                self.logger.info(f"User registered successfully: {username}")
                await self._send_auth_response(client_id, True, "Registration successful", session_token)

            elif action == 'login':
                await self._handle_login(client_id, username, password)
            else:
                self.logger.warning(f"Invalid auth action received: {action}")
                await self._send_auth_response(client_id, False, "Invalid action")

        except Exception as e:
            self.logger.error(f"Error handling auth request: {e}", exc_info=True)
            await self._send_auth_response(client_id, False, "Internal server error")

    async def _handle_login(self, client_id: str, username: str, password: str) -> None:
        """Handle login requests."""
        user = await self.user_module.get_user(username)

        if not user:
            await self._send_auth_response(client_id, False, "Invalid username or password")
            return

        if not self.user_module._verify_password(password, user['password_hash']):
            await self._send_auth_response(client_id, False, "Invalid username or password")
            return

        if user['status'] != 'active':
            await self._send_auth_response(client_id, False, "Account is not active")
            return

        # Create session
        session_token = await self._create_session(user['id'])
        if not session_token:
            await self._send_auth_response(client_id, False, "Failed to create session")
            return

        # Update last login
        await self.user_module.update_last_login(user['id'])

        # Add to active sessions
        self.active_sessions[client_id] = {
            'user_id': user['id'],
            'username': username,
            'token': session_token,
            'expires_at': datetime.now() + timedelta(hours=24)
        }

        await self._send_auth_response(client_id, True, "Login successful", session_token)
        self.logger.info(f"User {username} logged in successfully")

    async def _handle_registration(self, client_id: str, username: str, password: str,
                                   email: Optional[str] = None) -> None:
        """Handle registration requests."""
        # Check if username exists
        existing_user = await self.user_module.get_user(username)
        if existing_user:
            await self._send_auth_response(client_id, False, "Username already exists")
            return

        # Create new user
        user_id = await self.user_module.create_user(username, password, email)
        if not user_id:
            await self._send_auth_response(client_id, False, "Failed to create user")
            return

        # Create session
        session_token = await self._create_session(user_id)
        if not session_token:
            await self._send_auth_response(client_id, False, "Failed to create session")
            return

        # Add to active sessions
        self.active_sessions[client_id] = {
            'user_id': user_id,
            'username': username,
            'token': session_token,
            'expires_at': datetime.now() + timedelta(hours=24)
        }

        await self._send_auth_response(client_id, True, "Registration successful", session_token)
        self.logger.info(f"New user registered: {username}")

    async def _create_session(self, user_id: int) -> Optional[str]:
        """Create a new session for a user."""
        try:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(hours=24)

            query = """
                INSERT INTO sessions (user_id, token, expires_at)
                VALUES (?, ?, ?)
            """

            await self.db_module.execute(query, (user_id, token, expires_at.isoformat()))
            return token

        except Exception as e:
            self.logger.error(f"Failed to create session: {e}")
            return None

    async def _remove_session(self, client_id: str) -> None:
        """Remove a client session."""
        try:
            if client_id in self.active_sessions:
                session = self.active_sessions[client_id]

                # Remove from database
                query = "DELETE FROM sessions WHERE token = ?"
                await self.db_module.execute(query, (session['token'],))

                # Remove from active sessions
                del self.active_sessions[client_id]

                self.logger.debug(f"Removed session for client {client_id}")

        except Exception as e:
            self.logger.error(f"Error removing session: {e}")

    async def _cleanup_expired_sessions(self) -> None:
        """Periodically clean up expired sessions."""
        while self.is_enabled:
            try:
                current_time = datetime.now()

                # Clean up memory sessions
                for client_id in list(self.active_sessions.keys()):
                    if current_time >= self.active_sessions[client_id]['expires_at']:
                        await self._remove_session(client_id)

                # Clean up database sessions
                query = "DELETE FROM sessions WHERE expires_at < ?"
                await self.db_module.execute(query, (current_time.isoformat(),))

            except Exception as e:
                self.logger.error(f"Error in session cleanup: {e}")

            await asyncio.sleep(300)  # Run every 5 minutes

    async def _send_auth_response(self, client_id: str, success: bool, message: str, token: str = None) -> None:
        """Send authentication response to client with better error handling."""
        try:
            response = {
                'type': 'auth_response',
                'success': success,
                'message': message,
                'timestamp': datetime.now().isoformat()
            }

            if token:
                response['token'] = token

            network_module = self.server.module_manager.modules.get('network_module')
            if network_module:
                await network_module.send_message(client_id, response)
            else:
                self.logger.error("Network module not available for sending response")

        except Exception as e:
            self.logger.error(f"Error sending auth response to {client_id}: {e}")

    def _is_authenticated(self, client_id: str) -> bool:
        """Check if a client is authenticated."""
        return client_id in self.active_sessions