import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from flask import Flask, jsonify

app = Flask(__name__)


# Setup logging
def setup_logging(log_path):
    if not os.path.exists(os.path.dirname(log_path)):
        os.makedirs(os.path.dirname(log_path))

    handler = RotatingFileHandler(log_path, maxBytes=10000000, backupCount=5)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)


@app.route('/health')
def health_check():
    return jsonify({"status": "healthy", "pid": os.getpid()})


@app.route('/api/status')
def status():
    return jsonify({
        "status": "running",
        "pid": os.getpid(),
        "python_version": sys.version
    })


if __name__ == '__main__':
    # Get configuration from command line arguments
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    log_path = sys.argv[2] if len(sys.argv) > 2 else 'logs/flask_app.log'

    setup_logging(log_path)
    app.logger.info(f"Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port)