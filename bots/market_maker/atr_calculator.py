"""Average True Range (ATR) calculator for adaptive grid spacing."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from bots.indicators.binance_extgap_indicator_5m import Candle


@dataclass
class ATRState:
    """Snapshot of ATR calculation state."""
    period: int
    current_atr: Optional[float]
    samples: int
    prev_close: Optional[float]


class ATRCalculator:
    """Calculates Average True Range for grid spacing.

    ATR measures market volatility by averaging the True Range over a period.
    True Range = max(high - low, |high - prev_close|, |low - prev_close|)

    Used to adapt grid spacing to current market conditions:
    - Higher ATR = wider grid spacing
    - Lower ATR = tighter grid spacing

    Example:
        >>> atr = ATRCalculator(period=14)
        >>> for candle in candles:
        ...     current_atr = atr.update(candle)
        >>> spacing = atr.get_atr() * 0.5  # 0.5 ATR spacing
    """

    def __init__(self, period: int = 14):
        """Initialize ATR calculator.

        Args:
            period: Number of candles for ATR averaging (default 14)
        """
        self.period = period
        self.tr_values: Deque[float] = deque(maxlen=period)
        self.current_atr: Optional[float] = None
        self.prev_close: Optional[float] = None

    def update(self, candle: "Candle") -> Optional[float]:
        """Update ATR with new candle data.

        Args:
            candle: Candle with OHLC data

        Returns:
            Current ATR value if enough data, None otherwise
        """
        if self.prev_close is None:
            # First candle - just record close, can't calculate TR yet
            self.prev_close = candle.close
            return None

        # Calculate True Range
        # TR = max(
        #   high - low,           (current bar range)
        #   |high - prev_close|,  (gap up range)
        #   |low - prev_close|    (gap down range)
        # )
        tr = max(
            candle.high - candle.low,
            abs(candle.high - self.prev_close),
            abs(candle.low - self.prev_close)
        )

        self.tr_values.append(tr)
        self.prev_close = candle.close

        # Calculate ATR as simple moving average of TR
        if len(self.tr_values) >= self.period:
            self.current_atr = sum(self.tr_values) / len(self.tr_values)
        elif len(self.tr_values) >= 1:
            # Allow partial ATR before full period (for faster warmup)
            self.current_atr = sum(self.tr_values) / len(self.tr_values)

        return self.current_atr

    def get_atr(self) -> Optional[float]:
        """Get current ATR value.

        Returns:
            Current ATR or None if not enough data
        """
        return self.current_atr

    def is_ready(self) -> bool:
        """Check if ATR has full period of data.

        Returns:
            True if ATR is calculated with full period
        """
        return len(self.tr_values) >= self.period

    def get_state(self) -> ATRState:
        """Get current ATR state for logging/debugging.

        Returns:
            ATRState snapshot
        """
        return ATRState(
            period=self.period,
            current_atr=self.current_atr,
            samples=len(self.tr_values),
            prev_close=self.prev_close
        )

    def reset(self) -> None:
        """Reset ATR calculator to initial state."""
        self.tr_values.clear()
        self.current_atr = None
        self.prev_close = None
