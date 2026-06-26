from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, request, flash, jsonify
from flask_login import login_required, current_user
from .extensions import db
from .models import User, Analysis, Report, Setting, Log

admin_bp = Blueprint("admin", __name__, template_folder="../templates/admin")


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != "admin":
            flash("Admin access required.", "error")
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route("/")
@login_required
@admin_required
def index():
    stats = {
        "total_users": User.query.count(),
        "total_analyses": Analysis.query.count(),
        "reports_generated": Report.query.count(),
        "today_analyses": Analysis.query.filter(
            Analysis.created_at >= datetime.utcnow().date()
        ).count(),
    }
    recent_logs = (
        Log.query.order_by(Log.created_at.desc()).limit(10).all()
    )
    return render_template("admin/dashboard.html", stats=stats, logs=recent_logs)


@admin_bp.route("/users")
@login_required
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template("admin/users.html", users=all_users)


@admin_bp.route("/users/add", methods=["POST"])
@login_required
@admin_required
def add_user():
    username = request.form.get("username", "").strip()
    email = request.form.get("email", "").strip().lower()
    password = request.form.get("password", "")
    role = request.form.get("role", "researcher")

    if not all([username, email, password]):
        flash("All fields required.", "error")
        return redirect(url_for("admin.users"))

    if User.query.filter_by(username=username).first():
        flash("Username already exists.", "error")
        return redirect(url_for("admin.users"))

    if User.query.filter_by(email=email).first():
        flash("Email already exists.", "error")
        return redirect(url_for("admin.users"))

    user = User(username=username, email=email, role=role)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    Log(
        user_id=current_user.id,
        action="add_user",
        category="admin",
        details=f"Added user: {username}",
        ip_address=request.remote_addr,
    )
    db.session.commit()

    flash(f"User {username} created.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/edit/<uuid>", methods=["POST"])
@login_required
@admin_required
def edit_user(uuid):
    user = User.query.filter_by(uuid=uuid).first_or_404()
    user.username = request.form.get("username", user.username).strip()
    user.email = request.form.get("email", user.email).strip().lower()
    user.role = request.form.get("role", user.role)
    user.is_active = request.form.get("is_active") == "on"

    password = request.form.get("password", "")
    if password:
        user.set_password(password)

    db.session.commit()

    Log(
        user_id=current_user.id,
        action="edit_user",
        category="admin",
        details=f"Edited user: {user.username}",
        ip_address=request.remote_addr,
    )
    db.session.commit()

    flash(f"User {user.username} updated.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/delete/<uuid>", methods=["POST"])
@login_required
@admin_required
def delete_user(uuid):
    user = User.query.filter_by(uuid=uuid).first_or_404()
    if user.id == current_user.id:
        flash("Cannot delete yourself.", "error")
        return redirect(url_for("admin.users"))

    username = user.username
    db.session.delete(user)
    db.session.commit()

    Log(
        user_id=current_user.id,
        action="delete_user",
        category="admin",
        details=f"Deleted user: {username}",
        ip_address=request.remote_addr,
    )
    db.session.commit()

    flash(f"User {username} deleted.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/reset-password/<uuid>", methods=["POST"])
@login_required
@admin_required
def reset_password(uuid):
    user = User.query.filter_by(uuid=uuid).first_or_404()
    new_password = request.form.get("new_password", "reset123")
    user.set_password(new_password)
    db.session.commit()

    Log(
        user_id=current_user.id,
        action="reset_password",
        category="admin",
        details=f"Password reset for: {user.username}",
        ip_address=request.remote_addr,
    )
    db.session.commit()

    flash(f"Password reset for {user.username}.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/settings", methods=["GET", "POST"])
@login_required
@admin_required
def settings():
    if request.method == "POST":
        for key in request.form:
            setting = Setting.query.filter_by(key=key).first()
            if setting:
                setting.value = request.form[key]
        db.session.commit()

        Log(
            user_id=current_user.id,
            action="update_settings",
            category="admin",
            details="System settings updated",
            ip_address=request.remote_addr,
        )
        db.session.commit()

        flash("Settings saved.", "success")
        return redirect(url_for("admin.settings"))

    all_settings = {s.key: s.value for s in Setting.query.all()}
    return render_template("admin/settings.html", settings=all_settings)


@admin_bp.route("/logs")
@login_required
@admin_required
def logs():
    category = request.args.get("category", "")
    query = Log.query.order_by(Log.created_at.desc())

    if category:
        query = query.filter_by(category=category)

    page = request.args.get("page", 1, type=int)
    pagination = query.paginate(page=page, per_page=50)
    return render_template(
        "admin/logs.html", logs=pagination.items, pagination=pagination, category=category
    )


@admin_bp.route("/api/stats")
@login_required
@admin_required
def api_stats():
    return jsonify({
        "total_users": User.query.count(),
        "total_analyses": Analysis.query.count(),
        "reports_generated": Report.query.count(),
        "today_analyses": Analysis.query.filter(
            Analysis.created_at >= datetime.utcnow().date()
        ).count(),
        "active_users": User.query.filter_by(is_active=True).count(),
    })
