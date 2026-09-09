from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import requests
from bs4 import BeautifulSoup

from .config import Config
from .models import Product

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-EC,es;q=0.9,en;q=0.8",
}

CORAL_CATEGORIES = [
    "/ofertas/descuentos-del-mes/comisariato.html",
    "/ofertas/descuentos-del-mes/ferreteria.html",
    "/ofertas/descuentos-del-mes/hogar.html",
    "/ofertas/descuentos-del-mes/iluminacion.html",
    "/ofertas/descuentos-del-mes/material-electrico.html",
    "/ofertas/descuentos-del-mes/stanley.html",
    "/ofertas/descuentos-del-mes/textiles-y-manufactura.html",
    "/ofertas/descuentos-del-mes/automotriz.html",
    "/ofertas/descuentos-del-mes/maquinaria.html",
    "/ofertas/descuentos-del-mes/acabados.html",
    "/ofertas/fiestas-julianas/bebidas-y-licores.html",
    "/ofertas/fiestas-julianas/confiteria.html",
    "/ofertas/fiestas-julianas/hogar.html",
    "/ofertas/fiestas-julianas/snacks-y-mas.html",
]


class CoralClient:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.base_url = "https://www.coralhipermercados.com"
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.min_discount = getattr(config, "coral_min_discount_pct", 40.0)
        self.max_pages = getattr(config, "coral_max_pages_per_category", 10)
        self.categories = getattr(config, "coral_categories", CORAL_CATEGORIES)

    def search_multi_category(self) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for cat in self.categories:
            products = self._scrape_category(cat)
            for p in products:
                pid = p.get("product_id", "")
                if pid and pid not in seen:
                    seen.add(pid)
                    all_items.append(p)

        logger.info("Coral total unique products: %d", len(all_items))
        return all_items

    def _scrape_category(self, category_path: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        category_name = category_path.split("/")[-1].replace(".html", "")
        seen_urls: set[str] = set()

        for page in range(1, self.max_pages + 1):
            url = f"{self.base_url}{category_path}"
            params: dict[str, str] = {"product_list_limit": "24"}
            if page > 1:
                params["p"] = str(page)

            try:
                resp = self.session.get(url, params=params, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.warning("Coral request failed for %s page %d: %s", category_name, page, e)
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            product_items = soup.select("li.product-item")

            if not product_items:
                break

            new_count = 0
            for item in product_items:
                product = self._parse_item(item, category_name)
                if product is None:
                    continue
                if product["discount_pct"] < self.min_discount:
                    continue
                if product["url"] not in seen_urls:
                    seen_urls.add(product["url"])
                    items.append(product)
                    new_count += 1

            logger.info("Coral %s page %d: %d items, %d deals (≥%.0f%%)",
                        category_name, page, len(product_items), new_count, self.min_discount)

            if new_count == 0 and page > 1:
                break

            if page < self.max_pages:
                time.sleep(self.config.request_delay if hasattr(self.config, "request_delay") else 1.5)

        return items

    def _parse_item(self, item: Any, category: str) -> dict[str, Any] | None:
        try:
            name_tag = item.select_one("a.product-item-link")
            if not name_tag:
                return None
            url = name_tag.get("href", "")
            name = name_tag.get_text(strip=True)
            if not url or not name:
                return None

            price_box = item.select_one("div.price-box")
            product_id = price_box.get("data-product-id", "") if price_box else ""
            if not product_id:
                product_id = hashlib.md5(url.encode()).hexdigest()[:12]

            final_tag = item.select_one("span[data-price-type='finalPrice']")
            discount_price = float(final_tag.get("data-price-amount", 0)) if final_tag else 0.0

            old_tag = item.select_one("span[data-price-type='oldPrice']")
            original_price = float(old_tag.get("data-price-amount", 0)) if old_tag else 0.0

            if discount_price <= 0 or original_price <= 0 or original_price <= discount_price:
                return None

            discount_pct = round((original_price - discount_price) / original_price * 100, 1)

            img_tag = item.select_one("a.product-item-photo img")
            image_url = img_tag.get("src", "") if img_tag else ""

            badge_tag = item.select_one("p.product-item-discount")
            badge_text = badge_tag.get_text(strip=True).lower() if badge_tag else ""
            is_2x1 = "2x1" in badge_text or "dos por uno" in badge_text

            return {
                "product_id": str(product_id),
                "title": name[:200],
                "deal_price": round(discount_price, 2),
                "list_price": round(original_price, 2),
                "discount_pct": discount_pct,
                "url": url,
                "image_url": image_url,
                "category": category,
                "is_2x1": is_2x1,
                "store": "coral",
            }
        except (ValueError, TypeError, AttributeError):
            return None
