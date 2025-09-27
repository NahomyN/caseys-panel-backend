import re
import logging
from typing import Any, Dict
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


logger = logging.getLogger(__name__)


_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b")
_SSN = re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b")
_DOB = re.compile(r"\b(?:\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4})\b")
_MRN = re.compile(r"\b(?:MRN|MedRec|Medical\s*Record\s*Number)[:#\s]*\w+\b", re.IGNORECASE)
_ADDR = re.compile(r"\b\d+\s+[A-Za-z0-9'.\-\s]+\b")
_ZIP = re.compile(r"\b\d{5}(?:-\d{4})?\b")


def scrub_phi_text(text: str) -> str:
    if not text:
        return text
    redacted = text
    redacted = _EMAIL.sub("[REDACTED_EMAIL]", redacted)
    redacted = _PHONE.sub("[REDACTED_PHONE]", redacted)
    redacted = _SSN.sub("[REDACTED_SSN]", redacted)
    redacted = _DOB.sub("[REDACTED_DOB]", redacted)
    redacted = _MRN.sub("[REDACTED_MRN]", redacted)
    # Coarse address/zip redaction
    redacted = _ZIP.sub("[REDACTED_ZIP]", redacted)
    return redacted


def _scrub_any(value: Any) -> Any:
    if isinstance(value, str):
        return scrub_phi_text(value)
    if isinstance(value, dict):
        return {k: _scrub_any(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_any(v) for v in value]
    return value


class PHILoggingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # Scrub common attributes that may carry PHI-like strings
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = scrub_phi_text(record.msg)
        if hasattr(record, "args") and isinstance(record.args, tuple):
            record.args = tuple(scrub_phi_text(a) if isinstance(a, str) else a for a in record.args)
        return True


class PHIMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Do not log request bodies; optionally log minimal metadata
        try:
            response = await call_next(request)
        except Exception as e:
            logger.error("Unhandled error: %s", str(e))
            raise
        # Scrub known response headers without clearing (MutableHeaders has no clear())
        # Iterate over a copy of keys to avoid mutation during iteration
        for k in list(response.headers.keys()):
            try:
                v = response.headers.get(k)
                if v is not None:
                    response.headers[k] = scrub_phi_text(v)
            except Exception:
                # Fail soft on unusual header values
                pass
        return response


def scrub_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    return _scrub_any(data)




