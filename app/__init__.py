# ...
from flask_login import current_user

def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)
    # ... (init/register blueprint เหมือนเดิม)
    # ใหม่: render template แทน return string
    @app.get("/")
    def home():
        return render_template("home.html")
    return app