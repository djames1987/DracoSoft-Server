from typing import Dict, Any, Optional
import asyncio
import json
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from DracoSoft_Server.core.baseModule import BaseModule, ModuleInfo, ModuleState
from DracoSoft_Server.core.moduleEventSystem import Event, EventTypes, EventPriority


@dataclass
class GameWorld:
    """Represents the game world state"""
    servers: Dict[str, Any]  # Server states
    players: Dict[str, Any]  # Player states
    active_sessions: Dict[str, Any]  # Active game sessions


class GameServerModule(BaseModule):
    def __init__(self, server):
        super().__init__(server)
        self.module_info = ModuleInfo(
            name="GameServer",
            version="1.0.0",
            description="Handles game world state and player interactions",
            author="Your Name",
            dependencies=['network_module', 'user_management_module',
                          'authorization_module', 'flask_module']
        )

        # Core components
        self.network_module = None
        self.user_module = None
        self.auth_module = None
        self.flask_module = None
        self.app_manager = None  # Flask app manager instance

        # Game state
        self.world = GameWorld(
            servers={},
            players={},
            active_sessions={}
        )

        self._cleanup_task = None
        self.game_loop_task = None

    async def load(self) -> bool:
        """Load the game server module."""
        try:
            # Get required modules
            self.network_module = self.server.module_manager.modules.get('network_module')
            self.user_module = self.server.module_manager.modules.get('user_management_module')
            self.auth_module = self.server.module_manager.modules.get('authorization_module')
            self.flask_module = self.server.module_manager.modules.get('flask_module')

            if not all([self.network_module, self.user_module, self.auth_module, self.flask_module]):
                raise RuntimeError("Missing required modules")

            # Register event handlers
            self.server.event_manager.register_handler(
                EventTypes.CLIENT_MESSAGE.value,
                self._handle_client_message,
                EventPriority.NORMAL
            )

            self.server.event_manager.register_handler(
                EventTypes.CLIENT_DISCONNECTED.value,
                self._handle_client_disconnected,
                EventPriority.NORMAL
            )

            # Initialize game state
            await self._initialize_game_state()

            # Create Flask routes
            self._setup_api_routes()

            self.state = ModuleState.LOADED
            self.logger.info("Game server module loaded successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to load game server module: {e}")
            self.state = ModuleState.ERROR
            return False

    def _setup_api_routes(self):
        """Set up Flask API routes for the game server."""
        try:
            # Create a new Flask app through the Flask module
            port = self.config.get('network', {}).get('api_port', 5001)
            self.app_manager = self.flask_module.create_app('game_server', port)
            if not self.app_manager:
                raise RuntimeError("Failed to create Flask app")

            app = self.app_manager.app

            # Set up routes
            @app.route('/api/game/status', methods=['GET'])
            async def get_game_status():
                return {
                    'active_players': len(self.world.players),
                    'active_servers': len(self.world.servers),
                    'active_sessions': len(self.world.active_sessions)
                }

            @app.route('/api/game/servers', methods=['GET'])
            async def get_game_servers():
                return {'servers': list(self.world.servers.values())}

            @app.route('/api/game/players', methods=['GET'])
            async def get_players():
                return {'players': list(self.world.players.values())}

            @app.route('/api/game/server/<server_id>', methods=['GET'])
            async def get_server_info(server_id):
                if server_id not in self.world.servers:
                    return {'error': 'Server not found'}, 404
                return {'server': self.world.servers[server_id]}

            @app.route('/api/game/player/<player_id>/servers', methods=['GET'])
            async def get_player_servers(player_id):
                player_servers = {
                    server_id: server for server_id, server in self.world.servers.items()
                    if server.get('owner_id') == player_id
                }
                return {'servers': list(player_servers.values())}

            # Start the Flask app
            if not self.app_manager.start():
                raise RuntimeError("Failed to start Flask app")

            self.logger.info(f"Game server API started on port {port}")

        except Exception as e:
            self.logger.error(f"Error setting up API routes: {e}")
            raise

    async def _handle_client_disconnected(self, event: Event) -> None:
        """Handle client disconnection."""
        client_id = event.data.get('client_id')
        if client_id in self.world.active_sessions:
            await self._handle_game_disconnect(client_id, {})

    async def _initialize_game_state(self):
        """Initialize or load saved game state."""
        try:
            # Load saved server states
            server_states = await self._load_server_states()
            self.world.servers.update(server_states)

            # Load active player states
            player_states = await self._load_player_states()
            self.world.players.update(player_states)

            self.logger.info("Game state initialized")

        except Exception as e:
            self.logger.error(f"Error initializing game state: {e}")
            raise

    async def _handle_client_message(self, event: Event) -> None:
        """Handle incoming client messages."""
        try:
            message = event.data.get('message', {})
            client_id = event.data.get('client_id')

            if not message.get('type', '').startswith('game:'):
                return

            # Verify authentication
            if not await self._verify_client_auth(client_id, message):
                await self._send_auth_required(client_id)
                return

            # Handle different game message types
            handlers = {
                'game:connect': self._handle_game_connect,
                'game:disconnect': self._handle_game_disconnect,
                'game:server_action': self._handle_server_action,
                'game:player_action': self._handle_player_action
            }

            handler = handlers.get(message['type'])
            if handler:
                await handler(client_id, message)
            else:
                self.logger.warning(f"Unknown game message type: {message['type']}")

        except Exception as e:
            self.logger.error(f"Error handling client message: {e}")

    async def enable(self) -> bool:
        """Enable the game server module."""
        try:
            if not await self.validate_dependencies():
                return False

            # Start game loop
            self.game_loop_task = asyncio.create_task(self._game_loop())

            # Start cleanup task
            self._cleanup_task = asyncio.create_task(self._cleanup_inactive_sessions())

            self.state = ModuleState.ENABLED
            self.logger.info("Game server module enabled")
            return True

        except Exception as e:
            self.logger.error(f"Failed to enable game server module: {e}")
            return False

    async def disable(self) -> bool:
        """Disable the game server module."""
        try:
            # Stop game loop
            if self.game_loop_task:
                self.game_loop_task.cancel()
                try:
                    await self.game_loop_task
                except asyncio.CancelledError:
                    pass

            # Stop cleanup task
            if self._cleanup_task:
                self._cleanup_task.cancel()
                try:
                    await self._cleanup_task
                except asyncio.CancelledError:
                    pass

            # Save game state
            await self._save_game_state()

            # Disconnect all players
            for client_id in list(self.world.active_sessions.keys()):
                await self._handle_game_disconnect(client_id, {})

            # Stop Flask app
            if self.app_manager:
                self.app_manager.stop()
                self.app_manager = None

            self.state = ModuleState.DISABLED
            self.logger.info("Game server module disabled")
            return True

        except Exception as e:
            self.logger.error(f"Failed to disable game server module: {e}")
            return False

    async def _game_loop(self):
        """Main game loop for updating game state."""
        try:
            while self.is_enabled:
                await self._update_game_state()
                await asyncio.sleep(1 / 60)  # 60 FPS game loop
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.logger.error(f"Error in game loop: {e}")

    async def _update_game_state(self):
        """Update game state."""
        try:
            # Update server states
            for server_id, server in self.world.servers.items():
                # Update server resources
                await self._update_server_resources(server_id)

            # Update player states
            for session in self.world.active_sessions.values():
                if session.get('current_server'):
                    await self._update_player_state(session)

            # Broadcast updates to connected clients
            await self._broadcast_state_updates()

        except Exception as e:
            self.logger.error(f"Error updating game state: {e}")

    async def _cleanup_inactive_sessions(self):
        """Clean up inactive game sessions."""
        while self.is_enabled:
            try:
                now = datetime.now()
                timeout = self.config.get('session_timeout', 300)  # 5 minutes default

                for client_id, session in list(self.world.active_sessions.items()):
                    last_activity = datetime.fromisoformat(session['last_activity'])
                    if (now - last_activity).total_seconds() > timeout:
                        await self._handle_game_disconnect(client_id, {})

            except Exception as e:
                self.logger.error(f"Error in cleanup task: {e}")

            await asyncio.sleep(60)  # Run cleanup every minute

    async def _verify_client_auth(self, client_id: str, message: Dict[str, Any]) -> bool:
        """Verify client authentication."""
        try:
            token = message.get('token')
            if not token:
                return False
            return bool(self.auth_module.validate_session(token))
        except Exception as e:
            self.logger.error(f"Error verifying client auth: {e}")
            return False

    async def _send_error(self, client_id: str, error_message: str):
        """Send error message to client."""
        try:
            error = {
                'type': 'game:error',
                'message': error_message,
                'timestamp': datetime.now().isoformat()
            }
            await self.network_module.send_message(client_id, error)
        except Exception as e:
            self.logger.error(f"Error sending error message: {e}")

    async def _send_auth_required(self, client_id: str):
        """Send authentication required message to client."""
        await self._send_error(client_id, "Authentication required")

    async def _load_server_states(self) -> Dict[str, Any]:
        """Load server states from storage."""
        try:
            server_data = Path(self.config.get('data_dir', 'data')) / 'servers.json'
            if server_data.exists():
                with open(server_data, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            self.logger.error(f"Error loading server states: {e}")
            return {}

    async def _load_player_states(self) -> Dict[str, Any]:
        """Load player states from storage."""
        try:
            player_data = Path(self.config.get('data_dir', 'data')) / 'players.json'
            if player_data.exists():
                with open(player_data, 'r') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            self.logger.error(f"Error loading player states: {e}")
            return {}

    async def _save_game_state(self):
        """Save current game state."""
        try:
            data_dir = Path(self.config.get('data_dir', 'data'))
            data_dir.mkdir(parents=True, exist_ok=True)

            # Save server states
            with open(data_dir / 'servers.json', 'w') as f:
                json.dump(self.world.servers, f, indent=2)

            # Save player states
            with open(data_dir / 'players.json', 'w') as f:
                json.dump(self.world.players, f, indent=2)

            self.logger.info("Game state saved successfully")

        except Exception as e:
            self.logger.error(f"Error saving game state: {e}")

    async def _broadcast_state_updates(self):
        """Broadcast state updates to all connected clients."""
        try:
            update_message = {
                'type': 'game:state_update',
                'timestamp': datetime.now().isoformat(),
                'servers': self.world.servers,
                'players': self.world.players
            }

            for client_id in self.world.active_sessions:
                await self.network_module.send_message(client_id, update_message)

        except Exception as e:
            self.logger.error(f"Error broadcasting state updates: {e}")

    def get_module_stats(self) -> Dict[str, Any]:
        """Get module statistics."""
        return {
            'active_players': len(self.world.players),
            'active_servers': len(self.world.servers),
            'active_sessions': len(self.world.active_sessions),
            'game_loop_running': bool(self.game_loop_task and not self.game_loop_task.done()),
            'cleanup_task_running': bool(self._cleanup_task and not self._cleanup_task.done())
        }

    async def unload(self) -> bool:
        """Unload the game server module and cleanup resources."""
        try:
            # First disable if enabled
            if self.is_enabled:
                await self.disable()

            # Unregister all event handlers
            self.server.event_manager.unregister_all_handlers(self.module_info.name)

            # Clear game state after saving
            try:
                await self._save_game_state()
            except Exception as e:
                self.logger.error(f"Error saving game state during unload: {e}")

            self.world.servers.clear()
            self.world.players.clear()
            self.world.active_sessions.clear()

            # Clear module references
            self.network_module = None
            self.user_module = None
            self.auth_module = None
            self.flask_module = None
            self.app_manager = None

            self.state = ModuleState.UNLOADED
            self.logger.info("Game server module unloaded successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error unloading game server module: {e}")
            return False