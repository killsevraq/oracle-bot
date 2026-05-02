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
import { BetHistory } from "./BetHistory";

const STRATEGY_DESCRIPTIONS: Record<string, string> = {
  candle:
    "Double confirmation : la couleur de la bougie qui vient de fermer doit s'aligner avec le trend Binance court-terme. UP+UP -> pari UP ; DOWN+DOWN -> pari DOWN ; sinon skip.",
  arbitrage:
    "Detecte le retard du carnet Polymarket vs Binance. Calcule fair_yes a partir du prix BTC actuel. Si l'ecart fair_yes vs market_yes depasse le seuil, on parie le mispricing.",
};

const STRATEGY_LABELS: Record<string, string> = {
  candle: "Strategie Candle (bougie + trend)",
  arbitrage: "Strategie Arbitrage (lag Polymarket)",
};

const STRATEGY_COLORS: Record<string, string> = {
  candle: "#4cc9f0",
  arbitrage: "#f9c74f",
};

interface Props {
  strategy: "candle" | "arbitrage";
  refreshKey: number;
}

export function StrategyDashboard({ strategy, refreshKey }: Props) {
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

  const data: StrategyBreakdown =
    stats?.by_strategy?.[strategy] ?? {
      strategy,
      bets_total: 0,
      bets_won: 0,
      bets_lost: 0,
      bets_skipped: 0,
      total_staked: 0,
      pnl: 0,
      win_rate: 0,
    };

  const color = STRATEGY_COLORS[strategy];
  const label = STRATEGY_LABELS[strategy];
  const description = STRATEGY_DESCRIPTIONS[strategy];
  const resolved = data.bets_won + data.bets_lost;
  const cumulative = stats?.cumulative_pnl_by_strategy?.[strategy] ?? [];

  return (
    <>
      <div className="card" style={{ borderTop: `3px solid ${color}` }}>
        <h2 style={{ marginTop: 0, color }}>{label}</h2>
        <p className="muted" style={{ marginTop: 0 }}>
          {description}
        </p>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr 1fr 1fr",
            gap: 12,
            marginTop: 12,
          }}
        >
          <div className="metric">
            <span className="label">Win rate</span>
            <span className="value">{data.win_rate.toFixed(1)}%</span>
            <div className="gauge">
              <div
                className="fill"
                style={{
                  width: `${Math.max(0, Math.min(100, data.win_rate))}%`,
                  background: color,
                }}
              />
            </div>
          </div>
          <div className="metric">
            <span className="label">PnL</span>
            <span className={"value " + (data.pnl >= 0 ? "up" : "down")}>
              {data.pnl >= 0 ? "+" : ""}
              {data.pnl.toFixed(2)} USDC
            </span>
          </div>
          <div className="metric">
            <span className="label">Paris resolus</span>
            <span className="value">{resolved}</span>
          </div>
          <div className="metric">
            <span className="label">Total mise</span>
            <span className="value">{data.total_staked.toFixed(2)} USDC</span>
          </div>
        </div>

        <div className="row" style={{ marginTop: 12 }}>
          <label>Detail</label>
          <span className="value">
            <span className="up">{data.bets_won} W</span> /{" "}
            <span className="down">{data.bets_lost} L</span> /{" "}
            <span className="muted">{data.bets_skipped} skip</span>
          </span>
        </div>

        <div style={{ height: 220, marginTop: 12 }}>
          <ResponsiveContainer>
            <LineChart data={cumulative}>
              <CartesianGrid stroke="#2a2f3f" strokeDasharray="3 3" />
              <XAxis dataKey="ts" stroke="#8a93a6" hide />
              <YAxis stroke="#8a93a6" />
              <Tooltip contentStyle={{ background: "#161a23", border: "1px solid #232838" }} />
              <Line type="monotone" dataKey="pnl" stroke={color} dot={false} strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      <BetHistory
        refreshKey={refreshKey}
        strategy={strategy}
        title={`Paris ${strategy}`}
      />
    </>
  );
}
