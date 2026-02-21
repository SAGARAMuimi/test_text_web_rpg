import random

class Battle:
    def __init__(self, player, monster):
        self.player = player
        self.monster = monster
        self.battle_log = []

    def calculate_damage(self, attacker, defender):
        base_damage = max(1, attacker.attack - defender.defense)
        return random.randint(base_damage - 2, base_damage + 2)

    def execute_turn(self):
        # プレイヤーの攻撃
        player_damage = self.calculate_damage(self.player, self.monster)
        self.monster.hp -= player_damage
        self.battle_log.append(f"{self.player.name}が{player_damage}のダメージを与えた！")

        # モンスターの反撃（HPが残っている場合）
        if self.monster.hp > 0:
            monster_damage = self.calculate_damage(self.monster, self.player)
            self.player.hp -= monster_damage
            self.battle_log.append(f"{self.monster.name}が{monster_damage}のダメージを与えた！")

        return self.battle_log 