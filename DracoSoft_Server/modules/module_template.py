from typing import Dict, Any

from DracoSoft_Server.core.baseModule import BaseModule, ModuleInfo, ModuleState
from DracoSoft_Server.core.moduleEventSystem import Event, EventTypes, EventPriority


class TemplateModule(BaseModule):
    """
    Template for creating new modules.
    Replace this docstring with a description of your module's purpose.
    """

    def __init__(self, server):
        super().__init__(server)

        # Define module information
        self.module_info = ModuleInfo(
            name="Template",  # Replace with your module name
            version="1.0.0",  # Your module version
            description="Template module",  # Your module description
            author="Your Name",  # Module author
            dependencies=[]  # List of required module names
        )

        # Initialize any required class variables
        self._cleanup_task = None
        self._data_store: Dict[str, Any] = {}

    async def load(self) -> bool:
        """
        Load the module and its resources.
        Called when the module is first loaded by the module manager.
        """
        try:
            # Register event handlers
            self.server.event_manager.register_handler(
                EventTypes.CLIENT_MESSAGE.value,
                self._handle_client_message,
                self.module_info.name,
                EventPriority.NORMAL
            )

            # Initialize resources
            # Example: database connections, file handles, caches

            self.state = ModuleState.LOADED
            self.logger.info(f"{self.module_info.name} module loaded successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to load {self.module_info.name} module: {e}")
            self.state = ModuleState.ERROR
            return False

    async def unload(self) -> bool:
        """
        Unload the module and cleanup resources.
        Called when the module is being removed from the system.
        """
        try:
            if self.is_enabled:
                await self.disable()

            # Unregister all event handlers
            self.server.event_manager.unregister_all_handlers(self.module_info.name)

            # Clean up any resources
            # Example: close connections, save state, etc.

            self.state = ModuleState.UNLOADED
            self.logger.info(f"{self.module_info.name} module unloaded")
            return True

        except Exception as e:
            self.logger.error(f"Failed to unload {self.module_info.name} module: {e}")
            return False

    async def enable(self) -> bool:
        """
        Enable the module functionality.
        Called after loading to start the module's active operations.
        """
        try:
            # Validate dependencies
            if not await self.validate_dependencies():
                return False

            # Start any required tasks or services
            # Example: start background tasks, initialize active components

            self.state = ModuleState.ENABLED
            self.logger.info(f"{self.module_info.name} module enabled")
            return True

        except Exception as e:
            self.logger.error(f"Failed to enable {self.module_info.name} module: {e}")
            return False

    async def disable(self) -> bool:
        """
        Disable the module functionality.
        Called when the module needs to be temporarily disabled.
        """
        try:
            # Stop any running tasks or services
            # Example: stop background tasks, close active connections
            if self._cleanup_task:
                self._cleanup_task.cancel()

            self.state = ModuleState.DISABLED
            self.logger.info(f"{self.module_info.name} module disabled")
            return True

        except Exception as e:
            self.logger.error(f"Failed to disable {self.module_info.name} module: {e}")
            return False

    async def _handle_client_message(self, event: Event) -> None:
        """Handle incoming client messages."""
        try:
            message = event.data.get('message', {})
            client_id = event.data.get('client_id')

            # Process messages specific to this module
            if message.get('type') == 'template_action':
                await self._process_template_action(client_id, message)

        except Exception as e:
            self.logger.error(f"Error handling client message: {e}")

    async def _process_template_action(self, client_id: str, message: Dict[str, Any]) -> None:
        """
        Process a specific action for this module.
        Replace with your module's specific message handling.
        """
        try:
            # Implement your message processing logic here
            action = message.get('action')
            data = message.get('data')

            # Example response
            response = {
                'type': 'template_response',
                'status': 'success',
                'data': {'processed': True}
            }

            # Get network module to send response
            network_module = self.server.module_manager.modules.get('network_module')
            if network_module:
                await network_module.send_message(client_id, response)

        except Exception as e:
            self.logger.error(f"Error processing template action: {e}")

    def get_module_stats(self) -> Dict[str, Any]:
        """
        Get module statistics and status information.
        Customize this method to return relevant stats for your module.
        """
        return {
            'state': self.state.value,
            'data_count': len(self._data_store),
            # Add any other relevant statistics
        }

    async def _cleanup_old_data(self) -> None:
        """
        Example of a background cleanup task.
        Replace with your module's maintenance tasks.
        """
        try:
            # Implement your cleanup logic here
            old_keys = []  # Determine what needs to be cleaned up
            for key in old_keys:
                self._data_store.pop(key, None)
        except Exception as e:
            self.logger.error(f"Error in cleanup task: {e}")