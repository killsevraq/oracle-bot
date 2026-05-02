import type { Bet, BotState, Stats } from "./types";

const BASE = "/api";

async function jsonFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export const api = {
  state: () => jsonFetch<BotState>("/state"),
  start: () => jsonFetch<BotState>("/bot/start", { method: "POST" }),
  stop: () => jsonFetch<BotState>("/bot/stop", { method: "POST" }),
  setBetAmount: (amount: number) =>
    jsonFetch<BotState>("/bot/bet-amount", { method: "POST", body: JSON.stringify({ amount }) }),
  setStopLoss: (value: number) =>
    jsonFetch<BotState>("/bot/stop-loss", { method: "POST", body: JSON.stringify({ value }) }),
  setTakeProfit: (value: number) =>
    jsonFetch<BotState>("/bot/take-profit", { method: "POST", body: JSON.stringify({ value }) }),
  setMode: (mode: "demo" | "prod") =>
    jsonFetch<BotState>("/bot/mode", { method: "POST", body: JSON.stringify({ mode }) }),
  setMarket: (market: string) =>
    jsonFetch<BotState>("/bot/target-market", { method: "POST", body: JSON.stringify({ market }) }),
  bets: (limit = 100, strategy?: string) =>
    jsonFetch<Bet[]>(`/bets?limit=${limit}${strategy ? `&strategy=${strategy}` : ""}`),
  stats: () => jsonFetch<Stats>("/stats"),
};

export function subscribe(onEvent: (type: string, data: unknown) => void): () => void {
  const es = new EventSource(`${BASE}/events`);
  const listener = (event: MessageEvent) => {
    try {
      onEvent(event.type, JSON.parse(event.data));
    } catch {
      onEvent(event.type, event.data);
    }
  };
  ["state", "bet", "polymarket", "ping", "message"].forEach((evt) =>
    es.addEventListener(evt, listener as EventListener),
  );
  return () => es.close();
}
