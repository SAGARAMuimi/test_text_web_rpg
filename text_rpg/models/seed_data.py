from .database import SessionLocal
from .dungeon import Dungeon
from .enemy import Enemy


# ---------------------------------------------------------------------------
# ダンジョン初期データ
# ---------------------------------------------------------------------------
_DUNGEONS = [
    Dungeon(id=1, name="入門の洞窟",   floor=1),
    Dungeon(id=2, name="試練の迷宮",   floor=2),
    Dungeon(id=3, name="魔王の城",     floor=3),
]

# ---------------------------------------------------------------------------
# 敵初期データ
# ---------------------------------------------------------------------------
_ENEMIES = [
    # --- 階層 1 (入門の洞窟) ---
    Enemy(name="スライム",     dungeon_id=1, floor=1, hp=50,  attack=8,  is_boss=0),
    Enemy(name="ゴブリン",     dungeon_id=1, floor=1, hp=70,  attack=12, is_boss=0),
    Enemy(name="コボルト",     dungeon_id=1, floor=1, hp=60,  attack=10, is_boss=0),
    Enemy(name="ゴブリン鬼長", dungeon_id=1, floor=1, hp=150, attack=20, is_boss=1),  # ボス
    # --- 階層 2 (試練の迷宮) ---
    Enemy(name="オーク",       dungeon_id=2, floor=2, hp=140, attack=22, is_boss=0),
    Enemy(name="ウィザード",   dungeon_id=2, floor=2, hp=110, attack=26, is_boss=0),
    Enemy(name="トロール",     dungeon_id=2, floor=2, hp=165, attack=24, is_boss=0),
    Enemy(name="オークキング",  dungeon_id=2, floor=2, hp=300, attack=38, is_boss=1),  # ボス
    # --- 階層 3 (魔王の城) ---
    Enemy(name="ダークナイト", dungeon_id=3, floor=3, hp=220, attack=33, is_boss=0),
    Enemy(name="リッチ",       dungeon_id=3, floor=3, hp=200, attack=37, is_boss=0),
    Enemy(name="ドラゴン",     dungeon_id=3, floor=3, hp=440, attack=45, is_boss=1),  # ボス
]


def seed_dungeons() -> None:
    """3階層ダンジョンのマスターデータを投入する。既存データはアップデート。"""
    db = SessionLocal()
    try:
        for d in _DUNGEONS:
            db.merge(d)   # 同じ id があれば更新、なければ挿入
        db.commit()
        print(f"ダンジョンデータ {len(_DUNGEONS)} 件を投入しました。")
    finally:
        db.close()


def seed_enemies() -> None:
    """3階層分の敵データを投入・更新する。既存データは同キーで上書き。"""
    db = SessionLocal()
    try:
        upserted = 0
        for e in _ENEMIES:
            row = (
                db.query(Enemy)
                .filter(
                    Enemy.dungeon_id == e.dungeon_id,
                    Enemy.floor == e.floor,
                    Enemy.name == e.name,
                )
                .first()
            )
            if row is None:
                db.add(
                    Enemy(
                        name=e.name,
                        dungeon_id=e.dungeon_id,
                        floor=e.floor,
                        hp=e.hp,
                        attack=e.attack,
                        is_boss=e.is_boss,
                    )
                )
            else:
                row.hp = e.hp
                row.attack = e.attack
                row.is_boss = e.is_boss
            upserted += 1

        db.commit()
        print(f"敵データ {upserted} 件を投入/更新しました。")
    finally:
        db.close()


if __name__ == "__main__":
    seed_dungeons()
    seed_enemies()
