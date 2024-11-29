import psutil  # To get uptime information
import requests
import socket
import os
import time

import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.info("Info log")
logger.error("Error log")

def get_uptime(start_time):
    """Get system uptime in seconds."""
    return time.time() - start_time

SERVER_ID = os.getenv("MY_POD_NAME")

class LeaderElection:
    def __init__(self, peers, start_time):
        self.server_ip = socket.gethostbyname(socket.gethostname())
        self.peers = peers
        self.leader_ip = None
        self.uptime = get_uptime(start_time)

    def start_election(self,start_time):
        self.uptime = get_uptime(start_time)
        logger.debug(f"Server {self.server_ip} starting election with uptime {self.uptime}")
        self.leader_ip = self.server_ip

        max_uptime = self.uptime
        max_uptime_ip = self.server_ip

        for peer in self.peers:
            if peer != f"{SERVER_ID}":
                logger.debug(f"Attempting to contact peer: {peer}")
                try:
                    response = requests.get(f"http://{peer}.database-server.database.svc.cluster.local:5000/election", timeout=20)
                    logger.info(f"Received response: {response.status_code}")
                    if response.status_code == 200:
                        peer_info = response.json()
                        if peer_info["uptime"] > max_uptime or (
                                                peer_info["uptime"] == max_uptime and ip_address(peer_info["ip"]) > ip_address(max_uptime_ip)
                                            ):
                                                max_uptime = peer_info["uptime"]
                                                max_uptime_ip = peer_info["ip"]
                                                logger.info(f"New candidate leader: {max_uptime_ip} with uptime {max_uptime}")
                except requests.exceptions.Timeout as e:
                    logger.info(f"Timeout while contacting peer {peer}: {e}")
                except requests.exceptions.ConnectionError as e:
                    logger.info(f"Connection error while contacting peer {peer}: {e}")
                except requests.exceptions.RequestException as e:
                    logger.info(f"Request error while contacting peer {peer}: {e}")
                except Exception as e:
                    logger.info(f"Unexpected error while contacting peer {peer}: {e}")

        self.leader_ip = max_uptime_ip
        logger.info(f"Elected leader: {self.leader_ip}")
        self.broadcast_leader()

    def broadcast_leader(self):
        """Notify all servers about the new leader."""
        for peer in self.peers:
            if peer != f"{SERVER_ID}":
                try:
                    logger.info("broadcast")
                    requests.post(f"http://{peer}.database-server.database.svc.cluster.local:5000/new_leader", json={"leader_ip": self.leader_ip}, timeout=5)
                    logger.info(f"Notified {peer} about new leader: {self.leader_ip}")
                except requests.exceptions.Timeout as e:
                    logger.info(f"Failed to notify {peer} about new leader")
                except requests.exceptions.ConnectionError as e:
                    logger.info(f"Failed to notify {peer} about new leader")
                except requests.exceptions.RequestException as e:
                    logger.info(f"Failed to notify {peer} about new leader")
                except Exception as e:
                    logger.info(f"Failed to notify {peer} about new leader")

    def get_leader(self,start_time):
        """Returns the current leader IP or starts an election."""
        if not self.leader_ip:
            self.start_election(start_time)
        return self.leader_ip

