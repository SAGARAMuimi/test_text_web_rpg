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
    Enemy(name="オーク",       dungeon_id=2, floor=2, hp=120, attack=18, is_boss=0),
    Enemy(name="ウィザード",   dungeon_id=2, floor=2, hp=90,  attack=25, is_boss=0),
    Enemy(name="トロール",     dungeon_id=2, floor=2, hp=140, attack=20, is_boss=0),
    Enemy(name="オークキング",  dungeon_id=2, floor=2, hp=250, attack=35, is_boss=1),  # ボス
    # --- 階層 3 (魔王の城) ---
    Enemy(name="ダークナイト", dungeon_id=3, floor=3, hp=180, attack=30, is_boss=0),
    Enemy(name="リッチ",       dungeon_id=3, floor=3, hp=160, attack=35, is_boss=0),
    Enemy(name="ドラゴン",     dungeon_id=3, floor=3, hp=500, attack=50, is_boss=1),  # ボス
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
    """3階層分の敵データを投入する。投入済みの場合はスキップする。"""
    db = SessionLocal()
    try:
        if db.query(Enemy).count() == 0:
            db.add_all(_ENEMIES)
            db.commit()
            print(f"敵データ {len(_ENEMIES)} 件を投入しました。")
        else:
            print("敵データは投入済みです。スキップします。")
    finally:
        db.close()


if __name__ == "__main__":
    seed_dungeons()
    seed_enemies()
