
from flask import Flask, request, jsonify
from flask_cors import CORS
from apscheduler.schedulers.background import BackgroundScheduler
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
import asyncio
import time
import random
from threading import Thread
import os

app = Flask(__name__)
CORS(app)
scheduler = BackgroundScheduler()
scheduler.start()

# Directory to store session files
SESSIONS_DIR = "sessions"
os.makedirs(SESSIONS_DIR, exist_ok=True)

session_data = {
    "client": None,
    "loop": None,
    "messages": [],
    "target": "",
    "status": "Idle",
    "sent": 0,
    "timeout": 60,
    "sending": False
}

def run_asyncio_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    api_id = int(data['api_id'])
    api_hash = data['api_hash']

    session_file = os.path.join(SESSIONS_DIR, f"{api_id}.session")

    try:
        if os.path.exists(session_file):
            client = TelegramClient(session_file, api_id, api_hash)
        else:
            client = TelegramClient(session_file, api_id, api_hash)
            client.connect()
            if not client.is_user_authorized():
                return jsonify({"error": "User not authorized. Please login once via code."}), 401

        client.start()
        if session_data['loop']:
            session_data['loop'].stop()

        loop = asyncio.new_event_loop()
        t = Thread(target=run_asyncio_loop, args=(loop,), daemon=True)
        t.start()

        session_data['client'] = client
        session_data['loop'] = loop
        session_data['status'] = "Logged in"
        session_data['sent'] = 0
        session_data['messages'] = []
        session_data['sending'] = False

        return jsonify({"message": "Login successful with saved session"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

async def send_messages_async():
    client = session_data['client']
    target = session_data['target']
    timeout = session_data['timeout']
    messages = session_data['messages']
    session_data['status'] = "Sending"
    session_data['sent'] = 0
    session_data['sending'] = True

    try:
        for msg in messages:
            await client.send_message(target, msg)
            session_data['sent'] += 1
            delay = random.randint(max(1, timeout - 30), timeout + 30)
            for _ in range(delay):
                if not session_data['sending']:
                    session_data['status'] = "Stopped"
                    return
                time.sleep(1)
    except Exception as e:
        session_data['status'] = f"Error: {str(e)}"
        session_data['sending'] = False
        return

    session_data['status'] = "Completed"
    session_data['sending'] = False

@app.route('/send', methods=['POST'])
def send_messages():
    data = request.json
    messages = data['messages']
    target = data['target']
    timeout = int(data['timeout'])

    if not session_data['client']:
        return jsonify({"error": "Not logged in"}), 401

    session_data['messages'] = messages
    session_data['target'] = target
    session_data['timeout'] = timeout
    session_data['sent'] = 0

    asyncio.run_coroutine_threadsafe(send_messages_async(), session_data['loop'])
    return jsonify({"message": "Sending started"})

@app.route('/stop', methods=['POST'])
def stop_sending():
    session_data['sending'] = False
    session_data['status'] = "Stopped"
    return jsonify({"message": "Sending stopped"})

@app.route('/status', methods=['GET'])
def get_status():
    return jsonify({
        "status": session_data['status'],
        "sent": session_data['sent'],
        "total": len(session_data['messages']),
        "target": session_data['target']
    })

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
