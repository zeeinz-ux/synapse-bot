import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_LOG_FORMAT = "[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_LOG_DIR = None
_LOG_FILE = None

_initialized = False

def get_log_dir():
    global _LOG_DIR
    if _LOG_DIR is None:
        _LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
    return _LOG_DIR

def get_log_file(name="bot"):
    global _LOG_FILE
    if _LOG_FILE is None:
        _LOG_FILE = os.path.join(get_log_dir(), f"{name}.log")
    return _LOG_FILE

def setup_logging(name="bot", level=logging.INFO, log_to_file=True):
    global _initialized
    if _initialized:
        return logging.getLogger(name)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_LOG_DATE_FORMAT)

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(level)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    if log_to_file:
        log_dir = get_log_dir()
        try:
            os.makedirs(log_dir, exist_ok=True)
            fh = RotatingFileHandler(
                get_log_file(name),
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            fh.setLevel(level)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except Exception as e:
            logger.warning("Failed to setup file logging: %s", e)

    _initialized = True
    return logger

def get_logger(name="bot"):
    logger = logging.getLogger(name)
    if not logger.handlers:
        return setup_logging(name)
    return logger
