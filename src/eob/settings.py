"""Cloud-mode settings. Values come from the environment or a local .env file (never committed)."""
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_FILE = ROOT / ".env"
DEFAULT_MODEL = "claude-sonnet-5-5"
DEFAULT_EFFORT = "medium"

# USD per million tokens (input, output), from the Claude model docs (checked Nov 2026).
# Estimates only: the Claude Console shows actual billing.
PRICES_PER_MTOK = {
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}


class MissingKeyError(RuntimeError):
    pass


@dataclass(frozen=True)
class CloudSettings:
    model: str
    effort: str | None


def load_cloud_settings(env_file: Path | None = DEFAULT_ENV_FILE) -> CloudSettings:
    if env_file is not None and env_file.exists():
        load_dotenv(env_file)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise MissingKeyError("ANTHROPIC_API_KEY is not set. Put it in the .env file (see .env.example).")
    return CloudSettings(
        model=os.environ.get("EOB_CLOUD_MODEL") or DEFAULT_MODEL,
        effort=os.environ.get("EOB_CLOUD_EFFORT") or DEFAULT_EFFORT,
    )


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float | None:
    prices = PRICES_PER_MTOK.get(model)
    if prices is None:
        return None
    return (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000


class MissingLocalModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalSettings:
    model: str
    base_url: str
    think: bool | None


def load_local_settings(env_file: Path | None = DEFAULT_ENV_FILE) -> LocalSettings:
    if env_file is not None and env_file.exists():
        load_dotenv(env_file)
    model = (os.environ.get("EOB_LOCAL_MODEL") or "").strip()
    if not model:
        raise MissingLocalModelError(
            "EOB_LOCAL_MODEL is not set. Add a line like EOB_LOCAL_MODEL=qwen3:8b to the .env file."
        )
    think_text = (os.environ.get("EOB_LOCAL_THINK") or "").strip().lower()
    return LocalSettings(
        model=model,
        base_url=os.environ.get("EOB_LOCAL_URL") or "http://localhost:11434",
        think={"true": True, "false": False}.get(think_text),
    )
