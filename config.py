import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
INSTANCE_DIR = BASE_DIR / "instance"
INSTANCE_DIR.mkdir(exist_ok=True)

DEFAULT_SQLITE_URI = (
    f"sqlite:///{(INSTANCE_DIR / 'finance_tracker.sqlite3').as_posix()}"
)


class BaseConfig:
    SQLALCHEMY_TRACK_MODIFICATIONS = False


class DevelopmentConfig(BaseConfig):
    ENV_NAME = "development"
    DEBUG = True
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", DEFAULT_SQLITE_URI)


class ProductionConfig(BaseConfig):
    ENV_NAME = "production"
    DEBUG = False
    SECRET_KEY = os.getenv("SECRET_KEY")
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True


CONFIGS = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}


def get_config():
    env_name = os.getenv("APP_ENV", "development").strip().lower()
    return CONFIGS.get(env_name, DevelopmentConfig)


def validate_required_env(config_class) -> None:
    if config_class is not ProductionConfig:
        return

    missing = []
    if not os.getenv("SECRET_KEY"):
        missing.append("SECRET_KEY")
    if not os.getenv("DATABASE_URL"):
        missing.append("DATABASE_URL")

    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(
            f"Missing required environment variables for production: {missing_str}"
        )
