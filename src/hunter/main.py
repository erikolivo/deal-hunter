from __future__ import annotations

import logging
import sys

from .config import Config, load_config
from .amazon_deals_client import AmazonDealsClient
from .aliexpress_client import AliExpressClient
from .coral_client import CoralClient
from .discount_engine import DiscountEngine
from .models import Product
from .state_store import StateStore
from .telegram_notifier import TelegramNotifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("hunter")


def run(config: Config | None = None, only: str | None = None) -> None:
    cfg = config or load_config()
    errors = cfg.validate()
    if errors:
        for e in errors:
            logger.error("Config error: %s", e)
        sys.exit(1)

    logger.info("Deal Hunter starting (dry_run=%s, only=%s)", cfg.dry_run, only or "all")

    state = StateStore(cfg)
    engine = DiscountEngine(cfg, state)
    notifier = TelegramNotifier(cfg)

    all_products: list[Product] = []

    # ── Amazon ─────────────────────────────────────────────────────
    if only in (None, "amazon", "api"):
        try:
            amazon_client = AmazonDealsClient(cfg)
            raw_deals = amazon_client.fetch_deals()
            logger.info("Amazon raw deals: %d", len(raw_deals))
            for deal in raw_deals:
                p = Product.from_api_deal(deal)
                if p is not None:
                    all_products.append(p)
        except Exception as e:
            logger.error("Amazon fetch failed: %s", e)

    # ── AliExpress ─────────────────────────────────────────────────
    if only in (None, "aliexpress", "api"):
        try:
            ali_client = AliExpressClient(cfg)
            raw_items = ali_client.search_multi_query()
            logger.info("AliExpress raw items: %d", len(raw_items))
            for item in raw_items:
                p = Product.from_aliexpress(item)
                if p is not None:
                    all_products.append(p)
        except Exception as e:
            logger.error("AliExpress fetch failed: %s", e)

    # ── Coral (Ecuador) ────────────────────────────────────────────
    if only in (None, "coral"):
        try:
            coral_client = CoralClient(cfg)
            raw_coral = coral_client.search_multi_category()
            logger.info("Coral raw items: %d", len(raw_coral))
            for item in raw_coral:
                p = Product.from_coral(item)
                if p is not None:
                    all_products.append(p)
        except Exception as e:
            logger.error("Coral fetch failed: %s", e)

    logger.info("Total valid products: %d", len(all_products))

    # ── Evaluate ───────────────────────────────────────────────────
    results = engine.evaluate_all(all_products)

    # ── Alert ──────────────────────────────────────────────────────
    alerts_sent = 0
    for verdict in ("STRONG_BUY", "WATCH"):
        for p in results[verdict]:
            if not state.is_in_cooldown(f"{p.store}:{p.asin}"):
                if notifier.send_alert(p):
                    state.set_alert_cooldown(f"{p.store}:{p.asin}")
                    alerts_sent += 1

    # ── Persist state ──────────────────────────────────────────────
    for p in all_products:
        state.record_price(p)
        if p.deal_id:
            state.mark_deal_processed(p.deal_id)

    state.save()

    # ── Summary only if there were alerts ──────────────────────────
    if alerts_sent > 0:
        stats = state.get_stats()
        notifier.send_summary(results, stats)

    logger.info(
        "Run complete: %d processed, %d alerts sent",
        len(all_products),
        alerts_sent,
    )


if __name__ == "__main__":
    only_arg = None
    if "--only" in sys.argv:
        idx = sys.argv.index("--only")
        if idx + 1 < len(sys.argv):
            only_arg = sys.argv[idx + 1]
    run(only=only_arg)
