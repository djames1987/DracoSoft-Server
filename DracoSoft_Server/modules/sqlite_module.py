# modules/sqlite_module.py
import asyncio
from pathlib import Path
from typing import Dict, List, Optional

import aiosqlite

from DracoSoft_Server.core.baseModule import BaseModule, ModuleInfo, ModuleState


class SQLiteModule(BaseModule):
    def __init__(self, server):
        super().__init__(server)
        self.module_info = ModuleInfo(
            name="SQLite",
            version="1.0.0",
            description="Handles SQLite database operations",
            author="DracoSoft",
            dependencies=[]
        )

        self.db_path: Optional[Path] = None
        self.db_lock = asyncio.Lock()
        self._connection_pool: Dict[str, aiosqlite.Connection] = {}

    async def load(self) -> bool:
        try:
            # Get database configuration
            db_config = self.config.get('database', {})
            self.db_path = Path(db_config.get('path', 'data/server.db'))

            # Ensure database directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            # Initialize database
            await self._init_database()

            self.state = ModuleState.LOADED
            self.logger.info("SQLite module loaded successfully")
            return True

        except Exception as e:
            self.logger.error(f"Failed to load SQLite module: {e}")
            return False

    async def unload(self) -> bool:
        """Unload the SQLite module and cleanup resources."""
        try:
            if self.is_enabled:
                await self.disable()

            # Close all connections
            for conn in self._connection_pool.values():
                await conn.close()
            self._connection_pool.clear()

            self.state = ModuleState.UNLOADED
            self.logger.info("SQLite module unloaded")
            return True
        except Exception as e:
            self.logger.error(f"Failed to unload SQLite module: {e}")
            return False

    async def enable(self) -> bool:
        try:
            self.state = ModuleState.ENABLED
            self.logger.info("SQLite module enabled")
            return True
        except Exception as e:
            self.logger.error(f"Failed to enable SQLite module: {e}")
            return False

    async def disable(self) -> bool:
        try:
            # Close all connections
            for conn in self._connection_pool.values():
                await conn.close()
            self._connection_pool.clear()

            self.state = ModuleState.DISABLED
            self.logger.info("SQLite module disabled")
            return True
        except Exception as e:
            self.logger.error(f"Failed to disable SQLite module: {e}")
            return False

    async def _init_database(self):
        """Initialize the database and create tables if they don't exist."""
        async with self.db_lock:
            async with aiosqlite.connect(self.db_path) as db:
                # Enable foreign keys
                await db.execute("PRAGMA foreign_keys = ON")

                # Create users table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        email TEXT UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_login TIMESTAMP,
                        status TEXT DEFAULT 'active'
                    )
                """)

                # Create sessions table
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        token TEXT UNIQUE NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP NOT NULL,
                        FOREIGN KEY (user_id) REFERENCES users (id)
                    )
                """)

                await db.commit()

    async def get_connection(self) -> aiosqlite.Connection:
        """Get a database connection from the pool."""
        task_id = id(asyncio.current_task())
        if task_id not in self._connection_pool:
            conn = await aiosqlite.connect(self.db_path)
            await conn.execute("PRAGMA foreign_keys = ON")
            self._connection_pool[task_id] = conn
        return self._connection_pool[task_id]

    async def execute(self, query: str, params: tuple = ()) -> Optional[int]:
        """Execute a query and return last row id."""
        async with self.db_lock:
            conn = await self.get_connection()
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                await conn.commit()
                return cursor.lastrowid

    async def execute_many(self, query: str, params_list: List[tuple]) -> None:
        """Execute many queries in a batch."""
        async with self.db_lock:
            conn = await self.get_connection()
            async with conn.cursor() as cursor:
                await cursor.executemany(query, params_list)
                await conn.commit()

    async def fetch_one(self, query: str, params: tuple = ()) -> Optional[tuple]:
        """Fetch a single row from the database."""
        async with self.db_lock:
            conn = await self.get_connection()
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                return await cursor.fetchone()

    async def fetch_all(self, query: str, params: tuple = ()) -> List[tuple]:
        """Fetch all rows from the database."""
        async with self.db_lock:
            conn = await self.get_connection()
            async with conn.cursor() as cursor:
                await cursor.execute(query, params)
                return await cursor.fetchall()