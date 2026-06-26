import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "ngx-arima-secret-key-change-in-production")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'data', 'ngx_arima.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "jwt-secret-change-in-production")
    JWT_ACCESS_TOKEN_EXPIRES = 3600
    DATA_DIR = os.path.join(BASE_DIR, "data")
    MAX_LOGIN_ATTEMPTS = 5
    ACCOUNT_LOCK_MINUTES = 15
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "data", "uploads")
    DOWNLOAD_FOLDER = os.path.join(BASE_DIR, "data", "downloads")
