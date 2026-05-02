"""Logique de signal et de double confirmation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Direction(str, Enum):
    UP = "UP"
    DOWN = "DOWN"
    FLAT = "FLAT"


class CandleColor(str, Enum):
    GREEN = "GREEN"
    RED = "RED"
    NONE = "NONE"


@dataclass(frozen=True)
class Candle:
    """Bougie OHLCV."""

    open_price: float
    high: float
    low: float
    close: float
    is_closed: bool = True

    @property
    def color(self) -> CandleColor:
        if self.close > self.open_price:
            return CandleColor.GREEN
        if self.close < self.open_price:
            return CandleColor.RED
        return CandleColor.NONE

    @property
    def candle_direction(self) -> Direction:
        if self.color == CandleColor.GREEN:
            return Direction.UP
        if self.color == CandleColor.RED:
            return Direction.DOWN
        return Direction.FLAT


@dataclass(frozen=True)
class Signal:
    direction: Direction
    candle_color: CandleColor
    binance_trend: Direction
    confirmed: bool
    reason: str


def binance_short_term_trend(prices: list[float], threshold_pct: float = 0.02) -> Direction:
    """Estime la tendance Binance temps reel sur les derniers prix.

    `prices` doit contenir au moins 2 echantillons recents (dernier en dernier).
    `threshold_pct` est le seuil minimum (en %) pour qualifier une direction (sinon FLAT).
    Defaut 0.02% (~16 USD sur 78kBTC) — un mouvement clair, pas du bruit.
    """
    if len(prices) < 2:
        return Direction.FLAT
    first = prices[0]
    last = prices[-1]
    if first == 0:
        return Direction.FLAT
    change = (last - first) / first * 100
    if change > threshold_pct:
        return Direction.UP
    if change < -threshold_pct:
        return Direction.DOWN
    return Direction.FLAT


def candle_body_pct(candle: Candle) -> float:
    """Renvoie la taille du corps de la bougie en % du prix d'ouverture."""
    if candle.open_price == 0:
        return 0.0
    return abs(candle.close - candle.open_price) / candle.open_price * 100


def evaluate_signal(
    candle: Candle,
    recent_prices: list[float],
    *,
    min_body_pct: float = 0.02,
    trend_threshold_pct: float = 0.02,
) -> Signal:
    """Applique la regle de double confirmation stricte (cahier des charges).

    Pari UP   : bougie verte significative ET tendance Binance UP.
    Pari DOWN : bougie rouge significative ET tendance Binance DOWN.
    Sinon (doji, bougie trop petite, FLAT, contradiction) : skip.

    Filtres "humain" :
    - Le corps de la bougie doit etre >= `min_body_pct` (sinon = quasi-doji = bruit).
    - La tendance Binance doit franchir `trend_threshold_pct` (sinon = sideways = bruit).
    """
    candle_dir = candle.candle_direction
    binance_dir = binance_short_term_trend(recent_prices, threshold_pct=trend_threshold_pct)
    body_pct = candle_body_pct(candle)

    # Filtre 1 : doji ou bougie trop petite -> skip avant meme de regarder Binance.
    if candle_dir == Direction.FLAT:
        return Signal(
            direction=Direction.FLAT,
            candle_color=candle.color,
            binance_trend=binance_dir,
            confirmed=False,
            reason="bougie doji (open == close)",
        )
    if body_pct < min_body_pct:
        return Signal(
            direction=Direction.FLAT,
            candle_color=candle.color,
            binance_trend=binance_dir,
            confirmed=False,
            reason=f"bougie trop petite (corps {body_pct:.4f}% < {min_body_pct:.4f}%)",
        )

    # Filtre 2 : double confirmation stricte.
    if candle_dir == Direction.UP and binance_dir == Direction.UP:
        return Signal(
            direction=Direction.UP,
            candle_color=candle.color,
            binance_trend=binance_dir,
            confirmed=True,
            reason=f"bougie verte ({body_pct:.3f}%) + tendance Binance UP",
        )
    if candle_dir == Direction.DOWN and binance_dir == Direction.DOWN:
        return Signal(
            direction=Direction.DOWN,
            candle_color=candle.color,
            binance_trend=binance_dir,
            confirmed=True,
            reason=f"bougie rouge ({body_pct:.3f}%) + tendance Binance DOWN",
        )

    if binance_dir == Direction.FLAT:
        reason = f"tendance Binance neutre (bougie={candle_dir.value}, binance=FLAT)"
    else:
        reason = f"signaux contradictoires (bougie={candle_dir.value}, binance={binance_dir.value})"
    return Signal(
        direction=Direction.FLAT,
        candle_color=candle.color,
        binance_trend=binance_dir,
        confirmed=False,
        reason=reason,
    )
