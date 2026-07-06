"""External data provider adapters."""

from stock_mover_screener.providers.alpaca import (
    AlpacaApiError,
    AlpacaCredentialsMissingError,
    AlpacaMarketDataConfig,
    AlpacaMarketDataProvider,
)
from stock_mover_screener.providers.fmp import (
    FmpApiError,
    FmpCredentialsMissingError,
    FmpReferenceConfig,
    FmpReferenceProvider,
)
from stock_mover_screener.providers.finra import (
    FinraApiError,
    FinraShortInterestConfig,
    FinraShortInterestProvider,
    parse_short_interest_file,
)
from stock_mover_screener.providers.sec_edgar import (
    SecEdgarApiError,
    SecEdgarConfig,
    SecEdgarProvider,
    SecTickerNotFoundError,
    SecUserAgentMissingError,
)

__all__ = [
    "AlpacaApiError",
    "AlpacaCredentialsMissingError",
    "AlpacaMarketDataConfig",
    "AlpacaMarketDataProvider",
    "FmpApiError",
    "FmpCredentialsMissingError",
    "FmpReferenceConfig",
    "FmpReferenceProvider",
    "FinraApiError",
    "FinraShortInterestConfig",
    "FinraShortInterestProvider",
    "parse_short_interest_file",
    "SecEdgarApiError",
    "SecEdgarConfig",
    "SecEdgarProvider",
    "SecTickerNotFoundError",
    "SecUserAgentMissingError",
]
