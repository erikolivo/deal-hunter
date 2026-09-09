from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://aliexpress-true-api.p.rapidapi.com"
API_HOST = "aliexpress-true-api.p.rapidapi.com"

SEARCH_QUERIES = [
    "flash deal",
    "clearance",
    "sale",
    "hot sale",
    "best seller",
]


class AliExpressClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "X-RapidAPI-Key": config.rapidapi_key,
            "X-RapidAPI-Host": API_HOST,
        })

    def search_products(
        self,
        query: str = "phone",
        country: str = "US",
        max_pages: int = 2,
    ) -> list[dict[str, Any]]:
        all_products: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for page in range(1, max_pages + 1):
            params = {
                "keywords": query,
                "page_no": str(page),
                "page_size": "20",
                "target_currency": "USD",
                "target_language": "EN",
                "ship_to_country": country,
            }

            try:
                resp = self.session.get(f"{BASE_URL}/api/v3/products", params=params, timeout=30)
                logger.info("AliExpress response status: %d for query='%s' page=%d", resp.status_code, query, page)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning("AliExpress request failed: %s", e)
                if hasattr(e, 'response') and e.response is not None:
                    logger.warning("AliExpress response body: %s", e.response.text[:500])
                break

            data = resp.json()

            if page == 1:
                logger.info("AliExpress response keys: %s", list(data.keys()) if isinstance(data, dict) else type(data))

            products = _extract_products(data)

            if not products:
                logger.info("AliExpress: no products extracted for query='%s' page=%d", query, page)
                break

            if page == 1 and products:
                logger.info("AliExpress sample keys: %s", list(products[0].keys()))
                logger.info("AliExpress sample: %s", {k: v for k, v in list(products[0].items())[:15]})

            new_count = 0
            for p in products:
                pid = str(p.get("product_id") or p.get("id") or p.get("item_id") or "")
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

    def search_multi_query(self, country: str = "US") -> list[dict[str, Any]]:
        """Try multiple search queries to maximize product coverage."""
        all_products: list[dict[str, Any]] = []
        seen_ids: set[str] = set()

        for query in SEARCH_QUERIES:
            products = self.search_products(query=query, country=country, max_pages=1)
            for p in products:
                pid = str(p.get("product_id") or p.get("id") or p.get("item_id") or "")
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    all_products.append(p)

        logger.info("AliExpress multi-query total: %d products", len(all_products))
        return all_products


def _extract_products(data: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []

    # Handle: {result: {resultList: [{item: {...}}]}}
    result = data.get("result")
    if isinstance(result, dict):
        result_list = result.get("resultList")
        if isinstance(result_list, list):
            # Extract items from {item: {...}} wrappers
            items = []
            for entry in result_list:
                if isinstance(entry, dict):
                    item = entry.get("item")
                    if isinstance(item, dict):
                        items.append(item)
                    else:
                        items.append(entry)
            if items:
                return items

        # Handle: {result: {products: [...]}}
        for key in ("products", "items", "list", "data"):
            val = result.get(key)
            if isinstance(val, list) and val:
                return val

    # Handle: {data: {products: [...]}}
    inner = data.get("data")
    if isinstance(inner, dict):
        for key in ("products", "items", "list", "resultList"):
            val = inner.get(key)
            if isinstance(val, list) and val:
                return val

    # Handle: {products: [...]} or {items: [...]}
    for key in ("products", "items", "list"):
        val = data.get(key)
        if isinstance(val, list) and val:
            return val

    return []
