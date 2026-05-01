import { useEffect, useState } from "react";
import { api } from "../api";
import type { Bet } from "../types";

export function BetHistory({ refreshKey }: { refreshKey: number }) {
  const [bets, setBets] = useState<Bet[]>([]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await api.bets(50);
        if (!cancelled) setBets(data);
      } catch {
        // ignore
      }
    };
    load();
  }, [refreshKey]);

  return (
    <div className="card">
      <h2>Historique des paris</h2>
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Heure</th>
            <th>Mode</th>
            <th>Marche</th>
            <th>Dir</th>
            <th>Mise</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>Statut</th>
            <th>PnL</th>
          </tr>
        </thead>
        <tbody>
          {bets.map((b) => (
            <tr key={b.id}>
              <td>{b.id}</td>
              <td>{new Date(b.created_at).toLocaleTimeString()}</td>
              <td>{b.mode.toUpperCase()}</td>
              <td>{b.market}</td>
              <td className={b.direction === "UP" ? "up" : b.direction === "DOWN" ? "down" : "muted"}>{b.direction}</td>
              <td>{b.amount.toFixed(2)}</td>
              <td>{b.entry_price.toFixed(2)}</td>
              <td>{b.exit_price ? b.exit_price.toFixed(2) : "—"}</td>
              <td>{b.status}</td>
              <td className={b.pnl > 0 ? "up" : b.pnl < 0 ? "down" : "muted"}>{b.pnl > 0 ? "+" : ""}{b.pnl.toFixed(2)}</td>
            </tr>
          ))}
          {bets.length === 0 && (
            <tr>
              <td colSpan={10} className="muted" style={{ textAlign: "center", padding: 24 }}>
                Aucun pari pour l'instant. Demarre le bot pour commencer.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
