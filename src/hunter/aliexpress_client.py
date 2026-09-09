from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://ali-express1.p.rapidapi.com"


class AliExpressClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "X-RapidAPI-Key": config.rapidapi_key,
            "X-RapidAPI-Host": "ali-express1.p.rapidapi.com",
        })

    def search_deals(
        self,
        query: str = "deals",
        min_discount: int = 50,
        country: str = "US",
        max_pages: int = 3,
    ) -> list[dict[str, Any]]:
        all_products: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for page in range(1, max_pages + 1):
            params = {
                "query": query,
                "country": country,
                "page": str(page),
            }

            try:
                resp = self.session.get(f"{BASE_URL}/search", params=params, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning("AliExpress request failed on page %d: %s", page, e)
                break

            data = resp.json()
            products = _extract_products(data)

            if not products:
                logger.info("AliExpress: no more products on page %d", page)
                break

            if page == 1 and products:
                logger.info("AliExpress sample keys: %s", list(products[0].keys()))
                logger.info("AliExpress sample: %s", {k: v for k, v in list(products[0].items())[:12]})

            new_count = 0
            for p in products:
                pid = str(p.get("product_id") or p.get("id", ""))
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    all_products.append(p)
                    new_count += 1

            logger.info("AliExpress page %d: %d products (%d new)", page, len(products), new_count)

            if new_count == 0:
                break

            if page < max_pages:
                time.sleep(1)

        logger.info("AliExpress total unique products: %d", len(all_products))
        return all_products


def _extract_products(data: dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(data, dict):
        # Try common response structures
        for key in ("products", "items", "data", "results"):
            if key in data and isinstance(data[key], list):
                return data[key]
        # If data itself is a list
        if isinstance(data.get("data"), list):
            return data["data"]
    return []
