"""Bounded local logs. No request bodies, passwords, provider headers or raw exceptions."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.security import clean


class SafeFormatter(logging.Formatter):
    def __init__(self, settings):
        super().__init__("%(asctime)s %(levelname)s %(name)s %(message)s")
        self.settings = settings

    def format(self, record):
        return clean(self.settings, super().format(record))


def attach_runtime_log(settings, component):
    folder = Path(make_url(settings.database_url).database).resolve().parent / "logs"
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = folder / (component + ".log")
    path.touch(mode=0o600, exist_ok=True)
    path.chmod(0o600)
    handler = RotatingFileHandler(path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    handler.setFormatter(SafeFormatter(settings))
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    return handler


def detach_runtime_log(handler):
    logging.getLogger("app").removeHandler(handler)
    handler.close()
