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
    # Bougie verte mais Binance flat / down => pas de pari
    candle = Candle(open_price=100, high=110, low=99, close=105)
    sig = evaluate_signal(candle, [105, 104, 103])
    assert not sig.confirmed
    assert sig.direction == Direction.FLAT


def test_no_signal_when_doji():
    candle = Candle(open_price=100, high=101, low=99, close=100)
    sig = evaluate_signal(candle, [100, 101, 102])
    assert not sig.confirmed
    assert sig.direction == Direction.FLAT
