from flask import Flask, render_template, request, redirect, url_for
from models.database import get_db
from models.character import Player
from game.battle import Battle

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/create_character', methods=['POST'])
def create_character():
    name = request.form['name']
    db = next(get_db())
    player = Player(name=name)
    db.add(player)
    db.commit()
    return redirect(url_for('game_menu', player_id=player.id))

@app.route('/game_menu/<int:player_id>')
def game_menu(player_id):
    db = next(get_db())
    player = db.query(Player).get(player_id)
    return render_template('game_menu.html', player=player)

if __name__ == '__main__':
    app.run(debug=True, port=5000) 

    