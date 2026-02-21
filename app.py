from flask import Flask, render_template, request, redirect, url_for, session, flash
from text_rpg.models.database import get_db
from text_rpg.models.character import Character
from text_rpg.game.battle import Battle
from text_rpg.models.enemy import Enemy
import random
from sqlalchemy import func
import os
import os.path

template_dir = os.path.abspath('text_rpg/templates')
app = Flask(__name__, template_folder=template_dir)
app.secret_key = 'your_secret_key'  # セッション管理用

# データベースファイルのパス
DATABASE_FILE = 'game.db'

# データベースが存在しない場合は作成
if not os.path.exists(DATABASE_FILE):
    from text_rpg.models.create_tables import create_tables
    create_tables()

# キャラクタークラスのテンプレート定義（DBに依存しない固定定義）
CHARACTER_TEMPLATES = {
    "Fighter": {"class_name": "戦士",    "hp": 100, "attack": 20, "icon": "⚔️",  "description": "渾身の一撃で2倍ダメージを与える"},
    "Mage":    {"class_name": "魔法使い", "hp":  70, "attack": 30, "icon": "🔥",  "description": "防御を無視するファイアボール"},
    "Rogue":   {"class_name": "盗賊",    "hp":  80, "attack": 25, "icon": "🗡️", "description": "急所攻撃で最大3倍ダメージ"},
    "Cleric":  {"class_name": "僧侶",    "hp":  90, "attack": 15, "icon": "✨",  "description": "ヒールで仲間のHPを30%回復"},
}

@app.route('/')
def index():
    return render_template('index.html',
        character_templates=CHARACTER_TEMPLATES,
        game_started=session.get('game_started', False),
        current_floor=session.get('current_floor', 1),
        party=session.get('party', []),
        in_battle=session.get('in_battle', False),
        enemy=session.get('current_enemy', None),
        battle_logs=session.get('battle_logs', [])
    )

@app.route('/start_game', methods=['POST'])
def start_game():
    slots = [request.form.get(f'slot_{i}', '') for i in range(1, 5)]

    if any(s not in CHARACTER_TEMPLATES for s in slots):
        flash('クラスの選択が不正です。もう一度選択してください。', 'error')
        return redirect(url_for('index'))

    party = []
    for i, class_type in enumerate(slots, 1):
        tmpl = CHARACTER_TEMPLATES[class_type]
        party.append({
            'id':         i,
            'name':       tmpl['class_name'],
            'class_type': class_type,
            'class_name': tmpl['class_name'],
            'icon':       tmpl['icon'],
            'current_hp': tmpl['hp'],
            'max_hp':     tmpl['hp'],
            'attack':     tmpl['attack'],
        })

    session['game_started'] = True
    session['current_floor'] = 1
    session['party']         = party
    session['in_battle']     = False
    session['battle_logs']   = []

    return redirect(url_for('index'))

@app.route('/explore', methods=['POST'])
def explore():
    # ランダムエンカウント処理
    if random.random() < 0.7:  # 70%の確率で戦闘発生
        db = next(get_db())
        current_floor = session.get('current_floor')
        enemy = db.query(Enemy).filter_by(floor=current_floor).order_by(func.random()).first()
        
        if enemy is None:  # 敵が見つからない場合の処理
            session['battle_logs'] = ['このフロアには敵がいないようだ...']
            return redirect(url_for('index'))
        
        session['in_battle'] = True
        session['current_enemy'] = {
            'name': enemy.name,
            'current_hp': enemy.hp,
            'max_hp': enemy.hp,
            'attack': enemy.attack
        }
        session['battle_logs'] = ['敵が現れた！']
    
    return redirect(url_for('index'))

@app.route('/battle_action', methods=['POST'])
def battle_action():
    action = request.form.get('action')
    battle_logs = session.get('battle_logs', [])
    
    if action == 'attack':
        # 戦闘処理の例
        enemy = session.get('current_enemy')
        party = session.get('party')
        
        # パーティーの攻撃
        damage = sum(char['attack'] for char in party) // 2
        enemy['current_hp'] -= damage
        battle_logs.append(f'{damage}のダメージを与えた！')
        
        # 敵の反撃
        if enemy['current_hp'] > 0:
            target = random.choice(party)
            enemy_damage = enemy['attack']
            target['current_hp'] -= enemy_damage
            battle_logs.append(f'{target["name"]}が{enemy_damage}のダメージを受けた！')
        
        session['current_enemy'] = enemy
        session['party'] = party
        session['battle_logs'] = battle_logs
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True) 

    