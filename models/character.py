from sqlalchemy import Column, Integer, String
from .database import Base

class Player(Base):
    __tablename__ = "players"
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    level = Column(Integer, default=1)
    hp = Column(Integer, default=100)
    attack = Column(Integer, default=10)
    defense = Column(Integer, default=5)
    exp = Column(Integer, default=0)

    def level_up(self):
        self.level += 1
        self.hp += 20
        self.attack += 5
        self.defense += 3 