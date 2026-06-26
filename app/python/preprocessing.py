import pandas as pd
import numpy as np


def preprocess_data(df):
    df = df.copy()
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    df = df.drop_duplicates(subset=["Date"])
    df["Close"] = pd.to_numeric(df["Close"], errors="coerce")
    df["Close"] = df["Close"].interpolate(method="linear").bfill()
    df["log_return"] = np.log(df["Close"] / df["Close"].shift(1))
    df["simple_return"] = df["Close"].pct_change()
    df["rolling_mean_5"] = df["Close"].rolling(window=5).mean()
    df["rolling_mean_20"] = df["Close"].rolling(window=20).mean()
    df["rolling_std_20"] = df["Close"].rolling(window=20).std()
    df["volatility"] = df["log_return"].rolling(window=20).std() * np.sqrt(252)
    df["volume_ma"] = (
        df["Volume"].rolling(window=20).mean()
        if "Volume" in df.columns
        else np.nan
    )
    return df


def generate_descriptive_stats(df):
    return {
        "total_days": len(df),
        "start_date": df["Date"].iloc[0].strftime("%Y-%m-%d"),
        "end_date": df["Date"].iloc[-1].strftime("%Y-%m-%d"),
        "min_price": float(df["Close"].min()),
        "max_price": float(df["Close"].max()),
        "mean_price": float(df["Close"].mean()),
        "std_price": float(df["Close"].std()),
        "min_return": float(df["log_return"].min()),
        "max_return": float(df["log_return"].max()),
        "mean_return": float(df["log_return"].mean()),
        "std_return": float(df["log_return"].std()),
        "skewness": float(df["log_return"].skew()),
        "kurtosis": float(df["log_return"].kurtosis()),
    }
