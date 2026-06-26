import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
from forecasting import generate_simulated_equities
from config import Config

app = create_app()

if __name__ == "__main__":
    print("Ensuring simulated datasets exist...")
    generate_simulated_equities(Config.DATA_DIR)

    print("Starting NGX-ARIMA Platform on port 5000...")
    app.run(host="0.0.0.0", port=5000, debug=True)
