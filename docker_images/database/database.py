import threading
import requests
import logging
import os
import socket
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERVER_ID = os.getenv("MY_POD_NAME")
PEERS = os.getenv("PEERS").split(",")
SERVER_IP = socket.gethostbyname(socket.gethostname())

class Database:
    def __init__(self, peers, user_file="users.json", bid_file="bids.json"):
        self.user_file = user_file
        self.bid_file = bid_file
        self.lock = threading.Lock()
        self.users = self._load_data(self.user_file)
        self.bids = self._load_data(self.bid_file)
        self.peers = peers

    def _load_data(self, file_name):
        if os.path.exists(file_name):
            with open(file_name, 'r') as file:
                return json.load(file)
        return {}

    def _save_data(self, file_name, data):
        """Save database to file."""
        with open(file_name, 'w') as file:
            json.dump(data, file, indent=4)

    def write_record(self, key, value, leader_ip, db_type):
        self.users = self._load_data(self.user_file)
        self.bids = self._load_data(self.bid_file)
        with self.lock:
            if db_type == "users":
                self.users[key] = value
                logger.info(f"User record {key} updated to {value}\n")
                self._save_data(self.user_file, self.users)
            elif db_type == "bids":
                self.bids[key] = value
                logger.info(f"Bid record {key} updated to {value}\n")
                self._save_data(self.bid_file, self.bids)
            else:
                raise ValueError(f"Invalid database type: {db_type}")

            if SERVER_IP == leader_ip:
                self.replicate_to_followers(key, value, db_type)

    def read_record(self, key, db_type):
        self.users = self._load_data(self.user_file)
        self.bids = self._load_data(self.bid_file)
        with self.lock:
            if db_type == "users":
                return self.users.get(key, None)
            elif db_type == "bids":
                return self.bids.get(key, None)
            else:
                raise ValueError(f"Invalid database type: {db_type}")

    def get_all_records(self):
        return {"users": self.users, "bids": self.bids}

    def synchronize_with_leader(self, leader_ip):
        self.users = self._load_data(self.user_file)
        self.bids = self._load_data(self.bid_file)
        try:
            response = requests.get(f"http://{leader_ip}:5001/data", timeout=5)
            response.raise_for_status()
            leader_data = response.json()

            # Synchronize users
            for key, value in leader_data.get("users", {}).items():
                if key not in self.users or self.users[key] != value:
                    self.users[key] = value
                    logger.info(f"Replicated user record: {key} -> {value}\n")

            # Synchronize bids
            for key, value in leader_data.get("bids", {}).items():
                if key not in self.bids or self.bids[key] != value:
                    self.bids[key] = value
                    logger.info(f"Replicated bid record: {key} -> {value}\n")

            self._save_data(self.user_file, self.users)
            self._save_data(self.bid_file, self.bids)
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to synchronize with leader {leader_ip}: {e}\n")

    def replicate_to_followers(self, key, value, db_type):
        for peer in self.peers:
            if peer != f"{SERVER_ID}":
                try:
                    requests.post(
                        f"http://{peer}.database-server.database.svc.cluster.local:5001/replicate",
                        json={"key": key, "value": value, "db_type": db_type},
                        timeout=2
                    )
                    logger.info(f"Replicated {db_type} record {key} -> {value} to {peer}\n")
                except requests.exceptions.RequestException as e:
                    logger.error(f"Failed to replicate to {peer}: {e}\n")

    def add_user(self, username, password, leader_ip):
        self.users = self._load_data(self.user_file)
        self.bids = self._load_data(self.bid_file)
        if username in self.users:
            return False
        self.users[username] = {"password": password}
        self._save_data(self.user_file, self.users)
        logger.info(f"User {username} added.\n")
        if SERVER_IP == leader_ip:
            self.replicate_to_followers(username, self.users[username], "users")
        return True

    def authenticate_user(self, username, password):
        self.users = self._load_data(self.user_file)
        self.bids = self._load_data(self.bid_file)
        user = self.users.get(username)
        if user and user["password"] == password:
            return True
        return False

