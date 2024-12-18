# DracoSoft Server Framework Documentation

## Overview
DracoSoft Server is a modular, event-driven game server framework written in Python. It provides a flexible architecture for building multiplayer game servers with features like user authentication, session management, real-time communication, and extensible module system.

## Key Features
- Modular architecture with hot-reloadable modules
- Event-driven communication between modules
- Built-in user authentication and session management
- SQLite database integration
- WebSocket and TCP/UDP support
- Administrative console and GUI interface
- Configuration management with YAML
- Comprehensive logging system

## Getting Started

### Prerequisites
- Python 3.7+
- Required Python packages (install via pip):
  - aiosqlite
  - pyyaml
  - watchdog
  - qasync
  - PyQt6 (for GUI module)
  - Flask (for web interface)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/djames1987/DracoSoft-Server.git
cd dracosoft-server
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Create necessary directories:
```bash
mkdir -p config/server config/modules data logs
```

### Basic Configuration

The server uses YAML configuration files located in the `config` directory. Key configuration files include:

- `config/server/server.yaml`: Main server configuration
- `config/main.yaml`: Module loading and general settings
- `config/modules/*.yaml`: Individual module configurations

### Starting the Server

Run the server using:
```bash
python main.py
```

## Architecture

### Core Components

1. **CoreServer**
   - Base server implementation
   - Handles basic networking and client connections
   - Manages module lifecycle

2. **ModuleManager**
   - Discovers and loads modules
   - Manages module dependencies
   - Handles module lifecycle (load, enable, disable, unload)

3. **EventManager**
   - Provides event-driven communication between modules
   - Supports prioritized event handling
   - Maintains event history

4. **ConfigurationManager**
   - Manages YAML-based configuration files
   - Supports hot-reloading of configurations
   - Validates configuration schemas

### Built-in Modules

1. **NetworkModule**
   - Handles client connections and message routing
   - Implements the messaging protocol
   - Manages client sessions

2. **SQLiteModule**
   - Provides database functionality
   - Manages connection pooling
   - Handles database migrations

3. **AuthorizationModule**
   - Manages user authentication
   - Handles session tokens
   - Implements security measures

4. **UserManagementModule**
   - Manages user accounts
   - Handles user data and permissions
   - Implements password hashing and validation

5. **FlaskModule**
   - Provides web interface functionality
   - Handles HTTP requests
   - Supports REST API endpoints

6. **ServerGUIModule**
   - Provides graphical interface for server management
   - Displays real-time server status
   - Allows module management through UI

## Creating Custom Modules

### Module Structure

Create a new module by subclassing `BaseModule`:

```python
from DracoSoft_Server.core.baseModule import BaseModule, ModuleInfo, ModuleState

class CustomModule(BaseModule):
    def __init__(self, server):
        super().__init__(server)
        self.module_info = ModuleInfo(
            name="CustomModule",
            version="1.0.0",
            description="Description of your module",
            author="Your Name",
            dependencies=[]
        )

    async def load(self) -> bool:
        # Initialize resources
        return True

    async def unload(self) -> bool:
        # Cleanup resources
        return True

    async def enable(self) -> bool:
        # Start module functionality
        return True

    async def disable(self) -> bool:
        # Stop module functionality
        return True
```

### Module Configuration

Create a configuration file for your module in `config/modules/`:

```yaml
# config/modules/custom_module.yaml
enabled: true
auto_load: true
settings:
  setting1: value1
  setting2: value2
```

### Event Handling

Register event handlers in your module:

```python
def __init__(self, server):
    super().__init__(server)
    self.server.event_manager.register_handler(
        EventTypes.CLIENT_MESSAGE.value,
        self._handle_client_message,
        self.module_info.name,
        EventPriority.NORMAL
    )

async def _handle_client_message(self, event: Event):
    message = event.data.get('message', {})
    client_id = event.data.get('client_id')
    # Handle the message
```

### Module Dependencies

Specify module dependencies in your ModuleInfo:

```python
self.module_info = ModuleInfo(
    name="CustomModule",
    version="1.0.0",
    description="Description",
    author="Your Name",
    dependencies=['sqlite_module', 'network_module']
)
```

### Adding to Server

1. Place your module file in the `modules` directory
2. Add module configuration to `config/main.yaml`:
```yaml
modules:
  mapping:
    custom: "custom_module"
  load_order:
    - "network"
    - "sqlite"
    - "custom"
```

## Best Practices

### Module Development
- Always implement proper error handling
- Use async/await for potentially blocking operations
- Implement proper cleanup in unload() method
- Use the logger for debugging and monitoring
- Follow PEP 8 style guidelines

### Event Handling
- Use appropriate event priorities
- Keep event handlers lightweight
- Implement proper error handling in handlers
- Use event filtering when possible

### Configuration
- Validate all configuration values
- Provide sensible defaults
- Document configuration options
- Use appropriate data types

### Security
- Validate all user input
- Implement proper authentication checks
- Use secure password hashing
- Implement rate limiting where appropriate

## Troubleshooting

### Common Issues

1. **Module Loading Failures**
   - Check module dependencies
   - Verify configuration files exist
   - Check logs for specific error messages

2. **Connection Issues**
   - Verify port availability
   - Check firewall settings
   - Ensure correct host configuration

3. **Database Errors**
   - Check database file permissions
   - Verify SQLite installation
   - Check database path configuration

### Debugging

1. Enable debug logging in `server.yaml`:
```yaml
logging:
  level: "DEBUG"
  file: "server.log"
```

2. Check the log files in the `logs` directory
3. Use the GUI module for real-time monitoring
4. Enable module-specific debugging in their configs

## API Reference

### Core Server Methods
- `start()`: Start the server
- `shutdown()`: Stop the server
- `broadcast_message(message)`: Send message to all clients
- `handle_client_connection(reader, writer)`: Handle new client connection

### Event Types
- `CLIENT_CONNECTED`: New client connection
- `CLIENT_DISCONNECTED`: Client disconnection
- `CLIENT_MESSAGE`: Incoming client message
- `MODULE_LOADED`: Module loaded
- `MODULE_UNLOADED`: Module unloaded

### Module Lifecycle Methods
- `load()`: Initialize module
- `unload()`: Cleanup module
- `enable()`: Start module functionality
- `disable()`: Stop module functionality

## Contributing

1. Fork the repository
2. Create a feature branch
3. Implement your changes
4. Add tests if applicable
5. Submit a pull request

Follow the project's coding standards and include appropriate documentation.
