from flask import Blueprint

tx_bp = Blueprint("transactions", __name__, url_prefix="/transactions")