import os
import json
import pandas as pd
import numpy as np
from flask import Blueprint, jsonify, request
from flask_login import login_required, current_user
from .extensions import db
from .models import User, Analysis, Report, Log
from config import Config

api_bp = Blueprint("api", __name__)


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
    from forecasting import run_forecasting_pipeline, save_to_history

    body = request.json or {}
    symbol = body.get("symbol", "ASI.NGX")
    p = int(body.get("p", 1))
    d = int(body.get("d", 1))
    q = int(body.get("q", 2))
    window_size = int(body.get("window_size", 250))
    test_size = int(body.get("test_size", 50))

    try:
        result = run_forecasting_pipeline(
            symbol=symbol, p=p, d=d, q=q,
            window_size=window_size, test_size=test_size,
            data_dir=Config.DATA_DIR,
        )

        if current_user.is_authenticated:
            analysis = Analysis(
                user_id=current_user.id,
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

        Log(
            user_id=current_user.id,
            action="start_forecast",
            category="forecast",
            details=f"{symbol} ARIMA({p},{d},{q}) w={window_size} t={test_size}",
            ip_address=request.remote_addr,
        )
        db.session.commit()

        return jsonify({"status": "completed", "result": result})
    except Exception as e:
        return jsonify({"status": "failed", "error": str(e)}), 400





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
    from forecasting import generate_report_latex
    result_data = body.get("result")
    if result_data:
        latex_text = generate_report_latex(result_data)
        return jsonify({"latex": latex_text})
    return jsonify({"error": "Result data not provided"}), 400


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
