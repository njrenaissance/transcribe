"""Project exception hierarchy."""


class AppError(Exception):
    """Base class for all domain-specific errors in this project."""


class CredentialError(AppError):
    """Raised when required Azure Speech credentials are missing or empty."""
