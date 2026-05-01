import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api";
import type { BotState, Stats } from "../types";

interface Props {
  state: BotState;
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

  return (
    <div className="card">
      <h2>Statistiques temps reel</h2>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12, marginBottom: 12 }}>
        <div className="metric">
          <span className="label">Win rate</span>
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
        <label>Paris</label>
        <span className="value">
          <span className="up">{state.bets_won} W</span> / <span className="down">{state.bets_lost} L</span> / <span className="muted">{state.bets_skipped} skip</span>
        </span>
      </div>

      <div style={{ height: 220, marginTop: 12 }}>
        <ResponsiveContainer>
          <LineChart data={stats?.cumulative_pnl ?? []}>
            <CartesianGrid stroke="#2a2f3f" strokeDasharray="3 3" />
            <XAxis dataKey="ts" stroke="#8a93a6" hide />
            <YAxis stroke="#8a93a6" />
            <Tooltip contentStyle={{ background: "#161a23", border: "1px solid #232838" }} />
            <Line type="monotone" dataKey="pnl" stroke="#4cc9f0" dot={false} strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
