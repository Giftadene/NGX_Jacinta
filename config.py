import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

IS_VERCEL = bool(os.environ.get("VERCEL_ENV")) or bool(os.environ.get("VERCEL"))
if IS_VERCEL:
    DATA_DIR = "/tmp/data"
else:
    DATA_DIR = os.path.join(BASE_DIR, "data")

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "ngx-arima-secret-key-change-in-production")
    DATABASE_URL = os.environ.get("DATABASE_URL", "")
    if DATABASE_URL:
        SQLALCHEMY_DATABASE_URI = DATABASE_URL
    elif IS_VERCEL:
        SQLALCHEMY_DATABASE_URI = f"sqlite:////tmp/ngx_arima.db"
    else:
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.join(DATA_DIR, 'ngx_arima.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "jwt-secret-change-in-production")
    JWT_ACCESS_TOKEN_EXPIRES = 3600
    DATA_DIR = DATA_DIR
    MAX_LOGIN_ATTEMPTS = 5
    ACCOUNT_LOCK_MINUTES = 15
    UPLOAD_FOLDER = os.path.join(DATA_DIR, "uploads")
    DOWNLOAD_FOLDER = os.path.join(DATA_DIR, "downloads")
