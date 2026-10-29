// Shared response types mirroring the backend schemas.

export interface User {
  id: string;
  email: string;
  username: string;
  full_name: string | null;
  /** Provider that can sign this account in; null for password-only accounts. */
  oauth_provider?: string | null;
  is_active: boolean;
  is_superuser?: boolean;
}

export interface Tokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface AuthResponse {
  user: User;
  tokens: Tokens;
}

export interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  quote_volume?: number;
  trades_count?: number;
}

export interface Ticker {
  symbol: string;
  lastPrice?: string;
  priceChangePercent?: string;
  highPrice?: string;
  lowPrice?: string;
  volume?: string;
  quoteVolume?: string;
}

export interface Orderbook {
  bids: [string, string][];
  asks: [string, string][];
}

export interface MicrostructureMetrics {
  symbol: string;
  best_bid: number;
  best_ask: number;
  mid: number;
  microprice: number;
  spread: number;
  spread_bps: number;
  imbalance: number;
  bid_depth: number;
  ask_depth: number;
  bid_levels: number;
  ask_levels: number;
  levels: number;
  depth_bps: number;
}

export interface Signal {
  action: 'BUY' | 'SELL' | 'WAIT';
  symbol: string;
  timeframe: string;
  confidence: number;
  reasoning: string;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
}

export interface AgentDecision {
  action: 'BUY' | 'SELL' | 'WAIT';
  confidence: number;
  reasoning: string;
  entry_price: number | null;
  stop_loss: number | null;
  take_profit: number | null;
  invalidation_level: number | null;
  risk_reward_ratio: number | null;
}

export interface StrategyMeta {
  name: string;
  description: string;
}

export interface RiskConfig {
  max_risk_per_trade_pct: number;
  max_daily_loss_pct: number;
  max_leverage: number;
  max_portfolio_exposure_pct: number;
  max_concurrent_trades: number;
  cooldown_period_minutes: number;
  circuit_breaker_active: boolean;
}

export interface RiskState {
  circuit_breaker_active: boolean;
  circuit_breaker_reason: string | null;
  daily_loss_usd: number;
  peak_portfolio_value: number;
  current_drawdown_pct: number;
  updated_at: string | null;
}

export interface PaperAccount {
  id: string;
  name: string;
  initial_balance: number;
  current_balance: number;
  realized_pnl: number;
  unrealized_pnl: number;
  currency: string;
  is_active: boolean;
}

export interface PaperPosition {
  id: string;
  account_id: string;
  symbol: string;
  side: string;
  quantity: number;
  entry_price: number;
  current_price: number;
  unrealized_pnl: number;
  realized_pnl: number;
  stop_loss: number | null;
  take_profit: number | null;
  status: string;
}

export interface PaperOrder {
  id: string;
  account_id: string;
  symbol: string;
  side: string;
  order_type: string;
  quantity: number;
  price: number;
  filled_price: number | null;
  filled_quantity: number;
  status: string;
  stop_loss: number | null;
  take_profit: number | null;
}

export interface LiveOrder {
  id: string;
  client_order_id: string;
  exchange_order_id: string | null;
  symbol: string;
  side: string;
  order_type: string;
  quantity: number;
  price: number | null;
  status: string;
  filled_quantity: number;
  filled_price: number | null;
  commission: number;
  is_testnet: boolean;
  rejection_reason: string | null;
  created_at: string | null;
}

export interface KillSwitchStatus {
  circuit_breaker_active: boolean;
  reason: string | null;
  daily_loss_usd: number;
  current_drawdown_pct: number;
  updated_at: string | null;
}

export interface AssetAllocation {
  symbol: string;
  allocation_pct: number;
  value_usd: number;
}

export interface PortfolioSummary {
  total_equity_usd: number;
  cash_balance_usd: number;
  realized_pnl_usd: number;
  unrealized_pnl_usd: number;
  win_rate_pct: number | null;
  total_trades_count: number;
  closed_trades_count: number;
  open_positions_count: number;
  allocations: AssetAllocation[];
}

export interface BacktestMetrics {
  total_return_pct: number;
  net_profit_usd: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  win_rate_pct: number;
  profit_factor: number;
  total_trades: number;
  winning_trades: number;
  losing_trades: number;
  avg_trade_pnl_usd: number;
}

export interface EquityPoint {
  timestamp: string;
  equity: number;
  drawdown_pct: number;
}

export interface BacktestResult {
  symbol: string;
  timeframe: string;
  strategy_name: string;
  initial_capital: number;
  final_equity: number;
  metrics: BacktestMetrics;
  equity_curve: EquityPoint[];
  trades: Record<string, unknown>[];
}

export interface MarketMakingParams {
  symbol: string;
  timeframe: string;
  gamma: number;
  k: number;
  horizon: number;
  order_size: number;
  max_inventory: number;
  fee_rate: number;
  vol_window: number;
}

export interface QuotePoint {
  timestamp: string;
  mid: number;
  bid: number;
  ask: number;
  inventory: number;
  pnl: number;
}

export interface MarketMakingFill {
  timestamp: string;
  side: string;
  price: number;
  size: number;
  edge: number;
}

export interface MarketMakingMetrics {
  total_pnl: number;
  spread_pnl: number;
  inventory_pnl: number;
  fees_paid: number;
  num_fills: number;
  num_buys: number;
  num_sells: number;
  fill_ratio: number;
  sharpe_ratio: number;
  max_inventory: number;
  final_inventory: number;
  avg_spread_bps: number;
}

export interface MarketMakingResult {
  symbol: string;
  timeframe: string;
  params: MarketMakingParams;
  metrics: MarketMakingMetrics;
  series: QuotePoint[];
  fills: MarketMakingFill[];
}

export interface JournalEntry {
  id: string;
  trade_id: string;
  symbol: string;
  timeframe: string;
  direction: string;
  entry_price: number;
  stop_loss: number | null;
  take_profit: number | null;
  risk_reward: number | null;
  ai_reasoning: string | null;
  realized_pnl: number | null;
  user_notes: string | null;
  lessons: string | null;
  tags: string[] | null;
  created_at: string;
}

export interface ExperimentRecord {
  experiment_id: string;
  strategy_name: string;
  strategy_version: string;
  symbol: string;
  timeframe: string;
  metrics: Record<string, number> | null;
  created_at: string | null;
}

export interface AIObservability {
  window_days: number;
  total_ai_decisions: number;
  ai_win_rate_pct: number | null;
  ai_expectancy_usd: number | null;
  settled_decisions: number;
  avg_latency_ms: number | null;
  avg_confidence: number | null;
  total_tokens_used: number;
  total_cost_usd: number;
  validated_decisions_pct: number | null;
  action_breakdown: Record<string, number>;
}

export interface SubsystemHealth {
  status: string;
  healthy: boolean;
  latency_ms?: number;
  error?: string | null;
  [key: string]: unknown;
}

export interface SystemHealth {
  status: string;
  checked_at: string;
  subsystems: Record<string, SubsystemHealth>;
}

export interface WalkForwardWindow {
  window_id: number;
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
  train_bars: number;
  test_bars: number;
  in_sample_sharpe: number;
  out_of_sample_sharpe: number;
  in_sample_return_pct: number;
  out_of_sample_return_pct: number;
  out_of_sample_trades: number;
}

export interface WalkForwardResult {
  strategy_name: string;
  symbol: string;
  timeframe: string;
  total_windows: number;
  avg_in_sample_sharpe: number;
  avg_out_of_sample_sharpe: number;
  efficiency_ratio: number;
  overfitting_warning: boolean;
  message: string;
  windows: WalkForwardWindow[];
}

export interface OptimizationCandidate {
  params: Record<string, unknown>;
  sharpe_ratio: number;
  sortino_ratio: number;
  total_return_pct: number;
  max_drawdown_pct: number;
  profit_factor: number;
  total_trades: number;
}

export interface OptimizationResult {
  strategy_name: string;
  symbol: string;
  timeframe: string;
  method: string;
  total_evaluations: number;
  best_candidate: OptimizationCandidate | null;
  top_candidates: OptimizationCandidate[];
  overfitting_warning: boolean;
  recommendation: string;
  probabilistic_sharpe: number | null;
  deflated_sharpe: number | null;
  probability_of_backtest_overfitting: number | null;
}

export interface MonteCarloSummary {
  num_simulations: number;
  num_trades_per_path: number;
  initial_capital: number;
  mean_final_equity: number;
  median_final_equity: number;
  probability_of_ruin_pct: number;
  worst_case_drawdown_95_pct: number;
  median_max_drawdown_pct: number;
  expected_longest_losing_streak: number;
  percentile_5_equity: number;
  percentile_95_equity: number;
}

export interface BiasCheckReport {
  strategy_name: string;
  has_lookahead_bias: boolean;
  bars_tested: number;
  violations_found: number;
  violations: {
    bar_index: number;
    timestamp: string;
    signal_with_history_only: string;
    signal_with_future_visible: string;
  }[];
  message: string;
}

export interface ApiError {
  error: boolean;
  message: string;
  details?: unknown;
}

export interface CoverageRow {
  symbol: string;
  timeframe: string;
  candle_count: number;
  oldest: string | null;
  newest: string | null;
  has_data: boolean;
  is_stale: boolean;
}

export interface MarketCoverage {
  symbols: string[];
  timeframes: string[];
  pairs_total: number;
  pairs_with_data: number;
  pairs_missing: number;
  pairs_stale: number;
  total_candles: number;
  coverage: CoverageRow[];
}
