from __future__ import annotations

from typing import Dict, Optional


class AcvpSchemaError(Exception):
    def __init__(self, code: str, message: str, path: Optional[str] = None):
        self.code = code
        self.message = message
        self.path = path
        super().__init__(message)

    def to_dict(self) -> Dict[str, object]:
        return {
            "ok": False,
            "errorType": "schema",
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }


def schema_error(code: str, message: str, path: Optional[str] = None) -> AcvpSchemaError:
    return AcvpSchemaError(code, message, path)
