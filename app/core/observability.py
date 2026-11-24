import contextvars
import json
import logging
import re
import sys
from datetime import datetime, timezone


request_id_context: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_SECRET_PATTERN = re.compile(
    r"(?i)\b(password|secret|token|authorization|cookie)\b\s*[:=]\s*[^,\s;]+"
)


def _redact(value: str) -> str:
    without_emails = _EMAIL_PATTERN.sub("[REDACTED_EMAIL]", value)
    return _SECRET_PATTERN.sub(r"\1=[REDACTED]", without_emails)


class SecurityRedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact(record.getMessage())
        record.args = ()
        return True


class JSONLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        safe_extras = {
            key: value
            for key, value in record.__dict__.items()
            if key in {"account_hash", "ip_hash", "user_id", "action", "status_code"}
            and isinstance(value, (str, int, float, bool))
        }
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", request_id_context.get()),
            "message": _redact(record.getMessage()),
            **{
                key: _redact(value) if isinstance(value, str) else value
                for key, value in safe_extras.items()
            },
        }
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def configure_logging(level: str) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    handlers = root_logger.handlers or [logging.StreamHandler(sys.stderr)]
    if not root_logger.handlers:
        root_logger.addHandler(handlers[0])
    for handler in handlers:
        handler.setFormatter(JSONLogFormatter())
        if not any(isinstance(item, SecurityRedactionFilter) for item in handler.filters):
            handler.addFilter(SecurityRedactionFilter())
