from flask import Flask, request, jsonify, g, send_from_directory, Response
from flask_cors import CORS
import sqlite3
import hashlib
import json
import time
from queue import Queue

# --- Twilio WhatsApp Alert Integration ---
from twilio.rest import Client

def send_alert(message):
    try:
        # 🔹 Your Twilio credentials
        account_sid = "AC35f644d923d6eee48d85e96a7732b262"
        auth_token = "f42fd4ab05ffe1b3ce3e6e140a1a17c4"
        client = Client(account_sid, auth_token)

        client.messages.create(
            body=message,
            from_="whatsapp:+14155238886",   # Twilio WhatsApp Sandbox number
            to="whatsapp:+918310002064"      # ✅ Your WhatsApp number
        )
        print("✅ WhatsApp Alert sent:", message)
    except Exception as e:
        print("⚠️ Could not send WhatsApp alert:", e)


DB = 'iotopia.db'
app = Flask(__name__, static_folder='static')
CORS(app)

subscribers = []

# ---------- DB ----------
def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''
    CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL,
        patient_id TEXT,
        vitals_json TEXT,
        ai_result TEXT,
        record_hash TEXT
    )
    ''')
    conn.commit()
    conn.close()

# ---------- Helpers ----------
def compute_hash(payload: dict) -> str:
    s = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(s.encode('utf-8')).hexdigest()

def ai_check(vitals: dict) -> str:
    alerts = []
    hr = vitals.get('heart_rate')
    spo2 = vitals.get('spo2')
    glucose = vitals.get('glucose')
    temp = vitals.get('temp')

    if hr is not None and hr > 120:
        alerts.append('High heart rate — possible arrhythmia')
    if spo2 is not None and spo2 < 92:
        alerts.append('Low oxygen level — possible respiratory issue')
    if glucose is not None and glucose > 200:
        alerts.append('High glucose — possible diabetes complication')
    if temp is not None and temp > 38.0:
        alerts.append('Fever — possible infection')

    if not alerts:
        return 'Normal'

    # ---------- NEW: Send WhatsApp Alert ----------
    alert_message = "; ".join(alerts)
    send_alert(f"⚠️ Critical Alert: {alert_message} | Vitals: {vitals}")

    return alert_message

def broadcast_event(event: dict):
    payload = f"data: {json.dumps(event)}\n\n"
    to_remove = []
    for q in subscribers:
        try:
            q.put(payload)
        except Exception:
            to_remove.append(q)
    for r in to_remove:
        subscribers.remove(r)

# ---------- Routes ----------
@app.route('/')
def index():
    return send_from_directory('static', 'index.html')

@app.route('/ingest', methods=['POST'])
def ingest():
    data = request.get_json()
    patient_id = data.get('patient_id', 'unknown')
    vitals = data.get('vitals', {})
    ts = time.time()

    ai_result = ai_check(vitals)

    record = {
        'timestamp': ts,
        'patient_id': patient_id,
        'vitals': vitals,
        'ai_result': ai_result
    }

    record_hash = compute_hash(record)

    db = get_db()
    c = db.cursor()
    c.execute('INSERT INTO records (timestamp, patient_id, vitals_json, ai_result, record_hash) VALUES (?, ?, ?, ?, ?)',
              (ts, patient_id, json.dumps(vitals), ai_result, record_hash))
    db.commit()
    record_id = c.lastrowid

    broadcast_event({'type': 'new_record', 'id': record_id, 'record': record, 'hash': record_hash})

    return jsonify({'status': 'ok', 'id': record_id, 'hash': record_hash})

@app.route('/records', methods=['GET'])
def get_records():
    db = get_db()
    c = db.cursor()
    c.execute('SELECT id, timestamp, patient_id, vitals_json, ai_result, record_hash FROM records ORDER BY id DESC LIMIT 100')
    rows = c.fetchall()
    out = []
    for r in rows:
        out.append({
            'id': r['id'],
            'timestamp': r['timestamp'],
            'patient_id': r['patient_id'],
            'vitals': json.loads(r['vitals_json']),
            'ai_result': r['ai_result'],
            'hash': r['record_hash']
        })
    return jsonify(out)

@app.route('/verify/<int:record_id>', methods=['GET'])
def verify(record_id):
    db = get_db()
    c = db.cursor()
    c.execute('SELECT timestamp, patient_id, vitals_json, ai_result, record_hash FROM records WHERE id=?', (record_id,))
    r = c.fetchone()
    if not r:
        return jsonify({'status': 'not_found'}), 404
    payload = {
        'timestamp': r['timestamp'],
        'patient_id': r['patient_id'],
        'vitals': json.loads(r['vitals_json']),
        'ai_result': r['ai_result']
    }
    recomputed = compute_hash(payload)
    valid = (recomputed == r['record_hash'])
    return jsonify({'valid': valid, 'stored_hash': r['record_hash'], 'recomputed': recomputed})

@app.route('/stream')
def stream():
    def gen():
        q = Queue()
        subscribers.append(q)
        try:
            while True:
                data = q.get()
                yield data
        except GeneratorExit:
            try:
                subscribers.remove(q)
            except Exception:
                pass
    return Response(gen(), mimetype='text/event-stream')

if __name__ == '__main__':
    init_db()
    print('Starting IoTopia backend on http://127.0.0.1:5000')
    app.run(debug=True, threaded=True)
