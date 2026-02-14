"""Custom exception hierarchy for the core engine (TASK-005)."""


class CoreEngineError(Exception):
    """Base exception for all core engine errors."""


class CapacityError(CoreEngineError):
    """Raised when session creation exceeds maximum capacity."""


class ConcurrentRunError(CoreEngineError):
    """Raised when a second query is attempted on a session with an active run."""


class SessionNotFoundError(CoreEngineError):
    """Raised when a referenced session does not exist."""
