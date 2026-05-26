import logging
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "app.log"


def setup_logger(name: str = "app") -> logging.Logger:
    logger = logging.getLogger("app")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        return logger

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter("[%(levelname)s] %(message)s")
    console_handler.setFormatter(console_format)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_format = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_format)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


def get_logger(name: str = "app") -> logging.Logger:
    setup_logger()
    return logging.getLogger(name if name == "app" else f"app.{name}")


def log_exception(logger: logging.Logger, exc: Exception, message: str = "Ocurrio una excepcion"):
    logger.exception(f"{message}: {str(exc)}")


def log_error(logger: logging.Logger, exc: Exception, message: str):
    logger.error(f"{message}: {str(exc)}")
