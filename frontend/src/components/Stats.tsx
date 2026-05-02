import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import type { BotState, Stats, StrategyBreakdown } from "../types";

interface Props {
  state: BotState;
}

const STRATEGY_LABELS: Record<string, string> = {
  candle: "Candle (bougie + trend)",
  arbitrage: "Arbitrage (lag Polymarket)",
};

const STRATEGY_COLORS: Record<string, string> = {
  candle: "#4cc9f0",
  arbitrage: "#f9c74f",
};

function StrategyPanel({ data }: { data: StrategyBreakdown }) {
  const label = STRATEGY_LABELS[data.strategy] ?? data.strategy;
  const color = STRATEGY_COLORS[data.strategy] ?? "#aaa";
  const resolved = data.bets_won + data.bets_lost;
  return (
    <div className="card" style={{ borderTop: `3px solid ${color}` }}>
      <h3 style={{ marginTop: 0, color }}>{label}</h3>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
        <div className="metric">
          <span className="label">Win rate</span>
          <span className="value">{data.win_rate.toFixed(1)}%</span>
          <div className="gauge">
            <div className="fill" style={{ width: `${Math.max(0, Math.min(100, data.win_rate))}%`, background: color }} />
          </div>
        </div>
        <div className="metric">
          <span className="label">PnL</span>
          <span className={"value " + (data.pnl >= 0 ? "up" : "down")}>
            {data.pnl >= 0 ? "+" : ""}
            {data.pnl.toFixed(2)} USDC
          </span>
        </div>
      </div>
      <div className="row" style={{ marginTop: 8 }}>
        <label>Paris ({resolved} resolus)</label>
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

export function StatsCard({ state }: Props) {
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
  }, [state.bets_total, state.bets_won, state.bets_lost]);

  const breakdown = stats?.by_strategy ?? {};
  const strategies = Object.keys(breakdown);
  const showBreakdown = strategies.length >= 2 || (strategies.length === 1 && strategies[0] !== "candle");

  return (
    <div className="card">
      <h2>Statistiques temps reel</h2>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 12 }}>
        <div className="metric">
          <span className="label">Win rate global</span>
          <span className="value">{state.win_rate.toFixed(1)}%</span>
          <div className="gauge"><div className="fill" style={{ width: `${Math.max(0, Math.min(100, state.win_rate))}%` }}></div></div>
        </div>
        <div className="metric">
          <span className="label">PnL net</span>
          <span className={"value " + (state.pnl >= 0 ? "up" : "down")}>{state.pnl >= 0 ? "+" : ""}{state.pnl.toFixed(2)} USDC</span>
        </div>
        <div className="metric">
          <span className="label">Total mise</span>
          <span className="value">{state.total_staked.toFixed(2)} USDC</span>
        </div>
      </div>

      <div className="row">
        <label>Paris global</label>
        <span className="value">
          <span className="up">{state.bets_won} W</span> / <span className="down">{state.bets_lost} L</span> / <span className="muted">{state.bets_skipped} skip</span>
        </span>
      </div>

      {showBreakdown && (
        <div style={{ display: "grid", gridTemplateColumns: `repeat(${strategies.length}, 1fr)`, gap: 12, marginTop: 12 }}>
          {strategies.map((s) => (
            <StrategyPanel key={s} data={breakdown[s]} />
          ))}
        </div>
      )}

      <div style={{ height: 220, marginTop: 12 }}>
        <ResponsiveContainer>
          <LineChart>
            <CartesianGrid stroke="#2a2f3f" strokeDasharray="3 3" />
            <XAxis dataKey="ts" stroke="#8a93a6" hide />
            <YAxis stroke="#8a93a6" />
            <Tooltip contentStyle={{ background: "#161a23", border: "1px solid #232838" }} />
            {showBreakdown
              ? strategies.map((s) => (
                  <Line
                    key={s}
                    type="monotone"
                    data={stats?.cumulative_pnl_by_strategy?.[s] ?? []}
                    dataKey="pnl"
                    name={STRATEGY_LABELS[s] ?? s}
                    stroke={STRATEGY_COLORS[s] ?? "#aaa"}
                    dot={false}
                    strokeWidth={2}
                  />
                ))
              : (
                <Line
                  type="monotone"
                  data={stats?.cumulative_pnl ?? []}
                  dataKey="pnl"
                  stroke="#4cc9f0"
                  dot={false}
                  strokeWidth={2}
                />
              )}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
