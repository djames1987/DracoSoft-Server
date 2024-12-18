import sys
import asyncio
import json
import logging
import msvcrt  # Windows-specific keyboard input
import queue
import shlex
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Callable

from DracoSoft_Server.core.baseModule import BaseModule, ModuleInfo, ModuleState

CTRL_C = b'\x03'
BACKSPACE = b'\x08'
ENTER = b'\r'
ESC = b'\x1b'
UP = b'H'
DOWN = b'P'


class ConsoleCommand:
    def __init__(self, func: Callable, help_text: str, min_args: int = 0, usage: str = ""):
        self.func = func
        self.help_text = help_text
        self.min_args = min_args
        self.usage = usage


class ConsoleUI:
    def __init__(self, command_queue: queue.Queue, response_queue: queue.Queue):
        self.command_queue = command_queue
        self.response_queue = response_queue
        self.running = True
        self.command_history: List[str] = []
        self.history_index = 0
        self.current_input = ""
        self.available_commands = {}

    def set_commands(self, commands: Dict[str, ConsoleCommand]):
        """Set available commands for help display"""
        self.available_commands = commands

    def _print_prompt(self):
        """Print the command prompt"""
        sys.stdout.write('\r(server) ' + self.current_input)
        sys.stdout.flush()

    def _clear_line(self):
        """Clear the current line"""
        sys.stdout.write('\r' + ' ' * (len(self.current_input) + 9) + '\r')
        sys.stdout.flush()

    def run(self):
        """Main console UI loop"""
        print("\nWelcome to the DracoSoft Server Console")
        print("Type 'help' for available commands\n")

        self._print_prompt()

        while self.running:
            if msvcrt.kbhit():
                char = msvcrt.getch()

                if char == ENTER:
                    print()  # New line after command
                    command = self.current_input.strip()
                    if command:
                        if command.lower() in ['exit', 'quit']:
                            self.running = False
                            break

                        self.command_history.append(command)
                        self.history_index = len(self.command_history)

                        self.command_queue.put(command)

                        try:
                            response = self.response_queue.get(timeout=5.0)
                            if response:
                                print(response)
                        except queue.Empty:
                            print("No response received from server")

                    self.current_input = ""
                    self._print_prompt()

                elif char == BACKSPACE:
                    if self.current_input:
                        self.current_input = self.current_input[:-1]
                        self._clear_line()
                        self._print_prompt()

                elif char == ESC:
                    if msvcrt.kbhit():
                        next_char = msvcrt.getch()
                        if next_char == b'[':  # Arrow keys
                            arrow = msvcrt.getch()
                            if arrow == UP and self.history_index > 0:  # Up arrow
                                self.history_index -= 1
                                self.current_input = self.command_history[self.history_index]
                            elif arrow == DOWN:  # Down arrow
                                if self.history_index < len(self.command_history) - 1:
                                    self.history_index += 1
                                    self.current_input = self.command_history[self.history_index]
                                else:
                                    self.history_index = len(self.command_history)
                                    self.current_input = ""
                            self._clear_line()
                            self._print_prompt()

                elif char == CTRL_C:
                    self.running = False
                    break

                elif 32 <= ord(char) <= 126:  # Printable characters
                    self.current_input += char.decode('ascii')
                    self._clear_line()
                    self._print_prompt()


class AdminConsoleModule(BaseModule):
    """Administrative console module for local server management."""

    def __init__(self, server):
        super().__init__(server)
        self.module_info = ModuleInfo(
            name="AdminConsole",
            version="1.0.0",
            description="Local administrative console",
            author="DracoSoft",
            dependencies=['sqlite_module']
        )

        self.command_queue = queue.Queue()
        self.response_queue = queue.Queue()
        self.console_thread: Optional[threading.Thread] = None
        self.commands: Dict[str, ConsoleCommand] = {}
        self.console_ui: Optional[ConsoleUI] = None
        self._register_commands()

    def _register_commands(self):
        """Register all available console commands"""
        self.commands = {
            'help': ConsoleCommand(
                self._cmd_help,
                "Show available commands",
                0,
                "help [command]"
            ),
            'status': ConsoleCommand(
                self._cmd_status,
                "Show server and module status",
                0,
                "status [module_name]"
            ),
            'modules': ConsoleCommand(
                self._cmd_modules,
                "List all modules",
                0,
                "modules [detail]"
            ),
            'start': ConsoleCommand(
                self._cmd_start_module,
                "Start/enable a module",
                1,
                "start <module_name>"
            ),
            'stop': ConsoleCommand(
                self._cmd_stop_module,
                "Stop/disable a module",
                1,
                "stop <module_name>"
            ),
            'restart': ConsoleCommand(
                self._cmd_restart_module,
                "Restart a module",
                1,
                "restart <module_name>"
            ),
            'shutdown': ConsoleCommand(
                self._cmd_shutdown,
                "Shutdown the server",
                0,
                "shutdown [force]"
            ),
            'db': ConsoleCommand(
                self._cmd_db,
                "Execute database commands",
                1,
                "db <query>"
            ),
            'users': ConsoleCommand(
                self._cmd_users,
                "List or manage users",
                0,
                "users [list|add|remove|modify] [args...]"
            ),
            'sessions': ConsoleCommand(
                self._cmd_sessions,
                "List active sessions",
                0,
                "sessions [list|clear]"
            ),
            'config': ConsoleCommand(
                self._cmd_config,
                "View or modify configuration",
                1,
                "config <module_name> [get|set] [key] [value]"
            ),
            'clients': ConsoleCommand(
                self._cmd_clients,
                "List connected clients",
                0,
                "clients [list|disconnect] [client_id]"
            ),
            'stats': ConsoleCommand(
                self._cmd_stats,
                "Show server statistics",
                0,
                "stats [module_name]"
            ),
            'logs': ConsoleCommand(
                self._cmd_logs,
                "View recent log entries",
                0,
                "logs [level] [limit]"
            )
        }

    async def load(self) -> bool:
        """Load the admin console module"""
        try:
            # Create console UI
            self.console_ui = ConsoleUI(self.command_queue, self.response_queue)
            self.console_ui.set_commands(self.commands)

            # Start console in a separate thread
            self.console_thread = threading.Thread(
                target=self._run_console,
                daemon=True
            )
            self.console_thread.start()

            # Start command processor
            loop = asyncio.get_running_loop()
            self._processor_task = loop.create_task(self._process_commands())

            self.state = ModuleState.LOADED
            self.logger.info("Admin console module loaded")
            return True

        except Exception as e:
            self.logger.error(f"Failed to load admin console: {e}")
            self.state = ModuleState.ERROR
            return False

    async def unload(self) -> bool:
        """Unload the admin console module"""
        try:
            if self.is_enabled:
                await self.disable()

            # Cleanup console thread
            if self.console_ui:
                self.console_ui.running = False

            if self.console_thread and self.console_thread.is_alive():
                self.console_thread.join(timeout=5.0)

            self.state = ModuleState.UNLOADED
            self.logger.info("Admin console module unloaded")
            return True

        except Exception as e:
            self.logger.error(f"Failed to unload admin console: {e}")
            return False

    def _run_console(self):
        """Run the console interface"""
        try:
            self.console_ui.run()
        except Exception as e:
            self.logger.error(f"Console error: {e}")

    async def _process_commands(self):
        """Process commands from the console"""
        try:
            while self.is_enabled:
                try:
                    # Check for commands
                    try:
                        command_line = self.command_queue.get_nowait()
                        response = await self._process_command(command_line)
                        self.response_queue.put(response)
                    except queue.Empty:
                        pass

                    await asyncio.sleep(0.1)

                except Exception as e:
                    self.logger.error(f"Error processing command: {e}")

        except asyncio.CancelledError:
            self.logger.info("Command processor task cancelled")
        except Exception as e:
            self.logger.error(f"Command processor error: {e}")

    async def _process_command(self, command_line: str) -> str:
        """Process a console command"""
        try:
            parts = shlex.split(command_line)
            if not parts:
                return ""

            command = parts[0].lower()
            args = parts[1:]

            if command in self.commands:
                cmd_obj = self.commands[command]
                if len(args) < cmd_obj.min_args:
                    return f"Error: {command} requires at least {cmd_obj.min_args} arguments\nUsage: {cmd_obj.usage}"
                return await cmd_obj.func(*args)

            return f"Unknown command: {command}. Type 'help' for available commands."

        except Exception as e:
            self.logger.error(f"Error processing command: {e}")
            return f"Error: {str(e)}"

    async def _cmd_help(self, command: str = None) -> str:
        """Show help for commands"""
        if command:
            if command in self.commands:
                cmd = self.commands[command]
                return f"{command}:\n  Usage: {cmd.usage}\n  {cmd.help_text}"
            return f"Unknown command: {command}"

        result = ["Available Commands:"]
        for name, cmd in sorted(self.commands.items()):
            result.append(f"\n{name}:")
            result.append(f"  Usage: {cmd.usage}")
            result.append(f"  {cmd.help_text}")
        return "\n".join(result)

    async def _cmd_status(self, module_name: str = None) -> str:
        """Show server status and optionally specific module status"""
        if module_name:
            if module_name not in self.server.module_manager.modules:
                return f"Module {module_name} not found"
            module = self.server.module_manager.modules[module_name]
            return f"Module {module_name} Status:\n" + "\n".join(
                f"  {k}: {v}" for k, v in module.get_status().items()
            )

        status = ["Server Status:"]
        status.append(f"Running: {self.server.running}")
        status.append(f"Active Modules: {len(self.server.module_manager.modules)}")

        status.append("\nModule States:")
        for name, module in self.server.module_manager.modules.items():
            status.append(f"  {name}: {module.state.value}")
        return "\n".join(status)

    async def _cmd_modules(self, detail: str = None) -> str:
        """List all modules and their status"""
        modules = self.server.module_manager.get_all_modules_status()

        if detail == "detail":
            result = ["Installed Modules:"]
            for name, info in modules.items():
                result.append(f"\n{name}:")
                for key, value in info.items():
                    result.append(f"  {key}: {value}")
        else:
            result = ["Modules:"]
            for name, info in modules.items():
                result.append(f"  {name}: {info['state']} (v{info['version']})")

        return "\n".join(result)

    async def _cmd_start_module(self, module_name: str) -> str:
        """Start/enable a module"""
        if not await self.server.module_manager.enable_module(module_name):
            return f"Failed to start module {module_name}"
        return f"Module {module_name} started successfully"

    async def _cmd_stop_module(self, module_name: str) -> str:
        """Stop/disable a module"""
        if not await self.server.module_manager.disable_module(module_name):
            return f"Failed to stop module {module_name}"
        return f"Module {module_name} stopped successfully"

    async def _cmd_restart_module(self, module_name: str) -> str:
        """Restart a module"""
        if not await self.server.module_manager.reload_module(module_name):
            return f"Failed to restart module {module_name}"
        return f"Module {module_name} restarted successfully"

    async def _cmd_shutdown(self, force: str = None) -> str:
        """Shutdown the server"""
        try:
            if force == "force":
                self.server.running = False
                return "Force shutting down server..."

            await self.server.shutdown()
            return "Server shutdown initiated"
        except Exception as e:
            return f"Error during shutdown: {e}"

    async def _cmd_db(self, *args) -> str:
        """Execute database commands"""
        if not args:
            return "Error: No query provided"

        db_module = self.server.module_manager.modules.get('sqlite_module')
        if not db_module:
            return "Database module not available"

        query = " ".join(args)
        try:
            if query.lower().startswith("select"):
                results = await db_module.fetch_all(query)
                if not results:
                    return "No results found"
                return "\n".join(str(row) for row in results)
            else:
                await db_module.execute(query)
                return "Query executed successfully"
        except Exception as e:
            return f"Database error: {e}"

    async def _cmd_users(self, action: str = "list", *args) -> str:
        """Manage users"""
        user_module = self.server.module_manager.modules.get('user_management_module')
        if not user_module:
            return "User management module not available"

        if action == "list":
            query = "SELECT * FROM users"
            db_module = self.server.module_manager.modules.get('sqlite_module')
            results = await db_module.fetch_all(query)
            if not results:
                return "No users found"
            return "\n".join(
                f"ID: {r[0]}, Username: {r[1]}, Email: {r[3]}, Status: {r[6]}"
                for r in results
            )

        return f"Unknown user action: {action}"

    async def _cmd_sessions(self, action: str = "list") -> str:
        """Manage active sessions"""
        auth_module = self.server.module_manager.modules.get('authorization_module')
        if not auth_module:
            return "Authorization module not available"

        if action == "list":
            sessions = auth_module.active_sessions
            if not sessions:
                return "No active sessions"
            result = ["Active Sessions:"]
            for client_id, session in sessions.items():
                result.append(f"\nClient: {client_id}")
                result.append(f"  User: {session['username']}")
                result.append(f"  Expires: {session['expires_at']}")
            return "\n".join(result)
        elif action == "clear":
            count = len(auth_module.active_sessions)
            auth_module.active_sessions.clear()
            return f"Cleared {count} active sessions"

        return f"Unknown session action: {action}"

    async def _cmd_config(self, module_name: str, action: str = "get", *args) -> str:
        """View or modify module configuration"""
        if module_name not in self.server.module_manager.modules:
            return f"Module {module_name} not found"

        module = self.server.module_manager.modules[module_name]

        if action == "get":
            if not args:
                return json.dumps(module.config, indent=2)
            key = args[0]
            return f"{key}: {module.config.get(key, 'Not found')}"
        elif action == "set" and len(args) >= 2:
            key = args[0]
            value = args[1]
            try:
                # Try to parse value as JSON for proper type conversion
                value = json.loads(value)
            except json.JSONDecodeError:
                # If not valid JSON, use as string
                pass

            module.config[key] = value
            return f"Updated configuration: {key} = {value}"

        return f"Unknown config action: {action}"

    async def _cmd_clients(self, action: str = "list", client_id: str = None) -> str:
        """Manage connected clients"""
        network_module = self.server.module_manager.modules.get('network_module')
        if not network_module:
            return "Network module not available"

        if action == "list":
            clients = network_module.clients
            if not clients:
                return "No connected clients"

            result = ["Connected Clients:"]
            for cid, session in clients.items():
                result.append(f"\nID: {cid}")
                result.append(f"  Address: {session.address}")
                result.append(f"  Connected: {datetime.fromtimestamp(session.connected_at)}")
                result.append(f"  Authenticated: {session.authenticated}")
            return "\n".join(result)

        elif action == "disconnect" and client_id:
            if client_id not in network_module.clients:
                return f"Client {client_id} not found"
            await network_module._disconnect_client(client_id)
            return f"Disconnected client {client_id}"

        return f"Unknown clients action: {action}"

    async def _cmd_stats(self, module_name: str = None) -> str:
        """Show server statistics"""
        stats = ["Server Statistics:"]

        # Basic server stats
        network_module = self.server.module_manager.modules.get('network_module')
        if network_module:
            stats.append(f"Connected Clients: {len(network_module.clients)}")

        auth_module = self.server.module_manager.modules.get('authorization_module')
        if auth_module:
            stats.append(f"Active Sessions: {len(auth_module.active_sessions)}")

        # Module-specific stats
        if module_name:
            if module_name not in self.server.module_manager.modules:
                return f"Module {module_name} not found"
            module = self.server.module_manager.modules[module_name]
            if hasattr(module, 'get_stats'):
                stats.extend([f"\n{module_name} Statistics:"])
                module_stats = module.get_stats()
                for key, value in module_stats.items():
                    stats.append(f"  {key}: {value}")
            else:
                stats.append(f"\nNo statistics available for {module_name}")

        return "\n".join(stats)

    async def _cmd_logs(self, level: str = "INFO", limit: str = "50") -> str:
        """View recent log entries"""
        try:
            limit = int(limit)
            log_level = getattr(logging, level.upper(), logging.INFO)

            # Get the path to the current log file from logging configuration
            log_file = self.server.config_manager.get_config('server').get('logging', {}).get('file')
            if not log_file:
                return "No log file configured"

            log_path = Path(log_file)
            if not log_path.exists():
                return "Log file not found"

            # Read last N lines from log file
            lines = []
            with open(log_path, 'r') as f:
                # Use a basic circular buffer for last N lines
                lines = [''] * limit
                i = 0
                for line in f:
                    lines[i % limit] = line.strip()
                    i += 1

                if i < limit:
                    lines = lines[:i]
                else:
                    lines = lines[i % limit:] + lines[:i % limit]

            # Filter by log level
            filtered_lines = [
                line for line in lines
                if line and self._get_log_level(line) >= log_level
            ]

            if not filtered_lines:
                return f"No log entries found with level {level} or higher"

            return "\n".join(filtered_lines)

        except ValueError:
            return "Invalid limit value"
        except Exception as e:
            return f"Error reading logs: {e}"

    def _get_log_level(self, log_line: str) -> int:
        """Extract log level from a log line and convert to numeric value"""
        for level in ['CRITICAL', 'ERROR', 'WARNING', 'INFO', 'DEBUG']:
            if level in log_line:
                return getattr(logging, level)
        return 0

    async def enable(self) -> bool:
        """Enable the admin console"""
        try:
            self.state = ModuleState.ENABLED
            self.logger.info("Admin console enabled")
            return True
        except Exception as e:
            self.logger.error(f"Failed to enable admin console: {e}")
            return False

    async def disable(self) -> bool:
        """Disable the admin console"""
        try:
            # Stop the console UI
            if self.console_ui:
                self.console_ui.running = False

            # Wait for console thread to finish
            if self.console_thread and self.console_thread.is_alive():
                self.console_thread.join(timeout=5.0)
                self.console_thread = None

            self.state = ModuleState.DISABLED
            self.logger.info("Admin console disabled")
            return True
        except Exception as e:
            self.logger.error(f"Failed to disable admin console: {e}")
            return False