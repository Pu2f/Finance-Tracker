from flask import Flask
from flask import render_template
from config import get_config, validate_required_env

from .extensions import csrf, db, login_manager, migrate
from .models import User


def create_app(config_object=None):
    config_object = config_object or get_config()
    validate_required_env(config_object)

    app = Flask(__name__)
    app.config.from_object(config_object)

    # init extensions
    csrf.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    if app.config.get("AUTO_CREATE_TABLES", False):
        with app.app_context():
            db.create_all()

    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id: str):
        return User.query.get(int(user_id))

    # register blueprints
    from .auth.routes import auth_bp
    from .main.transactions.routes import tx_bp
    from .main.categories.routes import cat_bp
    from .main.dashboard.routes import dash_bp
    from .main.budgets.routes import budget_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(tx_bp)
    app.register_blueprint(cat_bp)
    app.register_blueprint(dash_bp)
    app.register_blueprint(budget_bp)

    # simple home route
    @app.get("/")
    def home():
        return render_template("home.html")

    return app
