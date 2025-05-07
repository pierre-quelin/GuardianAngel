import logging
import json
from logging.handlers import RotatingFileHandler

# Load logging configuration from config.json
with open('cfg/config.json', 'r') as config_file:
    config = json.load(config_file)
    logging_config = config.get('logging', {})

# Extract logging parameters
log_level = logging_config.get('level', 'INFO').upper()
log_file = logging_config.get('file', 'log/application.log')
log_format = logging_config.get('format', '%(asctime)s - %(levelname)s - %(message)s')
log_max_size = logging_config.get('max_size', 5 * 1024 * 1024)  # Default: 5 MB
log_backup_count = logging_config.get('backup_count', 0)  # Default: No backups

# Configure the logger
rotating_handler = RotatingFileHandler(
    log_file,
    maxBytes=log_max_size,  # Maximum size of the log file in bytes
    backupCount=log_backup_count  # Number of backup files to keep
)
rotating_handler.setFormatter(logging.Formatter(log_format))

logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),  # Convert level string to logging constant
    handlers=[
        rotating_handler,  # Log to a rotating file
        logging.StreamHandler()  # Log to the console
    ]
)

def get_logger(name):
    return logging.getLogger(name)
