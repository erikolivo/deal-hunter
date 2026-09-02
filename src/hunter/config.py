from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Config:
    # Discount range (inclusive)
    min_discount_pct: float = 60.0
    max_discount_pct: float = 90.0

    # Price bounds (USD) — ignore deals outside this range
    min_price: float = 5.0
    max_price: float = 500.0

    # Anchor validation: if current list_price > median * ratio → suspicious
    anchor_inflation_ratio: float = 1.8

    # Minimum historical observations before trusting an anchor
    min_anchor_observations: int = 3

    # Cooldown: don't re-alert the same ASIN within N hours
    alert_cooldown_hours: int = 24

    # API pagination
    deals_page_size: int = 50
    max_pages: int = 10

    # RapidAPI
    rapidapi_key: str = field(default_factory=lambda: os.getenv("RAPIDAPI_KEY", ""))

    # Telegram
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))

    # Dry run: if True, print instead of sending Telegram
    dry_run: bool = field(default_factory=lambda: os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes"))

    # State file path
    state_file: str = "state.json"

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.rapidapi_key:
            errors.append("RAPIDAPI_KEY not set")
        if not self.dry_run:
            if not self.telegram_bot_token:
                errors.append("TELEGRAM_BOT_TOKEN not set")
            if not self.telegram_chat_id:
                errors.append("TELEGRAM_CHAT_ID not set")
        return errors


def load_config() -> Config:
    return Config()
