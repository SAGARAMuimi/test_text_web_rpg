import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """
    アプリケーション設定クラス

    DB切替方法: .env の DATABASE_URL を変更するだけでOK
      開発 (SQLite) : DATABASE_URL=sqlite:///game.db
      本番 (MySQL)  : DATABASE_URL=mysql+mysqlclient://user:pass@host:3306/dbname
    """

    # --- データベース ---
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite:///game.db"  # .env 未設定時のフォールバック
    )

    # --- Flask ---
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    DEBUG: bool = os.getenv("FLASK_DEBUG", "true").lower() == "true"
