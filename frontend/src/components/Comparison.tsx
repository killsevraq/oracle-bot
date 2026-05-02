import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import type { Stats, StrategyBreakdown } from "../types";

const STRATEGY_LABELS: Record<string, string> = {
  candle: "Candle",
  arbitrage: "Arbitrage",
};

const STRATEGY_COLORS: Record<string, string> = {
  candle: "#4cc9f0",
  arbitrage: "#f9c74f",
};

interface Props {
  refreshKey: number;
}

function emptyBreakdown(strategy: string): StrategyBreakdown {
  return {
    strategy,
    bets_total: 0,
    bets_won: 0,
    bets_lost: 0,
    bets_skipped: 0,
    total_staked: 0,
    pnl: 0,
    win_rate: 0,
  };
}

function StrategyCard({
  data,
  isLeader,
  isSignificant,
}: {
  data: StrategyBreakdown;
  isLeader: boolean;
  isSignificant: boolean;
}) {
  const color = STRATEGY_COLORS[data.strategy] ?? "#aaa";
  const label = STRATEGY_LABELS[data.strategy] ?? data.strategy;
  const resolved = data.bets_won + data.bets_lost;
  const ratio = resolved ? data.bets_won - data.bets_lost : 0;
  return (
    <div
      className="card"
      style={{
        borderTop: `4px solid ${color}`,
        boxShadow: isLeader && isSignificant ? `0 0 0 2px ${color}` : undefined,
        position: "relative",
      }}
    >
      {isLeader && isSignificant && (
        <span
          className="badge"
          style={{
            position: "absolute",
            top: 12,
            right: 12,
            background: color,
            color: "#0c0e14",
          }}
        >
          EN TETE
        </span>
      )}
      <h3 style={{ marginTop: 0, color }}>{label}</h3>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <div className="metric">
          <span className="label">Win rate</span>
          <span className="value">{data.win_rate.toFixed(1)}%</span>
        </div>
        <div className="metric">
          <span className="label">PnL</span>
          <span className={"value " + (data.pnl >= 0 ? "up" : "down")}>
            {data.pnl >= 0 ? "+" : ""}
            {data.pnl.toFixed(2)}
          </span>
        </div>
        <div className="metric">
          <span className="label">W - L</span>
          <span className={"value " + (ratio > 0 ? "up" : ratio < 0 ? "down" : "muted")}>
            {ratio > 0 ? "+" : ""}
            {ratio}
          </span>
        </div>
        <div className="metric">
          <span className="label">Resolus</span>
          <span className="value">{resolved}</span>
        </div>
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <label>Detail</label>
        <span className="value">
          <span className="up">{data.bets_won} W</span> /{" "}
          <span className="down">{data.bets_lost} L</span> /{" "}
          <span className="muted">{data.bets_skipped} skip</span>
        </span>
      </div>
      <div className="row">
        <label>Total mise</label>
        <span className="value">{data.total_staked.toFixed(2)} USDC</span>
      </div>
    </div>
  );
}

export function Comparison({ refreshKey }: Props) {
  const [stats, setStats] = useState<Stats | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const data = await api.stats();
        if (!cancelled) setStats(data);
      } catch {
        // ignore
      }
    };
    tick();
    const id = setInterval(tick, 10000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [refreshKey]);

  const candle = stats?.by_strategy?.candle ?? emptyBreakdown("candle");
  const arbitrage = stats?.by_strategy?.arbitrage ?? emptyBreakdown("arbitrage");

  const candleResolved = candle.bets_won + candle.bets_lost;
  const arbResolved = arbitrage.bets_won + arbitrage.bets_lost;
  const minResolved = Math.min(candleResolved, arbResolved);

  // Le winner est la strategie au PnL net superieur. On considere "significatif"
  // seulement si chaque strategie a >= 10 paris resolus (sinon c'est de la variance pure).
  const isSignificant = minResolved >= 10;
  let leader: "candle" | "arbitrage" | null = null;
  if (candle.pnl > arbitrage.pnl) leader = "candle";
  else if (arbitrage.pnl > candle.pnl) leader = "arbitrage";

  const cumulCandle = stats?.cumulative_pnl_by_strategy?.candle ?? [];
  const cumulArb = stats?.cumulative_pnl_by_strategy?.arbitrage ?? [];

  let recommendation: string;
  let recommendationClass = "muted";
  if (candleResolved + arbResolved === 0) {
    recommendation =
      "Aucun pari pour l'instant. Lance le bot avec SIGNAL_MODE=both pour collecter des donnees.";
  } else if (!isSignificant) {
    const need = 10 - minResolved;
    recommendation = `Pas assez de paris pour decider. Encore ~${need} pari(s) sur la strategie en retard pour avoir un verdict statistique.`;
  } else if (leader === null) {
    recommendation = "Egalite parfaite sur le PnL. Continue a collecter.";
  } else if (leader === "candle" && candle.pnl > 0) {
    recommendation =
      "Candle est gagnante. Garder Candle, retirer Arbitrage si l'ecart se confirme sur 30+ paris.";
    recommendationClass = "up";
  } else if (leader === "arbitrage" && arbitrage.pnl > 0) {
    recommendation =
      "Arbitrage est gagnante. Garder Arbitrage, retirer Candle si l'ecart se confirme sur 30+ paris.";
    recommendationClass = "up";
  } else {
    recommendation = `${
      leader === "candle" ? "Candle" : "Arbitrage"
    } est moins mauvaise mais les deux sont negatives. Faut tester d'autres parametres ou attendre.`;
    recommendationClass = "warn";
  }

  return (
    <>
      <div className="card">
        <h2 style={{ marginTop: 0 }}>Comparaison des deux strategies</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          Les deux strategies misent en parallele dans la meme DB. Le gagnant est celui dont le PnL
          est superieur, considere statistiquement valide a partir de 10 paris resolus de chaque
          cote.
        </p>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, marginTop: 12 }}>
          <StrategyCard
            data={candle}
            isLeader={leader === "candle"}
            isSignificant={isSignificant}
          />
          <StrategyCard
            data={arbitrage}
            isLeader={leader === "arbitrage"}
            isSignificant={isSignificant}
          />
        </div>
        <div className="row" style={{ marginTop: 16 }}>
          <label>Verdict</label>
          <span className={"value " + recommendationClass}>{recommendation}</span>
        </div>
      </div>

      <div className="card">
        <h3 style={{ marginTop: 0 }}>PnL cumule (cote a cote)</h3>
        <div style={{ height: 280 }}>
          <ResponsiveContainer>
            <LineChart>
              <CartesianGrid stroke="#2a2f3f" strokeDasharray="3 3" />
              <XAxis dataKey="ts" stroke="#8a93a6" hide />
              <YAxis stroke="#8a93a6" />
              <Tooltip contentStyle={{ background: "#161a23", border: "1px solid #232838" }} />
              <Line
                type="monotone"
                data={cumulCandle}
                dataKey="pnl"
                name="Candle"
                stroke={STRATEGY_COLORS.candle}
                dot={false}
                strokeWidth={2}
              />
              <Line
                type="monotone"
                data={cumulArb}
                dataKey="pnl"
                name="Arbitrage"
                stroke={STRATEGY_COLORS.arbitrage}
                dot={false}
                strokeWidth={2}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div style={{ display: "flex", gap: 16, marginTop: 8, fontSize: 13 }}>
          <span style={{ color: STRATEGY_COLORS.candle }}>● Candle</span>
          <span style={{ color: STRATEGY_COLORS.arbitrage }}>● Arbitrage</span>
        </div>
      </div>
    </>
  );
}
