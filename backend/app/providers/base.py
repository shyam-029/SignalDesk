# Market data provider interface (D16: swappable data sources).
#
# New concept: abstract base class. Defines a *contract* (method signatures)
# without implementing them. Each concrete provider (yfinance, a future source)
# inherits from MarketDataProvider and must implement every method. Ingestion
# code depends on this interface — never on a specific provider — so swapping
# sources later requires no changes to ingestion logic.

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class OHLCV:
    """One daily price bar (open / high / low / close / volume)."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


@dataclass(frozen=True)
class StockProfile:
    """Basic identifying/fundamental info for a symbol."""

    symbol: str
    name: str | None
    sector: str | None
    industry: str | None


@dataclass(frozen=True)
class Fundamentals:
    """Financial snapshot for one symbol (raw provider values).

    Profitability fields (roe/roa/margins) are stored as DECIMALS exactly as
    the provider returns them (e.g. 0.18 = 18%); the scoring layer normalizes
    to percent. `trailing_pe`/`debt_to_equity` are already in their natural
    units. None means the provider did not supply the field.
    """

    symbol: str
    market_cap: float | None = None
    trailing_pe: float | None = None
    enterprise_value: float | None = None
    ebitda: float | None = None
    price_to_book: float | None = None
    price_to_sales: float | None = None
    # Profitability (decimals: 0.18 = 18%).
    return_on_equity: float | None = None
    return_on_assets: float | None = None
    operating_margin: float | None = None
    profit_margin: float | None = None
    # Solvency.
    debt_to_equity: float | None = None
    interest_coverage: float | None = None
    current_ratio: float | None = None


class MarketDataProvider(ABC):
    """Contract every market data source must implement."""

    @abstractmethod
    async def get_price_history(self, symbol: str, period: str) -> list[OHLCV]:
        """Return daily OHLCV bars for the given symbol.

        Args:
            symbol: fully-qualified symbol, e.g. "RELIANCE.NS".
            period: yfinance-style lookback, e.g. "1y", "2y".

        Returns:
            Chronological list of OHLCV bars. Empty if the symbol is unknown.
        """
        ...

    @abstractmethod
    async def get_stock_profile(self, symbol: str) -> StockProfile:
        """Return identifying/fundamental info for a symbol.

        Returns an object with available fields (None where the source has none).
        """
        ...

    @abstractmethod
    async def get_fundamentals(self, symbol: str) -> Fundamentals:
        """Return the latest financial snapshot for a symbol.

        Returns a Fundamentals object; fields the source cannot supply are None.
        """
        ...