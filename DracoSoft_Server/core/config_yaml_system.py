import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Union, List

import yaml


class ConfigValidationError(Exception):
    """Custom exception for configuration validation errors."""
    pass


class ConfigurationScope(Enum):
    """Defines the scope of configuration settings."""
    SERVER = "server"
    MODULE = "module"
    GLOBAL = "global"


@dataclass
class ConfigField:
    """Defines a configuration field with validation rules."""
    name: str
    type: type
    required: bool = True
    default: Any = None
    choices: Optional[List[Any]] = None
    min_value: Optional[Union[int, float]] = None
    max_value: Optional[Union[int, float]] = None
    description: str = ""


class ConfigurationManager:
    """
    Manages loading, validation, and access to YAML configuration files
    for both the server and its modules.
    """

    def __init__(self, base_path: Union[str, Path]):
        self.base_path = Path(base_path)
        self.logger = logging.getLogger(__name__)

        # Create configuration directories if they don't exist
        self.config_dirs = {
            ConfigurationScope.SERVER: self.base_path / "server",
            ConfigurationScope.MODULE: self.base_path / "modules",
            ConfigurationScope.GLOBAL: self.base_path / ""
        }

        for directory in self.config_dirs.values():
            directory.mkdir(parents=True, exist_ok=True)

        self.configs: Dict[str, Dict[str, Any]] = {}
        self.schema_registry: Dict[str, List[ConfigField]] = {}

    def register_schema(self, name: str, schema: List[ConfigField]) -> None:
        """Register a configuration schema for validation."""
        self.schema_registry[name] = schema
        self.logger.debug(f"Registered schema: {name}")

    def _validate_config(self, config: Dict[str, Any], schema: List[ConfigField]) -> None:
        """Validate configuration against its schema."""
        for field in schema:
            # Check required fields
            if field.required and field.name not in config:
                raise ConfigValidationError(f"Missing required field: {field.name}")

            if field.name in config:
                value = config[field.name]

                # Type validation
                if not isinstance(value, field.type):
                    raise ConfigValidationError(
                        f"Field {field.name} must be of type {field.type.__name__}"
                    )

                # Choices validation
                if field.choices and value not in field.choices:
                    raise ConfigValidationError(
                        f"Field {field.name} must be one of {field.choices}"
                    )

                # Range validation for numeric types
                if isinstance(value, (int, float)):
                    if field.min_value is not None and value < field.min_value:
                        raise ConfigValidationError(
                            f"Field {field.name} must be >= {field.min_value}"
                        )
                    if field.max_value is not None and value > field.max_value:
                        raise ConfigValidationError(
                            f"Field {field.name} must be <= {field.max_value}"
                        )

    def load_config(self,
                    name: str,
                    scope: ConfigurationScope,
                    schema_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Load and validate a configuration file.
        Returns the configuration dict if successful.
        """
        config_path = self.config_dirs[scope] / f"{name}.yaml"

        try:
            if not config_path.exists():
                self.logger.warning(f"Configuration file not found: {config_path}")
                return {}

            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)

            if schema_name and schema_name in self.schema_registry:
                self._validate_config(config, self.schema_registry[schema_name])

            self.configs[name] = config
            return config

        except yaml.YAMLError as e:
            self.logger.error(f"Error parsing YAML configuration {name}: {e}")
            raise
        except ConfigValidationError as e:
            self.logger.error(f"Configuration validation failed for {name}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Error loading configuration {name}: {e}")
            raise

    def save_config(self,
                    name: str,
                    config: Dict[str, Any],
                    scope: ConfigurationScope) -> bool:
        """Save a configuration to file."""
        config_path = self.config_dirs[scope] / f"{name}.yaml"

        try:
            with open(config_path, 'w') as f:
                yaml.dump(config, f, default_flow_style=False)
            return True
        except Exception as e:
            self.logger.error(f"Error saving configuration {name}: {e}")
            return False

    def get_config(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a loaded configuration by name."""
        return self.configs.get(name)

    def update_config(self,
                      name: str,
                      updates: Dict[str, Any],
                      scope: ConfigurationScope,
                      schema_name: Optional[str] = None) -> bool:
        """Update an existing configuration."""
        current_config = self.get_config(name) or {}
        updated_config = {**current_config, **updates}

        try:
            if schema_name and schema_name in self.schema_registry:
                self._validate_config(updated_config, self.schema_registry[schema_name])

            self.configs[name] = updated_config
            return self.save_config(name, updated_config, scope)

        except Exception as e:
            self.logger.error(f"Error updating configuration {name}: {e}")
            return False

    def create_default_configs(self) -> None:
        """Create default configuration files if they don't exist."""
        default_server_config = {
            "host": "0.0.0.0",
            "port": 8888,
            "max_clients": 1000,
            "tick_rate": 60,
            "logging": {
                "level": "INFO",
                "file": "server.log"
            }
        }

        default_module_config = {
            "enabled": True,
            "auto_load": True,
            "settings": {}
        }

        # Create default server config
        if not (self.config_dirs[ConfigurationScope.SERVER] / "server.yaml").exists():
            self.save_config("server", default_server_config, ConfigurationScope.SERVER)

        # Create default module config template
        if not (self.config_dirs[ConfigurationScope.MODULE] / "module_template.yaml").exists():
            self.save_config("module_template", default_module_config, ConfigurationScope.MODULE)


# Example usage and schema definitions
def create_example_schemas():
    """Create example configuration schemas."""
    # Server configuration schema
    server_schema = [
        ConfigField("host", str, default="0.0.0.0"),
        ConfigField("port", int, min_value=1, max_value=65535, default=8888),
        ConfigField("max_clients", int, min_value=1, default=1000),
        ConfigField("tick_rate", int, min_value=1, max_value=120, default=60),
        ConfigField(
            "logging",
            dict,
            default={"level": "INFO", "file": "server.log"}
        )
    ]

    # Authentication module schema example
    auth_module_schema = [
        ConfigField("enabled", bool, default=True),
        ConfigField("session_timeout", int, min_value=60, default=3600),
        ConfigField(
            "password_policy",
            dict,
            default={
                "min_length": 8,
                "require_special": True,
                "require_numbers": True
            }
        ),
        ConfigField(
            "jwt_settings",
            dict,
            default={
                "secret_key": "change_me_in_production",
                "algorithm": "HS256",
                "token_expiry": 86400
            }
        )
    ]

    return {
        "server": server_schema,
        "auth_module": auth_module_schema
    }