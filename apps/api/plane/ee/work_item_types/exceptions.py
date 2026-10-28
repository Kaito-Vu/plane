from rest_framework.exceptions import ValidationError


class WorkItemValidationError(ValidationError):
    def __init__(self, code: str, message: str, details: dict | None = None):
        super().__init__({"error_code": code, "error": message, "details": details or {}})
        self.error_code = code
