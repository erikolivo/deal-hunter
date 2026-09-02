from __future__ import annotations

import logging
from typing import Any

import requests

from .config import Config
from .models import Product

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

VERDICT_EMOJI = {
    "STRONG_BUY": "\U0001f7e2",
    "WATCH": "\U0001f7e1",
    "SUSPICIOUS_ANCHOR": "\U0001f6ab",
    "OUT_OF_RANGE": "\u26aa",
}


class TelegramNotifier:
    def __init__(self, config: Config) -> None:
        self.config = config

    def send_alert(self, product: Product) -> bool:
        text = self._format_message(product)
        if self.config.dry_run:
            logger.info("[DRY RUN] Alert for %s:\n%s", product.asin, text)
            return True

        url = TELEGRAM_API.format(token=self.config.telegram_bot_token)
        payload = {
            "chat_id": self.config.telegram_chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            logger.info("Alert sent for %s", product.asin)
            return True
        except requests.RequestException as e:
            logger.error("Failed to send alert for %s: %s", product.asin, e)
            return False

    def send_summary(self, results: dict[str, list[Product]], stats: dict[str, Any]) -> bool:
        lines = [
            "<b>\U0001f4ca Deal Hunter Summary</b>",
            "",
            f"\U0001f7e2 STRONG_BUY: {len(results.get('STRONG_BUY', []))}",
            f"\U0001f7e1 WATCH: {len(results.get('WATCH', []))}",
            f"\U0001f6ab SUSPICIOUS: {len(results.get('SUSPICIOUS_ANCHOR', []))}",
            f"\u26aa OUT_OF_RANGE: {len(results.get('OUT_OF_RANGE', []))}",
            "",
            f"\U0001f4c8 Tracked ASINs: {stats.get('tracked_asins', 0)}",
            f"\U0001f4ca Total observations: {stats.get('total_observations', 0)}",
        ]
        text = "\n".join(lines)

        if self.config.dry_run:
            logger.info("[DRY RUN] Summary:\n%s", text)
            return True

        url = TELEGRAM_API.format(token=self.config.telegram_bot_token)
        payload = {
            "chat_id": self.config.telegram_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        try:
            resp = requests.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            return True
        except requests.RequestException as e:
            logger.error("Failed to send summary: %s", e)
            return False

    def _format_message(self, p: Product) -> str:
        emoji = VERDICT_EMOJI.get(p.verdict, "\u2753")
        lines = [
            f"{emoji} <b>{p.verdict}</b>",
            "",
            f"\U0001f4f1 <b>{_escape(p.title[:80])}</b>",
            "",
            f"\U0001f3f7\ufe0f ASIN: <code>{p.asin}</code>",
            f"\U0001f4b0 Deal: <b>${p.deal_price:.2f}</b>",
            f"\U0001f4b2 List: <s>${p.list_price:.2f}</s>",
            f"\U0001f4b5 Savings: ${p.savings_usd:.2f} ({p.calculated_discount_pct:.1f}%)",
        ]
        if p.rating is not None:
            lines.append(f"\u2b50 Rating: {p.rating:.1f}")
        if p.reviews_count is not None:
            lines.append(f"\U0001f4ac Reviews: {p.reviews_count:,}")
        if p.anchor_median is not None:
            lines.append(f"\U0001f4d0 Anchor median: ${p.anchor_median:.2f} ({p.anchor_observations} obs)")
        if p.time_remaining:
            lines.append(f"\u23f0 Time left: {p.time_remaining}")
        if p.url:
            lines.append(f"\U0001f517 <a href=\"{p.url}\">View deal</a>")
        return "\n".join(lines)


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
