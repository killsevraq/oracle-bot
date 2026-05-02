"""Tests unitaires pour la strategie d'arbitrage Polymarket vs Binance."""

from __future__ import annotations

import math

from backend.polymarket_clob import (
    BookSnapshot,
    _best_prices_from_book,
    fair_yes_probability,
)


def test_fair_yes_at_strike_is_half():
    p = fair_yes_probability(78_000, 78_000, time_remaining_s=300, vol_5min_pct=0.20)
    assert math.isclose(p, 0.5, abs_tol=1e-9)


def test_fair_yes_above_strike_high_proba_when_close_to_end():
    p = fair_yes_probability(78_000 * 1.005, 78_000, time_remaining_s=60, vol_5min_pct=0.20)
    assert p > 0.99


def test_fair_yes_below_strike_low_proba_when_close_to_end():
    p = fair_yes_probability(78_000 * 0.995, 78_000, time_remaining_s=60, vol_5min_pct=0.20)
    assert p < 0.01


def test_fair_yes_time_zero_above_strike():
    assert fair_yes_probability(100.01, 100, time_remaining_s=0, vol_5min_pct=0.20) == 1.0


def test_fair_yes_time_zero_at_strike():
    assert fair_yes_probability(100, 100, time_remaining_s=0, vol_5min_pct=0.20) == 0.5


def test_fair_yes_time_zero_below_strike():
    assert fair_yes_probability(99.99, 100, time_remaining_s=0, vol_5min_pct=0.20) == 0.0


def test_fair_yes_invalid_strike_returns_neutral():
    assert fair_yes_probability(78_000, 0, time_remaining_s=300, vol_5min_pct=0.20) == 0.5


def test_fair_yes_monotonic_in_btc_now():
    """Fair YES doit augmenter de maniere monotone avec le prix BTC actuel."""
    p_low = fair_yes_probability(77_900, 78_000, time_remaining_s=120, vol_5min_pct=0.20)
    p_mid = fair_yes_probability(78_000, 78_000, time_remaining_s=120, vol_5min_pct=0.20)
    p_high = fair_yes_probability(78_100, 78_000, time_remaining_s=120, vol_5min_pct=0.20)
    assert p_low < p_mid < p_high


def test_book_parser_basic():
    payload = {
        "bids": [{"price": "0.45", "size": "100"}, {"price": "0.40", "size": "50"}],
        "asks": [{"price": "0.55", "size": "100"}, {"price": "0.60", "size": "50"}],
    }
    book = _best_prices_from_book(payload)
    assert book.best_bid == 0.45
    assert book.best_ask == 0.55
    assert book.mid == 0.5
    assert math.isclose(book.spread, 0.10, abs_tol=1e-9)


def test_book_parser_empty_bids():
    payload = {"bids": [], "asks": [{"price": "0.89", "size": "10"}]}
    book = _best_prices_from_book(payload)
    assert book.best_bid == 0.0
    assert book.best_ask == 0.89


def test_book_parser_empty_asks():
    payload = {"bids": [{"price": "0.20", "size": "10"}], "asks": []}
    book = _best_prices_from_book(payload)
    assert book.best_bid == 0.20
    assert book.best_ask == 1.0


def test_book_snapshot_spread():
    b = BookSnapshot(best_bid=0.4, best_ask=0.6, mid=0.5)
    assert math.isclose(b.spread, 0.20, abs_tol=1e-9)

    # Spread negatif (croise) -> 0
    b2 = BookSnapshot(best_bid=0.6, best_ask=0.4, mid=0.5)
    assert b2.spread == 0.0
