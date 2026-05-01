import { useState } from "react";
import { api } from "../api";
import type { BotState } from "../types";

interface Props {
  state: BotState;
}

export function ControlPanel({ state }: Props) {
  const [betAmount, setBetAmount] = useState<number>(state.bet_amount);
  const [stopLoss, setStopLoss] = useState<number>(state.stop_loss);
  const [takeProfit, setTakeProfit] = useState<number>(state.take_profit);
  const [market, setMarket] = useState<string>(state.target_market);
  const [busy, setBusy] = useState<string | null>(null);

  const wrap = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    try {
      await fn();
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="card">
      <h2>Controle</h2>

      <div className="row">
        <label>Statut</label>
        <div>
          <span className={`dot ${state.running ? "on" : "off"}`}></span>
          <span className="value">{state.running ? "Actif" : "Arrete"}</span>
          {state.halted_reason && <span className="muted"> — {state.halted_reason}</span>}
        </div>
      </div>

      <div className="row">
        <label>Mode</label>
        <select
          value={state.mode}
          disabled={busy === "mode"}
          onChange={(e) => wrap("mode", () => api.setMode(e.target.value as "demo" | "prod"))}
        >
          <option value="demo">DEMO</option>
          <option value="prod">PROD</option>
        </select>
      </div>

      <div className="row">
        <label>Marche cible</label>
        <input
          value={market}
          disabled={busy === "market"}
          onChange={(e) => setMarket(e.target.value)}
          onBlur={() => wrap("market", () => api.setMarket(market))}
        />
      </div>

      <div className="row">
        <label>Mise (USDC)</label>
        <input
          type="number"
          min={0.01}
          step={0.01}
          value={betAmount}
          disabled={busy === "amount"}
          onChange={(e) => setBetAmount(Number(e.target.value))}
          onBlur={() => wrap("amount", () => api.setBetAmount(betAmount))}
        />
      </div>

      <div className="row">
        <label>Stop-Loss (USDC, 0=off)</label>
        <input
          type="number"
          min={0}
          step={0.5}
          value={stopLoss}
          disabled={busy === "sl"}
          onChange={(e) => setStopLoss(Number(e.target.value))}
          onBlur={() => wrap("sl", () => api.setStopLoss(stopLoss))}
        />
      </div>

      <div className="row">
        <label>Take-Profit (USDC, 0=off)</label>
        <input
          type="number"
          min={0}
          step={0.5}
          value={takeProfit}
          disabled={busy === "tp"}
          onChange={(e) => setTakeProfit(Number(e.target.value))}
          onBlur={() => wrap("tp", () => api.setTakeProfit(takeProfit))}
        />
      </div>

      <div className="row" style={{ marginTop: 12 }}>
        <button
          className="btn success"
          disabled={state.running || busy === "start"}
          onClick={() => wrap("start", api.start)}
        >
          Demarrer
        </button>
        <button
          className="btn danger"
          disabled={!state.running || busy === "stop"}
          onClick={() => wrap("stop", api.stop)}
        >
          Arreter
        </button>
      </div>
    </div>
  );
}
