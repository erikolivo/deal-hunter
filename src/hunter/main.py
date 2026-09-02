from __future__ import annotations

import logging
import sys

from .config import Config, load_config
from .amazon_deals_client import AmazonDealsClient
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


def run(config: Config | None = None) -> None:
    cfg = config or load_config()
    errors = cfg.validate()
    if errors:
        for e in errors:
            logger.error("Config error: %s", e)
        sys.exit(1)

    logger.info("Deal Hunter starting (dry_run=%s)", cfg.dry_run)

    client = AmazonDealsClient(cfg)
    state = StateStore(cfg)
    engine = DiscountEngine(cfg, state)
    notifier = TelegramNotifier(cfg)

    # Fetch deals
    raw_deals = client.fetch_deals()
    logger.info("Raw deals fetched: %d", len(raw_deals))

    # Convert to Product objects
    products: list[Product] = []
    for deal in raw_deals:
        p = Product.from_api_deal(deal)
        if p is not None:
            products.append(p)
    logger.info("Valid products: %d", len(products))

    # Evaluate
    results = engine.evaluate_all(products)

    # Alert on STRONG_BUY (with cooldown check)
    alerts_sent = 0
    for p in results["STRONG_BUY"]:
        if not state.is_in_cooldown(p.asin):
            if notifier.send_alert(p):
                state.set_alert_cooldown(p.asin)
                alerts_sent += 1

    # Alert on WATCH (first time only)
    for p in results["WATCH"]:
        if not state.is_in_cooldown(p.asin):
            if notifier.send_alert(p):
                state.set_alert_cooldown(p.asin)
                alerts_sent += 1

    # Record all prices
    for p in products:
        state.record_price(p)

    # Mark deals as processed
    for p in products:
        if p.deal_id:
            state.mark_deal_processed(p.deal_id)

    # Save state
    state.save()

    # Send summary
    stats = state.get_stats()
    notifier.send_summary(results, stats)

    logger.info(
        "Run complete: %d processed, %d alerts sent, stats: %s",
        len(products),
        alerts_sent,
        stats,
    )


if __name__ == "__main__":
    run()
