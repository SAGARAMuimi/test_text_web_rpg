from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship

from .database import Base


class Character(Base):
    """
    プレイヤーキャラクターモデル — spec: characters テーブル

    class_type は DBカラム名 'class_type'。
    例: 'Fighter' / 'Mage' / 'Rogue' / 'Cleric'
    """

    __tablename__ = "characters"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    name = Column(String(50), nullable=False)
    class_type = Column(String(50), nullable=False)  # キャラクタークラス
    level = Column(Integer, default=1, nullable=False)
    hp = Column(Integer, nullable=False)
    attack = Column(Integer, nullable=False)

    # 属主ユーザーへの back-reference
    user = relationship("User", back_populates="characters")

    def __repr__(self) -> str:
        return (
            f"<Character id={self.id} name={self.name!r} "
            f"class={self.class_type} lv={self.level}>"
        )
