import psutil  # To get uptime information
import requests
import socket
import os
import time

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Info log")
logger.error("Error log")

def get_uptime(start_time):
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
        logger.info(f"Server {self.server_ip} starting election with uptime {self.uptime}\n")
        self.leader_ip = self.server_ip

        max_uptime = self.uptime
        max_uptime_ip = self.server_ip

        for peer in self.peers:
            if peer != f"{SERVER_ID}":
                logger.info(f"Attempting to contact peer: {peer}\n")
                try:
                    response = requests.get(f"http://{peer}.database-server.database.svc.cluster.local:5001/election", timeout=20)
                    logger.info(f"Received response: {response.status_code}\n")
                    if response.status_code == 200:
                        peer_info = response.json()
                        if peer_info["uptime"] > max_uptime or (
                                                peer_info["uptime"] == max_uptime and ip_address(peer_info["ip"]) > ip_address(max_uptime_ip)
                                            ):
                                                max_uptime = peer_info["uptime"]
                                                max_uptime_ip = peer_info["ip"]
                                                logger.info(f"New candidate leader: {max_uptime_ip} with uptime {max_uptime}\n")
                except requests.exceptions.Timeout as e:
                    logger.error(f"Timeout while contacting peer {peer}: {e}\n")
                except requests.exceptions.ConnectionError as e:
                    logger.error(f"Connection error while contacting peer {peer}: {e}\n")
                except requests.exceptions.RequestException as e:
                    logger.error(f"Request error while contacting peer {peer}: {e}\n")
                except Exception as e:
                    logger.error(f"Unexpected error while contacting peer {peer}: {e}\n")

        self.leader_ip = max_uptime_ip
        logger.info(f"Elected leader: {self.leader_ip}\n")
        self.broadcast_leader()

    def broadcast_leader(self):
        logger.info("broadcasting new leader to peers\n")
        for peer in self.peers:
            if peer != f"{SERVER_ID}":
                try:
                    requests.post(f"http://{peer}.database-server.database.svc.cluster.local:5001/new_leader", json={"leader_ip": self.leader_ip}, timeout=5)
                    logger.info(f"Notified {peer} about new leader: {self.leader_ip}\n")
                except requests.exceptions.Timeout as e:
                    logger.error(f"Failed to notify {peer} about new leader\n")
                except requests.exceptions.ConnectionError as e:
                    logger.error(f"Failed to notify {peer} about new leader\n")
                except requests.exceptions.RequestException as e:
                    logger.error(f"Failed to notify {peer} about new leader\n")
                except Exception as e:
                    logger.error(f"Failed to notify {peer} about new leader\n")

    def get_leader(self,start_time):
        """Returns the current leader IP or starts an election."""
        if not self.leader_ip:
            self.start_election(start_time)
        return self.leader_ip

