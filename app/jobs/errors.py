class TransientError(Exception):
    """Raised for simulated transient failures that should be retried."""


class QueueFullError(Exception):
    """Raised when the job queue has reached its capacity."""
