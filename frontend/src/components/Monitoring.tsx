import type { BotState } from "../types";

interface Props {
  state: BotState;
}

function trendBadge(trend: string) {
  if (trend === "UP") return <span className="up">UP ↑</span>;
  if (trend === "DOWN") return <span className="down">DOWN ↓</span>;
  return <span className="muted">FLAT</span>;
}

function signalBadge(signal: string) {
  if (signal === "UP") return <span className="up">UP ↑</span>;
  if (signal === "DOWN") return <span className="down">DOWN ↓</span>;
  return <span className="warn">INCERTAIN</span>;
}

export function Monitoring({ state }: Props) {
  return (
    <div className="card">
      <h2>Monitoring</h2>
      <div className="row">
        <label>Prix BTC</label>
        <span className="value">{state.btc_price ? state.btc_price.toFixed(2) : "—"} USD {trendBadge(state.btc_trend)}</span>
      </div>
      <div className="row">
        <label>Bougie</label>
        <span className="value">
          {state.last_candle_color === "GREEN" && <span className="up">Verte</span>}
          {state.last_candle_color === "RED" && <span className="down">Rouge</span>}
          {(!state.last_candle_color || state.last_candle_color === "NONE") && <span className="muted">—</span>}
        </span>
      </div>
      <div className="row">
        <label>Signal courant</label>
        <span className="value">{signalBadge(state.current_signal)}</span>
      </div>
      <div className="row">
        <label>Prochain pari prevu</label>
        <span className="value">
          {state.next_bet_eta ? new Date(state.next_bet_eta).toLocaleTimeString() : <span className="muted">—</span>}
          {" "}
          <span className="muted">@ {state.bet_amount.toFixed(2)} USDC</span>
        </span>
      </div>
      <div className="row">
        <label>Solde {state.mode === "demo" ? "virtuel" : "reel"}</label>
        <span className="value">{state.balance.toFixed(2)} USDC</span>
      </div>
      <div className="event">{state.last_event || "Aucun evenement recent."}</div>
    </div>
  );
}
