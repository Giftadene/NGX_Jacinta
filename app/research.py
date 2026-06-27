from flask import Blueprint, render_template
from flask_login import login_required

research_bp = Blueprint("research", __name__, template_folder="../templates")


@research_bp.route("/eda")
@login_required
def eda():
    return render_template("eda/index.html")

@research_bp.route("/acquisition")
@login_required
def acquisition():
    return render_template("acquisition/index.html")


@research_bp.route("/preprocessing")
@login_required
def preprocessing():
    return render_template("preprocessing/index.html")


@research_bp.route("/stationarity")
@login_required
def stationarity():
    return render_template("stationarity/index.html")


@research_bp.route("/identification")
@login_required
def identification():
    return render_template("identification/index.html")


@research_bp.route("/evaluation")
@login_required
def evaluation():
    return render_template("evaluation/index.html")


@research_bp.route("/export")
@login_required
def export():
    return render_template("export/index.html")
