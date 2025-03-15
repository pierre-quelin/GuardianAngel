import json

class Config:
    def __init__(self, config_file='config.json'):
        self.config_file = config_file
        self._data = self._load_config()

    def _load_config(self):
        try:
            with open(self.config_file, 'r') as file:
                return json.load(file)
        except FileNotFoundError:
            raise Exception(f"Configuration file '{self.config_file}' not found.")
        except json.JSONDecodeError:
            raise Exception(f"Error decoding JSON in '{self.config_file}'.")

    def get(self, key, default=None):
        return self._data.get(key, default)