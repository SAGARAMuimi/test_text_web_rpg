from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship

from .database import Base


class Dungeon(Base):
    """
    ダンジョンモデル — spec: dungeons テーブル

    floor: そのダンジョンの最大階層数（要件: 3階層）
    """

    __tablename__ = "dungeons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    floor = Column(Integer, nullable=False)  # 最大階層数

    # 做する敵們 — ダンジョン削除時に cascade
    enemies = relationship(
        "Enemy",
        back_populates="dungeon",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Dungeon id={self.id} name={self.name!r} floor={self.floor}>"
