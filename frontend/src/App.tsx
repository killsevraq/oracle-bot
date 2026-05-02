import { useEffect, useMemo, useState } from "react";
import { api, subscribe } from "./api";
import { ControlPanel } from "./components/ControlPanel";
import { Monitoring } from "./components/Monitoring";
import { StatsCard } from "./components/Stats";
import { BetHistory } from "./components/BetHistory";
import { StrategyDashboard } from "./components/StrategyDashboard";
import { Comparison } from "./components/Comparison";
import type { BotState } from "./types";

const DEFAULT_STATE: BotState = {
  running: false,
  mode: "demo",
  bet_amount: 5,
  stop_loss: 0,
  take_profit: 0,
  target_market: "BTC-5min",
  btc_price: 0,
  btc_trend: "",
  last_candle_color: "",
  current_signal: "INCERTAIN",
  next_bet_eta: null,
  balance: 100,
  total_staked: 0,
  total_won: 0,
  total_lost: 0,
  bets_total: 0,
  bets_won: 0,
  bets_lost: 0,
  bets_skipped: 0,
  last_event: "",
  started_at: null,
  halted_reason: "",
  win_rate: 0,
  pnl: 0,
  server_time: "",
};

type Tab = "global" | "candle" | "arbitrage" | "comparison";

const TABS: { id: Tab; label: string }[] = [
  { id: "global", label: "Vue globale" },
  { id: "candle", label: "Strategie Candle" },
  { id: "arbitrage", label: "Strategie Arbitrage" },
  { id: "comparison", label: "Comparaison" },
];

export default function App() {
  const [state, setState] = useState<BotState>(DEFAULT_STATE);
  const [betsRefresh, setBetsRefresh] = useState(0);
  const [connected, setConnected] = useState(false);
  const [tab, setTab] = useState<Tab>("global");

  useEffect(() => {
    api.state().then(setState).catch(() => undefined);
    const unsub = subscribe((type, data) => {
      if (type === "state" && data && typeof data === "object") {
        setState((prev) => ({ ...prev, ...(data as Partial<BotState>) }));
        setConnected(true);
      } else if (type === "bet") {
        setBetsRefresh((n) => n + 1);
      }
    });
    return () => unsub();
  }, []);

  const badge = useMemo(() => (state.mode === "prod" ? "prod" : "demo"), [state.mode]);

  return (
    <div className="app">
      <div className="header">
        <h1>Oracle Bot V2</h1>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span className={"badge " + badge}>{state.mode}</span>
          <span className="muted" style={{ fontSize: 12 }}>
            {connected ? "live ●" : "connexion…"}
          </span>
        </div>
      </div>

      <div className="tabs">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={"tab " + (tab === t.id ? "active" : "")}
            onClick={() => setTab(t.id)}
            type="button"
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "global" && (
        <div className="grid">
          <ControlPanel state={state} />
          <Monitoring state={state} />
          <StatsCard state={state} />
          <BetHistory refreshKey={betsRefresh} />
        </div>
      )}

      {tab === "candle" && (
        <div className="grid">
          <ControlPanel state={state} />
          <Monitoring state={state} />
          <StrategyDashboard strategy="candle" refreshKey={betsRefresh} />
        </div>
      )}

      {tab === "arbitrage" && (
        <div className="grid">
          <ControlPanel state={state} />
          <Monitoring state={state} />
          <StrategyDashboard strategy="arbitrage" refreshKey={betsRefresh} />
        </div>
      )}

      {tab === "comparison" && (
        <div className="grid">
          <Comparison refreshKey={betsRefresh} />
        </div>
      )}
    </div>
  );
}
