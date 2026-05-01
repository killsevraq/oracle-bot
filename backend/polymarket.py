"""Client Polymarket : lecture publique + interface placeholder pour le mode prod."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)


@dataclass
class MarketQuote:
    """Snapshot d'un marche Polymarket (UP / DOWN)."""

    slug: str
    question: str
    yes_price: float  # probabilite implicite UP (entre 0 et 1)
    no_price: float
    end_date: str = ""


class PolymarketReader:
    """Lit les marches publics Polymarket sans wallet."""

    def __init__(
        self,
        gamma_url: str | None = None,
        clob_url: str | None = None,
        timeout: float = 10.0,
    ) -> None:
        self.gamma_url = gamma_url or settings.polymarket_gamma_url
        self.clob_url = clob_url or settings.polymarket_api_url
        self.timeout = timeout

    async def fetch_market(self, slug: str) -> MarketQuote | None:
        """Recupere un marche par slug. Retourne None si introuvable."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.gamma_url}/markets",
                params={"slug": slug, "limit": 1},
            )
            if r.status_code != 200:
                logger.warning("Polymarket /markets %s -> %s", slug, r.status_code)
                return None
            data = r.json() or []
            if not data:
                return None
            m = data[0]
            outcomes = m.get("outcomePrices") or m.get("outcome_prices") or []
            yes, no = self._parse_outcomes(outcomes)
            return MarketQuote(
                slug=m.get("slug", slug),
                question=m.get("question", ""),
                yes_price=yes,
                no_price=no,
                end_date=str(m.get("endDate") or m.get("end_date") or ""),
            )

    async def fetch_btc_market(self) -> MarketQuote | None:
        """Heuristique simple : trouve un marche BTC court (5/10 min) actif."""
        slug = settings.polymarket_market_slug
        if slug:
            return await self.fetch_market(slug)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            r = await client.get(
                f"{self.gamma_url}/markets",
                params={"active": "true", "closed": "false", "limit": 50, "tag": "Bitcoin"},
            )
            if r.status_code != 200:
                return None
            data = r.json() or []
            for m in data:
                q = (m.get("question") or "").lower()
                if "bitcoin" in q and ("up" in q or "down" in q or "5 min" in q):
                    outcomes = m.get("outcomePrices") or m.get("outcome_prices") or []
                    yes, no = self._parse_outcomes(outcomes)
                    return MarketQuote(
                        slug=m.get("slug", ""),
                        question=m.get("question", ""),
                        yes_price=yes,
                        no_price=no,
                        end_date=str(m.get("endDate") or ""),
                    )
        return None

    @staticmethod
    def _parse_outcomes(outcomes: object) -> tuple[float, float]:
        try:
            if isinstance(outcomes, str):
                import json

                outcomes = json.loads(outcomes)
            if isinstance(outcomes, list) and len(outcomes) >= 2:
                return float(outcomes[0]), float(outcomes[1])
        except (ValueError, TypeError):
            pass
        return 0.0, 0.0
