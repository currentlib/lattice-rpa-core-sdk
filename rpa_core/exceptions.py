class RPAException(Exception):
    """Base exception for RPA operations."""
    pass


class BusinessRuleException(RPAException):
    """Business rule validation failure (e.g. invalid invoice amount). Does NOT trigger retries."""
    pass


class ApplicationException(RPAException):
    """Technical/Application failure (e.g. element timeout, network issue). Triggers automatic retry."""
    pass
