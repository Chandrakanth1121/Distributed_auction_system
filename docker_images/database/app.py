from flask import Flask, request, jsonify, redirect
from leader_election import LeaderElection
from database import Database
import socket
import threading
import time
import os
import requests
import psutil
start_time = time.time()

app = Flask(__name__)

import logging

# Set up basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
SERVER_ID = os.getenv("MY_POD_NAME")
PEERS = os.getenv("PEERS").split(",")
SERVER_IP = socket.gethostbyname(socket.gethostname())

leader_election = LeaderElection(PEERS, start_time)
database = Database(PEERS)

heartbeat_timeout = 15  # Timeout for heartbeat (in seconds)
write_in_progress = False  # Flag for write operation status
read_retry_timeout = 30  # Time limit for retrying read requests

last_heartbeat = time.time()

# Synchronize with leader during startup
leader_ip = leader_election.get_leader(start_time)
while not leader_ip:
    print("waiting for leader election")
    time.sleep(2)

if leader_ip != SERVER_IP:
    logger.info(f"Synchronizing data with leader {leader_ip}...")
    database.synchronize_with_leader(leader_ip)
else:
    logger.info("No synchronization needed, this server is the leader.")

# Periodic heartbeat from the leader
def send_heartbeat():
    while True:
        if leader_election.get_leader(start_time) == SERVER_IP:  # Only leader sends heartbeat
            for peer in PEERS:
                if peer != f"{SERVER_ID}" and leader_election.get_leader(start_time) == SERVER_IP:
                    try:
                        response = requests.post(f"http://{peer}.database-server.database.svc.cluster.local:5001/heartbeat", timeout=2)
                        if response.status_code == 200:
                            logger.info(f"Sent heartbeat to {peer}")
                    except requests.exceptions.Timeout as e:
                        logger.info(f"Timeout while sending heartbeat to peer {peer}: {e}")
                    except requests.exceptions.ConnectionError as e:
                        logger.info(f"Connection error while sending heartbeat to {peer}: {e}")
                    except requests.exceptions.RequestException as e:
                        logger.info(f"Request error while sending heartbeat to peer {peer}: {e}")
                    except Exception as e:
                        logger.info(f"Unexpected error while sending heartbeat to peer {peer}: {e}")
        time.sleep(5)  # Send heartbeat every 5 seconds

# Start the heartbeat thread
heartbeat_thread = threading.Thread(target=send_heartbeat)
heartbeat_thread.daemon = True
heartbeat_thread.start()

# Monitoring heartbeat in followers
def monitor_heartbeat():
    """Monitor the heartbeat of the leader."""
    global last_heartbeat
    last_heartbeat = time.time()
    while True:
        if leader_election.get_leader(start_time) != SERVER_IP:  # Only follower waits for heartbeat
            if time.time() - last_heartbeat > heartbeat_timeout and leader_election.get_leader(start_time) != SERVER_IP:
                logger.info("Leader failed, starting election...")
                leader_election.start_election(start_time)  # Trigger leader election
        time.sleep(10)  # Check every 10 seconds for heartbeat

# Start the heartbeat monitoring thread
monitor_thread = threading.Thread(target=monitor_heartbeat)
monitor_thread.daemon = True
monitor_thread.start()

@app.route('/write', methods=['POST'])
def handle_write():
    global write_in_progress
    global start_time
    leader_ip = leader_election.get_leader(start_time)
    data = request.json
    key = data["key"]
    value = data["value"]
    db_type = data["db_type"]  # Specify which database to write to: "users" or "bids"

    if leader_ip != SERVER_IP:
        try:
            response = requests.post(
                f"http://{leader_ip}:5001/write",
                json={"key": key, "value": value, "db_type": db_type},
                timeout=2
            )
            response.raise_for_status()
            return response.json(), response.status_code
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to forward write to leader {leader_ip}: {e}")
            return jsonify({"error": "Failed to forward write request to the leader"}), 500

    # Begin write operation if this node is the leader
    write_in_progress = True
    database.write_record(key, value, leader_ip, db_type)
    write_in_progress = False
    return jsonify({"message": f"Write successful to {db_type} database"}), 200

@app.route('/add_user', methods=['POST'])
def add_user():
    global write_in_progress
    global start_time
    data = request.json
    username = data["username"]
    password = data["password"]

    leader_ip = leader_election.get_leader(start_time)
    
    if leader_ip != SERVER_IP:
        # Redirect request to the leader
        try:
            response = requests.post(
                f"http://{leader_ip}:5001/add_user",
                json={"username": username, "password": password},
                timeout=2
            )
            response.raise_for_status()
            return response.json(), response.status_code
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to forward add_user request to leader {leader_ip}: {e}")
            return jsonify({"error": "Failed to forward request to the leader"}), 500
    
    # Handle user creation if this is the leader
    write_in_progress = True
    if database.add_user(username, password, leader_ip):
        write_in_progress = False
        return jsonify({"message": f"User {username} added successfully."}), 200
    write_in_progress = False
    return jsonify({"error": f"User {username} already exists."}), 400


@app.route('/read/<db_type>/<key>', methods=['GET'])
def handle_read(db_type, key):
    global start_time
    leader_ip = leader_election.get_leader(start_time)
    timeout = 30
    st_time = time.time()

    while time.time() - st_time < timeout:
        try:
            response = requests.get(f"http://{leader_ip}:5001/lock_status", timeout=2)
            if response.status_code == 200:
                lock_status = response.json().get("write_in_progress", False)
                if not lock_status:
                    value = database.read_record(key, db_type)
                    if value is None:
                        return jsonify({"error": "Record not found"}), 404
                    return jsonify({"key": key, "value": value}), 200
        except requests.exceptions.RequestException as e:
            logger.info(f"Failed to contact leader: {e}")
        time.sleep(2)

    return jsonify({"error": "Read request timed out"}), 503

@app.route('/authenticate_user', methods=['POST'])
def authenticate_user():
    global start_time
    data = request.json
    username = data["username"]
    password = data["password"]

    leader_ip = leader_election.get_leader(start_time)
    timeout = 30  # Maximum wait time in seconds
    st_time = time.time()

    while time.time() - st_time < timeout:
        try:
            response = requests.get(f"http://{leader_ip}:5001/lock_status", timeout=2)
            if response.status_code == 200:
                lock_status = response.json().get("write_in_progress", False)
                if not lock_status:  # Leader is not locked
                    if database.authenticate_user(username, password):
                        return jsonify({"message": "Authentication successful."}), 200
                    return jsonify({"error": "Invalid username or password."}), 401
        except requests.exceptions.RequestException as e:
            logger.info(f"Failed to contact leader: {e}")
        time.sleep(2)
    return jsonify({"error": "Authentication request timed out"}), 503


@app.route('/replicate', methods=['POST'])
def handle_replication():
    data = request.json
    key = data["key"]
    value = data["value"]
    db_type = data["db_type"]
    leader_ip = leader_election.get_leader(start_time)
    database.write_record(key, value, leader_ip, db_type)
    return jsonify({"message": "Replication successful"}), 200

@app.route('/new_leader', methods=['POST'])
def handle_new_leader():
    new_leader_ip = request.json.get("leader_ip")
    logger.info(f"New leader elected: {new_leader_ip}")
    leader_election.leader_ip = new_leader_ip
    return jsonify({"message": "Leader update received"}), 200

@app.route('/heartbeat', methods=['POST'])
def handle_heartbeat():
    """Leader sends a heartbeat. Follower acknowledges."""
    global last_heartbeat
    last_heartbeat = time.time()  # Update the last heartbeat timestamp
    return jsonify({"message": "Heartbeat received"}), 200

@app.route('/lock_status', methods=['GET'])
def handle_lock_status():
    """Return the leader's lock status."""
    return jsonify({"write_in_progress": write_in_progress}), 200

@app.route('/election', methods=['GET'])
def handle_election():
    logger.info("Election endpoint hit")
    uptime = time.time() - start_time
    return jsonify({"ip": SERVER_IP, "uptime": uptime}), 200

@app.route('/liveness', methods=['GET'])
def liveness_probe():
    uptime = time.time() - start_time
    return jsonify({"message": "endpoint is live", "uptime": uptime}), 200

@app.route('/data', methods=['GET'])
def handle_data_request():
    return jsonify(database.get_all_records()), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)