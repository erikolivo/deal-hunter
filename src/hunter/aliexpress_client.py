from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .config import Config

logger = logging.getLogger(__name__)

BASE_URL = "https://ali-express1.p.rapidapi.com"

# Search terms that tend to return products with discounts
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
            "X-RapidAPI-Host": "ali-express1.p.rapidapi.com",
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
                "query": query,
                "country": country,
                "page": str(page),
            }

            try:
                resp = self.session.get(f"{BASE_URL}/search", params=params, timeout=30)
                logger.info("AliExpress response status: %d for query='%s' page=%d", resp.status_code, query, page)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning("AliExpress request failed: %s", e)
                # Log response body if available
                if hasattr(e, 'response') and e.response is not None:
                    logger.warning("AliExpress response body: %s", e.response.text[:500])
                break

            data = resp.json()

            # Log raw response structure on first page
            if page == 1:
                if isinstance(data, dict):
                    logger.info("AliExpress response keys: %s", list(data.keys()))
                    inner = data.get("data")
                    if isinstance(inner, dict):
                        logger.info("AliExpress 'data' keys: %s", list(inner.keys()))
                        for k, v in inner.items():
                            if isinstance(v, list):
                                logger.info("AliExpress data.'%s' is list with %d items", k, len(v))
                                if v:
                                    logger.info("AliExpress data.'%s' sample keys: %s", k, list(v[0].keys()) if isinstance(v[0], dict) else type(v[0]))
                            elif isinstance(v, dict):
                                logger.info("AliExpress data.'%s' is dict with keys: %s", k, list(v.keys())[:10])
                            else:
                                logger.info("AliExpress data.'%s' = %s", k, str(v)[:100])
                    elif isinstance(inner, list):
                        logger.info("AliExpress 'data' is a list with %d items", len(inner))
                elif isinstance(data, list):
                    logger.info("AliExpress response is a list with %d items", len(data))

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

    # Handle: {data: {result: [...], data: [...]}}
    inner = data.get("data")
    if isinstance(inner, dict):
        for key in ("data", "result", "items", "products", "list"):
            val = inner.get(key)
            if isinstance(val, list) and val:
                return val
            # Handle: {data: {data: {items: [...]}}}
            if isinstance(val, dict):
                for inner_key in ("items", "products", "list"):
                    inner_val = val.get(inner_key)
                    if isinstance(inner_val, list):
                        return inner_val

    # Handle: {data: [...]}
    if isinstance(inner, list):
        return inner

    # Handle: {products: [...]} at top level
    for key in ("products", "items", "results", "data"):
        val = data.get(key)
        if isinstance(val, list):
            return val

    return []
