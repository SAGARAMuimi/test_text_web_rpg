"""
game/dungeon.py  —  ダンジョン探索ロジック

spec 準拠:
  - 3階層のダンジョン
  - 各階層でランダムエンカウント 2〜3回
  - 各階層の最後にボス戦

クラス構成:
  DungeonPhase    — 探索フェーズの状態定義 (Enum)
  DungeonExplorer — DB クエリ担当（敵の取得）
  DungeonSession  — ゲームフロー全体の管理（Flask session 保存対応）
"""
from __future__ import annotations

import random
from enum import Enum
from typing import Optional

from sqlalchemy.sql import func

try:
    from models.enemy import Enemy
    from game.battle import Battle
except ImportError:
    from text_rpg.models.enemy import Enemy
    from text_rpg.game.battle import Battle


# ---------------------------------------------------------------------------
# DungeonPhase — 探索フェーズ（状態機械）
# ---------------------------------------------------------------------------
class DungeonPhase(str, Enum):
    """
    ダンジョン探索の進行フェーズ。
    str の Enum なので JSON / Flask session にそのまま保存可能。

    遷移図::

        EXPLORING
          |--- encounters_remaining > 0  --> begin_battle(normal)
          |         [IN_BATTLE]              |-- 勝利 --> EXPLORING
          |                                  `-- 全滅 --> GAME_OVER
          |
          `--- encounters_remaining == 0 --> begin_battle(boss)
                    [BOSS_BATTLE]            |-- 勝利(途中階) --> FLOOR_CLEARED
                                             |-- 勝利(最終階) --> DUNGEON_CLEARED
                                             `-- 全滅        --> GAME_OVER

        FLOOR_CLEARED --> advance_to_next_floor() --> EXPLORING
    """
    EXPLORING       = "exploring"
    IN_BATTLE       = "in_battle"
    BOSS_BATTLE     = "boss_battle"
    FLOOR_CLEARED   = "floor_cleared"
    DUNGEON_CLEARED = "dungeon_cleared"
    GAME_OVER       = "game_over"


# ---------------------------------------------------------------------------
# DungeonExplorer — DB クエリ担当
# ---------------------------------------------------------------------------
class DungeonExplorer:
    """
    DB から敵情報を取得するクラス。
    DB セッションに依存するため、必要なタイミングでインスタンス化する。

    使用例::

        explorer = DungeonExplorer(db, dungeon_id=1)
        enemy = explorer.get_random_encounter(floor=1)   # 通常敵
        boss  = explorer.get_boss(floor=1)               # ボス
    """

    MAX_FLOOR                = 3   # spec: 3階層
    ENCOUNTERS_PER_FLOOR_MIN = 2   # spec: 2〜3回
    ENCOUNTERS_PER_FLOOR_MAX = 3

    def __init__(self, db_session, dungeon_id: int = 1) -> None:
        self.db = db_session
        self.dungeon_id = dungeon_id

    def get_random_encounter(self, floor: int) -> Optional[Enemy]:
        """指定階層の通常敵（ボス除外）をランダムに1体返す。"""
        return (
            self.db.query(Enemy)
            .filter(
                Enemy.dungeon_id == self.dungeon_id,
                Enemy.floor      == floor,
                Enemy.is_boss    == 0,
            )
            .order_by(func.random())
            .first()
        )

    def get_boss(self, floor: int) -> Optional[Enemy]:
        """指定階層のボス敵を返す。"""
        return (
            self.db.query(Enemy)
            .filter(
                Enemy.dungeon_id == self.dungeon_id,
                Enemy.floor      == floor,
                Enemy.is_boss    == 1,
            )
            .first()
        )

    @staticmethod
    def roll_encounters() -> int:
        """階層ごとのエンカウント数をランダム決定（2〜3回）。"""
        return random.randint(
            DungeonExplorer.ENCOUNTERS_PER_FLOOR_MIN,
            DungeonExplorer.ENCOUNTERS_PER_FLOOR_MAX,
        )


# ---------------------------------------------------------------------------
# _PartyMemberProxy — party dict を Battle に渡すための軽量プロキシ
# ---------------------------------------------------------------------------
class _PartyMemberProxy:
    """
    DungeonSession の party（dict）を Battle（モデルリスト）に渡すためのプロキシ。
    Battle が参照するプロパティ (name/hp/attack/class_type) だけを持つ。
    """
    def __init__(self, data: dict) -> None:
        self.name       = data["name"]
        self.hp         = data["current_hp"]   # 現在HP（戦闘開始後の残HP）
        self.max_hp     = data["max_hp"]        # 最大HP（ヒール上限に使用）
        self.attack     = data["attack"]
        self.class_type = data["class_type"]
        self.id         = data.get("id")
        self.level      = data.get("level", 1)


# ---------------------------------------------------------------------------
# DungeonSession — ダンジョン探索全体の状態管理
# ---------------------------------------------------------------------------
class DungeonSession:
    """
    ダンジョン探索セッション管理クラス。
    Flask session (dict) への保存・復元に対応。
    戦闘間のパーティ HP を引き継ぎ、全3階層を通じたゲームフローを管理する。

    Flask ルートでの典型的な使用フロー::

        # 1. セッション開始
        ds = DungeonSession.start(characters, dungeon_id=1)
        flask_session["dungeon"] = ds.to_dict()

        # 2. 状態確認
        ds    = DungeonSession.from_dict(flask_session["dungeon"])
        state = ds.get_state()   # テンプレートへ渡す dict

        # 3. 戦闘開始 (phase == EXPLORING)
        explorer = DungeonExplorer(db, ds.dungeon_id)
        if state["encounters_remaining"] > 0:
            enemy = explorer.get_random_encounter(ds.current_floor)
        else:
            enemy = explorer.get_boss(ds.current_floor)
        battle = ds.begin_battle(enemy)
        flask_session["dungeon"] = ds.to_dict()

        # 4. ターン処理 (phase == IN_BATTLE / BOSS_BATTLE)
        ds     = DungeonSession.from_dict(flask_session["dungeon"])
        battle = ds.restore_battle()
        battle.process_turn(char_index, action)
        ds.sync_battle(battle)
        if battle.is_over:
            ds.finish_battle(battle)
        flask_session["dungeon"] = ds.to_dict()

        # 5. 階層クリア後に次の階へ (phase == FLOOR_CLEARED)
        ds = DungeonSession.from_dict(flask_session["dungeon"])
        ds.advance_to_next_floor()
        flask_session["dungeon"] = ds.to_dict()
    """

    def __init__(self) -> None:
        # <- start() / from_dict() 経由で生成する。直接呼び出しは不可。
        self.dungeon_id:           int          = 1
        self.current_floor:        int          = 1
        self.encounters_remaining: int          = 0
        self.phase:                DungeonPhase = DungeonPhase.EXPLORING
        self.logs:                 list[str]    = []
        self.party:                list[dict]   = []
        self._battle_dict:         Optional[dict] = None

    # ------------------------------------------------------------------
    # ファクトリ
    # ------------------------------------------------------------------

    @classmethod
    def start(cls, party_chars: list, dungeon_id: int = 1) -> "DungeonSession":
        """
        ダンジョン探索を新規開始する。

        Args:
            party_chars: Character モデルインスタンスのリスト（最大4名）
            dungeon_id:  探索対象のダンジョン ID
        """
        s = cls()
        s.dungeon_id           = dungeon_id
        s.current_floor        = 1
        s.encounters_remaining = DungeonExplorer.roll_encounters()
        s.phase                = DungeonPhase.EXPLORING
        s.logs = [
            f"⚔️  ダンジョン探索開始！ 1 階層目へ踏み込む..."
            f"（エンカウント × {s.encounters_remaining}）"
        ]
        s.party = [
            {
                "id":         getattr(c, "id", None),
                "name":       c.name,
                "class_type": getattr(c, "class_type", ""),
                "level":      getattr(c, "level", 1),
                "max_hp":     c.hp,
                "current_hp": c.hp,
                "attack":     c.attack,
            }
            for c in party_chars
        ]
        return s

    @classmethod
    def from_dict(cls, data: dict) -> "DungeonSession":
        """Flask session の dict から復元する。"""
        s = cls()
        s.dungeon_id           = data["dungeon_id"]
        s.current_floor        = data["current_floor"]
        s.encounters_remaining = data["encounters_remaining"]
        s.phase                = DungeonPhase(data["phase"])
        s.logs                 = data.get("logs", [])
        s.party                = data["party"]
        s._battle_dict         = data.get("battle")
        return s

    def to_dict(self) -> dict:
        """Flask session へ保存するシリアライズ辞書。"""
        return {
            "dungeon_id":           self.dungeon_id,
            "current_floor":        self.current_floor,
            "encounters_remaining": self.encounters_remaining,
            "phase":                self.phase.value,
            "logs":                 self.logs[-50:],
            "party":                self.party,
            "battle":               self._battle_dict,
        }

    # ------------------------------------------------------------------
    # 状態取得
    # ------------------------------------------------------------------

    def get_state(self) -> dict:
        """テンプレートへ渡す全状態辞書。"""
        return {
            "phase":                self.phase.value,
            "current_floor":        self.current_floor,
            "max_floor":            DungeonExplorer.MAX_FLOOR,
            "encounters_remaining": self.encounters_remaining,
            "party":                self.party,
            "logs":                 self.logs[-20:],
            "battle":               self._battle_dict,
            # テンプレート用ブールフラグ
            "is_exploring":     self.phase == DungeonPhase.EXPLORING,
            "in_battle":        self.phase in (
                                    DungeonPhase.IN_BATTLE,
                                    DungeonPhase.BOSS_BATTLE,
                                ),
            "is_floor_cleared": self.phase == DungeonPhase.FLOOR_CLEARED,
            "is_game_over":     self.phase == DungeonPhase.GAME_OVER,
            "is_cleared":       self.phase == DungeonPhase.DUNGEON_CLEARED,
            "boss_ready": (
                self.phase == DungeonPhase.EXPLORING
                and self.encounters_remaining == 0
            ),
        }

    # ------------------------------------------------------------------
    # 戦闘管理
    # ------------------------------------------------------------------

    def begin_battle(self, enemy) -> Battle:
        """
        エンカウントまたはボス戦を開始する。
        通常エンカウント時は encounters_remaining を 1 減らす。

        Args:
            enemy: Enemy モデルインスタンス
        Returns:
            初期化済みの Battle インスタンス
        """
        living = [p for p in self.party if p["current_hp"] > 0]
        if not living:
            raise RuntimeError("生存メンバーがいません。")

        is_boss = bool(getattr(enemy, "is_boss", 0))
        if not is_boss:
            self.encounters_remaining = max(0, self.encounters_remaining - 1)

        proxies   = [_PartyMemberProxy(p) for p in living]
        battle    = Battle(proxies, enemy)
        self.phase = DungeonPhase.BOSS_BATTLE if is_boss else DungeonPhase.IN_BATTLE
        kind      = "ボス" if is_boss else "通常"
        boss_mark = "👹" if is_boss else "👾"
        self.logs.append(
            f"{boss_mark} {self.current_floor} 階 — {kind}戦闘開始: {enemy.name}"
        )
        self._battle_dict = battle.to_session_dict()
        return battle

    def restore_battle(self) -> Optional[Battle]:
        """セッションに保存された戦闘状態を Battle として復元する。"""
        if self._battle_dict is None:
            return None
        return Battle.from_session_dict(self._battle_dict)

    def sync_battle(self, battle: Battle) -> None:
        """process_turn 後の Battle 状態をセッションに同期する。"""
        self._battle_dict = battle.to_session_dict()

    def finish_battle(self, battle: Battle) -> None:
        """
        戦闘終了後の処理。
          - パーティ HP を戦闘後の値に更新する
          - defeat      --> GAME_OVER
          - 通常勝利    --> EXPLORING
          - ボス勝利    --> FLOOR_CLEARED / DUNGEON_CLEARED
        """
        # 戦闘前に生存していたパーティメンバーの HP を更新
        living = [p for p in self.party if p["current_hp"] > 0]
        for i, fighter in enumerate(battle.fighters):
            if i < len(living):
                living[i]["current_hp"] = fighter.current_hp

        self.logs.extend(battle.logs[-10:])
        self._battle_dict = None

        if battle.result == Battle.RESULT_DEFEAT:
            self.phase = DungeonPhase.GAME_OVER
            self.logs.append("💀 パーティが全滅しました...")
            return

        if self.phase == DungeonPhase.BOSS_BATTLE:
            self.logs.append(f"👑 {self.current_floor} 階のボスを倒した！")
            self.phase = DungeonPhase.FLOOR_CLEARED
        else:
            enc_msg = (
                f"残エンカウント: {self.encounters_remaining}"
                if self.encounters_remaining > 0
                else "ボス戦へ進め！"
            )
            self.logs.append(f"✅ 戦闘勝利！ {enc_msg}")
            self.phase = DungeonPhase.EXPLORING

    # ------------------------------------------------------------------
    # 階層進行
    # ------------------------------------------------------------------

    def advance_to_next_floor(self) -> bool:
        """
        FLOOR_CLEARED フェーズで呼び出す。次の階層へ進む。

        Returns:
            True  : 次の階層へ進んだ（EXPLORING に遷移）
            False : 全階層クリア（DUNGEON_CLEARED に遷移）
        """
        self.current_floor += 1
        # dungeon_id は floor と 1:1 対応（シードデータの設計に合わせて同期）
        self.dungeon_id = self.current_floor

        if self.current_floor > DungeonExplorer.MAX_FLOOR:
            self.phase = DungeonPhase.DUNGEON_CLEARED
            self.logs.append("🏆 全ダンジョンを制覇した！")
            return False

        self.encounters_remaining = DungeonExplorer.roll_encounters()
        self.phase = DungeonPhase.EXPLORING
        self.logs.append(
            f"🚪 {self.current_floor} 階層に突入！"
            f"（エンカウント × {self.encounters_remaining}）"
        )
        return True
