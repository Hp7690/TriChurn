"""Domain errors (mapped to HTTP codes by the service layer, never by this package)."""
from __future__ import annotations


class RevenueIntelligenceError(Exception):
    code = "REVENUE_INTELLIGENCE_ERROR"


class RevenueConfigError(RevenueIntelligenceError):
    code = "CONFIGURATION_INVALID"


class RevenueInputError(RevenueIntelligenceError):
    code = "INVALID_INPUT"


class RevenueDataUnavailableError(RevenueIntelligenceError):
    code = "DATA_UNAVAILABLE"
