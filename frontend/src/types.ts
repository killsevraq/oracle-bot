export interface BotState {
  running: boolean;
  mode: "demo" | "prod";
  bet_amount: number;
  stop_loss: number;
  take_profit: number;
  target_market: string;
  btc_price: number;
  btc_trend: string;
  last_candle_color: string;
  current_signal: string;
  next_bet_eta: string | null;
  balance: number;
  total_staked: number;
  total_won: number;
  total_lost: number;
  bets_total: number;
  bets_won: number;
  bets_lost: number;
  bets_skipped: number;
  last_event: string;
  started_at: string | null;
  halted_reason: string;
  win_rate: number;
  pnl: number;
  server_time: string;
}

export interface Bet {
  id: number;
  created_at: string;
  resolved_at: string | null;
  mode: string;
  market: string;
  direction: string;
  amount: number;
  entry_price: number;
  polymarket_price: number;
  exit_price: number | null;
  status: string;
  pnl: number;
  signal_candle: string;
  signal_binance_trend: string;
  notes: string;
}

export interface Stats {
  win_rate: number;
  pnl: number;
  balance: number;
  total_staked: number;
  bets_total: number;
  bets_won: number;
  bets_lost: number;
  bets_skipped: number;
  cumulative_pnl: { ts: string; pnl: number }[];
}
