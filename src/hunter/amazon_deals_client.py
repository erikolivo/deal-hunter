from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://real-time-amazon-data.p.rapidapi.com/deals-v2"


class DealsFetchError(Exception):
    pass


class AmazonDealsClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "X-RapidAPI-Key": config.rapidapi_key,
            "X-RapidAPI-Host": "real-time-amazon-data.p.rapidapi.com",
        })

    def fetch_deals(
        self,
        discount_range: str = "5",
        country: str = "US",
    ) -> list[dict[str, Any]]:
        all_deals: list[dict[str, Any]] = []
        seen_asins: set[str] = set()

        for page in range(1, self.config.max_pages + 1):
            params = {
                "discount_range": discount_range,
                "country": country,
                "page_number": str(page),
                "page_size": str(self.config.deals_page_size),
            }

            try:
                resp = self.session.get(BASE_URL, params=params, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning("Request failed on page %d: %s", page, e)
                break

            data = resp.json()
            deals = _extract_deals(data)

            if not deals:
                logger.info("No more deals on page %d", page)
                break

            new_count = 0
            for deal in deals:
                asin = deal.get("product_asin") or deal.get("asin", "")
                if asin and asin not in seen_asins:
                    seen_asins.add(asin)
                    all_deals.append(deal)
                    new_count += 1

            logger.info("Page %d: %d deals (%d new)", page, len(deals), new_count)

            if new_count == 0:
                break

            # Polite delay between pages
            if page < self.config.max_pages:
                time.sleep(1)

        logger.info("Total unique deals fetched: %d", len(all_deals))
        return all_deals


def _extract_deals(data: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        inner = data.get("data", data)
        if isinstance(inner, dict):
            return inner.get("deals", [])
    return []
