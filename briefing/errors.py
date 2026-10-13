"""The one exception type that ends a run with a human-readable reason."""


class BriefingError(Exception):
    """Raised for any run-ending failure; str(e) is the one-line reason."""
