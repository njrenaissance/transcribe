"""Project exception hierarchy."""

from pathlib import Path


class AppError(Exception):
    """Base class for all domain-specific errors raised by this project."""


class MissingFileError(AppError):
    """Raised when an input file path does not exist on disk."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"file not found: {path}")
        self.path = path


class UnsupportedFileTypeError(AppError):
    """Raised when an input file's extension is not a supported audio type."""

    def __init__(self, path: Path) -> None:
        super().__init__(f"unsupported file extension '{path.suffix}': {path}")
        self.path = path


class CredentialError(AppError):
    """Raised when required Azure Speech credentials are missing or empty."""


class TranscriptionError(AppError):
    """Raised when a fast-transcription request fails (auth, non-2xx, or network error)."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"fast-transcription request failed for {path}: {reason}")
        self.path = path


class TranscriptionTimeoutError(AppError):
    """Raised when a fast-transcription request exceeds the configured timeout."""

    def __init__(self, path: Path, timeout: float) -> None:
        super().__init__(f"fast-transcription request for {path} timed out after {timeout}s")
        self.path = path
