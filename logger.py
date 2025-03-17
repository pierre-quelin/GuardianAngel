import logging
import json

# Load logging configuration from config.json
with open('config.json', 'r') as config_file:
    config = json.load(config_file)
    logging_config = config.get('logging', {})

# Extract logging parameters
log_level = logging_config.get('level', 'INFO').upper()
log_file = logging_config.get('file', 'application.log')
log_format = logging_config.get('format', '%(asctime)s - %(levelname)s - %(message)s')

# Configure the logger
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),  # Convert level string to logging constant
    format=log_format,
    handlers=[
        logging.FileHandler(log_file),  # Log to a file
        logging.StreamHandler()  # Log to the console
    ]
)

def get_logger(name):
    return logging.getLogger(name)
