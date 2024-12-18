import asyncio
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any

import psutil
import requests

from DracoSoft_Server.core.baseModule import BaseModule, ModuleInfo, ModuleState
from DracoSoft_Server.core.moduleEventSystem import Event, EventTypes, EventPriority


class FlaskModule(BaseModule):
    """
    Module to manage a Flask application in a separate process.
    Handles starting, stopping, and monitoring the Flask server.
    """

    def __init__(self, server):
        super().__init__(server)

        self.module_info = ModuleInfo(
            name="Flask",
            version="1.0.0",
            description="Flask server process manager",
            author="DracoSoft",
            dependencies=[]
        )

        self.process: Optional[subprocess.Popen] = None
        self.flask_port: int = 5000
        self.health_check_interval: int = 30
        self._health_check_task: Optional[asyncio.Task] = None
        self._process_monitor_task: Optional[asyncio.Task] = None
        self.flask_script_path: Path = Path(__file__).parent / "flask_server.py"
        self.restart_attempts = 0
        self.max_restart_attempts = 3

    async def load(self) -> bool:
        """Load the Flask module."""
        try:
            # Validate Flask script exists
            if not self.flask_script_path.exists():
                raise FileNotFoundError(f"Flask script not found: {self.flask_script_path}")

            # Get configuration
            self.flask_port = self.config.get('port', 5000)
            self.health_check_interval = self.config.get('health_check_interval', 30)
            self.max_restart_attempts = self.config.get('max_restart_attempts', 3)

            # Register event handlers
            self.server.event_manager.register_handler(
                EventTypes.CLIENT_MESSAGE.value,
                self._handle_client_message,
                self.module_info.name,
                EventPriority.NORMAL
            )

            self.state = ModuleState.LOADED
            self.logger.info("Flask module loaded successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to load Flask module: {e}")
            self.state = ModuleState.ERROR
            return False

    async def enable(self) -> bool:
        """Enable the Flask module and start the Flask server process."""
        try:
            # Start Flask process
            if not await self._start_flask_server():
                return False

            # Start monitoring tasks
            self._health_check_task = asyncio.create_task(self._health_check_loop())
            self._process_monitor_task = asyncio.create_task(self._monitor_process())

            self.state = ModuleState.ENABLED
            self.logger.info("Flask module enabled")
            return True

        except Exception as e:
            self.logger.error(f"Failed to enable Flask module: {e}")
            return False

    async def disable(self) -> bool:
        """Disable the Flask module and stop the Flask server."""
        try:
            # Cancel monitoring tasks
            if self._health_check_task:
                self._health_check_task.cancel()
            if self._process_monitor_task:
                self._process_monitor_task.cancel()

            # Stop Flask server
            await self._stop_flask_server()

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

            self.server.event_manager.unregister_all_handlers(self.module_info.name)

            self.state = ModuleState.UNLOADED
            await self._stop_flask_server()
            self.logger.info("Flask module unloaded")
            return True

        except Exception as e:
            self.logger.error(f"Failed to unload Flask module: {e}")
            return False

    async def _start_flask_server(self) -> bool:
        """Start the Flask server process."""
        try:
            # Ensure old process is stopped
            await self._stop_flask_server()

            # Prepare log path
            log_path = Path("logs/flask_app.log")
            log_path.parent.mkdir(parents=True, exist_ok=True)

            # Start Flask process
            self.process = subprocess.Popen([
                sys.executable,
                str(self.flask_script_path),
                str(self.flask_port),
                str(log_path)
            ])

            # Wait for server to start
            for _ in range(10):  # Try for 10 seconds
                try:
                    response = requests.get(f"http://localhost:{self.flask_port}/health")
                    if response.status_code == 200:
                        self.logger.info(f"Flask server started on port {self.flask_port}")
                        self.restart_attempts = 0
                        return True
                except requests.RequestException:
                    await asyncio.sleep(1)

            raise TimeoutError("Flask server failed to start")

        except Exception as e:
            self.logger.error(f"Error starting Flask server: {e}")
            return False

    async def _stop_flask_server(self) -> None:
        """Stop the Flask server process."""
        if self.process:
            try:
                # Try graceful shutdown first
                parent = psutil.Process(self.process.pid)
                children = parent.children(recursive=True)

                for child in children:
                    child.terminate()
                parent.terminate()

                # Wait for processes to terminate
                gone, alive = psutil.wait_procs([parent] + children, timeout=3)

                # Force kill if still alive
                for p in alive:
                    p.kill()

            except psutil.NoSuchProcess:
                pass
            except Exception as e:
                self.logger.error(f"Error stopping Flask server: {e}")
            finally:
                self.process = None

    async def _health_check_loop(self) -> None:
        """Periodically check Flask server health."""
        while True:
            try:
                await asyncio.sleep(self.health_check_interval)

                if not self.process:
                    continue

                response = requests.get(f"http://localhost:{self.flask_port}/health")
                if response.status_code != 200:
                    self.logger.warning("Flask server health check failed")
                    await self._handle_server_failure()

            except requests.RequestException:
                self.logger.warning("Flask server not responding")
                await self._handle_server_failure()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in health check: {e}")

    async def _monitor_process(self) -> None:
        """Monitor the Flask process for unexpected termination."""
        while True:
            try:
                await asyncio.sleep(1)

                if self.process and self.process.poll() is not None:
                    self.logger.warning("Flask process terminated unexpectedly")
                    await self._handle_server_failure()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error monitoring process: {e}")

    async def _handle_server_failure(self) -> None:
        """Handle Flask server failures."""
        self.restart_attempts += 1

        if self.restart_attempts <= self.max_restart_attempts:
            self.logger.info(f"Attempting to restart Flask server (attempt {self.restart_attempts})")
            await self._start_flask_server()
        else:
            self.logger.error("Max restart attempts reached")
            # Could emit an event here to notify other modules

    async def _handle_client_message(self, event: Event) -> None:
        """Handle client messages for Flask module control."""
        try:
            message = event.data.get('message', {})
            client_id = event.data.get('client_id')

            if message.get('type') != 'flask_control':
                return

            action = message.get('action')
            response_data = {"success": False, "message": "Unknown action"}

            if action == 'status':
                response_data = await self._get_status()
            elif action == 'restart':
                success = await self._start_flask_server()
                response_data = {
                    "success": success,
                    "message": "Server restarted" if success else "Restart failed"
                }
            elif action == 'stop':
                await self._stop_flask_server()
                response_data = {"success": True, "message": "Server stopped"}

            # Send response
            network_module = self.server.module_manager.modules.get('network_module')
            if network_module:
                await network_module.send_message(client_id, {
                    "type": "flask_control_response",
                    "data": response_data
                })

        except Exception as e:
            self.logger.error(f"Error handling client message: {e}")

    async def _get_status(self) -> Dict[str, Any]:
        """Get Flask server status."""
        try:
            if not self.process:
                return {"status": "stopped", "pid": None}

            response = requests.get(f"http://localhost:{self.flask_port}/api/status")
            return {
                "success": True,
                "data": response.json(),
                "restart_attempts": self.restart_attempts
            }
        except Exception:
            return {
                "success": False,
                "status": "error",
                "pid": self.process.pid if self.process else None,
                "restart_attempts": self.restart_attempts
            }