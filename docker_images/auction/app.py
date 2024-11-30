from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import requests
from datetime import datetime, timedelta
import time

app = Flask(__name__)
app.secret_key = 'your_secret_key'

# Server configuration
DATABASE_URL = f'http://database-service-external.database.svc.cluster.local:5001'

# Helper function to get the current time
def current_time():
    return datetime.now()

# Helper function to check if an auction is active
def is_auction_active(auction):
    auction_time = datetime.strptime(auction['created_time'], '%Y-%m-%d %H:%M:%S')
    return current_time() < auction_time + timedelta(days=1)

# Routes
@app.route('/')
def home():
    response = requests.get(f'{DATABASE_URL}/data')
    auctions = response.json().get('bids', {})
    active_auctions = [
        auction for auction in auctions.values() if is_auction_active(auction)
    ]
    return render_template('auction_list.html', auctions=active_auctions)

@app.route('/auction/<auction_id>')
def auction_detail(auction_id):
    response = requests.get(f'{DATABASE_URL}/read/bids/{auction_id}')
    auction = response.json().get('value', {})
    if not auction or not is_auction_active(auction):
        return redirect(url_for('home'))
    return render_template('auction_detail.html', auction=auction, auction_id=auction_id)

@app.route('/bid/<auction_id>', methods=['POST'])
def bid(auction_id):
    if 'user_id' not in session:
        return jsonify({"error": "You must log in to bid."}), 401

    bid_amount = float(request.form['bid_amount'])
    response = requests.get(f'{DATABASE_URL}/read/bids/{auction_id}')
    auction = response.json().get('value', {})

    if not auction:
        return jsonify({"error": "Auction not found."}), 404

    # Check if the auction is active
    created_time = datetime.strptime(auction['created_time'], '%Y-%m-%d %H:%M:%S')
    if current_time() > created_time + timedelta(days=1):
        return jsonify({"error": "Auction is no longer active."}), 400

    # Validate the bid
    highest_bid = auction.get('highest_bid', auction['starting_bid'])
    if bid_amount > highest_bid:
        auction['highest_bid'] = bid_amount
        auction['highest_bidder'] = session['user_id']
        requests.post(
            f'{DATABASE_URL}/write',
            json={"key": auction_id, "value": auction, "db_type": "bids"}
        )
        return redirect(url_for('auction_detail', auction_id=auction_id))
    else:
        return jsonify({"error": "Bid must be higher than the current highest bid."}), 400

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        response = requests.post(f'{DATABASE_URL}/add_user', json={'username': username, 'password': password})
        if response.status_code == 200:
            return redirect(url_for('login'))
        else:
            return jsonify({"error": "User already exists."}), 400
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        response = requests.post(f'{DATABASE_URL}/authenticate_user', json={'username': username, 'password': password})
        if response.status_code == 200:
            session['user_id'] = username
            return redirect(url_for('home'))
        else:
            return jsonify({"error": "Invalid credentials."}), 400
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('home'))

@app.route('/create_auction', methods=['GET', 'POST'])
def create_auction():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        starting_bid = float(request.form['starting_bid'])
        auction = {
            'title': title,
            'description': description,
            'starting_bid': starting_bid,
            'highest_bid': starting_bid,
            'highest_bidder': None,
            'created_time': current_time().strftime('%Y-%m-%d %H:%M:%S')
        }
        auction_id = len(requests.get(f'{DATABASE_URL}/data').json().get('bids', {})) + 1
        requests.post(
            f'{DATABASE_URL}/write',
            json={"key": title, "value": auction, "db_type": "bids"}
        )
        return redirect(url_for('home'))
    return render_template('create_auction.html')

@app.route('/liveness', methods=['GET'])
def liveness():
    return jsonify({"liveness": "Service is live and listening to requests"}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

