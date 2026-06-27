import uuid
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from .extensions import db


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="researcher")
    is_active = db.Column(db.Boolean, default=True)
    login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    analyses = db.relationship("Analysis", backref="user", lazy="dynamic")
    logs = db.relationship("Log", backref="user", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_locked(self):
        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        return False

    def record_failed_attempt(self, max_attempts=5, lock_minutes=15):
        self.login_attempts = (self.login_attempts or 0) + 1
        if self.login_attempts >= max_attempts:
            self.locked_until = datetime.utcnow() + timedelta(minutes=lock_minutes)

    def reset_login_attempts(self):
        self.login_attempts = 0
        self.locked_until = None

    def to_dict(self):
        return {
            "id": self.uuid,
            "username": self.username,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Analysis(db.Model):
    __tablename__ = "analyses"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    symbol = db.Column(db.String(20), nullable=False)
    p = db.Column(db.Integer, default=1)
    d = db.Column(db.Integer, default=1)
    q = db.Column(db.Integer, default=2)
    window_size = db.Column(db.Integer, default=500)
    test_size = db.Column(db.Integer, default=100)
    status = db.Column(db.String(20), default="pending")
    rmse = db.Column(db.Float, nullable=True)
    mae = db.Column(db.Float, nullable=True)
    directional_accuracy = db.Column(db.Float, nullable=True)
    sharpe_ratio = db.Column(db.Float, nullable=True)
    aic = db.Column(db.Float, nullable=True)
    bic = db.Column(db.Float, nullable=True)
    result_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reports = db.relationship("Report", backref="analysis", lazy="dynamic")

    def to_dict(self):
        return {
            "id": self.uuid,
            "symbol": self.symbol,
            "model_type": f"ARIMA ({self.p},{self.d},{self.q})",
            "date_ran": self.created_at.strftime("%Y-%m-%d") if self.created_at else "",
            "rmse": self.rmse,
            "mae": self.mae,
            "directional_accuracy": self.directional_accuracy,
            "sharpe_ratio": self.sharpe_ratio,
            "status": self.status,
        }


class Report(db.Model):
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    analysis_id = db.Column(db.Integer, db.ForeignKey("analyses.id"), nullable=True)
    format = db.Column(db.String(10), default="latex")
    content = db.Column(db.Text, nullable=True)
    file_path = db.Column(db.String(256), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Setting(db.Model):
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ForecastTask(db.Model):
    __tablename__ = "forecast_tasks"

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.String(36), unique=True, nullable=False, index=True)
    status = db.Column(db.String(20), default="pending")
    progress = db.Column(db.Integer, default=0)
    logs = db.Column(db.Text, default="[]")
    error = db.Column(db.Text, nullable=True)
    result = db.Column(db.Text, nullable=True)
    symbol = db.Column(db.String(20), nullable=False)
    p = db.Column(db.Integer, default=1)
    d = db.Column(db.Integer, default=1)
    q = db.Column(db.Integer, default=2)
    window_size = db.Column(db.Integer, default=500)
    test_size = db.Column(db.Integer, default=100)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Log(db.Model):
    __tablename__ = "logs"

    id = db.Column(db.Integer, primary_key=True)
    uuid = db.Column(db.String(36), unique=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(50), nullable=False)
    category = db.Column(db.String(50), default="general")
    details = db.Column(db.Text, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.uuid,
            "user": self.user.username if self.user else "system",
            "action": self.action,
            "category": self.category,
            "details": self.details,
            "ip_address": self.ip_address,
            "created_at": self.created_at.isoformat() if self.created_at else "",
        }


def seed_defaults(app):
    from .extensions import db

    if not User.query.filter_by(role="admin").first():
        admin = User(
            username="admin",
            email="admin@ngx-arima.com",
            role="admin",
            is_active=True,
        )
        admin.set_password("admin123")
        db.session.add(admin)

    defaults = {
        "institution_name": "NGX-ARIMA Research Platform",
        "theme": "light",
        "maintenance_mode": "false",
        "default_training_pct": "80",
        "forecast_horizon": "30",
        "confidence_interval": "95",
        "max_ar_order": "5",
        "max_ma_order": "5",
        "adf_significance": "0.05",
        "auto_differencing": "true",
        "max_rolling_window": "1500",
        "cache_duration": "3600",
        "data_source_primary": "simulated",
        "data_source_backup": "simulated",
    }
    for key, value in defaults.items():
        if not Setting.query.filter_by(key=key).first():
            db.session.add(Setting(key=key, value=value))

    db.session.commit()
