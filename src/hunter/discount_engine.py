from __future__ import annotations

import logging
from typing import Any

from .config import Config
from .models import Product
from .state_store import StateStore

logger = logging.getLogger(__name__)

# Veredicts
STRONG_BUY = "STRONG_BUY"
WATCH = "WATCH"
SUSPICIOUS_ANCHOR = "SUSPICIOUS_ANCHOR"
OUT_OF_RANGE = "OUT_OF_RANGE"


class DiscountEngine:
    def __init__(self, config: Config, state: StateStore) -> None:
        self.config = config
        self.state = state

    def evaluate(self, product: Product) -> Product:
        # Step 1: Check discount is in range
        if not (self.config.min_discount_pct <= product.calculated_discount_pct <= self.config.max_discount_pct):
            product.verdict = OUT_OF_RANGE
            return product

        # Step 2: Check price bounds
        if product.deal_price < self.config.min_price or product.deal_price > self.config.max_price:
            product.verdict = OUT_OF_RANGE
            return product

        # Step 3: Record price and get anchor stats
        self.state.record_price(product)
        anchor_median, observations = self.state.get_anchor_stats(product.asin)
        product.anchor_median = anchor_median
        product.anchor_observations = observations

        # Step 4: If no history yet, mark as WATCH
        if anchor_median is None or observations < self.config.min_anchor_observations:
            product.verdict = WATCH
            return product

        # Step 5: Validate anchor — if current list_price inflated vs history → suspicious
        if anchor_median > 0:
            inflation = product.list_price / anchor_median
            if inflation >= self.config.anchor_inflation_ratio:
                product.verdict = SUSPICIOUS_ANCHOR
                return product

        # Step 6: All good
        product.verdict = STRONG_BUY
        return product

    def evaluate_all(self, products: list[Product]) -> dict[str, list[Product]]:
        results: dict[str, list[Product]] = {
            STRONG_BUY: [],
            WATCH: [],
            SUSPICIOUS_ANCHOR: [],
            OUT_OF_RANGE: [],
        }
        for p in products:
            self.evaluate(p)
            results[p.verdict].append(p)
        return results
