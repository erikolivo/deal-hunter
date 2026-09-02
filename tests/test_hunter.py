from __future__ import annotations

import pytest

from hunter.config import Config
from hunter.models import Product
from hunter.discount_engine import DiscountEngine, STRONG_BUY, WATCH, SUSPICIOUS_ANCHOR, OUT_OF_RANGE
from hunter.state_store import StateStore


@pytest.fixture
def config() -> Config:
    return Config(
        min_discount_pct=60.0,
        max_discount_pct=90.0,
        min_price=5.0,
        max_price=500.0,
        anchor_inflation_ratio=1.8,
        min_anchor_observations=3,
        alert_cooldown_hours=24,
        state_file=":memory:",
    )


@pytest.fixture
def state(config: Config, tmp_path) -> StateStore:
    config.state_file = str(tmp_path / "state.json")
    return StateStore(config)


@pytest.fixture
def engine(config: Config, state: StateStore) -> DiscountEngine:
    return DiscountEngine(config, state)


# ── Model tests ───────────────────────────────────────────────────


class TestProduct:
    def test_discount_calculation(self):
        p = Product(asin="B001", title="Test", deal_price=40, list_price=100)
        assert p.calculated_discount_pct == 60.0

    def test_no_discount(self):
        p = Product(asin="B002", title="Test", deal_price=100, list_price=100)
        assert p.calculated_discount_pct == 0.0

    def test_price_higher_than_list(self):
        p = Product(asin="B003", title="Test", deal_price=120, list_price=100)
        assert p.calculated_discount_pct == 0.0

    def test_savings_usd(self):
        p = Product(asin="B004", title="Test", deal_price=30, list_price=100)
        assert p.savings_usd == 70.0

    def test_time_remaining_none(self):
        p = Product(asin="B005", title="Test", deal_price=50, list_price=100)
        assert p.time_remaining is None

    def test_from_api_deal_valid(self):
        deal = {
            "product_asin": "B006",
            "product_title": "Widget",
            "deal_price": "25.00",
            "list_price": "100.00",
            "deal_id": "D1",
        }
        p = Product.from_api_deal(deal)
        assert p is not None
        assert p.asin == "B006"
        assert p.calculated_discount_pct == 75.0

    def test_from_api_deal_missing_asin(self):
        deal = {"product_title": "No ASIN", "deal_price": "10", "list_price": "50"}
        assert Product.from_api_deal(deal) is None

    def test_from_api_deal_zero_prices(self):
        deal = {"product_asin": "B007", "deal_price": "0", "list_price": "0"}
        assert Product.from_api_deal(deal) is None


# ── Engine verdict tests ──────────────────────────────────────────


class TestDiscountEngine:
    def test_out_of_range_low(self, engine):
        p = Product(asin="B010", title="Low", deal_price=80, list_price=100)  # 20%
        engine.evaluate(p)
        assert p.verdict == OUT_OF_RANGE

    def test_out_of_range_high(self, engine):
        p = Product(asin="B011", title="High", deal_price=5, list_price=100)  # 95%
        engine.evaluate(p)
        assert p.verdict == OUT_OF_RANGE

    def test_out_of_range_price_too_low(self, engine):
        p = Product(asin="B012", title="Cheap", deal_price=2, list_price=10)  # 80% but $2
        engine.evaluate(p)
        assert p.verdict == OUT_OF_RANGE

    def test_out_of_range_price_too_high(self, engine):
        p = Product(asin="B013", title="Expensive", deal_price=200, list_price=600)  # 67% but $200
        engine.evaluate(p)
        assert p.verdict == OUT_OF_RANGE

    def test_watch_no_history(self, engine):
        p = Product(asin="B020", title="New", deal_price=40, list_price=100)  # 60%
        engine.evaluate(p)
        assert p.verdict == WATCH

    def test_strong_buy_with_enough_history(self, engine, state):
        asin = "B021"
        for _ in range(5):
            p = Product(asin=asin, title="Tracked", deal_price=95, list_price=100)
            state.record_price(p)
        product = Product(asin=asin, title="Deal", deal_price=35, list_price=100)  # 65%
        engine.evaluate(product)
        assert product.verdict == STRONG_BUY

    def test_suspicious_anchor(self, engine, state):
        asin = "B022"
        for _ in range(5):
            p = Product(asin=asin, title="Old", deal_price=95, list_price=100)
            state.record_price(p)
        # list_price inflated to $250 (median was $100, ratio 2.5 > 1.8)
        product = Product(asin=asin, title="Inflated", deal_price=90, list_price=250)
        engine.evaluate(product)
        assert product.verdict == SUSPICIOUS_ANCHOR


# ── API inconsistency test (the real case from 30-aug-2026) ───────


class TestAPIInconsistency:
    def test_no_trust_savings_percentage_nor_badge(self, engine, state):
        """
        The API may report savings_percentage=30 but deal_badge='Lightning Deal'
        on a product where the REAL discount (from list_price vs deal_price) is 70%.
        We verify the engine recalculates and does NOT trust the API fields.
        """
        deal = {
            "product_asin": "B030",
            "product_title": "Inconsistent Widget",
            "deal_price": "30.00",
            "list_price": "100.00",
            "savings_percentage": "30",   # API says 30% — WRONG
            "deal_badge": "Lightning",    # API implies good deal
        }
        product = Product.from_api_deal(deal)
        assert product is not None
        assert product.calculated_discount_pct == 70.0  # We calculated correctly

        # With enough history at $100 list_price, anchor validates
        for _ in range(5):
            h = Product(asin="B030", title="Old", deal_price=95, list_price=100)
            state.record_price(h)

        engine.evaluate(product)
        assert product.verdict == STRONG_BUY


# ── State store tests ─────────────────────────────────────────────


class TestStateStore:
    def test_price_history_tracking(self, state):
        p = Product(asin="B040", title="Tracked", deal_price=50, list_price=100)
        state.record_price(p)
        history = state.get_price_history("B040")
        assert len(history) == 1
        assert history[0]["list_price"] == 100

    def test_anchor_stats(self, state):
        for i in range(5):
            p = Product(asin="B041", title="T", deal_price=50, list_price=100 + i * 10)
            state.record_price(p)
        median, count = state.get_anchor_stats("B041")
        assert count == 5
        assert median is not None

    def test_cooldown(self, state):
        p = Product(asin="B042", title="C", deal_price=50, list_price=100)
        assert not state.is_in_cooldown("B042")
        state.set_alert_cooldown("B042")
        assert state.is_in_cooldown("B042")

    def test_save_and_load(self, config, tmp_path):
        config.state_file = str(tmp_path / "test_state.json")
        s1 = StateStore(config)
        p = Product(asin="B043", title="S", deal_price=50, list_price=100)
        s1.record_price(p)
        s1.save()

        s2 = StateStore(config)
        assert len(s2.get_price_history("B043")) == 1
