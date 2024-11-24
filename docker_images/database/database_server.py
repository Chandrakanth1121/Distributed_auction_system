from flask import Flask, request, jsonify
import json
import os
import requests

app = Flask(__name__)
pod_name = os.getenv("MY_POD_NAME", "unknown_pod")

# List of other servers to replicate changes
other_servers = os.getenv("OTHER_SERVERS", "").split(",")


class SimpleDatabase:
    def __init__(self, filename="database.json"):
        self.filename = filename
        if not os.path.exists(self.filename) or os.stat(self.filename).st_size == 0:
            app.logger.info("Database file missing or empty. Attempting to sync from peers...")
            self.sync_from_peers()

    def sync_from_peers(self):
        for server in other_servers:
            try:
                response = requests.get(f"{server}/sync", timeout=2)
                if response.status_code == 200:
                    data = response.json()
                    self._save_data(data)
                    print(f"Synced database from {server}")
                    return
            except requests.exceptions.RequestException as e:
                app.logger.info(f"Failed to sync from {server}: {e}")
        print("Unable to sync from peers. Starting with an empty database.")
        self._save_data({})

    def _load_data(self):
        with open(self.filename, 'r') as db_file:
            return json.load(db_file)

    def _save_data(self, data):
        with open(self.filename, 'w') as db_file:
            json.dump(data, db_file, indent=4)

    def add_record(self, key, record):
        data = self._load_data()
        if key in data:
            return {"error": "Key already exists!"}, 400
        data[key] = record
        self._save_data(data)
        return {"message": "Record added successfully to "+pod_name}, 201

    def get_record(self, key):
        data = self._load_data()
        record = data.get(key)
        if record is None:
            return {"error": "Record not found!"}, 404
        return {"key": key, "record": record}, 200

    def update_record(self, key, updated_record):
        data = self._load_data()
        if key not in data:
            return {"error": "Record not found!"}, 404
        # Check if the record already matches the updated value
        if data[key] == updated_record:
            return {"error": "Record already has the updated value!"}, 409  
        data[key] = updated_record
        self._save_data(data)
        return {"message": "Record updated successfully in "+pod_name}, 200

    def delete_record(self, key):
        data = self._load_data()
        if key in data:
            del data[key]
            self._save_data(data)
            return {"message": "Record deleted successfully!"}, 200
        return {"error": "Record not found!"}, 404

    def list_records(self):
        data = self._load_data()
        return data, 200


# Initialize the database
db = SimpleDatabase()

# Replication logic
def replicate_change(endpoint, method, payload=None):
    for server in other_servers:
        url = f"{server}{endpoint}"
        app.logger.info("Replicating to " + server)
        if method == "POST":
            requests.post(url, json=payload, timeout=2)
        elif method == "PUT":
            requests.put(url, json=payload, timeout=2)
        elif method == "DELETE":
            requests.delete(url, timeout=2)

# Flask routes
@app.route('/records', methods=['POST'])
def add_record():
    data = request.get_json()
    key = data.get("key")
    record = data.get("record")
    if not key or not record:
        return {"error": "Key and record are required!"}, 400
    response, status = db.add_record(key, record)
    if status == 201:
        replicate_change(f"/records", "POST", {"key": key, "record": record})
    return response, status

@app.route('/records/<key>', methods=['GET'])
def get_record(key):
    return db.get_record(key)

@app.route('/records/<key>', methods=['PUT'])
def update_record(key):
    updated_record = request.get_json()
    response, status = db.update_record(key, updated_record)
    if status == 200:
        replicate_change(f"/records/{key}", "PUT", updated_record)
    return response, status

@app.route('/records/<key>', methods=['DELETE'])
def delete_record(key):
    response, status = db.delete_record(key)
    if status == 200:
        replicate_change(f"/records/{key}", "DELETE")
    return response, status

@app.route('/records', methods=['GET'])
def list_records():
    return db.list_records()

@app.route('/sync', methods=['GET'])
def sync_database():
    data, _ = db.list_records()
    return jsonify(data), 200

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000, debug=True)

