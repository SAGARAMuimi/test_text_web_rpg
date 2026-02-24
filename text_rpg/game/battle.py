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
        self._enemy_cooldowns: dict[str, int] = {
            "wizard_aoe": 0,
            "lich_aoe": 0,
            "ork_king_sweep": 0,
            "dragon_breath": 0,
        }
        self._enemy_defend_turns: int = 0

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
            "_enemy_cooldowns": self._enemy_cooldowns,
            "_enemy_defend_turns": self._enemy_defend_turns,
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
        instance._enemy_cooldowns = data.get(
            "_enemy_cooldowns",
            {
                "wizard_aoe": 0,
                "lich_aoe": 0,
                "ork_king_sweep": 0,
                "dragon_breath": 0,
            },
        )
        instance._enemy_defend_turns = data.get("_enemy_defend_turns", 0)
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
        """敵ターン: 敵種別に応じて行動（通常攻撃 / 魔法行動）"""
        alive = [f for f in self.fighters if f.is_alive]
        if not alive:
            return

        # 敵の防御状態は「敵の次ターン開始時」に解除（= プレイヤー側1巡分だけ有効）
        if self._enemy_defend_turns > 0:
            self._enemy_defend_turns -= 1
            if self._enemy_defend_turns == 0:
                self.enemy.is_defending = False

        # クールダウン経過
        self._tick_enemy_cooldowns()

        debuffed = self.enemy.atk_buff < 1.0
        eff_atk  = int(self.enemy.attack_power * self.enemy.atk_buff)
        self.enemy.atk_buff = 1.0   # 弱体化は敵の次行動で消費

        if self.enemy.name == "ウィザード":
            self._enemy_turn_wizard(alive, eff_atk, debuffed)
            return

        if self.enemy.name == "リッチ":
            self._enemy_turn_lich(alive, eff_atk, debuffed)
            return

        if self.enemy.name == "オークキング":
            self._enemy_turn_ork_king(alive, eff_atk, debuffed)
            return

        if self.enemy.name == "ドラゴン":
            self._enemy_turn_dragon(alive, eff_atk, debuffed)
            return

        if self.enemy.name == "トロール":
            self._enemy_turn_troll(alive, eff_atk, debuffed)
            return

        if self.enemy.name == "ダークナイト":
            self._enemy_turn_dark_knight(alive, eff_atk, debuffed)
            return

        target = random.choice(alive)
        damage = _calc_damage(eff_atk)
        actual = target.take_damage(damage)
        boss_mark = "👹" if self.enemy.is_boss else "👾"
        debuff_note = "（弱体化中）" if debuffed else ""
        self.logs.append(
            f"{boss_mark} {self.enemy.name} の攻撃！{debuff_note}"
            f" → {target.name} に {actual} ダメージ！"
            f"（残HP: {target.current_hp}/{target.max_hp}）"
        )

    def _tick_enemy_cooldowns(self) -> None:
        """敵専用スキルのクールダウンを1進める。"""
        for key, value in self._enemy_cooldowns.items():
            if value > 0:
                self._enemy_cooldowns[key] = value - 1

    def _enemy_turn_wizard(self, alive: list[Combatant], eff_atk: int, debuffed: bool) -> None:
        """ウィザードの行動: 全体魔法 / 単体魔法 / 通常攻撃。"""
        boss_mark = "👹" if self.enemy.is_boss else "👾"
        debuff_note = "（弱体化中）" if debuffed else ""

        # アークフレア: 全体 0.8倍（2ターンCT）
        if (
            self._enemy_cooldowns.get("wizard_aoe", 0) == 0
            and len(alive) >= 2
            and random.random() < 0.35
        ):
            self._enemy_cooldowns["wizard_aoe"] = 2
            total = 0
            details: list[str] = []
            for target in alive:
                damage = _calc_damage(int(eff_atk * 0.8))
                actual = target.take_damage(damage)
                total += actual
                details.append(f"{target.name}:{actual}")
            self.logs.append(
                f"{boss_mark} {self.enemy.name} の「アークフレア」！{debuff_note}"
                f" → 全体に魔法ダメージ！[{', '.join(details)}]"
                f"（合計 {total}）"
            )
            return

        # ファイアボルト: 単体 1.4倍・防御無視
        if random.random() < 0.60:
            target = random.choice(alive)
            damage = _calc_damage(int(eff_atk * 1.4))
            orig = target.is_defending
            target.is_defending = False
            actual = target.take_damage(damage)
            target.is_defending = orig
            self.logs.append(
                f"{boss_mark} {self.enemy.name} の「ファイアボルト」！{debuff_note}"
                f" → {target.name} に {actual} 魔法ダメージ！（防御無視）"
                f"（残HP: {target.current_hp}/{target.max_hp}）"
            )
            return

        # 通常攻撃
        target = random.choice(alive)
        damage = _calc_damage(eff_atk)
        actual = target.take_damage(damage)
        self.logs.append(
            f"{boss_mark} {self.enemy.name} の攻撃！{debuff_note}"
            f" → {target.name} に {actual} ダメージ！"
            f"（残HP: {target.current_hp}/{target.max_hp}）"
        )

    def _enemy_turn_lich(self, alive: list[Combatant], eff_atk: int, debuffed: bool) -> None:
        """リッチの行動: 全体魔法 / ドレイン / 呪詛 / 通常攻撃。"""
        boss_mark = "👹" if self.enemy.is_boss else "👾"
        debuff_note = "（弱体化中）" if debuffed else ""
        roll = random.random()

        # 死霊波: 全体 0.9倍（3ターンCT）
        if (
            self._enemy_cooldowns.get("lich_aoe", 0) == 0
            and len(alive) >= 2
            and roll < 0.25
        ):
            self._enemy_cooldowns["lich_aoe"] = 3
            total = 0
            details: list[str] = []
            for target in alive:
                damage = _calc_damage(int(eff_atk * 0.9))
                actual = target.take_damage(damage)
                total += actual
                details.append(f"{target.name}:{actual}")
            self.logs.append(
                f"{boss_mark} {self.enemy.name} の「死霊波」！{debuff_note}"
                f" → 全体に呪術ダメージ！[{', '.join(details)}]"
                f"（合計 {total}）"
            )
            return

        # ライフドレイン: 単体 1.0倍 + 与ダメの50%回復
        if roll < 0.60:
            target = random.choice(alive)
            damage = _calc_damage(eff_atk)
            actual = target.take_damage(damage)
            heal_amount = max(1, int(actual * 0.5))
            healed = self.enemy.heal(heal_amount)
            self.logs.append(
                f"{boss_mark} {self.enemy.name} の「ライフドレイン」！{debuff_note}"
                f" → {target.name} に {actual} ダメージ、{healed} 回復！"
                f"（敵HP: {self.enemy.current_hp}/{self.enemy.max_hp}）"
            )
            return

        # 呪詛: 対象の次攻撃を70%化
        if roll < 0.85:
            target = random.choice(alive)
            target.atk_buff = min(target.atk_buff, 0.7)
            self.logs.append(
                f"{boss_mark} {self.enemy.name} の「呪詛」！{debuff_note}"
                f" → {target.name} の次の攻撃が弱体化（70%）！"
            )
            return

        # 通常攻撃
        target = random.choice(alive)
        damage = _calc_damage(eff_atk)
        actual = target.take_damage(damage)
        self.logs.append(
            f"{boss_mark} {self.enemy.name} の攻撃！{debuff_note}"
            f" → {target.name} に {actual} ダメージ！"
            f"（残HP: {target.current_hp}/{target.max_hp}）"
        )

    def _enemy_turn_ork_king(self, alive: list[Combatant], eff_atk: int, debuffed: bool) -> None:
        """オークキングの行動: 薙ぎ払い / 渾身の一撃 / 通常攻撃。"""
        boss_mark = "👹" if self.enemy.is_boss else "👾"
        debuff_note = "（弱体化中）" if debuffed else ""

        # 薙ぎ払い: 防御有効の全体攻撃（2ターンCT）
        if (
            self._enemy_cooldowns.get("ork_king_sweep", 0) == 0
            and len(alive) >= 2
            and random.random() < 0.40
        ):
            self._enemy_cooldowns["ork_king_sweep"] = 2
            total = 0
            details: list[str] = []
            for target in alive:
                damage = _calc_damage(int(eff_atk * 0.9))
                actual = target.take_damage(damage)  # 防御が有効
                total += actual
                details.append(f"{target.name}:{actual}")
            self.logs.append(
                f"{boss_mark} {self.enemy.name} の「薙ぎ払い」！{debuff_note}"
                f" → 全体に物理ダメージ！[{', '.join(details)}]"
                f"（合計 {total}）"
            )
            return

        # 渾身の一撃: 単体 2.0倍
        if random.random() < 0.50:
            target = random.choice(alive)
            damage = _calc_damage(int(eff_atk * 2.0))
            actual = target.take_damage(damage)
            self.logs.append(
                f"{boss_mark} {self.enemy.name} の「渾身の一撃」！{debuff_note}"
                f" → {target.name} に {actual} 大ダメージ！"
                f"（残HP: {target.current_hp}/{target.max_hp}）"
            )
            return

        # 通常攻撃
        target = random.choice(alive)
        damage = _calc_damage(eff_atk)
        actual = target.take_damage(damage)
        self.logs.append(
            f"{boss_mark} {self.enemy.name} の攻撃！{debuff_note}"
            f" → {target.name} に {actual} ダメージ！"
            f"（残HP: {target.current_hp}/{target.max_hp}）"
        )

    def _enemy_turn_dragon(self, alive: list[Combatant], eff_atk: int, debuffed: bool) -> None:
        """ドラゴンの行動: ブレス / 通常攻撃。"""
        boss_mark = "👹" if self.enemy.is_boss else "👾"
        debuff_note = "（弱体化中）" if debuffed else ""

        # ブレス: 全体攻撃。防御効果を半減（防御中でも 25% 軽減止まり）
        if (
            self._enemy_cooldowns.get("dragon_breath", 0) == 0
            and len(alive) >= 2
            and random.random() < 0.30
        ):
            self._enemy_cooldowns["dragon_breath"] = 3
            total = 0
            details: list[str] = []
            for target in alive:
                damage = _calc_damage(int(eff_atk * 1.0))
                if target.is_defending:
                    actual = max(1, int(damage * 0.75))
                    target.current_hp = max(0, target.current_hp - actual)
                else:
                    actual = target.take_damage(damage)
                total += actual
                details.append(f"{target.name}:{actual}")
            self.logs.append(
                f"{boss_mark} {self.enemy.name} の「ブレス」！{debuff_note}"
                f" → 全体に灼熱ダメージ！（防御効果半減）[{', '.join(details)}]"
                f"（合計 {total}）"
            )
            return

        # 通常攻撃
        target = random.choice(alive)
        damage = _calc_damage(eff_atk)
        actual = target.take_damage(damage)
        self.logs.append(
            f"{boss_mark} {self.enemy.name} の攻撃！{debuff_note}"
            f" → {target.name} に {actual} ダメージ！"
            f"（残HP: {target.current_hp}/{target.max_hp}）"
        )

    def _enemy_turn_troll(self, alive: list[Combatant], eff_atk: int, debuffed: bool) -> None:
        """トロールの行動: 渾身の一撃 / 通常攻撃。"""
        boss_mark = "👹" if self.enemy.is_boss else "👾"
        debuff_note = "（弱体化中）" if debuffed else ""

        # 渾身の一撃: 単体 2.0倍
        if random.random() < 0.45:
            target = random.choice(alive)
            damage = _calc_damage(int(eff_atk * 2.0))
            actual = target.take_damage(damage)
            self.logs.append(
                f"{boss_mark} {self.enemy.name} の「渾身の一撃」！{debuff_note}"
                f" → {target.name} に {actual} 大ダメージ！"
                f"（残HP: {target.current_hp}/{target.max_hp}）"
            )
            return

        # 通常攻撃
        target = random.choice(alive)
        damage = _calc_damage(eff_atk)
        actual = target.take_damage(damage)
        self.logs.append(
            f"{boss_mark} {self.enemy.name} の攻撃！{debuff_note}"
            f" → {target.name} に {actual} ダメージ！"
            f"（残HP: {target.current_hp}/{target.max_hp}）"
        )

    def _enemy_turn_dark_knight(self, alive: list[Combatant], eff_atk: int, debuffed: bool) -> None:
        """ダークナイトの行動: 防御 / 通常攻撃。"""
        boss_mark = "👹" if self.enemy.is_boss else "👾"
        debuff_note = "（弱体化中）" if debuffed else ""

        # 防御: 次のプレイヤー側1巡のみ被ダメ半減
        if (not self.enemy.is_defending) and random.random() < 0.35:
            self.enemy.is_defending = True
            self._enemy_defend_turns = 1
            self.logs.append(
                f"{boss_mark} {self.enemy.name} は防御体勢をとった！"
                f"（次のターンまで被ダメージ半減）"
            )
            return

        # 通常攻撃
        target = random.choice(alive)
        damage = _calc_damage(eff_atk)
        actual = target.take_damage(damage)
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
