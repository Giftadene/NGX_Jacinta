import os
import pandas as pd
import numpy as np
from datetime import datetime

def fetch_ngx_data(symbol="ASI.NGX", start_year=2010, end_year=None, data_dir="data"):
    if end_year is None:
        end_year = datetime.now().year

    raw_path = os.path.join(data_dir, "ngx_asi_raw.csv")
    pre_path = os.path.join(data_dir, "ngx_asi_preprocessed.csv")

    if os.path.exists(pre_path):
        df = pd.read_csv(pre_path)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date")
        available_start = df["Date"].iloc[0].year
        available_end = df["Date"].iloc[-1].year

        if available_start <= start_year and available_end >= end_year:
            mask = (df["Date"].dt.year >= start_year) & (df["Date"].dt.year <= end_year)
            subset = df[mask].copy()
            return {
                "source": "cached",
                "records": len(subset),
                "start_date": subset["Date"].iloc[0].strftime("%Y-%m-%d"),
                "end_date": subset["Date"].iloc[-1].strftime("%Y-%m-%d"),
                "columns": list(subset.columns),
                "summary": subset.describe().to_dict(),
            }

    if os.path.exists(raw_path):
        df = pd.read_csv(raw_path)
        df["Date"] = pd.to_datetime(df["Date"])
        df = df.sort_values("Date")

        if "Close" in df.columns and "log_return" not in df.columns:
            df["log_return"] = np.log(df["Close"] / df["Close"].shift(1))

        df.to_csv(pre_path, index=False)
        mask = (df["Date"].dt.year >= start_year) & (df["Date"].dt.year <= end_year)
        subset = df[mask].copy()
        return {
            "source": "raw_converted",
            "records": len(subset),
            "start_date": subset["Date"].iloc[0].strftime("%Y-%m-%d"),
            "end_date": subset["Date"].iloc[-1].strftime("%Y-%m-%d"),
            "columns": list(subset.columns),
            "summary": subset.describe().to_dict(),
        }

    return {"source": "none", "error": "No data files found. Run generate_simulated_equities first."}


def validate_dataset(filepath):
    df = pd.read_csv(filepath)
    issues = []
    if df["Date"].duplicated().any():
        issues.append(f"Found {df['Date'].duplicated().sum()} duplicate dates")
    if df["Close"].isnull().any():
        issues.append(f"Found {df['Close'].isnull().sum()} missing prices")
    if not pd.api.types.is_numeric_dtype(df["Close"]):
        issues.append("Close column is not numeric")
    if not df["Date"].is_monotonic_increasing:
        issues.append("Dates are not in ascending order")
    return {"valid": len(issues) == 0, "issues": issues, "total_rows": len(df)}
