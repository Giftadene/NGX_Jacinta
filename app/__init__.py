import os
import shutil
from flask import Flask, render_template, jsonify, request
from config import Config, IS_VERCEL, DATA_DIR as CFG_DATA_DIR
from .extensions import db, migrate, login_manager, jwt, cors

def create_app(config_class=Config):
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "templates"),
        static_folder=os.path.join(os.path.dirname(os.path.dirname(__file__)), "static"),
        static_url_path="/static",
    )
    app.config.from_object(config_class)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    jwt.init_app(app)
    cors.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    from .models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api/"):
            return jsonify({"error": "Authentication required"}), 401
        return render_template("auth/login.html")

    from .auth import auth_bp
    from .admin import admin_bp
    from .dashboard import dashboard_bp
    from .api import api_bp
    from .research import research_bp

    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(research_bp, url_prefix="/research")

    @app.route("/")
    def index():
        return render_template("index.html")

    if IS_VERCEL:
        os.makedirs(CFG_DATA_DIR, exist_ok=True)
        os.makedirs(os.path.join(CFG_DATA_DIR, "uploads"), exist_ok=True)
        os.makedirs(os.path.join(CFG_DATA_DIR, "downloads"), exist_ok=True)
        src_data = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        if os.path.exists(src_data):
            for f in os.listdir(src_data):
                src_file = os.path.join(src_data, f)
                dst_file = os.path.join(CFG_DATA_DIR, f)
                if os.path.isfile(src_file) and not os.path.exists(dst_file):
                    shutil.copy2(src_file, dst_file)

    with app.app_context():
        from . import models
        db.create_all()
        models.seed_defaults(app)

    return app
