from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Product:
    asin: str
    title: str
    deal_price: float
    list_price: float
    store: str = "amazon"
    deal_id: str = ""
    url: str = ""
    image_url: str = ""
    rating: float | None = None
    reviews_count: int | None = None
    deal_end_time: str | None = None
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Computed fields
    calculated_discount_pct: float = 0.0
    verdict: str = "PENDING"
    anchor_median: float | None = None
    anchor_observations: int = 0

    def __post_init__(self) -> None:
        self.calculated_discount_pct = self._calc_discount()

    def _calc_discount(self) -> float:
        if self.list_price <= 0 or self.deal_price <= 0:
            return 0.0
        if self.deal_price >= self.list_price:
            return 0.0
        raw = (self.list_price - self.deal_price) / self.list_price * 100
        return round(min(max(raw, 0.0), 100.0), 2)

    @property
    def savings_usd(self) -> float:
        return round(max(self.list_price - self.deal_price, 0.0), 2)

    @property
    def time_remaining(self) -> str | None:
        if not self.deal_end_time:
            return None
        try:
            end = datetime.fromisoformat(self.deal_end_time.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = end - now
            if delta.total_seconds() <= 0:
                return "Expired"
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            if hours > 24:
                days = hours // 24
                hours = hours % 24
                return f"{days}d {hours}h {minutes}m"
            return f"{hours}h {minutes}m"
        except (ValueError, TypeError):
            return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "asin": self.asin,
            "title": self.title,
            "deal_price": self.deal_price,
            "list_price": self.list_price,
            "store": self.store,
            "calculated_discount_pct": self.calculated_discount_pct,
            "verdict": self.verdict,
            "deal_id": self.deal_id,
            "url": self.url,
            "image_url": self.image_url,
            "rating": self.rating,
            "reviews_count": self.reviews_count,
            "deal_end_time": self.deal_end_time,
            "fetched_at": self.fetched_at,
            "anchor_median": self.anchor_median,
            "anchor_observations": self.anchor_observations,
        }

    @classmethod
    def from_api_deal(cls, deal: dict[str, Any]) -> Product | None:
        try:
            asin = deal.get("product_asin") or deal.get("asin", "")
            if not asin:
                return None

            deal_price = _extract_price(deal, "deal_price") or _extract_price(deal, "price")
            list_price = _extract_price(deal, "list_price") or _extract_price(deal, "original_price")
            if deal_price is None or list_price is None or deal_price <= 0 or list_price <= 0:
                return None

            return cls(
                asin=asin,
                title=deal.get("product_title") or deal.get("deal_title") or deal.get("title", "Unknown"),
                deal_price=deal_price,
                list_price=list_price,
                store="amazon",
                deal_id=deal.get("deal_id", ""),
                url=deal.get("product_url") or deal.get("deal_url") or deal.get("url", ""),
                image_url=deal.get("product_image") or deal.get("deal_photo") or deal.get("image", ""),
                rating=_safe_float(deal.get("rating")),
                reviews_count=_safe_int(deal.get("reviews_count")),
                deal_end_time=deal.get("deal_end_time") or deal.get("deal_ends_at") or deal.get("end_time"),
            )
        except (ValueError, TypeError, KeyError):
            return None

    @classmethod
    def from_aliexpress(cls, item: dict[str, Any]) -> Product | None:
        try:
            pid = str(item.get("product_id") or item.get("id", ""))
            if not pid:
                return None

            # AliExpress prices can be nested or flat
            deal_price = (
                _extract_price(item, "price")
                or _extract_price(item, "sale_price")
                or _extract_price(item, "current_price")
            )
            list_price = (
                _extract_price(item, "original_price")
                or _extract_price(item, "regular_price")
                or _extract_price(item, "pre_crossed_out_price")
            )

            # If no list_price, try to extract from price range
            if list_price is None and isinstance(item.get("price"), dict):
                min_p = item["price"].get("min_value") or item["price"].get("min")
                max_p = item["price"].get("max_value") or item["price"].get("max")
                if min_p and max_p:
                    deal_price = _safe_float(min_p)
                    list_price = _safe_float(max_p)

            if deal_price is None or list_price is None or deal_price <= 0 or list_price <= 0:
                return None

            # AliExpress: if deal >= list, no discount
            if deal_price >= list_price:
                return None

            title = (
                item.get("title")
                or item.get("product_title")
                or item.get("name")
                or "Unknown"
            )

            # Build URL
            url = item.get("product_url") or item.get("url") or item.get("detail_url") or ""
            if not url and pid:
                url = f"https://www.aliexpress.com/item/{pid}.html"

            return cls(
                asin=pid,
                title=title[:200],
                deal_price=deal_price,
                list_price=list_price,
                store="aliexpress",
                deal_id=str(item.get("deal_id", "")),
                url=url,
                image_url=item.get("image") or item.get("product_image") or item.get("main_image") or "",
                rating=_safe_float(item.get("rating") or item.get("average_star")),
                reviews_count=_safe_int(item.get("reviews_count") or item.get("trade_count") or item.get("orders")),
            )
        except (ValueError, TypeError, KeyError):
            return None


def _extract_price(deal: dict[str, Any], key: str) -> float | None:
    val = deal.get(key)
    if val is None:
        return None
    if isinstance(val, dict):
        # Try common price keys: amount, min_value, min, value
        for field in ("amount", "min_value", "min", "value"):
            if field in val:
                return _safe_float(val[field])
        return None
    return _safe_float(val)


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
