"""Distribution installer errors."""


class InstallationValidationError(ValueError):
    """Pre-flight installation/update validation failure."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
