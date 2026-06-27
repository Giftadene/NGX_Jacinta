import os
import json
import uuid
import pandas as pd
import numpy as np
from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from .extensions import db
from .models import User, Analysis, Report, Log, ForecastTask
from config import Config

api_bp = Blueprint("api", __name__)

_forecast_running = set()


def update_task(task_id, **kwargs):
    task = ForecastTask.query.filter_by(task_id=task_id).first()
    if not task:
        return
    for key, value in kwargs.items():
        if key == "logs":
            existing = json.loads(task.logs or "[]")
            existing.append(value)
            task.logs = json.dumps(existing)
        elif key == "result":
            task.result = json.dumps(value)
        else:
            setattr(task, key, value)
    task.updated_at = datetime.utcnow()
    db.session.commit()


def run_forecast_sync(task_id, symbol, p, d, q, window_size, test_size, user_id=None):
    from forecasting import run_forecasting_pipeline, save_to_history

    update_task(task_id, status="running", logs="Loading dataset...")

    def progress_cb(current, total):
        pct = int((current / total) * 100)
        update_task(task_id, progress=pct, logs=f"Processing rolling step {current}/{total} ({pct}%)...")

    try:
        result = run_forecasting_pipeline(
            symbol=symbol, p=p, d=d, q=q,
            window_size=window_size, test_size=test_size,
            data_dir=Config.DATA_DIR, progress_callback=progress_cb,
        )

        if user_id:
            analysis = Analysis(
                user_id=user_id,
                symbol=symbol, p=p, d=d, q=q,
                window_size=window_size, test_size=test_size,
                status="completed",
                rmse=result["metrics"]["arima"]["rmse"],
                mae=result["metrics"]["arima"]["mae"],
                directional_accuracy=result["metrics"]["arima"]["directional_accuracy"],
                sharpe_ratio=result["metrics"]["arima"]["sharpe_ratio"],
                result_json=json.dumps(result),
            )
            db.session.add(analysis)
            db.session.commit()

        save_to_history(symbol, p, d, q, result["metrics"], Config.DATA_DIR)
        update_task(task_id, status="completed", result=result, logs="Forecast completed!")
    except Exception as e:
        update_task(task_id, status="failed", error=str(e), logs=f"ERROR: {str(e)}")
    finally:
        _forecast_running.discard(task_id)


@api_bp.route("/tickers")
def get_tickers():
    tickers = [
        {"symbol": "ASI.NGX", "name": "NGX All-Share Index"},
        {"symbol": "DANGCEM", "name": "Dangote Cement PLC"},
        {"symbol": "MTNN", "name": "MTN Nigeria Communications PLC"},
        {"symbol": "ZENITH", "name": "Zenith Bank PLC"},
    ]
    return jsonify(tickers)


@api_bp.route("/data-summary")
def get_data_summary():
    symbol = request.args.get("symbol", "ASI.NGX")
    try:
        from forecasting import get_data_filepath
        filepath = get_data_filepath(symbol, Config.DATA_DIR)
        df = pd.read_csv(filepath)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date")
        sample_df = df.tail(300)

        data = {
            "dates": sample_df["Date"].dt.strftime("%Y-%m-%d").tolist(),
            "prices": sample_df["Close"].tolist(),
            "log_returns": sample_df.get("log_return", pd.Series([0.0] * len(sample_df))).fillna(0.0).tolist(),
            "total_records": len(df),
            "start_date": df["Date"].iloc[0].strftime("%Y-%m-%d"),
            "end_date": df["Date"].iloc[-1].strftime("%Y-%m-%d"),
            "current_price": float(df["Close"].iloc[-1]),
        }
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/start-forecast", methods=["POST"])
@login_required
def start_forecast():
    body = request.json or {}
    symbol = body.get("symbol", "ASI.NGX")
    p = int(body.get("p", 1))
    d = int(body.get("d", 1))
    q = int(body.get("q", 2))
    window_size = int(body.get("window_size", 250))
    test_size = int(body.get("test_size", 50))

    task_id = str(uuid.uuid4())
    task = ForecastTask(
        task_id=task_id,
        status="pending",
        progress=0,
        logs=json.dumps(["Initializing..."]),
        symbol=symbol,
        p=p, d=d, q=q,
        window_size=window_size,
        test_size=test_size,
        user_id=current_user.id,
    )
    db.session.add(task)
    db.session.commit()

    Log(
        user_id=current_user.id,
        action="start_forecast",
        category="forecast",
        details=f"{symbol} ARIMA({p},{d},{q}) w={window_size} t={test_size}",
        ip_address=request.remote_addr,
    )
    db.session.commit()

    return jsonify({"task_id": task_id})


@api_bp.route("/forecast-status/<task_id>")
def get_forecast_status(task_id):
    task = ForecastTask.query.filter_by(task_id=task_id).first()
    if not task:
        return jsonify({"error": "Task not found"}), 404

    if task.status == "pending" and task_id not in _forecast_running:
        _forecast_running.add(task_id)
        run_forecast_sync(
            task_id=task_id,
            symbol=task.symbol,
            p=task.p, d=task.d, q=task.q,
            window_size=task.window_size,
            test_size=task.test_size,
            user_id=task.user_id,
        )
        task = ForecastTask.query.filter_by(task_id=task_id).first()

    return jsonify({
        "status": task.status,
        "progress": task.progress,
        "logs": json.loads(task.logs or "[]"),
        "error": task.error,
        "result": json.loads(task.result) if task.result else None,
    })


@api_bp.route("/history")
def get_history():
    history_file = os.path.join(Config.DATA_DIR, "history.json")
    runs = []
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                runs = json.load(f)
        except Exception:
            runs = []
    return jsonify(runs)


@api_bp.route("/my-analyses")
@login_required
def my_analyses():
    analyses = (
        Analysis.query.filter_by(user_id=current_user.id)
        .order_by(Analysis.created_at.desc())
        .all()
    )
    return jsonify([a.to_dict() for a in analyses])


@api_bp.route("/export-report", methods=["POST"])
def export_report():
    body = request.json or {}
    task_id = body.get("task_id")
    task = ForecastTask.query.filter_by(task_id=task_id).first()
    if not task or task.status != "completed":
        return jsonify({"error": "Completed task not found"}), 404

    from forecasting import generate_report_latex
    result = json.loads(task.result) if task.result else None
    if not result:
        return jsonify({"error": "Result data not found"}), 404
    latex_text = generate_report_latex(result)
    return jsonify({"latex": latex_text})


@api_bp.route("/users")
@login_required
def list_users():
    if current_user.role != "admin":
        return jsonify({"error": "Unauthorized"}), 403
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])


@api_bp.route("/analyses")
@login_required
def list_analyses():
    analyses = Analysis.query.order_by(Analysis.created_at.desc()).limit(50).all()
    return jsonify([a.to_dict() for a in analyses])


@api_bp.route("/logs")
@login_required
def list_logs():
    if current_user.role != "admin":
        return jsonify({"error": "Unauthorized"}), 403
    logs = Log.query.order_by(Log.created_at.desc()).limit(100).all()
    return jsonify([l.to_dict() for l in logs])


@api_bp.route("/stationarity", methods=["POST"])
def check_stationarity():
    data = request.get_json() or {}
    symbol = data.get("symbol", "ASI.NGX")
    try:
        from forecasting import get_data_filepath, run_adf_test
        filepath = get_data_filepath(symbol, Config.DATA_DIR)
        df = pd.read_csv(filepath)
        df["log_return"] = np.log(df["Close"] / df["Close"].shift(1))
        df = df.dropna(subset=["log_return"])
        result = run_adf_test(df["log_return"])
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/acf-pacf", methods=["POST"])
def get_acf_pacf():
    data = request.get_json() or {}
    symbol = data.get("symbol", "ASI.NGX")
    nlags = int(data.get("nlags", 20))
    try:
        from forecasting import get_data_filepath, calculate_acf_pacf
        filepath = get_data_filepath(symbol, Config.DATA_DIR)
        df = pd.read_csv(filepath)
        df["log_return"] = np.log(df["Close"] / df["Close"].shift(1))
        df = df.dropna(subset=["log_return"])
        result = calculate_acf_pacf(df["log_return"], nlags=nlags)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/export/csv")
def export_csv():
    symbol = request.args.get("symbol", "ASI.NGX")
    import io, csv
    from forecasting import get_data_filepath
    try:
        filepath = get_data_filepath(symbol, Config.DATA_DIR)
        df = pd.read_csv(filepath)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date")
        si = io.StringIO()
        cw = csv.writer(si)
        cw.writerow(df.columns.tolist())
        for _, row in df.iterrows():
            cw.writerow(row.tolist())
        from flask import Response
        return Response(
            si.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename={symbol}_data.csv"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/export/json")
def export_json():
    symbol = request.args.get("symbol", "ASI.NGX")
    from forecasting import get_data_filepath
    try:
        filepath = get_data_filepath(symbol, Config.DATA_DIR)
        df = pd.read_csv(filepath)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date")
        data = {
            "symbol": symbol,
            "total_records": len(df),
            "start_date": df["Date"].iloc[0].strftime("%Y-%m-%d"),
            "end_date": df["Date"].iloc[-1].strftime("%Y-%m-%d"),
            "data": json.loads(df.to_json(orient="records")),
        }
        from flask import Response
        return Response(
            json.dumps(data, indent=2, default=str),
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment;filename={symbol}_data.json"},
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@api_bp.route("/grid-search", methods=["POST"])
def grid_search():
    data = request.get_json() or {}
    symbol = data.get("symbol", "ASI.NGX")
    max_p = int(data.get("max_p", 5))
    max_d = int(data.get("max_d", 2))
    max_q = int(data.get("max_q", 5))
    try:
        from statsmodels.tsa.arima.model import ARIMA
        from forecasting import get_data_filepath
        filepath = get_data_filepath(symbol, Config.DATA_DIR)
        df = pd.read_csv(filepath)
        df["log_return"] = np.log(df["Close"] / df["Close"].shift(1))
        df = df.dropna(subset=["log_return"])
        series = df["log_return"].values
        results = []
        for p in range(max_p + 1):
            for d in range(max_d + 1):
                for q in range(max_q + 1):
                    if p == 0 and q == 0:
                        continue
                    try:
                        model = ARIMA(series, order=(p, d, q), enforce_stationarity=False, enforce_invertibility=False)
                        fitted = model.fit()
                        results.append({
                            "order": f"({p},{d},{q})",
                            "aic": round(fitted.aic, 4),
                            "bic": round(fitted.bic, 4),
                            "log_likelihood": round(fitted.llf, 4),
                        })
                    except Exception:
                        continue
        results.sort(key=lambda x: x["aic"])
        return jsonify({"results": results[:20]})
    except Exception as e:
        return jsonify({"error": str(e)}), 400
