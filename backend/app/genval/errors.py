from __future__ import annotations


class GenValError(RuntimeError):
    """Base error for Gen/Val provider failures."""


class GenValConfigurationError(GenValError):
    """Raised when a required Gen/Val binary or setting is missing."""


class GenValExecutionError(GenValError):
    """Raised when GenValAppRunner exits unsuccessfully."""


class GenValArtifactError(GenValError):
    """Raised when GenValAppRunner does not create required artifacts."""
