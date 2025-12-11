import logging.config

import structlog


def setup_logging(log_level: str, rich_tracebacks: bool, colored_logs: bool) -> dict:
    logging_level = getattr(logging, log_level.upper(), logging.INFO)
    # Full list of processors can be found at:
    # https://www.structlog.org/en/stable/api.html#module-structlog.processors
    shared_processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        # Timestamp format
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=True),
        # If some value is in bytes, decode it to a Unicode str.
        structlog.processors.UnicodeDecoder(),
    ]

    # Configuration for structlog. Shared processors and prepare structlog for the `formatter`
    structlog.configure(
        processors=shared_processors
        + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        # Effectively freeze configuration after creating the first bound logger.
        cache_logger_on_first_use=True,
    )

    # Capture warnings and redirect them to the logging system.
    logging.captureWarnings(True)

    # Configure rich tracebacks if enabled
    if rich_tracebacks:
        exception_formatter = structlog.dev.RichTracebackFormatter(
            max_frames=4, width=130, locals_max_string=30, extra_lines=2
        )
    else:
        exception_formatter = structlog.dev.plain_traceback

    # Configuration for the standard library logging module.
    logging_dict = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "parametrized_formatter": {
                "()": structlog.stdlib.ProcessorFormatter,
                "processors": [
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.dev.ConsoleRenderer(
                        colors=colored_logs,
                        exception_formatter=exception_formatter,
                    ),
                ],
                "foreign_pre_chain": shared_processors,
            },
        },
        "handlers": {
            "default": {
                "level": logging_level,
                "class": "logging.StreamHandler",
                "formatter": "parametrized_formatter",
            },
        },
        "loggers": {
            "": {
                "handlers": ["default"],
                "level": logging_level,
                "propagate": False,
            },
            "uvicorn": {
                "handlers": ["default"],
                "level": logging_level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": ["default"],
                "level": logging_level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["default"],
                "level": logging_level,
                "propagate": False,
            },
            "uvicorn.asgi": {
                "handlers": ["default"],
                "level": logging_level,
                "propagate": False,
            },
            "aiosqlite": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
            "httpx": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
            "httpcore": {
                "handlers": ["default"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }
    logging.config.dictConfig(logging_dict)
    return logging_dict
