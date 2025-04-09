import requests
import time
import threading
from queue import Queue, Empty
from logger import get_logger

class DiscordApi:
    def __init__(self, cfg):
        """
        Initialize the Discord bot.

        Args:
            cfg (dict): Configuration for the bot (e.g., token, channel ID).
        """
        self.cfg = cfg
        self.logger = get_logger("DiscordApi")

        # Extract configuration
        self.bot_token = cfg.get('bot_token')
        self.channel_id = cfg.get('channel_id')

        # Initialize the message queue
        self.message_queue = Queue()
        self.stop_event = threading.Event()

        # Start the message processing thread
        self.worker_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.worker_thread.start()

    def send_message(self, message):
        """
        Add a message to the queue for sending.

        Args:
            message (str): The message to send.
        """
        self.message_queue.put(message)
        self.logger.info(f"Message added to queue: {message}")

    def _process_queue(self):
        """
        Process the message queue and send messages to Discord.
        """
        while not self.stop_event.is_set():
            try:
                # Get the next message from the queue
                message = self.message_queue.get(timeout=1)  # Wait for a message
                self._send_message_to_discord(message)
                self.message_queue.task_done()
            except Empty: # Timeout when queue is empty
                continue
            except Exception as e:
                self.logger.error(f"Error processing message queue: {e}")

    def _send_message_to_discord(self, message):
        """
        Send a message to Discord.

        Args:
            message (str): The message to send.
        """
        url = f'https://discord.com/api/v10/channels/{self.channel_id}/messages'
        data = {'content': message}
        headers = {
            'Authorization': f'Bot {self.bot_token}',
            'Content-Type': 'application/json'
        }

        try:
            response = requests.post(url, headers=headers, json=data)

            if response.status_code == 200:
                self.logger.info(f"Message '{message}' sent successfully!")
            elif response.status_code == 429:
                retry_after = response.json().get('retry_after', 1)
                self.logger.warning(f"Rate limit hit. Retrying after {retry_after} seconds.")
                time.sleep(retry_after)
                self._send_message_to_discord(message)  # Retry the message
            else:
                self.logger.error(f"Error sending message: {response.status_code} - {response.text}")
        except Exception as e:
            self.logger.error(f"Error sending message: {e}")

    def stop(self):
        """
        Stop the message processing thread.
        """
        self.stop_event.set()
        self.worker_thread.join()