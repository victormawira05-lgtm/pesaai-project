from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import os

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

STATE = {"income": 10.0, "balance": 1240.50, "tx": [{"date":"2026-11-11","desc":"Demo start","amount":10}]}

@app.route('/')
def home(): return send_from_directory('.', 'index.html')

@app.route('/api/health')
def health(): return jsonify(status='ok')

@app.route('/api/balance')
def bal(): return jsonify(STATE)

@app.route('/api/reset-demo', methods=['POST','GET'])
def reset():
    STATE.update({"income":10.0,"balance":1240.50,"tx":[{"date":"2026-11-11","desc":"Demo reset","amount":10}]})
    return jsonify(message='Demo reset to $10 income', income=10, status='ok')

@app.route('/api/paypal/create-order', methods=['POST','GET'])
@app.route('/api/paypal', methods=['POST','GET'])
def paypal():
    return jsonify(message='PayPal order for $10.00 created (mock - add keys in Render env to go live)', approval_url='/', status='success')

@app.route('/api/chat', methods=['POST'])
def chat():
    m = (request.get_json(silent=True) or {}).get('message','')
    return jsonify(reply=f'PesaAI Coach: You said "{m}". Balance ${STATE["balance"]}. Tip: Save 20%!')

@app.route('/<path:p>')
def static_files(p):
    if os.path.exists(p): return send_from_directory('.', p)
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT',10000)))