import hashlib
import logging
import secrets
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path: str = "DracoSoft_Server/data/server.db"):
        self.db_path = Path(db_path)

        # Create data directory if it doesn't exist
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database
        self._init_database()

    def _init_database(self):
        """Initialize the database with required tables."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()

            # Enable foreign keys
            cursor.execute("PRAGMA foreign_keys = ON")

            # Create users table
            cursor.execute("""
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
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)

            conn.commit()

    def _hash_password(self, password: str) -> str:
        """Hash a password using SHA-256 and a salt."""
        salt = secrets.token_hex(16)
        hash_obj = hashlib.sha256(f"{password}{salt}".encode())
        return f"{salt}:{hash_obj.hexdigest()}"

    def create_user(self, username: str, password: str, email: str = None) -> bool:
        """Create a new user in the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Check if user exists
                cursor.execute("SELECT username FROM users WHERE username = ?", (username,))
                if cursor.fetchone():
                    logger.warning(f"User {username} already exists")
                    return False

                # Hash password
                password_hash = self._hash_password(password)

                # Insert user
                cursor.execute(
                    "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
                    (username, password_hash, email)
                )

                conn.commit()
                logger.info(f"Successfully created user: {username}")
                return True

        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return False

    def list_users(self):
        """List all users in the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT id, username, email, created_at, last_login, status 
                    FROM users
                """)
                users = cursor.fetchall()

                if not users:
                    logger.info("No users found in database")
                    return

                logger.info("\nRegistered Users:")
                for user in users:
                    logger.info(f"ID: {user[0]}")
                    logger.info(f"Username: {user[1]}")
                    logger.info(f"Email: {user[2]}")
                    logger.info(f"Created: {user[3]}")
                    logger.info(f"Last Login: {user[4]}")
                    logger.info(f"Status: {user[5]}")
                    logger.info("-" * 40)

        except Exception as e:
            logger.error(f"Error listing users: {e}")


def main():
    db_manager = DatabaseManager()

    # Create default admin user
    username = input("Enter username (default: admin): ") or "admin"
    password = input("Enter password (default: admin123): ") or "admin123"
    email = input("Enter email (optional): djames@atcoks.org ")

    if db_manager.create_user(username, password, email):
        logger.info("Default user created successfully")
    else:
        logger.error("Failed to create default user")

    # List all users
    db_manager.list_users()


if __name__ == "__main__":
    main()