from dotenv import load_dotenv
import os
import sys
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, ValidationError

# Try to load .env from infrastructure directory (local development)
dotenv_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), '../../../infrastructure/.env')
)
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    print(f'Loaded .env from: {dotenv_path}')
else:
    # Try to load from backend directory
    backend_dotenv = os.path.join(os.path.dirname(__file__), '../../.env')
    if os.path.exists(backend_dotenv):
        load_dotenv(backend_dotenv)
        print(f'Loaded .env from: {backend_dotenv}')
    else:
        print('No .env file found, using environment variables only')


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = Field(..., env="DATABASE_URL")

    # Ollama
    ollama_url: str = Field(..., env="OLLAMA_URL")

    # Backend
    backend_port: int = 8000
    secret_key: str = Field(..., env="SECRET_KEY")

    # MCP (optional for now)
    mcp_server_url: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )


def validate_settings():
    """Validate that all required settings are present."""
    required_vars = ["DATABASE_URL", "OLLAMA_URL", "SECRET_KEY"]
    missing = [var for var in required_vars if not os.environ.get(var)]

    if missing:
        print("\n❌ ERROR: Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        print("\nPlease set these environment variables before starting the application.")
        print("See .env.example for reference.\n")
        sys.exit(1)

    print("✅ All required environment variables are set")


# Validate settings on import
try:
    validate_settings()
    settings = Settings()
    print(f"✅ Configuration loaded successfully")
    print(f"  - Database: {settings.database_url.split('://')[0]}://...")
    print(f"  - Ollama: {settings.ollama_url}")
except ValidationError as e:
    print(f"\n❌ Configuration error: {e}\n")
    sys.exit(1)