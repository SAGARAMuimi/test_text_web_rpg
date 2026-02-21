import pytest
from game.battle import Battle
from models.character import Player

def test_battle_system():
    player = Player(name="テストプレイヤー", hp=100, attack=20, defense=10)
    monster = Player(name="テストモンスター", hp=50, attack=15, defense=5)
    
    battle = Battle(player, monster)
    battle.execute_turn()
    
    assert len(battle.battle_log) > 0
    assert monster.hp < 50  # ダメージが与えられていることを確認 