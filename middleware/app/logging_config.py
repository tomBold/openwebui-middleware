import logging
import sys
from typing import Any, cast

import structlog
from structlog.typing import EventDict, FilteringBoundLogger, Processor, WrappedLogger

LEADING_KEYS = ("timestamp", "level", "event")


def order_keys(_: WrappedLogger, __: str, event_dict: EventDict) -> EventDict:
    leading: dict[str, Any] = {
        key: event_dict.pop(key) for key in LEADING_KEYS if key in event_dict
    }
    return {**leading, **event_dict}


def configure_logging(level: str, *, json: bool) -> None:
    renderer: Processor = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            order_keys,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=False,
    )


def get_logger(name: str) -> FilteringBoundLogger:
    return cast("FilteringBoundLogger", structlog.get_logger(name))
