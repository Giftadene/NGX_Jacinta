from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from .extensions import db
from .models import User, Log
from config import Config

auth_bp = Blueprint("auth", __name__, template_folder="../templates/auth")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        remember = request.form.get("remember", False)

        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()

        if not user:
            flash("Invalid credentials.", "error")
            return render_template("auth/login.html")

        if not user.is_active:
            flash("This account has been disabled.", "error")
            return render_template("auth/login.html")

        if user.is_locked():
            remaining = (user.locked_until - datetime.utcnow()).seconds // 60
            flash(f"Account locked. Try again in {remaining} minutes.", "error")
            return render_template("auth/login.html")

        if user.check_password(password):
            user.reset_login_attempts()
            login_user(user, remember=remember)
            db.session.commit()

            Log(
                user_id=user.id,
                action="login",
                category="auth",
                details="User logged in successfully",
                ip_address=request.remote_addr,
            )
            db.session.commit()

            if user.role == "admin":
                return redirect(url_for("admin.index"))
            return redirect(url_for("dashboard.index"))
        else:
            user.record_failed_attempt(
                Config.MAX_LOGIN_ATTEMPTS, Config.ACCOUNT_LOCK_MINUTES
            )
            db.session.commit()
            flash("Invalid credentials.", "error")

    return render_template("auth/login.html")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            flash("All fields are required.", "error")
            return render_template("auth/register.html")

        if len(password) < 6:
            flash("Password must be at least 6 characters.", "error")
            return render_template("auth/register.html")

        if User.query.filter_by(username=username).first():
            flash("Username already taken.", "error")
            return render_template("auth/register.html")

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return render_template("auth/register.html")

        user = User(username=username, email=email, role="researcher")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        Log(
            user_id=user.id,
            action="register",
            category="auth",
            details="New researcher registered",
            ip_address=request.remote_addr,
        )
        db.session.commit()

        flash("Registration successful. Please log in.", "success")
        return redirect(url_for("auth.login"))

    return render_template("auth/register.html")


@auth_bp.route("/logout")
@login_required
def logout():
    Log(
        user_id=current_user.id,
        action="logout",
        category="auth",
        details="User logged out",
        ip_address=request.remote_addr,
    )
    db.session.commit()
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        current_pw = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")

        if not current_user.check_password(current_pw):
            flash("Current password is incorrect.", "error")
            return render_template("auth/change_password.html")

        if len(new_pw) < 6:
            flash("New password must be at least 6 characters.", "error")
            return render_template("auth/change_password.html")

        current_user.set_password(new_pw)
        db.session.commit()

        Log(
            user_id=current_user.id,
            action="change_password",
            category="auth",
            details="Password changed",
            ip_address=request.remote_addr,
        )
        db.session.commit()

        flash("Password changed successfully.", "success")
        return redirect(url_for("dashboard.index"))

    return render_template("auth/change_password.html")


@auth_bp.route("/profile")
@login_required
def profile():
    return render_template("auth/profile.html", user=current_user)


@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    user = User.query.filter(
        (User.username == username) | (User.email == username)
    ).first()

    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid credentials"}), 401

    if not user.is_active:
        return jsonify({"error": "Account disabled"}), 403

    from flask_jwt_extended import create_access_token

    token = create_access_token(
        identity=str(user.uuid), additional_claims={"role": user.role}
    )
    return jsonify({"token": token, "user": user.to_dict()})
