from email.mime import message
import logging
from pathlib import Path

from fastapi import logger

BASE_DIR = Path(__file__).resolve().parents[2]
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "app.log"


def setup_logger(name: str = "app") -> logging.Logger:
    """
    Configura y devuelve la instancia de un logger con manejadores para consola y archivo.

    :param name: Nombre que se le asignará al logger.
    :type name: str
    :return: La instancia del logger configurado.
    :rtype: logging.Logger
    """
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
    """
    Obtiene un logger configurado a partir de un nombre dado.

    :param name: El nombre específico del logger que se desea obtener.
    :type name: str
    :return: El logger correspondiente al nombre solicitado.
    :rtype: logging.Logger
    """
    setup_logger()
    return logging.getLogger(name if name == "app" else f"app.{name}")


def log_exception(logger: logging.Logger, exc: Exception, message: str = "Ocurrio una excepcion"):
    """
    Registra una excepción en el logger proporcionado junto con un mensaje y el rastreo de la pila.

    :param logger: El logger donde se registrará la excepción.
    :type logger: logging.Logger
    :param exc: La excepción que ha ocurrido y se desea registrar.
    :type exc: Exception
    :param message: Mensaje descriptivo adicional sobre la excepción.
    :type message: str
    :return: No retorna ningún valor.
    :rtype: None
    """
    logger.exception(f"{message}: {str(exc)}")


def log_error(logger: logging.Logger, exc: Exception, message: str):
    """
    Registra un mensaje de error en el logger proporcionado, incluyendo los detalles de la excepción.

    :param logger: El logger donde se registrará el error.
    :type logger: logging.Logger
    :param exc: La excepción asociada al error.
    :type exc: Exception
    :param message: Mensaje descriptivo del error a registrar.
    :type message: str
    :return: No retorna ningún valor.
    :rtype: None
    """
    logger.error(f"{message}: {str(exc)}")