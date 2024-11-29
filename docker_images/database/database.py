import threading
import requests
import logging
import os
import socket
from leader_election import LeaderElection

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.info("Info log")
logger.error("Error log")

SERVER_ID = os.getenv("MY_POD_NAME")
PEERS = os.getenv("PEERS").split(",")
SERVER_IP = socket.gethostbyname(socket.gethostname())

class Database:
    def __init__(self, peers, file_name="database.json"):
        self.file_name = file_name
        self.lock = threading.Lock()
        self.data = self._load_data()
        self.peers = peers

    def _load_data(self):
        """Load database from file."""
        if os.path.exists(self.file_name):
            with open(self.file_name, 'r') as file:
                return json.load(file)
        return {}

    def _save_data(self):
        """Save database to file."""
        with open(self.file_name, 'w') as file:
            json.dump(self.data, file, indent=4)

    def write_record(self, key, value, leader_ip):
        with self.lock:
            self.data[key] = value
            logger.info(f"Record {key} updated to {value}")
            self._save_data()
            logger.info(f"Record saved: {key} -> {value}")
            if SERVER_IP == leader_ip:
                self.replicate_to_followers(key, value)

    def read_record(self, key):
        with self.lock:
            return self.data.get(key, None)

    def get_all_records(self):
        return self.data

    def synchronize_with_leader(self, leader_ip):
        try:
            response = requests.get(f"http://{leader_ip}:5000/data", timeout=5)
            response.raise_for_status()
            leader_data = response.json()

            # Update local database with changes
            for key, value in leader_data.items():
                if key not in self.data or self.data[key] != value:
                    self.data[key] = value
                    logger.info(f"Replicated record: {key} -> {value}")
            self._save_data()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to synchronize with leader {leader_ip}: {e}")

    def replicate_to_followers(self, key, value):
        for peer in self.peers:
            if peer != f"{SERVER_ID}":
                try:
                    requests.post(f"http://{peer}.database-server.database.svc.cluster.local:5000/replicate", json={"key": key, "value": value}, timeout=2)
                    logger.info(f"Replicated {key} -> {value} to {peer}")
                except requests.exceptions.Timeout as e:
                    logger.info(f"Failed to replicate to {peer}: {e}")
                except requests.exceptions.ConnectionError as e:
                    logger.info(f"Failed to replicate to {peer}: {e}")
                except requests.exceptions.RequestException as e:
                    logger.info(f"Failed to replicate to {peer}: {e}")
                except Exception as e:
                    logger.info(f"Failed to replicate to {peer}: {e}")

