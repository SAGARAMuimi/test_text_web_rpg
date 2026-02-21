from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from .database import Base


class Enemy(Base):
    """
    敵モデル — spec: enemies テーブル

    floor: ダンジョン内の出現階層
    is_boss: True の場合はボス敗
    """

    __tablename__ = "enemies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    dungeon_id = Column(Integer, ForeignKey("dungeons.id"), nullable=False)
    floor = Column(Integer, nullable=False)       # 出現階層
    hp = Column(Integer, nullable=False)
    attack = Column(Integer, nullable=False)
    is_boss = Column(Integer, default=0)          # 0=通常, 1=ボス（boolは SQLite/MySQL 両対応で int 使用）

    dungeon = relationship("Dungeon", back_populates="enemies")

    def __repr__(self) -> str:
        boss = " [BOSS]" if self.is_boss else ""
        return f"<Enemy id={self.id} name={self.name!r} floor={self.floor}{boss}>"
