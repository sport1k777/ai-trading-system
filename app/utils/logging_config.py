import logging
import sys

from app.config import LOG_LEVEL


def setup_logging(name=None) -> logging.Logger:
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=level,
            format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
            stream=sys.stdout,
        )

    return logging.getLogger(name)
