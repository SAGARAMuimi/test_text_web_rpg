from flask import Flask, render_template, request, redirect, url_for, session, flash
from text_rpg.models.database import get_db
from text_rpg.models.character import Character
from text_rpg.game.battle import Battle, SKILLS as BATTLE_SKILLS
from text_rpg.game.dungeon import DungeonSession, DungeonExplorer, DungeonPhase
from text_rpg.models.enemy import Enemy
import random
import os
import os.path

template_dir = os.path.abspath('text_rpg/templates')
app = Flask(__name__, template_folder=template_dir)
app.secret_key = 'your_secret_key'  # セッション管理用

# 起動時に必ずテーブル作成＋シードデータ投入
from text_rpg.models.create_tables import create_tables
from text_rpg.models.seed_data import seed_dungeons, seed_enemies
create_tables()
seed_dungeons()
seed_enemies()

# キャラクタークラスのテンプレート定義（DBに依存しない固定定義）
CHARACTER_TEMPLATES = {
    "Fighter": {"class_name": "戦士",    "hp": 100, "attack": 20, "icon": "⚔️",  "description": "渾身の一撃で2倍ダメージを与える"},
    "Mage":    {"class_name": "魔法使い", "hp":  70, "attack": 30, "icon": "🔥",  "description": "防御を無視するファイアボール"},
    "Rogue":   {"class_name": "盗賊",    "hp":  80, "attack": 25, "icon": "🗡️", "description": "急所攻撃で最大3倍ダメージ"},
    "Cleric":  {"class_name": "僧侶",    "hp":  90, "attack": 15, "icon": "✨",  "description": "ヒールで仲間のHPを30%回復"},
}


def _ds_load() -> DungeonSession:
    """Flask session から DungeonSession を復元する。"""
    return DungeonSession.from_dict(session['dungeon'])


def _ds_save(ds: DungeonSession) -> None:
    """DungeonSession を Flask session に保存する。"""
    session['dungeon'] = ds.to_dict()


@app.route('/')
def index():
    ds_dict = session.get('dungeon')
    state   = ds_dict and DungeonSession.from_dict(ds_dict).get_state()

    # 戦闘中なら現在の行動者インデックスを計算
    current_char_index = -1
    battle_acted       = []
    if state and state['in_battle'] and state.get('battle'):
        bd           = state['battle']
        battle_acted = bd.get('_acted', [])
        for i, f in enumerate(bd.get('fighters', [])):
            if f['current_hp'] > 0 and not battle_acted[i]:
                current_char_index = i
                break

    return render_template('index.html',
        character_templates=CHARACTER_TEMPLATES,
        game_started=bool(ds_dict),
        state=state,
        current_char_index=current_char_index,
        battle_acted=battle_acted,
        skills_info=BATTLE_SKILLS,
    )


@app.route('/start_game', methods=['POST'])
def start_game():
    slots = [request.form.get(f'slot_{i}', '') for i in range(1, 5)]

    if any(s not in CHARACTER_TEMPLATES for s in slots):
        flash('クラスの選択が不正です。もう一度選択してください。', 'error')
        return redirect(url_for('index'))

    # テンプレートから擬似キャラオブジェクトを生成して DungeonSession を開始
    class _C:
        __slots__ = ('name', 'hp', 'attack', 'class_type', 'level', 'id')
    chars = []
    for i, class_type in enumerate(slots, 1):
        tmpl = CHARACTER_TEMPLATES[class_type]
        c = _C()
        c.id         = i
        c.name       = tmpl['class_name']
        c.hp         = tmpl['hp']
        c.attack     = tmpl['attack']
        c.class_type = class_type
        c.level      = 1
        chars.append(c)

    ds = DungeonSession.start(chars, dungeon_id=1)
    _ds_save(ds)
    return redirect(url_for('index'))


@app.route('/explore', methods=['POST'])
def explore():
    ds  = _ds_load()
    db  = next(get_db())
    exp = DungeonExplorer(db, ds.dungeon_id)

    state = ds.get_state()
    if state['boss_ready']:
        # 通常戦闘が全て終わった → ボス戦
        enemy_model = exp.get_boss(ds.current_floor)
        if enemy_model is None:
            flash('ボスが見つかりません。データを確認してください。', 'error')
            _ds_save(ds)
            return redirect(url_for('index'))
    else:
        # 通常エンカウント
        enemy_model = exp.get_random_encounter(ds.current_floor)
        if enemy_model is None:
            flash('このフロアには敵がいないようだ...', 'error')
            _ds_save(ds)
            return redirect(url_for('index'))

    ds.begin_battle(enemy_model)
    _ds_save(ds)
    return redirect(url_for('index'))


@app.route('/battle_action', methods=['POST'])
def battle_action():
    ds = _ds_load()

    action       = request.form.get('action', 'attack')
    char_index   = int(request.form.get('char_index', 0))
    skill_target = int(request.form.get('skill_target', 0))

    battle = ds.restore_battle()
    if battle is None:
        return redirect(url_for('index'))

    battle.process_turn(char_index, action, skill_target)
    ds.sync_battle(battle)

    if battle.is_over:
        ds.finish_battle(battle)

    _ds_save(ds)
    return redirect(url_for('index'))


@app.route('/next_floor', methods=['POST'])
def next_floor():
    ds = _ds_load()
    ds.advance_to_next_floor()
    _ds_save(ds)
    return redirect(url_for('index'))


@app.route('/reset', methods=['POST'])
def reset():
    session.pop('dungeon', None)
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(debug=True)