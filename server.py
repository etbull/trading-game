from flask import Flask, jsonify, request
from flask_cors import CORS 
import random
import time
import threading
import uuid

app = Flask(__name__)
CORS(app)

# ─── MARKET QUESTIONS ────────────────────────────────────────────────────────
MARKETS = [
    {"question": "How many cars are registered in Australia?", "answer": 20100000, "unit": "cars"},
    {"question": "How many McDonald's locations are there worldwide?", "answer": 40000, "unit": "locations"},
    {"question": "What is the population of Tokyo (millions)?", "answer": 13960000, "unit": "people"},
    {"question": "How many bones are in the adult human body?", "answer": 206, "unit": "bones"},
    {"question": "How many litres of blood does the average adult human have?", "answer": 5, "unit": "litres"},
    {"question": "How many countries are in the United Nations?", "answer": 193, "unit": "countries"},
    {"question": "How many words are in the English Oxford Dictionary (thousands)?", "answer": 171000, "unit": "words"},
    {"question": "How many Starbucks locations are there worldwide?", "answer": 35711, "unit": "locations"},
    {"question": "What is the height of Mount Everest in metres?", "answer": 8849, "unit": "metres"},
    {"question": "How many days did it take Apollo 11 to reach the Moon?", "answer": 4, "unit": "days"},
    {"question": "How many piano keys does a standard piano have?", "answer": 88, "unit": "keys"},
    {"question": "How many muscles are in the human body?", "answer": 650, "unit": "muscles"},
    {"question": "How many teeth does an adult human have?", "answer": 32, "unit": "teeth"},
    {"question": "How many floors does the Burj Khalifa have?", "answer": 163, "unit": "floors"},
    {"question": "What is the speed of light in km/s (thousands)?", "answer": 299792, "unit": "km/s"},
    {"question": "How many islands does Indonesia have?", "answer": 17508, "unit": "islands"},
    {"question": "How many gold medals did the USA win at the 2020 Tokyo Olympics?", "answer": 39, "unit": "medals"},
    {"question": "How many languages are spoken in Papua New Guinea?", "answer": 840, "unit": "languages"},
    {"question": "How many episodes does The Simpsons have (as of 2024)?", "answer": 757, "unit": "episodes"},
    {"question": "How many kilometres long is the Great Wall of China?", "answer": 21196, "unit": "km"},
]

# ─── GAME STATE ───────────────────────────────────────────────────────────────
game_state = {
    "active": False,
    "market": None,
    "order_book": {"bids": [], "asks": []},
    "trades": [],
    "players": {},
    "bots": [],
    "start_time": None,
    "duration": 300,  # 5 minutes
    "round": 0,
    "difficulty": "medium",
    "bot_thread": None,
    "lock": threading.Lock()
}

BOT_CONFIGS = [
    {"id": "bot_random",   "name": "Chaos Carl",    "type": "random",  "emoji": "🎲"},
    {"id": "bot_bullish",  "name": "Bullish Brenda", "type": "bullish", "emoji": "🐂"},
    {"id": "bot_scared",   "name": "Scared Steve",   "type": "scared",  "emoji": "😰"},
    {"id": "bot_smart",    "name": "Smart Sam",      "type": "smart",   "emoji": "🧠"},
    {"id": "bot_smart2",   "name": "Sneaky Sanjay",  "type": "smart",   "emoji": "🦊"},
]

DIFFICULTY_SETTINGS = {
    "easy":   {"spread_mult": 1.5, "bot_interval": 4.0, "noise": 0.20},
    "medium": {"spread_mult": 1.0, "bot_interval": 2.5, "noise": 0.12},
    "hard":   {"spread_mult": 0.6, "bot_interval": 1.2, "noise": 0.06},
}

# ─── HELPERS ──────────────────────────────────────────────────────────────────
def make_order(owner_id, owner_name, side, price, qty, is_bot=False):
    return {
        "id": str(uuid.uuid4())[:8],
        "owner_id": owner_id,
        "owner_name": owner_name,
        "side": side,
        "price": round(price, 2),
        "qty": qty,
        "is_bot": is_bot,
        "timestamp": time.time()
    }

def get_true_value():
    return game_state["market"]["answer"] if game_state["market"] else 100

def get_difficulty():
    return DIFFICULTY_SETTINGS[game_state["difficulty"]]

def clean_order_book():
    """Remove filled/zero qty orders."""
    gs = game_state
    gs["order_book"]["bids"] = [o for o in gs["order_book"]["bids"] if o["qty"] > 0]
    gs["order_book"]["asks"] = [o for o in gs["order_book"]["asks"] if o["qty"] > 0]
    gs["order_book"]["bids"].sort(key=lambda x: -x["price"])
    gs["order_book"]["asks"].sort(key=lambda x: x["price"])

def try_match_order(new_order):
    """Try to cross new order against resting book. Returns list of fills."""
    fills = []
    gs = game_state
    opposite = "asks" if new_order["side"] == "bid" else "bids"

    resting = gs["order_book"][opposite]
    for resting_order in resting:
        if new_order["qty"] <= 0:
            break
        if new_order["owner_id"] == resting_order["owner_id"]:
            continue
        # Check crossable
        if new_order["side"] == "bid" and new_order["price"] < resting_order["price"]:
            break
        if new_order["side"] == "ask" and new_order["price"] > resting_order["price"]:
            break

        fill_qty = min(new_order["qty"], resting_order["qty"])
        fill_price = resting_order["price"]

        # Update quantities
        new_order["qty"] -= fill_qty
        resting_order["qty"] -= fill_qty

        # Record trade
        trade = {
            "id": str(uuid.uuid4())[:8],
            "buyer_id": new_order["owner_id"] if new_order["side"] == "bid" else resting_order["owner_id"],
            "buyer_name": new_order["owner_name"] if new_order["side"] == "bid" else resting_order["owner_name"],
            "seller_id": new_order["owner_id"] if new_order["side"] == "ask" else resting_order["owner_id"],
            "seller_name": new_order["owner_name"] if new_order["side"] == "ask" else resting_order["owner_name"],
            "price": fill_price,
            "qty": fill_qty,
            "timestamp": time.time()
        }
        gs["trades"].append(trade)
        fills.append(trade)

        # Update positions
        for pid in [trade["buyer_id"], trade["seller_id"]]:
            if pid not in gs["players"]:
                gs["players"][pid] = {"cash": 1000, "position": 0, "name": "Unknown"}

        gs["players"][trade["buyer_id"]]["cash"] -= fill_price * fill_qty
        gs["players"][trade["buyer_id"]]["position"] += fill_qty
        gs["players"][trade["seller_id"]]["cash"] += fill_price * fill_qty
        gs["players"][trade["seller_id"]]["position"] -= fill_qty

    clean_order_book()
    return fills

# ─── BOT LOGIC ────────────────────────────────────────────────────────────────
def bot_action(bot):
    gs = game_state
    if not gs["active"]:
        return

    true_val = get_true_value()
    diff = get_difficulty()
    noise = diff["noise"]
    spread_mult = diff["spread_mult"]
    bot_type = bot["type"]
    bot_id = bot["id"]
    bot_pos = gs["players"].get(bot_id, {}).get("position", 0)

    perceived = true_val * random.uniform(1 - noise, 1 + noise)
    spread = true_val * 0.04 * spread_mult

    if bot_type == "random":
        # Completely random bids/asks around a noisy value
        base = true_val * random.uniform(0.7, 1.3)
        side = random.choice(["bid", "ask"])
        price = base * random.uniform(0.95, 1.05) if side == "bid" else base * random.uniform(0.95, 1.05)
        qty = random.randint(1, 5)

    elif bot_type == "bullish":
        # Biased upward — bids aggressively, asks high
        perceived *= random.uniform(1.05, 1.2)
        side = "bid" if random.random() < 0.65 else "ask"
        if side == "bid":
            price = perceived * random.uniform(0.98, 1.02)
        else:
            price = perceived * random.uniform(1.04, 1.10)
        qty = random.randint(1, 4)

    elif bot_type == "scared":
        # Wide spreads, small sizes, pulls orders quickly
        side = random.choice(["bid", "ask"])
        scared_spread = spread * 2.5
        if side == "bid":
            price = perceived - scared_spread * random.uniform(0.8, 1.5)
        else:
            price = perceived + scared_spread * random.uniform(0.8, 1.5)
        qty = 1

    elif bot_type == "smart":
        # Tight spread around perceived value; occasional wild bet
        if random.random() < 0.08:  # 8% chance of crazy bet
            side = random.choice(["bid", "ask"])
            price = true_val * random.uniform(0.4, 1.6)
            qty = random.randint(3, 7)
        else:
            # Tight market make
            side = random.choice(["bid", "ask"])
            half_spread = spread * 0.5
            if side == "bid":
                price = perceived - half_spread * random.uniform(0.5, 1.0)
            else:
                price = perceived + half_spread * random.uniform(0.5, 1.0)
            qty = random.randint(2, 5)

            # Lean away from position
            if bot_pos > 5 and side == "bid":
                price *= 0.97
            elif bot_pos < -5 and side == "ask":
                price *= 1.03

    price = max(1, round(price, 2))
    qty = max(1, qty)

    order = make_order(bot_id, bot["name"], side, price, qty, is_bot=True)
    gs["order_book"][side + "s"].append(order)
    try_match_order(order)
    clean_order_book()

    # Occasionally cancel own stale orders
    if random.random() < 0.3:
        own_side = "bids" if random.random() < 0.5 else "asks"
        own_orders = [o for o in gs["order_book"][own_side] if o["owner_id"] == bot_id]
        if own_orders:
            to_cancel = random.choice(own_orders)
            gs["order_book"][own_side] = [o for o in gs["order_book"][own_side] if o["id"] != to_cancel["id"]]

def bot_loop():
    gs = game_state
    while gs["active"]:
        diff = get_difficulty()
        interval = diff["bot_interval"]
        time.sleep(interval * random.uniform(0.5, 1.5))

        with gs["lock"]:
            if not gs["active"]:
                break
            bot = random.choice(gs["bots"])
            bot_action(bot)

# ─── ROUTES ───────────────────────────────────────────────────────────────────
@app.route("/api/start", methods=["POST"])
def start_game():
    data = request.json or {}
    player_name = data.get("player_name", "Trader")
    difficulty = data.get("difficulty", "medium")
    player_id = "player"

    with game_state["lock"]:
        # Reset
        market = random.choice(MARKETS)
        game_state.update({
            "active": True,
            "market": market,
            "order_book": {"bids": [], "asks": []},
            "trades": [],
            "players": {},
            "bots": [dict(b) for b in BOT_CONFIGS],
            "start_time": time.time(),
            "duration": 300,
            "difficulty": difficulty,
        })

        # Init all participants with 1000 cash
        all_ids = [player_id] + [b["id"] for b in BOT_CONFIGS]
        for pid in all_ids:
            name = player_name if pid == player_id else next(b["name"] for b in BOT_CONFIGS if b["id"] == pid)
            game_state["players"][pid] = {"cash": 1000, "position": 0, "name": name}

    # Start bot thread
    t = threading.Thread(target=bot_loop, daemon=True)
    t.start()

    return jsonify({"status": "started", "market_question": market["question"], "player_id": player_id})

@app.route("/api/state", methods=["GET"])
def get_state():
    gs = game_state
    with gs["lock"]:
        if not gs["active"] and gs["start_time"] is None:
            return jsonify({"active": False})

        elapsed = time.time() - gs["start_time"] if gs["start_time"] else 0
        remaining = max(0, gs["duration"] - elapsed)

        if remaining <= 0 and gs["active"]:
            gs["active"] = False
            # Final settlement
            true_val = get_true_value()
            for pid, p in gs["players"].items():
                p["pnl"] = p["cash"] - 1000 + p["position"] * true_val
                p["settlement_value"] = true_val

        bids = sorted(gs["order_book"]["bids"], key=lambda x: -x["price"])[:10]
        asks = sorted(gs["order_book"]["asks"], key=lambda x: x["price"])[:10]

        players_out = {}
        for pid, p in gs["players"].items():
            players_out[pid] = {
                "name": p["name"],
                "cash": round(p["cash"], 2),
                "position": p["position"],
                "pnl": round(p.get("pnl", p["cash"] - 1000), 2)
            }

        recent_trades = sorted(gs["trades"], key=lambda x: -x["timestamp"])[:20]

        return jsonify({
            "active": gs["active"],
            "remaining": round(remaining, 1),
            "market_question": gs["market"]["question"] if gs["market"] else "",
            "true_answer": gs["market"]["answer"] if not gs["active"] else None,
            "unit": gs["market"]["unit"] if gs["market"] else "",
            "order_book": {"bids": bids, "asks": asks},
            "trades": recent_trades,
            "players": players_out,
            "difficulty": gs["difficulty"],
            "bots": gs["bots"],
        })

@app.route("/api/order", methods=["POST"])
def place_order():
    data = request.json
    gs = game_state

    if not gs["active"]:
        return jsonify({"error": "No active game"}), 400

    player_id = "player"
    player = gs["players"].get(player_id)
    if not player:
        return jsonify({"error": "Player not found"}), 400

    side = data.get("side")
    price = float(data.get("price", 0))
    qty = int(data.get("qty", 1))

    if side not in ["bid", "ask"]:
        return jsonify({"error": "Invalid side"}), 400
    if price <= 0:
        return jsonify({"error": "Price must be positive"}), 400
    if qty <= 0 or qty > 20:
        return jsonify({"error": "Qty must be 1-20"}), 400

    # Validate: can player afford?
    if side == "bid":
        cost = price * qty
        if player["cash"] < cost:
            return jsonify({"error": f"Insufficient cash. Need {cost:.2f}, have {player['cash']:.2f}"}), 400
    if side == "ask":
        if player["position"] < qty:
            return jsonify({"error": f"Insufficient position to sell. Have {player['position']}, need {qty}"}), 400

    with gs["lock"]:
        order = make_order(player_id, player["name"], side, price, qty, is_bot=False)
        gs["order_book"][side + "s"].append(order)
        fills = try_match_order(order)
        clean_order_book()

    return jsonify({"status": "ok", "order_id": order["id"], "fills": len(fills)})

@app.route("/api/cancel", methods=["POST"])
def cancel_order():
    data = request.json
    order_id = data.get("order_id")
    gs = game_state

    with gs["lock"]:
        for side in ["bids", "asks"]:
            before = len(gs["order_book"][side])
            gs["order_book"][side] = [
                o for o in gs["order_book"][side]
                if not (o["id"] == order_id and o["owner_id"] == "player")
            ]
            if len(gs["order_book"][side]) < before:
                return jsonify({"status": "cancelled"})

    return jsonify({"error": "Order not found"}), 404

@app.route("/api/take", methods=["POST"])
def take_order():
    """Player hits a resting order directly."""
    data = request.json
    order_id = data.get("order_id")
    gs = game_state

    if not gs["active"]:
        return jsonify({"error": "No active game"}), 400

    player_id = "player"
    player = gs["players"].get(player_id)

    with gs["lock"]:
        for side in ["bids", "asks"]:
            for order in gs["order_book"][side]:
                if order["id"] == order_id:
                    if order["owner_id"] == player_id:
                        return jsonify({"error": "Cannot trade with yourself"}), 400

                    qty = order["qty"]
                    price = order["price"]

                    # Player takes opposite side
                    if side == "bids":  # Player sells to bidder
                        if player["position"] < qty:
                            qty = player["position"]
                        if qty <= 0:
                            return jsonify({"error": "No position to sell"}), 400
                    else:  # Player buys from asker
                        affordable_qty = int(player["cash"] / price)
                        qty = min(qty, affordable_qty)
                        if qty <= 0:
                            return jsonify({"error": "Insufficient cash"}), 400

                    order["qty"] -= qty
                    trade = {
                        "id": str(uuid.uuid4())[:8],
                        "buyer_id": player_id if side == "asks" else order["owner_id"],
                        "buyer_name": player["name"] if side == "asks" else order["owner_name"],
                        "seller_id": player_id if side == "bids" else order["owner_id"],
                        "seller_name": player["name"] if side == "bids" else order["owner_name"],
                        "price": price,
                        "qty": qty,
                        "timestamp": time.time()
                    }
                    gs["trades"].append(trade)

                    # Update positions
                    for pid in [trade["buyer_id"], trade["seller_id"]]:
                        if pid not in gs["players"]:
                            gs["players"][pid] = {"cash": 1000, "position": 0, "name": "Unknown"}
                    gs["players"][trade["buyer_id"]]["cash"] -= price * qty
                    gs["players"][trade["buyer_id"]]["position"] += qty
                    gs["players"][trade["seller_id"]]["cash"] += price * qty
                    gs["players"][trade["seller_id"]]["position"] -= qty

                    clean_order_book()
                    return jsonify({"status": "filled", "price": price, "qty": qty})

    return jsonify({"error": "Order not found"}), 404

@app.route("/api/stop", methods=["POST"])
def stop_game():
    with game_state["lock"]:
        game_state["active"] = False
    return jsonify({"status": "stopped"})

if __name__ == "__main__":
    app.run(debug=False, port=5000, threaded=True)