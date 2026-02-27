from flask import render_template
from flask_login import login_required

from . import data_bp


@data_bp.get("/")
@login_required
def index():
    return render_template("data/index.html")
