import threading
import requests
import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.info("Info log")
logger.error("Error log")

SERVER_ID = os.getenv("MY_POD_NAME")
PEERS = os.getenv("PEERS").split(",")
SERVER_IP = socket.gethostbyname(socket.gethostname())

class Database:
    def __init__(self, peers):
        self.data = {}
        self.lock = threading.Lock()
        self.peers = peers

    def write_record(self, key, value):
        with self.lock:
            self.data[key] = value
            logger.info(f"Record {key} updated to {value}")
            self.replicate_to_followers(key, value)

    def read_record(self, key):
        with self.lock:
            return self.data.get(key, None)

    def replicate_to_followers(self, key, value):
        for peer in self.peers:
            if peer != f"{SERVER_ID}":
                try:
                    requests.post(f"http://{peer}.database-server.database.svc.cluster.local:5000/replicate", json={"key": key, "value": value}, timeout=2)
                    logger.info(f"Replicated {key} -> {value} to {peer}")
                except requests.exceptions.Timeout as e:
                    logger.info(f"Failed to replicate to {peer}")
                except requests.exceptions.ConnectionError as e:
                    logger.info(f"Failed to replicate to {peer}")
                except requests.exceptions.RequestException as e:
                    logger.info(f"Failed to replicate to {peer}")
                except Exception as e:
                    logger.info(f"Failed to replicate to {peer}")

