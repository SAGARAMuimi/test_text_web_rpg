from .database import Base, engine

# 全モデルをインポートして Base.metadata に登録させる
from .user import User          # noqa: F401
from .character import Character  # noqa: F401
from .dungeon import Dungeon    # noqa: F401
from .enemy import Enemy        # noqa: F401


def create_tables() -> None:
    """
    全テーブルを作成する。
    - 既存テーブルはスキップされる（安全に何度でも実行可能）
    - SQLite / MySQL 共通
    """
    Base.metadata.create_all(bind=engine)
    print("テーブルを作成しました。")


if __name__ == "__main__":
    create_tables()
