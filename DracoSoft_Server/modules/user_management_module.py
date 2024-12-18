# modules/user_management_module.py
import hashlib
import secrets
from typing import Dict, Any, Optional

from DracoSoft_Server.core.baseModule import BaseModule, ModuleInfo, ModuleState


class UserManagementModule(BaseModule):
    def __init__(self, server):
        super().__init__(server)
        self.module_info = ModuleInfo(
            name="UserManagement",
            version="1.0.0",
            description="Handles user account management",
            author="DracoSoft",
            dependencies=['sqlite_module']  # Updated dependency name
        )

        self.db_module = None

    async def load(self) -> bool:
        try:
            # Get database module with correct name
            self.db_module = self.server.module_manager.modules.get('sqlite_module')
            if not self.db_module:
                raise RuntimeError("SQLite module not found")

            self.state = ModuleState.LOADED
            self.logger.info("User Management module loaded successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to load User Management module: {e}")
            self.state = ModuleState.ERROR
            return False

    async def unload(self) -> bool:
        """Unload the User Management module."""
        try:
            if self.is_enabled:
                await self.disable()

            self.state = ModuleState.UNLOADED
            self.logger.info("User Management module unloaded")
            return True
        except Exception as e:
            self.logger.error(f"Failed to unload User Management module: {e}")
            return False

    async def enable(self) -> bool:
        """Enable the User Management module."""
        try:
            # Validate dependencies
            if not await self.validate_dependencies():
                return False

            self.state = ModuleState.ENABLED
            self.logger.info("User Management module enabled")
            return True
        except Exception as e:
            self.logger.error(f"Failed to enable User Management module: {e}")
            return False

    async def disable(self) -> bool:
        """Disable the User Management module."""
        try:
            self.state = ModuleState.DISABLED
            self.logger.info("User Management module disabled")
            return True
        except Exception as e:
            self.logger.error(f"Failed to disable User Management module: {e}")
            return False

    async def create_user(self, username: str, password: str, email: str = None) -> Optional[int]:
        """Create a new user account."""
        try:
            # Hash password
            password_hash = self._hash_password(password)

            # Insert user into database
            query = """
                INSERT INTO users (username, password_hash, email)
                VALUES (?, ?, ?)
            """

            user_id = await self.db_module.execute(query, (username, password_hash, email))
            self.logger.info(f"Created new user: {username}")
            return user_id

        except Exception as e:
            self.logger.error(f"Failed to create user {username}: {e}")
            return None

    async def update_user(self, user_id: int, updates: Dict[str, Any]) -> bool:
        """Update user information."""
        try:
            set_clauses = []
            params = []

            for key, value in updates.items():
                if key == 'password':
                    set_clauses.append("password_hash = ?")
                    params.append(self._hash_password(value))
                elif key in ['email', 'status']:
                    set_clauses.append(f"{key} = ?")
                    params.append(value)

            if not set_clauses:
                return False

            params.append(user_id)
            query = f"""
                UPDATE users
                SET {', '.join(set_clauses)}
                WHERE id = ?
            """

            await self.db_module.execute(query, tuple(params))
            self.logger.info(f"Updated user {user_id}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to update user {user_id}: {e}")
            return False

    async def get_user(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user information by username."""
        try:
            query = """
                SELECT id, username, password_hash, email, created_at, last_login, status
                FROM users
                WHERE username = ?
            """

            result = await self.db_module.fetch_one(query, (username,))
            if result:
                return {
                    'id': result[0],
                    'username': result[1],
                    'password_hash': result[2],
                    'email': result[3],
                    'created_at': result[4],
                    'last_login': result[5],
                    'status': result[6]
                }
            return None

        except Exception as e:
            self.logger.error(f"Failed to get user {username}: {e}")
            return None

    async def update_last_login(self, user_id: int) -> bool:
        """Update user's last login timestamp."""
        try:
            query = """
                UPDATE users
                SET last_login = CURRENT_TIMESTAMP
                WHERE id = ?
            """

            await self.db_module.execute(query, (user_id,))
            return True

        except Exception as e:
            self.logger.error(f"Failed to update last login for user {user_id}: {e}")
            return False

    def _hash_password(self, password: str) -> str:
        """Hash a password using SHA-256 and a salt."""
        salt = secrets.token_hex(16)
        hash_obj = hashlib.sha256(f"{password}{salt}".encode())
        return f"{salt}:{hash_obj.hexdigest()}"

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash."""
        try:
            salt, hash_value = password_hash.split(':')
            test_hash = hashlib.sha256(f"{password}{salt}".encode()).hexdigest()
            return test_hash == hash_value
        except Exception:
            return False