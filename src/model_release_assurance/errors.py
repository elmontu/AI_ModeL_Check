class AssuranceError(Exception):
    """Base exception for assurance failures."""


class ContractError(AssuranceError):
    """The release or threat contract is incomplete or inconsistent."""


class IntegrityError(AssuranceError):
    """A hash, signature, or audit-chain verification failed."""


class AnalyzerError(AssuranceError):
    """An analyzer could not produce valid evidence."""
