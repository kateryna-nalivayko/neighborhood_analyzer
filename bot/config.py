"""Налаштування застосунку: читаємо секрети зі змінних оточення / файлу .env."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Не вистачає обов'язкового налаштування."""


@dataclass(frozen=True)
class Settings:
    telegram_token: str
    google_api_key: str
    language: str = "uk"
    region: str = "UA"
    default_radius: int = 1000
    cache_ttl_seconds: int = 3600


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"Змінна {name} має бути цілим числом, отримано: {raw!r}") from exc


def load_settings() -> Settings:
    """Завантажує налаштування з .env (якщо він є) та змінних оточення."""
    load_dotenv()

    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    api_key = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()

    missing = [name for name, value in (
        ("TELEGRAM_BOT_TOKEN", token),
        ("GOOGLE_MAPS_API_KEY", api_key),
    ) if not value]
    if missing:
        raise ConfigError(
            "Не задано: " + ", ".join(missing)
            + ". Скопіюйте .env.example у .env і впишіть свої ключі."
        )

    radius = _int_env("DEFAULT_RADIUS", 1000)
    if not 100 <= radius <= 5000:
        raise ConfigError("DEFAULT_RADIUS має бути в межах 100–5000 метрів")

    return Settings(
        telegram_token=token,
        google_api_key=api_key,
        language=os.getenv("LANGUAGE", "uk").strip() or "uk",
        region=os.getenv("REGION", "UA").strip() or "UA",
        default_radius=radius,
        cache_ttl_seconds=_int_env("CACHE_TTL_SECONDS", 3600),
    )
