"""
QuantX — Avellaneda-Stoikov market-making simulation over historical candles.

Each bar the maker quotes a bid and an ask from the A-S model (see ``model.py``)
and fills are simulated from the bar's range: the bid fills if the bar traded
down to it (``low <= bid``) and the ask fills if it traded up to it
(``high >= ask``). A single volatile bar can fill both and capture the spread —
which is the whole point of making markets.

Two risk controls keep it honest:
  * **Inventory cap.** The bid is withdrawn at the long limit and the ask at the
    short limit, so the book never accumulates unbounded directional risk.
  * **No look-ahead.** Quotes for bar *i* are computed from information through
    bar *i-1* (prior close and the volatility estimated up to it); only then is
    bar *i*'s high/low used to decide fills.

P&L is split into the two numbers that actually matter for a market maker:
  * **spread_pnl** — edge captured versus the mid at each fill (the making edge).
  * **inventory_pnl** — the residual from holding the running position as the
    price moved (the risk you take on to earn that edge).
"""

import numpy as np
import pandas as pd

from app.engines.market_making.model import avellaneda_stoikov_quote
from app.schemas.market_making import (
    MarketMakingFill,
    MarketMakingMetrics,
    MarketMakingRequest,
    MarketMakingResult,
    QuotePoint,
)

# Approximate bars per year per timeframe, for annualizing the Sharpe ratio.
_PERIODS_PER_YEAR: dict[str, float] = {
    "1m": 525_600, "5m": 105_120, "15m": 35_040,
    "1h": 8_760, "4h": 2_190, "1d": 365,
}
# Cap the returned time series so the payload stays chartable; the simulation
# still runs over every bar, the output is just strided down to this many points.
_MAX_SERIES_POINTS = 3_000
# Keep the most recent fills only; the full list can be large on 1m data.
_MAX_FILLS = 500
# Floor on the volatility estimate so a dead-flat window cannot collapse the
# spread to zero (which would quote bid == ask == mid).
_MIN_SIGMA = 1e-9


class MarketMakingEngine:
    """Event-driven Avellaneda-Stoikov market-making simulator."""

    def __init__(self, request: MarketMakingRequest) -> None:
        self.request = request

    def run(self, df_candles: pd.DataFrame) -> MarketMakingResult:
        """Simulate quoting over a chronological candle DataFrame.

        Args:
            df_candles: DataFrame with 'timestamp','open','high','low','close',
                ordered oldest-first.

        Returns:
            A MarketMakingResult with metrics, the quote/inventory/PnL series,
            and the simulated fills.
        """
        req = self.request
        if df_candles.empty or len(df_candles) < req.vol_window + 5:
            return self._empty_result()

        closes = df_candles["close"].to_numpy(dtype=float)
        highs = df_candles["high"].to_numpy(dtype=float)
        lows = df_candles["low"].to_numpy(dtype=float)
        timestamps = df_candles["timestamp"].astype(str).to_numpy()

        # Per-bar volatility in PRICE units: rolling std of close-to-close
        # changes. sigma[j] is known at the end of bar j, so quoting bar i uses
        # sigma[i-1] — no look-ahead.
        sigma = (
            pd.Series(closes).diff().rolling(req.vol_window).std().to_numpy(dtype=float)
        )

        cash = 0.0
        inventory = 0.0
        spread_pnl = 0.0
        fees_paid = 0.0
        num_buys = 0
        num_sells = 0
        max_abs_inventory = 0.0
        spread_bps_sum = 0.0
        steps = 0

        series: list[QuotePoint] = []
        fills: list[MarketMakingFill] = []
        equity_values: list[float] = []

        start = req.vol_window + 1
        for i in range(start, len(closes)):
            mid = closes[i - 1]
            step_sigma = sigma[i - 1]
            if not np.isfinite(step_sigma) or mid <= 0:
                continue
            step_sigma = max(step_sigma, _MIN_SIGMA)

            # Avellaneda-Stoikov's gamma and k carry units of 1/price, so a raw
            # default that suits a $0.50 token quotes a spread of hundreds of
            # dollars on BTC (and never fills). Express the request's
            # dimensionless gamma/k in the asset's own volatility units, which
            # makes the half-spread scale with sigma — so one default behaves
            # sensibly whatever the price level.
            gamma_abs = req.gamma / step_sigma
            k_abs = req.k / step_sigma
            quote = avellaneda_stoikov_quote(
                mid,
                inventory,
                step_sigma,
                gamma=gamma_abs,
                k=k_abs,
                time_remaining=req.horizon,
            )
            bid, ask = quote.bid, quote.ask
            steps += 1
            spread_bps_sum += (ask - bid) / mid * 10_000.0

            ts = str(timestamps[i])

            # Buy side: quoted only with room under the long cap; fills if the
            # bar traded down to the bid.
            if inventory < req.max_inventory and lows[i] <= bid:
                size = min(req.order_size, req.max_inventory - inventory)
                if size > 1e-12:
                    fee = bid * size * req.fee_rate
                    cash -= bid * size + fee
                    inventory += size
                    edge = (mid - bid) * size
                    spread_pnl += edge
                    fees_paid += fee
                    num_buys += 1
                    fills.append(
                        MarketMakingFill(
                            timestamp=ts, side="BUY", price=round(bid, 8),
                            size=round(size, 8), edge=round(edge, 6),
                        )
                    )

            # Sell side: quoted only with room above the short cap; fills if the
            # bar traded up to the ask.
            if inventory > -req.max_inventory and highs[i] >= ask:
                size = min(req.order_size, req.max_inventory + inventory)
                if size > 1e-12:
                    fee = ask * size * req.fee_rate
                    cash += ask * size - fee
                    inventory -= size
                    edge = (ask - mid) * size
                    spread_pnl += edge
                    fees_paid += fee
                    num_sells += 1
                    fills.append(
                        MarketMakingFill(
                            timestamp=ts, side="SELL", price=round(ask, 8),
                            size=round(size, 8), edge=round(edge, 6),
                        )
                    )

            max_abs_inventory = max(max_abs_inventory, abs(inventory))
            equity = cash + inventory * closes[i]
            equity_values.append(equity)
            series.append(
                QuotePoint(
                    timestamp=ts,
                    mid=round(closes[i], 8),
                    bid=round(bid, 8),
                    ask=round(ask, 8),
                    inventory=round(inventory, 8),
                    pnl=round(equity, 6),
                )
            )

        total_pnl = cash + inventory * closes[-1]
        # Residual attribution: total = spread capture + inventory P&L - fees.
        inventory_pnl = total_pnl - spread_pnl + fees_paid
        num_fills = num_buys + num_sells

        metrics = MarketMakingMetrics(
            total_pnl=round(total_pnl, 4),
            spread_pnl=round(spread_pnl, 4),
            inventory_pnl=round(inventory_pnl, 4),
            fees_paid=round(fees_paid, 4),
            num_fills=num_fills,
            num_buys=num_buys,
            num_sells=num_sells,
            # Two fills are possible per step (one per side).
            fill_ratio=round(num_fills / (2 * steps), 4) if steps else 0.0,
            sharpe_ratio=self._sharpe(equity_values),
            max_inventory=round(max_abs_inventory, 8),
            final_inventory=round(inventory, 8),
            avg_spread_bps=round(spread_bps_sum / steps, 4) if steps else 0.0,
        )

        return MarketMakingResult(
            symbol=req.symbol,
            timeframe=req.timeframe,
            params=req,
            metrics=metrics,
            series=self._downsample(series),
            fills=fills[-_MAX_FILLS:],
        )

    def _sharpe(self, equity: list[float]) -> float:
        """Annualized Sharpe of the per-bar P&L changes."""
        if len(equity) < 3:
            return 0.0
        steps = np.diff(np.asarray(equity, dtype=float))
        std = float(steps.std())
        if std == 0.0:
            return 0.0
        periods = _PERIODS_PER_YEAR.get(self.request.timeframe, 8_760)
        return round(float(steps.mean()) / std * float(np.sqrt(periods)), 4)

    @staticmethod
    def _downsample(series: list[QuotePoint]) -> list[QuotePoint]:
        """Stride a long series down to a chartable length, keeping the last point."""
        if len(series) <= _MAX_SERIES_POINTS:
            return series
        stride = len(series) // _MAX_SERIES_POINTS + 1
        sampled = series[::stride]
        if sampled[-1] is not series[-1]:
            sampled.append(series[-1])
        return sampled

    def _empty_result(self) -> MarketMakingResult:
        """Return an empty result when there is not enough data to simulate."""
        req = self.request
        return MarketMakingResult(
            symbol=req.symbol,
            timeframe=req.timeframe,
            params=req,
            metrics=MarketMakingMetrics(
                total_pnl=0.0, spread_pnl=0.0, inventory_pnl=0.0, fees_paid=0.0,
                num_fills=0, num_buys=0, num_sells=0, fill_ratio=0.0,
                sharpe_ratio=0.0, max_inventory=0.0, final_inventory=0.0,
                avg_spread_bps=0.0,
            ),
            series=[],
            fills=[],
        )
