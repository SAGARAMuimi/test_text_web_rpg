from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# text_rpgパッケージ内外どちらからも安全にインポートできるように
try:
    from config import Config
except ImportError:
    from text_rpg.config import Config

# SQLite は check_same_thread=False が必要。MySQL は不要。
_connect_args = (
    {"check_same_thread": False}
    if Config.DATABASE_URL.startswith("sqlite")
    else {}
)

engine = create_engine(
    Config.DATABASE_URL,
    connect_args=_connect_args,
    # MySQL本番環境向けの推奨設定（SQLite時は無視される）
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Flaskルート内で `db = next(get_db())` として利用する"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
