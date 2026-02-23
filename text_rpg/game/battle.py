"""
game/battle.py  —  ターン制バトルシステム

フロー:
  1. Battle(party, enemy) でインスタンス化
  2. パーティの各キャラが process_turn(char_index, action) を呼ぶ
       action: 'attack' | 'skill' | 'defend'
  3. 生存全員が行動を終えると自動で敵ターンが処理される
  4. battle.is_over == True になったら battle.result で結果確認
       battle.result: 'victory' | 'defeat'
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# クラス別スキル定義
# ---------------------------------------------------------------------------
SKILLS: dict[str, dict] = {
    "Fighter": {"name": "渾身の一撃",    "desc": "2倍ダメージの強攻撃",               "mp_cost": 20},
    "Mage":    {"name": "ファイアボール", "desc": "防御を無視する魔法攻撃（1.5倍）",     "mp_cost": 25},
    "Rogue":   {"name": "急所攻撃",     "desc": "1〜3倍のランダムダメージ",           "mp_cost": 15},
    "Cleric":  {"name": "ヒール",        "desc": "対象の最大HPの30%を回復",           "mp_cost": 20},
}
_DEFAULT_SKILL: dict = {"name": "必殺技", "desc": "1.5倍ダメージ", "mp_cost": 20}


# ---------------------------------------------------------------------------
# Combatant  —  DB モデルを戦闘用に包むラッパー
# ---------------------------------------------------------------------------
@dataclass
class Combatant:
    """Character / Enemy モデルから生成する戦闘用ステート"""
    name: str
    max_hp: int
    current_hp: int
    attack_power: int
    class_type: str = ""       # Character のみ使用
    is_boss: bool = False      # Enemy のみ使用
    is_defending: bool = False
    max_mp: int = 0             # 最大MP
    current_mp: int = 0         # 現在MP

    @property
    def is_alive(self) -> bool:
        return self.current_hp > 0

    def take_damage(self, damage: int) -> int:
        """ダメージを受ける。防御中なら半減。実ダメージ値を返す。"""
        if self.is_defending:
            damage = max(1, damage // 2)
        self.current_hp = max(0, self.current_hp - damage)
        return damage

    def heal(self, amount: int) -> int:
        """回復する。max_hp を超えない。実回復量を返す。"""
        before = self.current_hp
        self.current_hp = min(self.max_hp, self.current_hp + amount)
        return self.current_hp - before

    def to_dict(self) -> dict:
        return {
            "name":       self.name,
            "hp":         self.current_hp,
            "max_hp":     self.max_hp,
            "mp":         self.current_mp,
            "max_mp":     self.max_mp,
            "class_type": self.class_type,
            "is_alive":   self.is_alive,
            "is_defending": self.is_defending,
            "is_boss":    self.is_boss,
        }


# ---------------------------------------------------------------------------
# Battle  —  バトル管理クラス
# ---------------------------------------------------------------------------
class Battle:
    """
    ターン制バトル管理クラス。

    使用例::

        battle = Battle(party=[char1, char2, char3, char4], enemy=enemy_model)

        # char0 が攻撃
        state = battle.process_turn(0, 'attack')

        # char1 がスキル（Cleric の場合は skill_target でヒール先を指定）
        state = battle.process_turn(1, 'skill', skill_target=2)

        # char2 が防御
        state = battle.process_turn(2, 'defend')

        # char3 が攻撃 → 全員行動済みなので自動で敵ターン実行
        state = battle.process_turn(3, 'attack')

        if battle.is_over:
            print(battle.result)   # 'victory' or 'defeat'
    """

    RESULT_VICTORY = "victory"
    RESULT_DEFEAT  = "defeat"

    def __init__(self, party: list, enemy) -> None:
        """
        Args:
            party: Character モデルインスタンスのリスト（最大4名）
            enemy: Enemy モデルインスタンス
        """
        if not party:
            raise ValueError("パーティが空です。")

        self.fighters: list[Combatant] = [
            Combatant(
                name=c.name,
                max_hp=getattr(c, 'max_hp', c.hp),  # max_hp がなければ hp を使用
                current_hp=c.hp,
                attack_power=c.attack,
                class_type=getattr(c, "class_type", ""),
                max_mp=getattr(c, 'max_mp', 60),
                current_mp=getattr(c, 'mp', getattr(c, 'max_mp', 60)),
            )
            for c in party
        ]
        self.enemy = Combatant(
            name=enemy.name,
            max_hp=enemy.hp,
            current_hp=enemy.hp,
            attack_power=enemy.attack,
            is_boss=bool(getattr(enemy, "is_boss", False)),
        )
        self.logs: list[str] = []
        self._acted: list[bool] = [False] * len(self.fighters)
        self._result: Optional[str] = None

        boss_mark = "👹" if self.enemy.is_boss else "👾"
        self.logs.append(f"{boss_mark} {self.enemy.name} が現れた！（HP: {self.enemy.max_hp}）")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_over(self) -> bool:
        """戦闘が終了していれば True"""
        return self._result is not None

    @property
    def result(self) -> Optional[str]:
        """'victory' / 'defeat' / None（進行中）"""
        return self._result

    def get_state(self) -> dict:
        """現在の戦闘状態を辞書で返す（Flask テンプレートへ渡す用）"""
        return {
            "fighters": [f.to_dict() for f in self.fighters],
            "enemy":    self.enemy.to_dict(),
            "logs":     self.logs[-15:],   # 直近15件
            "result":   self._result,
            "acted":    self._acted[:],
        }

    def get_skill_info(self, char_index: int) -> dict:
        """指定キャラのスキル情報を返す（UI 表示用）"""
        if 0 <= char_index < len(self.fighters):
            ct = self.fighters[char_index].class_type
            return SKILLS.get(ct, _DEFAULT_SKILL)
        return _DEFAULT_SKILL

    def to_session_dict(self) -> dict:
        """
        Flask session へ保存するためのシリアライズ辞書を返す。
        DungeonSession.sync_battle() から呈び出される。
        """
        return {
            "fighters": [
                {
                    "name":         f.name,
                    "max_hp":       f.max_hp,
                    "current_hp":   f.current_hp,
                    "attack_power": f.attack_power,
                    "class_type":   f.class_type,
                    "is_boss":      f.is_boss,
                    "is_defending": f.is_defending,
                    "max_mp":       f.max_mp,
                    "current_mp":   f.current_mp,
                }
                for f in self.fighters
            ],
            "enemy": {
                "name":         self.enemy.name,
                "max_hp":       self.enemy.max_hp,
                "current_hp":   self.enemy.current_hp,
                "attack_power": self.enemy.attack_power,
                "class_type":   self.enemy.class_type,
                "is_boss":      self.enemy.is_boss,
                "is_defending": self.enemy.is_defending,
            },
            "logs":    self.logs,
            "_acted":  self._acted,
            "_result": self._result,
        }

    @classmethod
    def from_session_dict(cls, data: dict) -> "Battle":
        """
        Flask session の dict から Battle を復元する。
        DungeonSession.restore_battle() から啇び出される。
        """
        instance          = cls.__new__(cls)
        instance.fighters = [Combatant(**f) for f in data["fighters"]]
        instance.enemy    = Combatant(**data["enemy"])
        instance.logs     = data["logs"]
        instance._acted   = data["_acted"]
        instance._result  = data["_result"]
        return instance

    def process_turn(
        self,
        char_index: int,
        action: str,
        skill_target: int = 0,
    ) -> dict:
        """
        1キャラのアクションを処理し、全員行動後に敵が自動で反撃する。

        Args:
            char_index  : 行動するパーティメンバーのインデックス (0〜3)
            action      : 'attack' | 'skill' | 'defend'
            skill_target: Cleric のヒール対象インデックス（デフォルト 0）

        Returns:
            get_state() の戦闘状態辞書
        """
        if self.is_over:
            return self.get_state()

        if not (0 <= char_index < len(self.fighters)):
            return self.get_state()

        fighter = self.fighters[char_index]
        if not fighter.is_alive or self._acted[char_index]:
            return self.get_state()

        # --- プレイヤーアクション ---
        if action == "attack":
            self._do_attack(fighter)
        elif action == "skill":
            self._do_skill(fighter, skill_target)
        elif action == "defend":
            self._do_defend(fighter)
        else:
            self._do_attack(fighter)   # 不明なアクションは通常攻撃にフォールバック

        self._acted[char_index] = True

        # 敵撃破判定
        if not self.enemy.is_alive:
            self._result = self.RESULT_VICTORY
            self.logs.append(f"✨ {self.enemy.name} を倒した！ 戦闘勝利！")
            return self.get_state()

        # --- 生存している全員が行動済みなら敵ターン実行 ---
        living_indices = [i for i, f in enumerate(self.fighters) if f.is_alive]
        if living_indices and all(self._acted[i] for i in living_indices):
            self._enemy_turn()
            # 防御フラグ・行動フラグをリセット
            for f in self.fighters:
                f.is_defending = False
            self._acted = [False] * len(self.fighters)
            # 全滅判定
            if not any(f.is_alive for f in self.fighters):
                self._result = self.RESULT_DEFEAT
                self.logs.append("💀 パーティが全滅しました...")

        return self.get_state()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _do_attack(self, fighter: Combatant) -> None:
        """通常攻撃: 基本ダメージ ± 20% のぶれ"""
        damage = _calc_damage(fighter.attack_power)
        actual = self.enemy.take_damage(damage)
        self.logs.append(
            f"⚔️  {fighter.name} の攻撃！"
            f" → {self.enemy.name} に {actual} ダメージ！"
            f"（残HP: {self.enemy.current_hp}/{self.enemy.max_hp}）"
        )

    def _do_skill(self, fighter: Combatant, skill_target: int) -> None:
        """クラス別スキル。MP が不足の場合は通常攻撃にフォールバック。"""
        skill   = SKILLS.get(fighter.class_type, _DEFAULT_SKILL)
        mp_cost = skill.get("mp_cost", 0)

        # MP 不足チェック
        if fighter.current_mp < mp_cost:
            self.logs.append(
                f"💨 {fighter.name} の MP が不足！"
                f"（{fighter.current_mp}/{fighter.max_mp}）→ 通常攻撃に切り替え"
            )
            self._do_attack(fighter)
            return

        fighter.current_mp -= mp_cost
        self.logs.append(
            f"✨ MP 消費: -{mp_cost}"
            f"（残り {fighter.current_mp}/{fighter.max_mp}）"
        )

        if fighter.class_type == "Fighter":
            # 渾身の一撃: 2倍ダメージ
            damage = _calc_damage(fighter.attack_power * 2)
            actual = self.enemy.take_damage(damage)
            self.logs.append(
                f"💥 {fighter.name} の「{skill['name']}」！"
                f" → {self.enemy.name} に {actual} ダメージ！"
                f"（残HP: {self.enemy.current_hp}/{self.enemy.max_hp}）"
            )

        elif fighter.class_type == "Mage":
            # ファイアボール: 1.5倍・防御無視
            damage = _calc_damage(int(fighter.attack_power * 1.5))
            orig = self.enemy.is_defending
            self.enemy.is_defending = False      # 防御貫通
            actual = self.enemy.take_damage(damage)
            self.enemy.is_defending = orig
            self.logs.append(
                f"🔥 {fighter.name} の「{skill['name']}」！"
                f" → {self.enemy.name} に {actual} 魔法ダメージ！（防御無視）"
                f"（残HP: {self.enemy.current_hp}/{self.enemy.max_hp}）"
            )

        elif fighter.class_type == "Rogue":
            # 急所攻撃: 1〜3倍ランダムダメージ
            multiplier = random.uniform(1.0, 3.0)
            damage = _calc_damage(int(fighter.attack_power * multiplier))
            actual = self.enemy.take_damage(damage)
            self.logs.append(
                f"🗡️  {fighter.name} の「{skill['name']}」！"
                f" → {self.enemy.name} に {actual} ダメージ！"
                f"（残HP: {self.enemy.current_hp}/{self.enemy.max_hp}）"
            )

        elif fighter.class_type == "Cleric":
            # ヒール: 対象の最大HPの30%回復
            alive = [f for f in self.fighters if f.is_alive]
            target = alive[skill_target % len(alive)] if alive else fighter
            amount = max(1, int(target.max_hp * 0.30))
            actual = target.heal(amount)
            self.logs.append(
                f"✨ {fighter.name} の「{skill['name']}」！"
                f" → {target.name} の HP を {actual} 回復！"
                f"（{target.current_hp}/{target.max_hp}）"
            )

        else:
            # 未定義クラス: デフォルト 1.5倍攻撃
            damage = _calc_damage(int(fighter.attack_power * 1.5))
            actual = self.enemy.take_damage(damage)
            self.logs.append(
                f"✨ {fighter.name} の「{skill['name']}」！"
                f" → {self.enemy.name} に {actual} ダメージ！"
                f"（残HP: {self.enemy.current_hp}/{self.enemy.max_hp}）"
            )

    def _do_defend(self, fighter: Combatant) -> None:
        """防御: このターンの被ダメージを半減"""
        fighter.is_defending = True
        self.logs.append(
            f"🛡️  {fighter.name} は防御体勢をとった！（このターン被ダメージ半減）"
        )

    def _enemy_turn(self) -> None:
        """敵ターン: 生存中のランダムなパーティメンバーを攻撃"""
        alive = [f for f in self.fighters if f.is_alive]
        if not alive:
            return
        target = random.choice(alive)
        damage = _calc_damage(self.enemy.attack_power)
        actual = target.take_damage(damage)
        boss_mark = "👹" if self.enemy.is_boss else "👾"
        self.logs.append(
            f"{boss_mark} {self.enemy.name} の攻撃！"
            f" → {target.name} に {actual} ダメージ！"
            f"（残HP: {target.current_hp}/{target.max_hp}）"
        )


# ---------------------------------------------------------------------------
# モジュールレベルユーティリティ
# ---------------------------------------------------------------------------

def _calc_damage(base: int) -> int:
    """基本ダメージ値に ±20% のランダムぶれを加える（最低1）"""
    return max(1, int(base * random.uniform(0.8, 1.2)))
