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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SERVER_ID = os.getenv("MY_POD_NAME")
PEERS = os.getenv("PEERS").split(",")
SERVER_IP = socket.gethostbyname(socket.gethostname())

leader_election = LeaderElection(PEERS, start_time)
database = Database(PEERS)

heartbeat_timeout = 15
write_in_progress = False
read_retry_timeout = 30

last_heartbeat = time.time()

leader_ip = leader_election.get_leader(start_time)
while not leader_ip:
    print("waiting for leader election")
    time.sleep(2)

if leader_ip != SERVER_IP:
    logger.info(f"Synchronizing data with leader {leader_ip}...\n")
    database.synchronize_with_leader(leader_ip)
else:
    logger.info("No synchronization needed, this server is the leader.\n")

def send_heartbeat():
    while True:
        if leader_election.get_leader(start_time) == SERVER_IP:  # Only leader sends heartbeat
            for peer in PEERS:
                if peer != f"{SERVER_ID}" and leader_election.get_leader(start_time) == SERVER_IP:
                    try:
                        response = requests.post(f"http://{peer}.database-server.database.svc.cluster.local:5001/heartbeat", timeout=2)
                        if response.status_code == 200:
                            logger.info(f"Sent heartbeat to {peer}\n")
                    except requests.exceptions.Timeout as e:
                        logger.error(f"Timeout while sending heartbeat to peer {peer}: {e}\n")
                    except requests.exceptions.ConnectionError as e:
                        logger.error(f"Connection error while sending heartbeat to {peer}: {e}\n")
                    except requests.exceptions.RequestException as e:
                        logger.error(f"Request error while sending heartbeat to peer {peer}: {e}\n")
                    except Exception as e:
                        logger.error(f"Unexpected error while sending heartbeat to peer {peer}: {e}\n")
        time.sleep(5)  # Send heartbeat every 5 seconds

# Start the heartbeat thread
heartbeat_thread = threading.Thread(target=send_heartbeat)
heartbeat_thread.daemon = True
heartbeat_thread.start()

def monitor_heartbeat():
    global last_heartbeat
    last_heartbeat = time.time()
    while True:
        if leader_election.get_leader(start_time) != SERVER_IP:
            if time.time() - last_heartbeat > heartbeat_timeout and leader_election.get_leader(start_time) != SERVER_IP:
                logger.info("Leader failed, starting election...\n")
                leader_election.start_election(start_time)
        time.sleep(10)

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
    db_type = data["db_type"]

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
            logger.error(f"Failed to forward write to leader {leader_ip}: {e}\n")
            return jsonify({"error": "Failed to forward write request to the leader"}), 500
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
            logger.error(f"Failed to forward add_user request to leader {leader_ip}: {e}\n")
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
            logger.error(f"Failed to contact leader: {e}\n")
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
            logger.error(f"Failed to contact leader: {e}\n")
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
    logger.info(f"New leader elected: {new_leader_ip}\n")
    leader_election.leader_ip = new_leader_ip
    return jsonify({"message": "Leader update received"}), 200

@app.route('/heartbeat', methods=['POST'])
def handle_heartbeat():
    global last_heartbeat
    last_heartbeat = time.time()
    return jsonify({"message": "Heartbeat received"}), 200

@app.route('/lock_status', methods=['GET'])
def handle_lock_status():
    return jsonify({"write_in_progress": write_in_progress}), 200

@app.route('/election', methods=['GET'])
def handle_election():
    logger.info("Election endpoint hit\n")
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