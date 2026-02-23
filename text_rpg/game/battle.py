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
    "Fighter":    {"name": "渾身の一撃",    "desc": "2倍ダメージの強攻撃",                          "mp_cost": 20},
    "Mage":       {"name": "ファイアボール", "desc": "防御を無視する魔法攻撃（1.5倍）",          "mp_cost": 25},
    "Rogue":      {"name": "急所攻撃",     "desc": "1〜3倍のランダムダメージ",                  "mp_cost": 15},
    "Cleric":     {"name": "ヒール",        "desc": "対象の最大HPの30%を回復",                  "mp_cost": 20},
    "Archer":     {"name": "狙い撃ち",    "desc": "ブレなし確定2.2倍クリティカル",            "mp_cost": 20},
    "Monk":       {"name": "百裂拳",       "desc": "3〜5連撃、合計ダメージ約1.5〜3倍",         "mp_cost": 18},
    "Spellsword": {"name": "魔剣斬",       "desc": "1.8倍・防御半無視の複合攻撃",              "mp_cost": 22},
    "Shaman":     {"name": "呻縛",        "desc": "敵の次の攻撃を 50% に弱体化",             "mp_cost": 25},
    "Paladin":    {"name": "聖域",        "desc": "全員防御バフ＋HP 10%小回復",             "mp_cost": 30},
    "Bard":       {"name": "激励の歌",    "desc": "全員の次の攻撃を 1.5倍に強化",            "mp_cost": 25},
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
    atk_buff: float = 1.0       # 攻撃力バフ倍率（消費型: 攻撃時にリセット）

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
            "atk_buff":   self.atk_buff,
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
                    "atk_buff":     f.atk_buff,
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
                "max_mp":       self.enemy.max_mp,
                "current_mp":   self.enemy.current_mp,
                "atk_buff":     self.enemy.atk_buff,
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
        effective_atk    = int(fighter.attack_power * fighter.atk_buff)
        fighter.atk_buff = 1.0
        damage = _calc_damage(effective_atk)
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

        # 攻撃力バフを計算・消費（Cleric/Paladin/Bard は攻撃を行わないため消費のみ）
        atk_mult      = fighter.atk_buff
        effective_atk = int(fighter.attack_power * atk_mult)
        fighter.atk_buff = 1.0
        if atk_mult != 1.0:
            self.logs.append(f"⬆️  攻撃力バフ発動！（×{atk_mult:.1f}）")

        if fighter.class_type == "Fighter":
            # 渾身の一撃: 2倍ダメージ
            damage = _calc_damage(effective_atk * 2)
            actual = self.enemy.take_damage(damage)
            self.logs.append(
                f"💥 {fighter.name} の「{skill['name']}」！"
                f" → {self.enemy.name} に {actual} ダメージ！"
                f"（残HP: {self.enemy.current_hp}/{self.enemy.max_hp}）"
            )

        elif fighter.class_type == "Mage":
            # ファイアボール: 1.5倍・防御無視
            damage = _calc_damage(int(effective_atk * 1.5))
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
            damage = _calc_damage(int(effective_atk * multiplier))
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

        elif fighter.class_type == "Archer":
            # 狙い撃ち: ブレなし確定 2.2倍クリティカル
            damage = max(1, int(effective_atk * 2.2))
            actual = self.enemy.take_damage(damage)
            self.logs.append(
                f"🎯 {fighter.name} の「{skill['name']}」！"
                f" → {self.enemy.name} に {actual} 確定ダメージ！"
                f"（残HP: {self.enemy.current_hp}/{self.enemy.max_hp}）"
            )

        elif fighter.class_type == "Monk":
            # 百裂拳: 3〜5連撃、各ヒット約 0.6倍
            hits  = random.randint(3, 5)
            total = 0
            for _ in range(hits):
                dmg    = _calc_damage(int(effective_atk * 0.6))
                actual = self.enemy.take_damage(dmg)
                total += actual
                if not self.enemy.is_alive:
                    break
            self.logs.append(
                f"👊 {fighter.name} の「{skill['name']}」！"
                f" {hits} 連撃 → 合計 {total} ダメージ！"
                f"（残HP: {self.enemy.current_hp}/{self.enemy.max_hp}）"
            )

        elif fighter.class_type == "Spellsword":
            # 魔剣斬: 1.8倍・防御半無視（防御中でも25%軽減に留まる）
            damage = _calc_damage(int(effective_atk * 1.8))
            if self.enemy.is_defending:
                actual = max(1, int(damage * 0.75))   # 通常半減→25%軽減に緩和
                self.enemy.current_hp = max(0, self.enemy.current_hp - actual)
            else:
                actual = self.enemy.take_damage(damage)
            self.logs.append(
                f"⚔️✨ {fighter.name} の「{skill['name']}」！"
                f" → {self.enemy.name} に {actual} 魔法物理ダメージ！"
                + ("（防御貫通）" if self.enemy.is_defending else "")
                + f"（残HP: {self.enemy.current_hp}/{self.enemy.max_hp}）"
            )

        elif fighter.class_type == "Shaman":
            # 呪縛: 敵の次の攻撃を50%に弱体化（重ねがけは最低値を維持）
            self.enemy.atk_buff = min(self.enemy.atk_buff, 0.5)
            self.logs.append(
                f"🌑 {fighter.name} の「{skill['name']}」！"
                f" → {self.enemy.name} を呪縛！次の攻撃が 50% に弱体化！"
            )

        elif fighter.class_type == "Paladin":
            # 聖域: 生存全員に防御バフ＋HP 10% 小回復
            alive = [f for f in self.fighters if f.is_alive]
            healed_msgs = []
            for f in alive:
                f.is_defending = True
                amt    = max(1, int(f.max_hp * 0.10))
                actual = f.heal(amt)
                healed_msgs.append(f"{f.name}+{actual}")
            self.logs.append(
                f"🛡️✨ {fighter.name} の「{skill['name']}」！"
                f" → 全員防御体勢＋小回復！（{', '.join(healed_msgs)}）"
            )

        elif fighter.class_type == "Bard":
            # 激励の歌: 生存全員の次の攻撃を 1.5倍に強化
            alive = [f for f in self.fighters if f.is_alive]
            for f in alive:
                f.atk_buff = 1.5
            names = "・".join(f.name for f in alive)
            self.logs.append(
                f"🎵 {fighter.name} の「{skill['name']}」！"
                f" → {names} の次の攻撃が 1.5 倍に強化！"
            )

        else:
            # 未定義クラス: デフォルト 1.5倍攻撃
            damage = _calc_damage(int(effective_atk * 1.5))
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
        target    = random.choice(alive)
        debuffed  = self.enemy.atk_buff < 1.0
        eff_atk   = int(self.enemy.attack_power * self.enemy.atk_buff)
        self.enemy.atk_buff = 1.0   # デバフ消費
        damage = _calc_damage(eff_atk)
        actual = target.take_damage(damage)
        boss_mark = "👹" if self.enemy.is_boss else "👾"
        debuff_note = "（弱体化中）" if debuffed else ""
        self.logs.append(
            f"{boss_mark} {self.enemy.name} の攻撃！{debuff_note}"
            f" → {target.name} に {actual} ダメージ！"
            f"（残HP: {target.current_hp}/{target.max_hp}）"
        )


# ---------------------------------------------------------------------------
# モジュールレベルユーティリティ
# ---------------------------------------------------------------------------

def _calc_damage(base: int) -> int:
    """基本ダメージ値に ±20% のランダムぶれを加える（最低1）"""
    return max(1, int(base * random.uniform(0.8, 1.2)))
