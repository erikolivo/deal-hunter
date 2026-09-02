from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timezone
from typing import Any

from .config import Config
from .models import Product

logger = logging.getLogger(__name__)


class StateStore:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.state_file = config.state_file
        self._state: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load state: %s — starting fresh", e)
        return {"price_history": {}, "alert_cooldowns": {}, "processed_deals": []}

    def save(self) -> None:
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self._state, f, indent=2, ensure_ascii=False)
            logger.info("State saved to %s", self.state_file)
        except OSError as e:
            logger.error("Failed to save state: %s", e)

    # ── Price history ──────────────────────────────────────────────

    def record_price(self, product: Product) -> None:
        history = self._state.setdefault("price_history", {})
        asin_history: list[dict[str, Any]] = history.setdefault(product.asin, [])
        asin_history.append({
            "list_price": product.list_price,
            "deal_price": product.deal_price,
            "timestamp": product.fetched_at,
        })
        # Keep last 100 observations per ASIN
        if len(asin_history) > 100:
            history[product.asin] = asin_history[-100:]

    def get_price_history(self, asin: str) -> list[dict[str, Any]]:
        return self._state.get("price_history", {}).get(asin, [])

    def get_anchor_stats(self, asin: str) -> tuple[float | None, int]:
        history = self.get_price_history(asin)
        if not history:
            return None, 0
        list_prices = [h["list_price"] for h in history if h.get("list_price")]
        if not list_prices:
            return None, 0
        sorted_prices = sorted(list_prices)
        n = len(sorted_prices)
        if n % 2 == 0:
            median = (sorted_prices[n // 2 - 1] + sorted_prices[n // 2]) / 2
        else:
            median = sorted_prices[n // 2]
        return round(median, 2), n

    # ── Alert cooldowns ────────────────────────────────────────────

    def is_in_cooldown(self, asin: str) -> bool:
        cooldowns = self._state.get("alert_cooldowns", {})
        last_alert = cooldowns.get(asin)
        if not last_alert:
            return False
        try:
            last_time = datetime.fromisoformat(last_alert)
            now = datetime.now(timezone.utc)
            diff_hours = (now - last_time).total_seconds() / 3600
            return diff_hours < self.config.alert_cooldown_hours
        except (ValueError, TypeError):
            return False

    def set_alert_cooldown(self, asin: str) -> None:
        self._state.setdefault("alert_cooldowns", {})[asin] = datetime.now(timezone.utc).isoformat()

    # ── Processed deals ────────────────────────────────────────────

    def is_deal_processed(self, deal_id: str) -> bool:
        return deal_id in self._state.get("processed_deals", [])

    def mark_deal_processed(self, deal_id: str) -> None:
        processed = self._state.setdefault("processed_deals", [])
        if deal_id not in processed:
            processed.append(deal_id)
            # Keep last 5000
            if len(processed) > 5000:
                self._state["processed_deals"] = processed[-5000:]

    # ── Stats ──────────────────────────────────────────────────────

    def get_stats(self) -> dict[str, Any]:
        return {
            "tracked_asins": len(self._state.get("price_history", {})),
            "total_observations": sum(
                len(v) for v in self._state.get("price_history", {}).values()
            ),
            "active_cooldowns": len(self._state.get("alert_cooldowns", {})),
            "processed_deals": len(self._state.get("processed_deals", [])),
        }
