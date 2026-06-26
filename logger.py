import json
import logging
from logging.handlers import RotatingFileHandler


def configure_logging(level=None, log_file=None, log_format=None):
    try:
        with open('cfg/config.json', 'r') as config_file:
            config = json.load(config_file)
    except FileNotFoundError:
        config = {}

    logging_config = config.get('logging', {})
    log_level = (level or logging_config.get('level', 'INFO')).upper()
    log_file = log_file or logging_config.get('file', 'logs/application.log')
    log_format = log_format or logging_config.get('format', '%(asctime)s - %(levelname)s - %(message)s')
    log_max_size = logging_config.get('max_size', 5 * 1024 * 1024)
    log_backup_count = logging_config.get('backup_count', 0)

    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()

    rotating_handler = RotatingFileHandler(
        log_file,
        maxBytes=log_max_size,
        backupCount=log_backup_count,
    )
    rotating_handler.setFormatter(logging.Formatter(log_format))

    root_logger.setLevel(getattr(logging, log_level, logging.INFO))
    root_logger.addHandler(rotating_handler)
    root_logger.addHandler(logging.StreamHandler())

    return root_logger


configure_logging()


def get_logger(name):
    return logging.getLogger(name)
