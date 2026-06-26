import os
import uuid
import json
import threading
from flask import Flask, jsonify, request, render_template, send_from_directory
import pandas as pd
import numpy as np
import forecasting

app = Flask(__name__, template_folder="templates", static_folder="static")

# Directories
DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

# In-memory task tracker
ACTIVE_FORECASTS = {}

def init_history():
    """
    Initializes the history database with default runs from the dissertation paper
    so the user sees populated dashboards initially.
    """
    if os.path.exists(HISTORY_FILE):
        return
        
    default_history = [
        {
            "id": str(uuid.uuid4()),
            "symbol": "ASI.NGX",
            "model_type": "ARIMA (1,1,2)",
            "date_ran": "2023-12-22",
            "rmse": 0.009477,
            "mae": 0.006346,
            "directional_accuracy": 57.79,
            "sharpe_ratio": 0.213205
        },
        {
            "id": str(uuid.uuid4()),
            "symbol": "DANGCEM",
            "model_type": "ARIMA (0,1,1)",
            "date_ran": "2023-12-22",
            "rmse": 0.008924,
            "mae": 0.005812,
            "directional_accuracy": 54.12,
            "sharpe_ratio": 0.165412
        },
        {
            "id": str(uuid.uuid4()),
            "symbol": "MTNN",
            "model_type": "ARIMA (2,1,0)",
            "date_ran": "2023-12-22",
            "rmse": 0.009240,
            "mae": 0.006120,
            "directional_accuracy": 52.40,
            "sharpe_ratio": 0.124500
        },
        {
            "id": str(uuid.uuid4()),
            "symbol": "ZENITH",
            "model_type": "ARIMA (1,1,1)",
            "date_ran": "2023-12-22",
            "rmse": 0.009650,
            "mae": 0.006540,
            "directional_accuracy": 51.10,
            "sharpe_ratio": 0.098740
        }
    ]
    with open(HISTORY_FILE, "w") as f:
        json.dump(default_history, f, indent=4)

def save_to_history(symbol, p, d, q, metrics):
    """
    Appends a new forecast result to the history database.
    """
    runs = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                runs = json.load(f)
        except Exception:
            runs = []
            
    new_run = {
        "id": str(uuid.uuid4()),
        "symbol": symbol,
        "model_type": f"ARIMA ({p},{d},{q})",
        "date_ran": pd.Timestamp.now().strftime("%Y-%m-%d"),
        "rmse": round(metrics["arima"]["rmse"], 6),
        "mae": round(metrics["arima"]["mae"], 6),
        "directional_accuracy": round(metrics["arima"]["directional_accuracy"], 2),
        "sharpe_ratio": round(metrics["arima"]["sharpe_ratio"], 6)
    }
    
    # Prepend new run to show it first
    runs.insert(0, new_run)
    
    with open(HISTORY_FILE, "w") as f:
        json.dump(runs, f, indent=4)
        
    return new_run

# --- Pages ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dashboard')
def dashboard_page():
    return render_template('dashboard.html')

# --- API Endpoints ---

@app.route('/api/tickers', methods=['GET'])
def get_tickers():
    tickers = [
        {"symbol": "ASI.NGX", "name": "NGX All-Share Index"},
        {"symbol": "DANGCEM", "name": "Dangote Cement PLC"},
        {"symbol": "MTNN", "name": "MTN Nigeria Communications PLC"},
        {"symbol": "ZENITH", "name": "Zenith Bank PLC"}
    ]
    return jsonify(tickers)

@app.route('/api/data-summary', methods=['GET'])
def get_data_summary():
    symbol = request.args.get('symbol', 'ASI.NGX')
    try:
        filepath = forecasting.get_data_filepath(symbol, DATA_DIR)
        df = pd.read_csv(filepath)
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date')
        
        # We only return a sample of historical closing prices and returns for standard charting
        # to avoid sending 3,000 data points over the wire. Let's return the last 300 points
        sample_df = df.tail(300)
        
        data = {
            "dates": sample_df['Date'].dt.strftime("%Y-%m-%d").tolist(),
            "prices": sample_df['Close'].tolist(),
            "log_returns": sample_df['log_return'].fillna(0.0).tolist(),
            "total_records": len(df),
            "start_date": df['Date'].iloc[0].strftime("%Y-%m-%d"),
            "end_date": df['Date'].iloc[-1].strftime("%Y-%m-%d"),
            "current_price": float(df['Close'].iloc[-1])
        }
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

def async_forecast_worker(task_id, symbol, p, d, q, window_size, test_size):
    """
    Worker function running in a separate thread.
    """
    def progress_cb(current, total):
        pct = int((current / total) * 100)
        ACTIVE_FORECASTS[task_id]["progress"] = pct
        ACTIVE_FORECASTS[task_id]["logs"].append(f"Processing rolling step {current}/{total} ({pct}%)...")

    try:
        ACTIVE_FORECASTS[task_id]["status"] = "running"
        ACTIVE_FORECASTS[task_id]["logs"].append("Loading dataset and calculating log returns...")
        
        # Run pipeline
        result = forecasting.run_forecasting_pipeline(
            symbol=symbol,
            p=p, d=d, q=q,
            window_size=window_size,
            test_size=test_size,
            data_dir=DATA_DIR,
            progress_cb=progress_cb
        )
        
        # Save run to history database
        save_to_history(symbol, p, d, q, result["metrics"])
        
        ACTIVE_FORECASTS[task_id]["status"] = "completed"
        ACTIVE_FORECASTS[task_id]["result"] = result
        ACTIVE_FORECASTS[task_id]["logs"].append("Forecast analysis completed successfully!")
    except Exception as e:
        ACTIVE_FORECASTS[task_id]["status"] = "failed"
        ACTIVE_FORECASTS[task_id]["error"] = str(e)
        ACTIVE_FORECASTS[task_id]["logs"].append(f"CRITICAL ERROR: {str(e)}")

@app.route('/api/start-forecast', methods=['POST'])
def start_forecast():
    body = request.json or {}
    symbol = body.get('symbol', 'ASI.NGX')
    p = int(body.get('p', 1))
    d = int(body.get('d', 1)) # d is recorded but fitting is on returns
    q = int(body.get('q', 2))
    window_size = int(body.get('window_size', 500)) # default to 500 for speed
    test_size = int(body.get('test_size', 100)) # default to 100 for speed

    task_id = str(uuid.uuid4())
    ACTIVE_FORECASTS[task_id] = {
        "status": "pending",
        "progress": 0,
        "logs": ["Initializing forecast task in background..."],
        "error": None,
        "result": None
    }

    # Start task thread
    t = threading.Thread(
        target=async_forecast_worker,
        args=(task_id, symbol, p, d, q, window_size, test_size)
    )
    t.daemon = True
    t.start()

    return jsonify({"task_id": task_id})

@app.route('/api/forecast-status/<task_id>', methods=['GET'])
def get_forecast_status(task_id):
    task = ACTIVE_FORECASTS.get(task_id)
    if not task:
        return jsonify({"error": "Task not found"}), 404
    return jsonify(task)

@app.route('/api/history', methods=['GET'])
def get_history():
    runs = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                runs = json.load(f)
        except Exception:
            runs = []
    return jsonify(runs)

@app.route('/api/export-report', methods=['POST'])
def export_report():
    body = request.json or {}
    task_id = body.get('task_id')
    task = ACTIVE_FORECASTS.get(task_id)
    if not task or task["status"] != "completed":
        return jsonify({"error": "Completed task not found for the provided ID"}), 404
        
    latex_text = forecasting.generate_report_latex(task["result"])
    return jsonify({"latex": latex_text})

# --- Main Initialization ---

if __name__ == '__main__':
    # Generate datasets if they don't exist
    print("Generating simulated sector indices...")
    forecasting.generate_simulated_equities(DATA_DIR)
    
    # Initialize history DB
    init_history()
    
    print("Starting Flask web server on port 5000...")
    app.run(host='0.0.0.0', port=5000, debug=True)
