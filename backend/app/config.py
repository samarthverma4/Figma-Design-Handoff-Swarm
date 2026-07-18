"""Environment loading + fail-fast validation.

Secrets are read from a .env file. Values are NEVER logged. Missing required
keys raise a clear ConfigError at import/startup time so the process dies with
an actionable message instead of a deep stack trace mid-run.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the backend/ directory (this file lives in backend/app/).
_BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_DIR / ".env")


class ConfigError(RuntimeError):
    """Raised at startup when required configuration is missing/invalid."""


def _require(name: str) -> str:
    val = os.getenv(name, "").strip()
    if not val:
        raise ConfigError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return val


def _optional(name: str, default: str) -> str:
    val = os.getenv(name, "").strip()
    return val or default


@dataclass(frozen=True)
class Settings:
    # Figma
    figma_token: str
    figma_file_key: str
    # Slack
    slack_bot_token: str
    slack_channel_id: str
    # Azure OpenAI
    azure_api_key: str
    azure_endpoint: str
    azure_deployment: str
    azure_api_version: str
    # Tuning
    delivery_destination: str = "slack"
    http_timeout_seconds: float = 30.0
    max_tool_retries: int = 3
    retry_max_backoff_seconds: float = 3.0  # caps every heal/backoff sleep (demo snappiness)
    asset_dir: Path = field(default_factory=lambda: _BACKEND_DIR / "exports")
    sqlite_path: Path = field(default_factory=lambda: _BACKEND_DIR / "swarm_memory.db")

    def redacted(self) -> dict:
        """Safe-to-log view: presence booleans only, never values."""
        return {
            "figma_token": _mask(self.figma_token),
            "figma_file_key": self.figma_file_key,
            "slack_bot_token": _mask(self.slack_bot_token),
            "slack_channel_id": self.slack_channel_id,
            "azure_api_key": _mask(self.azure_api_key),
            "azure_endpoint": self.azure_endpoint,
            "azure_deployment": self.azure_deployment,
            "delivery_destination": self.delivery_destination,
        }


def _mask(secret: str) -> str:
    if not secret:
        return "<missing>"
    return f"<set:{len(secret)} chars>"


def load_settings() -> Settings:
    """Validate + build Settings. Raises ConfigError listing every missing key."""
    missing: list[str] = []

    def req(name: str) -> str:
        try:
            return _require(name)
        except ConfigError:
            missing.append(name)
            return ""

    figma_token = req("FIGMA_TOKEN")
    figma_file_key = req("FIGMA_FILE_KEY")
    slack_bot_token = req("SLACK_BOT_TOKEN")
    slack_channel_id = req("SLACK_CHANNEL_ID")
    azure_api_key = req("AZURE_OPENAI_API_KEY")
    azure_endpoint = req("AZURE_OPENAI_ENDPOINT")

    if missing:
        raise ConfigError(
            "Missing required environment variables: "
            + ", ".join(missing)
            + ".\nCopy .env.example to .env and fill them in."
        )

    asset_dir = Path(_optional("ASSET_DIR", str(_BACKEND_DIR / "exports")))
    if not asset_dir.is_absolute():
        asset_dir = (_BACKEND_DIR / asset_dir).resolve()
    sqlite_path = Path(_optional("SQLITE_PATH", str(_BACKEND_DIR / "swarm_memory.db")))
    if not sqlite_path.is_absolute():
        sqlite_path = (_BACKEND_DIR / sqlite_path).resolve()

    asset_dir.mkdir(parents=True, exist_ok=True)

    return Settings(
        figma_token=figma_token,
        figma_file_key=figma_file_key,
        slack_bot_token=slack_bot_token,
        slack_channel_id=slack_channel_id,
        azure_api_key=azure_api_key,
        azure_endpoint=azure_endpoint.rstrip("/"),
        azure_deployment=_optional("AZURE_OPENAI_DEPLOYMENT", "gpt-4.1-nano"),
        azure_api_version=_optional("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
        delivery_destination=_optional("DELIVERY_DESTINATION", "slack").lower(),
        http_timeout_seconds=float(_optional("HTTP_TIMEOUT_SECONDS", "30")),
        max_tool_retries=int(_optional("MAX_TOOL_RETRIES", "3")),
        retry_max_backoff_seconds=float(_optional("RETRY_MAX_BACKOFF_SECONDS", "3")),
        asset_dir=asset_dir,
        sqlite_path=sqlite_path,
    )


# Lazily-built singleton so importing submodules doesn't force full validation
# (tests can construct Settings directly).
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
