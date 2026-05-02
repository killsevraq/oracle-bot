"""Tests unitaires de la couche strategie / signal."""

from __future__ import annotations

from backend.strategy import (
    Candle,
    CandleColor,
    Direction,
    binance_short_term_trend,
    evaluate_signal,
)


def test_candle_color_green():
    c = Candle(open_price=100, high=110, low=99, close=105)
    assert c.color == CandleColor.GREEN
    assert c.candle_direction == Direction.UP


def test_candle_color_red():
    c = Candle(open_price=105, high=106, low=95, close=100)
    assert c.color == CandleColor.RED
    assert c.candle_direction == Direction.DOWN


def test_candle_color_doji():
    c = Candle(open_price=100, high=101, low=99, close=100)
    assert c.color == CandleColor.NONE
    assert c.candle_direction == Direction.FLAT


def test_binance_trend_up():
    assert binance_short_term_trend([100, 101, 102]) == Direction.UP


def test_binance_trend_down():
    assert binance_short_term_trend([102, 101, 100]) == Direction.DOWN


def test_binance_trend_flat_when_below_threshold():
    assert binance_short_term_trend([100.0, 100.005], threshold_pct=0.02) == Direction.FLAT


def test_binance_trend_empty():
    assert binance_short_term_trend([]) == Direction.FLAT
    assert binance_short_term_trend([100]) == Direction.FLAT


def test_double_confirmation_up():
    candle = Candle(open_price=100, high=110, low=99, close=105)
    sig = evaluate_signal(candle, [100, 101, 102, 103])
    assert sig.confirmed
    assert sig.direction == Direction.UP


def test_double_confirmation_down():
    candle = Candle(open_price=105, high=106, low=95, close=100)
    sig = evaluate_signal(candle, [105, 104, 103, 102])
    assert sig.confirmed
    assert sig.direction == Direction.DOWN


def test_no_signal_when_contradictory():
    # Bougie verte mais Binance baisse => contradiction reelle
    candle = Candle(open_price=100, high=110, low=99, close=105)
    sig = evaluate_signal(candle, [105, 104, 103])
    assert not sig.confirmed
    assert sig.direction == Direction.FLAT
    assert sig.reason.startswith("signaux contradictoires")


def test_no_signal_when_doji():
    candle = Candle(open_price=100, high=101, low=99, close=100)
    sig = evaluate_signal(candle, [100, 101, 102])
    assert not sig.confirmed
    assert sig.direction == Direction.FLAT
    assert sig.reason == "bougie doji (open == close)"


def test_signal_skipped_when_binance_flat_strict():
    # Bougie verte mais Binance FLAT -> skip avec un message neutre, pas de contradiction
    candle = Candle(open_price=100, high=101, low=99, close=100.5)
    sig = evaluate_signal(candle, [100.0, 100.001, 100.0])  # variation <0.005%
    assert sig.binance_trend == Direction.FLAT
    assert not sig.confirmed
    assert sig.direction == Direction.FLAT
    assert sig.reason.startswith("tendance Binance neutre")
    assert "contradictoire" not in sig.reason


def test_signal_skipped_red_candle_flat_binance():
    candle = Candle(open_price=100, high=101, low=99, close=99.5)
    sig = evaluate_signal(candle, [100.0, 100.0])
    assert sig.binance_trend == Direction.FLAT
    assert not sig.confirmed
    assert sig.direction == Direction.FLAT
    assert sig.reason.startswith("tendance Binance neutre")
    assert "contradictoire" not in sig.reason


def test_signal_doji_takes_priority_over_flat_binance():
    # Doji + Binance FLAT : on indique "doji" plutot que "contradictoires"
    candle = Candle(open_price=100, high=101, low=99, close=100)
    sig = evaluate_signal(candle, [100.0, 100.0])
    assert not sig.confirmed
    assert sig.reason == "bougie doji (open == close)"


def test_signal_skipped_when_candle_body_too_small():
    # Bougie verte mais corps < min_body_pct => skip "bougie trop petite"
    candle = Candle(open_price=100, high=101, low=99, close=100.005)  # 0.005% body
    sig = evaluate_signal(candle, [100, 102, 104], min_body_pct=0.02)
    assert not sig.confirmed
    assert sig.direction == Direction.FLAT
    assert sig.reason.startswith("bougie trop petite")


def test_signal_confirmed_when_body_above_min():
    # Bougie verte avec corps >= min_body_pct + Binance UP => confirme
    candle = Candle(open_price=100, high=101, low=99, close=100.05)  # 0.05% body
    sig = evaluate_signal(candle, [100, 102, 104], min_body_pct=0.02)
    assert sig.confirmed
    assert sig.direction == Direction.UP


def test_signal_uses_custom_trend_threshold():
    # Variation 0.01% en dessous du seuil 0.02% => Binance FLAT => skip
    candle = Candle(open_price=100, high=101, low=99, close=100.5)  # body 0.5%
    sig = evaluate_signal(
        candle,
        [100.0, 100.005, 100.01],
        min_body_pct=0.02,
        trend_threshold_pct=0.02,
    )
    assert sig.binance_trend == Direction.FLAT
    assert not sig.confirmed
    assert sig.reason.startswith("tendance Binance neutre")
