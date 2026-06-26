import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf


def grid_search_arima(series, max_p=5, max_d=2, max_q=5):
    results = []
    for p in range(max_p + 1):
        for d in range(max_d + 1):
            for q in range(max_q + 1):
                if p == 0 and q == 0:
                    continue
                try:
                    model = ARIMA(
                        series, order=(p, d, q),
                        enforce_stationarity=False,
                        enforce_invertibility=False,
                    )
                    fitted = model.fit()
                    results.append({
                        "order": f"({p},{d},{q})",
                        "p": p, "d": d, "q": q,
                        "aic": round(fitted.aic, 4),
                        "bic": round(fitted.bic, 4),
                        "hqic": round(fitted.hqic, 4),
                        "log_likelihood": round(fitted.llf, 4),
                    })
                except Exception:
                    continue
    results.sort(key=lambda x: x["aic"])
    return results


def suggest_arima_from_acf_pacf(acf_values, pacf_values):
    n = len(acf_values)
    acf_cutoff = 2.0 / np.sqrt(n)
    pacf_cutoff = 2.0 / np.sqrt(n)

    p_estimate = 0
    q_estimate = 0
    for i in range(1, len(pacf_values)):
        if abs(pacf_values[i]) > pacf_cutoff:
            p_estimate = i
        else:
            break
    for i in range(1, len(acf_values)):
        if abs(acf_values[i]) > acf_cutoff:
            q_estimate = i
        else:
            break

    suggestions = [
        {"order": f"({p_estimate},{d},{q_estimate})", "label": "ACF/PACF Estimate", "p": p_estimate, "d": 1, "q": q_estimate},
        {"order": "(1,1,1)", "label": "Parsimonious", "p": 1, "d": 1, "q": 1},
        {"order": "(2,1,2)", "label": "Medium Complexity", "p": 2, "d": 1, "q": 2},
        {"order": "(0,1,1)", "label": "IMA(1,1)", "p": 0, "d": 1, "q": 1},
        {"order": "(1,1,0)", "label": "AR(1)", "p": 1, "d": 1, "q": 0},
    ]
    return suggestions
