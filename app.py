from flask import Flask, render_template, request, redirect, session, url_for, flash
import requests
import psycopg2
from psycopg2.extras import DictCursor
import hashlib
import os

app = Flask(__name__)
app.secret_key = "user_securited"

ADMINS = ["wQueize_", "tenoste"]

# --- CONNEXION NEON (PostgreSQL) ---
# REMPLACE PAR TON LIEN COPIÉ SUR NEON
DB_URL = "postgresql://neondb_owner:npg_jQVktANW7Y8e@ep-gentle-glitter-aldcjmmp-pooler.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require"
def get_db_connection():
    # Connexion à la base de données cloud
    conn = psycopg2.connect(DB_URL, cursor_factory=DictCursor)
    return conn

# --- INITIALISATION DES TABLES ---
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('''CREATE TABLE IF NOT EXISTS films (
        id SERIAL PRIMARY KEY, 
        titre TEXT, 
        affiche TEXT, 
        lien TEXT, 
        description TEXT)''')
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY, 
        username TEXT UNIQUE, 
        password TEXT)''')
    conn.commit()
    cur.close()
    conn.close()

init_db()

# --- CONFIGURATION DES WEBHOOKS ET API ---
WEBHOOK_DEMANDES = "https://discord.com/api/webhooks/1500756368414605332/BqBPee66pcVIUBEfLqUe7hk4KZ0mg_hPt-4Tl81CkkKf-ts0V9YKvz-u6k_arVTBp5V_"
WEBHOOK_AJOUTS = "https://discord.com/api/webhooks/1502005094152011837/HNwcpRHhSdmd9A1VSk2IrsZ0w3Gi5dL7L7zYJspXqOUCHkgCuD4mJJrpzss5FtTUpzKk"
TMDB_API_KEY = "1dfef7dd68067ec8b05e87b494b9a7f4"

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE username = %s AND password = %s', (username, password))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user:
            session['user'] = username
            return render_template('login.html', success=True)
        flash("Identifiants incorrects")
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute('INSERT INTO users (username, password) VALUES (%s, %s)', (username, password))
            conn.commit()
            cur.close()
            conn.close()
            
            # On reste sur la page mais on dit que c'est un succès
            return render_template('register.html', success=True)
            
        except Exception as e:
            flash("Nom d'utilisateur déjà pris")
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, titre, affiche FROM films')
    films = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('index.html', films=films)

@app.route('/request', methods=['GET', 'POST'])
def page_request():
    if 'user' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        titre_film = request.form.get('titre')
        message_utilisateur = request.form.get('description')
        
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
                    "fields": [{"name": "Message", "value": message_utilisateur or "Aucun"}]
                }]
            }
            requests.post(WEBHOOK_DEMANDES, json=data)
            return "Demande envoyée ! <a href='/'>Retour</a>"
    return render_template('request.html')

@app.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    if 'user' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, titre, affiche, lien, description FROM films WHERE id = %s", (movie_id,))
    movie = cur.fetchone()
    cur.close()
    conn.close()
    
    if movie:
        return render_template('movie_detail.html', movie=movie)
    return "Film introuvable", 404

@app.route('/admin_ajouter', methods=['GET', 'POST'])
def admin_ajouter():
    if 'user' not in session or session['user'] not in ADMINS:
        return "Accès interdit", 403
    
    if request.method == 'POST':
        titre_film = request.form.get('titre')
        lien_video = request.form.get('lien')
        
        params = {"api_key": TMDB_API_KEY, "query": titre_film, "language": "fr-FR"}
        response = requests.get("https://api.themoviedb.org/3/search/movie", params=params).json()
        
        if response.get('results'):
            film = response['results'][0]
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO films (titre, affiche, lien, description) VALUES (%s, %s, %s, %s)", 
                         (film['title'], f"https://image.tmdb.org/t/p/w500{film['poster_path']}", lien_video, film['overview']))
            conn.commit()
            cur.close()
            conn.close()
            
            flash("Film ajouté !")
            return redirect(url_for('index'))
            
    return render_template('admin.html')
if __name__ == '__main__':
    # On initialise les tables uniquement au lancement
    with app.app_context():
        init_db()
    app.run(debug=True)