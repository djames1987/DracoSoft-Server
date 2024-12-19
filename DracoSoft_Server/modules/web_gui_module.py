# modules/web_gui_module.py
import asyncio
import datetime
import os
from pathlib import Path
from typing import Dict, Any, Optional
from flask import Blueprint, request, jsonify, send_from_directory, g
from functools import wraps
import jwt
from werkzeug.security import safe_join

from DracoSoft_Server.core.baseModule import BaseModule, ModuleInfo, ModuleState
from DracoSoft_Server.core.moduleEventSystem import Event, EventTypes, EventPriority


class WebGUIModule(BaseModule):
    def __init__(self, server):
        super().__init__(server)
        self.module_info = ModuleInfo(
            name="WebGUI",
            version="1.0.0",
            description="Web-based management interface",
            author="DracoSoft",
            dependencies=['flask_module', 'user_management_module', 'authorization_module']
        )

        self.flask_module = None
        self.user_module = None
        self.auth_module = None
        self.web_dir = Path("data/Web_Gui_Data")
        self.secret_key = None
        self.blueprint = None
        self.app_manager = None

    async def load(self) -> bool:
        """Load the WebGUI module."""
        try:
            # Get required modules
            self.flask_module = self.server.module_manager.modules.get('flask_module')
            self.user_module = self.server.module_manager.modules.get('user_management_module')
            self.auth_module = self.server.module_manager.modules.get('authorization_module')

            if not all([self.flask_module, self.user_module, self.auth_module]):
                raise RuntimeError("Required modules not found")

            # Ensure web directory exists
            self.web_dir.mkdir(parents=True, exist_ok=True)
            self.logger.info(f"Web directory path: {self.web_dir}")
            self.logger.info(f"Index file exists: {(self.web_dir / 'index.html').exists()}")
            self.logger.info(f"Static directory exists: {(self.web_dir / 'static').exists()}")

            if (self.web_dir / 'static').exists():
                static_files = list((self.web_dir / 'static').glob('**/*'))
                self.logger.info(f"Static files found: {static_files}")

                js_dir = self.web_dir / 'static' / 'js'
                if js_dir.exists():
                    js_files = list(js_dir.glob('*'))
                    self.logger.info(f"JS files found: {js_files}")
                else:
                    self.logger.warning(f"JS directory not found at {js_dir}")

            # Get configuration
            self.secret_key = self.config.get('secret_key', os.urandom(24).hex())
            web_gui_port = self.config.get('port', 5000)

            # Create Flask app and blueprint
            self.app_manager = self.flask_module.create_app('web_gui', port=web_gui_port)
            self.blueprint = Blueprint('web_gui', __name__)

            # Register routes and configure the app
            self._setup_app()
            self._register_routes()

            # Add blueprint to app
            self.app_manager.add_blueprint(self.blueprint)

            self.state = ModuleState.LOADED
            self.logger.info("WebGUI module loaded successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to load WebGUI module: {e}")
            self.state = ModuleState.ERROR
            return False

    def _setup_app(self):
        """Configure Flask application."""
        app = self.app_manager.app
        app.secret_key = self.secret_key

        # Setup CORS if configured
        if self.config.get('cors_enabled', True):
            from flask_cors import CORS
            CORS(app, resources={
                r"/api/*": {
                    "origins": self.config.get('allowed_origins', ["http://localhost:5000"]),
                    "methods": ["GET", "POST", "PUT", "DELETE"],
                    "allow_headers": ["Content-Type", "Authorization"]
                }
            })

    def require_auth(self, f):
        """Decorator to require authentication for routes."""

        @wraps(f)
        async def decorated(*args, **kwargs):
            auth_header = request.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({'message': 'Missing or invalid authorization header'}), 401

            try:
                token = auth_header.split(' ')[1]
                payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
                g.user_id = payload['user_id']
                g.username = payload['username']
                return await f(*args, **kwargs)
            except jwt.ExpiredSignatureError:
                return jsonify({'message': 'Token has expired'}), 401
            except jwt.InvalidTokenError:
                return jsonify({'message': 'Invalid token'}), 401
            except Exception as e:
                self.logger.error(f"Authentication error: {e}")
                return jsonify({'message': 'Authentication failed'}), 401

        return decorated

    async def _delayed_shutdown(self):
        """Shutdown the server after a brief delay to allow response to be sent."""
        try:
            await asyncio.sleep(1)  # Give time for response to be sent

            # Log shutdown initiation
            self.logger.info("Server shutdown initiated through Web GUI")

            # Stop the Flask app first
            if self.app_manager:
                self.app_manager.stop()

            # Set server running flag to False
            self.server.running = False

            # Initiate server shutdown
            asyncio.create_task(self.server.shutdown())

            self.logger.info("Server shutdown sequence completed")

        except Exception as e:
            self.logger.error(f"Error during shutdown sequence: {e}")

    def _register_routes(self):
        """Register routes with Flask blueprint."""

        @self.app_manager.app.route('/')
        def serve_index():
            """Serve the main index.html file"""
            return send_from_directory(str(self.web_dir), 'index.html')

        @self.app_manager.app.route('/static/js/<path:filename>')
        def serve_js(filename):
            """Serve JavaScript files"""
            js_dir = self.web_dir / 'static' / 'js'
            self.logger.debug(f"Serving JS file from {js_dir}: {filename}")
            return send_from_directory(str(js_dir), filename)

        @self.app_manager.app.route('/static/css/<path:filename>')
        def serve_css(filename):
            """Serve CSS files"""
            css_dir = self.web_dir / 'static' / 'css'
            self.logger.debug(f"Serving CSS file from {css_dir}: {filename}")
            return send_from_directory(str(css_dir), filename)

        @self.app_manager.app.route('/static/<path:filename>')
        def serve_static(filename):
            """Serve other static files"""
            static_dir = self.web_dir / 'static'
            self.logger.debug(f"Serving static file from {static_dir}: {filename}")
            return send_from_directory(str(static_dir), filename)

        @self.app_manager.app.route('/api/auth/login', methods=['POST'])
        async def login():
            """Handle user login"""
            data = request.get_json()
            username = data.get('username')
            password = data.get('password')

            if not username or not password:
                return jsonify({'message': 'Missing credentials'}), 400

            try:
                user = await self.user_module.get_user(username)
                if not user or not self.user_module._verify_password(password, user['password_hash']):
                    return jsonify({'message': 'Invalid credentials'}), 401

                if user.get('status') != 'active':
                    return jsonify({'message': 'Account is not active'}), 403

                token = jwt.encode({
                    'user_id': user['id'],
                    'username': username,
                    'exp': datetime.datetime.utcnow() + datetime.timedelta(
                        seconds=self.config.get('token_expiry', 86400)
                    )
                }, self.secret_key, algorithm='HS256')

                return jsonify({
                    'token': token,
                    'username': username,
                    'message': 'Login successful'
                })

            except Exception as e:
                self.logger.error(f"Login error: {e}")
                return jsonify({'message': 'Login failed'}), 500

        @self.app_manager.app.route('/api/modules', methods=['GET'])
        async def get_modules():
            """Get all module statuses"""
            auth_result = await self._check_auth()
            if auth_result is not None:
                return auth_result

            try:
                modules = self.server.module_manager.get_all_modules_status()
                return jsonify(modules)
            except Exception as e:
                self.logger.error(f"Error getting modules: {e}")
                return jsonify({'message': 'Failed to get modules'}), 500

        @self.app_manager.app.route('/api/modules/<module_name>/action', methods=['POST'])
        async def module_action(module_name):
            """Handle module actions (enable, disable, restart)"""
            auth_result = await self._check_auth()
            if auth_result is not None:
                return auth_result

            data = request.get_json()
            action = data.get('action')

            if action not in ['enable', 'disable', 'restart']:
                return jsonify({'message': 'Invalid action'}), 400

            try:
                result = False
                if action == 'enable':
                    result = await self.server.module_manager.enable_module(module_name)
                elif action == 'disable':
                    result = await self.server.module_manager.disable_module(module_name)
                elif action == 'restart':
                    result = await self.server.module_manager.reload_module(module_name)

                if result:
                    return jsonify({
                        'success': True,
                        'message': f'Successfully {action}d {module_name}'
                    })
                else:
                    return jsonify({
                        'success': False,
                        'message': f'Failed to {action} {module_name}'
                    }), 500

            except Exception as e:
                self.logger.error(f"Error performing {action} on {module_name}: {e}")
                return jsonify({
                    'success': False,
                    'message': f'Error performing {action}'
                }), 500

        @self.app_manager.app.route('/api/server/shutdown', methods=['POST'])
        async def shutdown_server():
            """Handle server shutdown request"""
            auth_result = await self._check_auth()
            if auth_result is not None:
                return auth_result

            try:
                # Create a task to shutdown the server after sending response
                asyncio.create_task(self._delayed_shutdown())
                self.logger.info("Shutdown task created")

                return jsonify({
                    'success': True,
                    'message': 'Server shutdown initiated'
                })
            except Exception as e:
                self.logger.error(f"Error initiating shutdown: {e}")
                return jsonify({
                    'success': False,
                    'message': 'Failed to initiate shutdown'
                }), 500

    async def _check_auth(self):
        """Helper method to check authentication"""
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'message': 'Missing or invalid authorization header'}), 401

        try:
            token = auth_header.split(' ')[1]
            payload = jwt.decode(token, self.secret_key, algorithms=['HS256'])
            g.user_id = payload['user_id']
            g.username = payload['username']
            return None
        except jwt.ExpiredSignatureError:
            return jsonify({'message': 'Token has expired'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'message': 'Invalid token'}), 401
        except Exception as e:
            self.logger.error(f"Authentication error: {e}")
            return jsonify({'message': 'Authentication failed'}), 401

    async def enable(self) -> bool:
        """Enable the WebGUI module."""
        try:
            if not await self.validate_dependencies():
                return False

            self.state = ModuleState.ENABLED
            self.logger.info("WebGUI module enabled")
            return True

        except Exception as e:
            self.logger.error(f"Failed to enable WebGUI module: {e}")
            return False

    async def disable(self) -> bool:
        """Disable the WebGUI module."""
        try:
            if self.app_manager and self.blueprint:
                self.app_manager.remove_blueprint(self.blueprint.name)

            self.state = ModuleState.DISABLED
            self.logger.info("WebGUI module disabled")
            return True

        except Exception as e:
            self.logger.error(f"Failed to disable WebGUI module: {e}")
            return False

    async def unload(self) -> bool:
        """Unload the WebGUI module."""
        try:
            if self.is_enabled:
                await self.disable()

            self.state = ModuleState.UNLOADED
            self.logger.info("WebGUI module unloaded")
            return True

        except Exception as e:
            self.logger.error(f"Failed to unload WebGUI module: {e}")
            return False