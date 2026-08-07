from typing import Any


class StudioError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        title: str,
        detail: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.title = title
        self.detail = detail
        self.extra = extra or {}


class NotFoundError(StudioError):
    def __init__(self, resource: str) -> None:
        super().__init__(404, "not_found", "Resource not found", f"{resource} was not found.")


class ConflictError(StudioError):
    def __init__(self, detail: str) -> None:
        super().__init__(409, "conflict", "Resource conflict", detail)


class ValidationError(StudioError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(422, code, "Dataset validation failed", detail)
