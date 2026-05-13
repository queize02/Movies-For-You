from flask import Flask, render_template, request, redirect, session, url_for, flash
import requests
import sqlite3
import hashlib
import os

app = Flask(__name__)
app.secret_key = "user_securited"

# --- CONFIGURATION DES CHEMINS ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILMS = os.path.join(BASE_DIR, 'films.db')
DB_USERS = os.path.join(BASE_DIR, 'users.db')

# --- CONFIGURATION DES WEBHOOKS ---
WEBHOOK_DEMANDES = "https://discord.com/api/webhooks/1500756368414605332/BqBPee66pcVIUBEfLqUe7hk4KZ0mg_hPt-4Tl81CkkKf-ts0V9YKvz-u6k_arVTBp5V_"
WEBHOOK_AJOUTS = "https://discord.com/api/webhooks/1502005094152011837/HNwcpRHhSdmd9A1VSk2IrsZ0w3Gi5dL7L7zYJspXqOUCHkgCuD4mJJrpzss5FtTUpzKk"
TMDB_API_KEY = "1dfef7dd68067ec8b05e87b494b9a7f4"

# --- INITIALISATION ---
def init_db():
    with sqlite3.connect(DB_FILMS) as conn_f:
        conn_f.execute('CREATE TABLE IF NOT EXISTS films (id INTEGER PRIMARY KEY AUTOINCREMENT, titre TEXT, affiche TEXT, lien TEXT)')
    with sqlite3.connect(DB_USERS) as conn_u:
        conn_u.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT)')

init_db()

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

# --- ROUTES ---

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        
        with sqlite3.connect(DB_USERS) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password))
            user = cursor.fetchone()
            
            if user:
                session['user'] = username
                flash('Connexion réussie ! Redirection...', 'success')
                # On renvoie la page avec une variable pour déclencher le JS
                return render_template('login.html', success=True)
            else:
                flash('Mot de passe ou utilisateur incorrect.', 'error')
                return redirect(url_for('login'))
                
    return render_template('login.html', success=False)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = hash_password(request.form['password'])
        
        try:
            with sqlite3.connect(DB_USERS) as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, password))
                conn.commit()
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            return "Ce nom d'utilisateur existe déjà. <a href='/register'>Réessayer</a>"
            
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user' not in session: return redirect(url_for('login'))
    with sqlite3.connect(DB_FILMS) as conn: # FIX : Utilise DB_FILMS
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM films ORDER BY id DESC")
        films = cursor.fetchall()
    return render_template('index.html', films=films)

@app.route('/request', methods=['GET', 'POST'])
def page_request():
    if 'user' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        titre_film = request.form.get('titre')
        description = request.form.get('description')
        params = {"api_key": TMDB_API_KEY, "query": titre_film, "language": "fr-FR"}
        response = requests.get("https://api.themoviedb.org/3/search/movie", params=params).json()
        if response.get('results'):
            film = response['results'][0]
            data = {
                "embeds": [{
                    "title": "💡 Nouvelle demande",
                    "description": f"De : **{session['user']}**\nFilm : **{film['title']}**",
                    "color": 3447003,
                    "thumbnail": {"url": f"https://image.tmdb.org/t/p/w500{film['poster_path']}"},
                    "fields": [{"name": "Message", "value": description if description else "Aucun."}]
                }]
            }
            requests.post(WEBHOOK_DEMANDES, json=data)
            return "Envoyé ! <a href='/'>Retour</a>"
    return render_template('request.html')

@app.route('/admin_ajouter', methods=['GET', 'POST'])
def admin_ajouter():
    if 'user' not in session or session['user'] != "wQueize_":
        return "Accès interdit", 403
    if request.method == 'POST':
        titre_film = request.form['titre']
        lien_video = request.form['lien']
        params = {"api_key": TMDB_API_KEY, "query": titre_film, "language": "fr-FR"}
        response = requests.get("https://api.themoviedb.org/3/search/movie", params=params).json()
        if response.get('results'):
            film = response['results'][0]
            with sqlite3.connect(DB_FILMS) as conn: # FIX : Utilise DB_FILMS
                cursor = conn.cursor()
                cursor.execute("INSERT INTO films (titre, affiche, lien) VALUES (?, ?, ?)", 
                             (film['title'], f"https://image.tmdb.org/t/p/w500{film['poster_path']}", lien_video))
                film_id = cursor.lastrowid
            
            lien_site = f"{request.host_url}film/{film_id}"
            data = {
                "embeds": [{
                    "title": "🎬 Nouveau film !",
                    "description": f"**{film['title']}** est dispo.",
                    "thumbnail": {"url": f"https://image.tmdb.org/t/p/w500{film['poster_path']}"},
                    "color": 15158332,
                    "fields": [{"name": "Lien", "value": f"[Regarder]({lien_site})"}]
                }]
            }
            requests.post(WEBHOOK_AJOUTS, json=data)
            return redirect(url_for('index'))
    return render_template('admin.html')

@app.route('/film/<int:film_id>')
def regarder_film(film_id):
    if 'user' not in session: return redirect(url_for('login'))
    with sqlite3.connect(DB_FILMS) as conn: # FIX : Utilise DB_FILMS
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM films WHERE id = ?", (film_id,))
        film = cursor.fetchone()
    return render_template('player.html', film=film) if film else ("Introuvable", 404)


@app.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    # Ici, tu dois chercher le film dans ta base de données avec son ID
    # Exemple si tu utilises SQLite :
    # movie = db.execute('SELECT * FROM films WHERE id = ?', (movie_id,)).fetchone()
    return render_template('movie_detail.html', movie=movie)



if __name__ == '__main__':
    app.run(debug=True)