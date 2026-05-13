from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import requests
import psycopg2
from psycopg2.extras import DictCursor
import hashlib
import os

app = Flask(__name__)
app.secret_key = "user_securited"

ADMINS = ["wQueize_", "tenoste"]

# --- CONNEXION NEON (PostgreSQL) ---
DB_URL = "postgresql://neondb_owner:npg_jQVktANW7Y8e@ep-gentle-glitter-aldcjmmp-pooler.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require"

def get_db_connection():
    return psycopg2.connect(DB_URL, cursor_factory=DictCursor)

# --- INITIALISATION DES TABLES ---
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # On s'assure que la colonne 'status' existe
    cur.execute('''CREATE TABLE IF NOT EXISTS films (
        id SERIAL PRIMARY KEY, 
        titre TEXT, 
        affiche TEXT, 
        lien TEXT, 
        description TEXT,
        status TEXT DEFAULT 'pending')''')
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY, 
        username TEXT UNIQUE, 
        password TEXT)''')
    conn.commit()
    cur.close()
    conn.close()

# --- CONFIGURATION WEBHOOKS ET API ---
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
            # On renvoie vers register.html avec un flag success pour le JS
            return render_template('register.html', success=True)
        except:
            flash("Nom d'utilisateur déjà pris")
    return render_template('register.html')

@app.route('/')
def index():
    if 'user' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    # IMPORTANT: On ne montre que les films 'approved'
    cur.execute("SELECT id, titre, affiche FROM films WHERE status = 'approved'")
    films = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('index.html', films=films)

@app.route('/admin_ajouter', methods=['GET', 'POST']) # Tu peux la renommer en /proposer si tu veux
def admin_ajouter():
    # MODIFICATION : On enlève "or session['user'] not in ADMINS"
    if 'user' not in session: 
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        titre_film = request.form.get('titre')
        lien_video = request.form.get('lien')
        params = {"api_key": TMDB_API_KEY, "query": titre_film, "language": "fr-FR"}
        response = requests.get("https://api.themoviedb.org/3/search/movie", params=params).json()
        if response.get('results'):
            film = response['results'][0]
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO films (titre, affiche, lien, description, status) VALUES (%s, %s, %s, %s, 'pending') RETURNING id", 
                         (film['title'], f"https://image.tmdb.org/t/p/w500{film['poster_path']}", lien_video, film['overview']))
            film_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()

            # Envoi vers Discord avec BOUTONS
          # Envoi vers Discord avec boutons de type LIEN (Style 5)
            payload = {
                "embeds": [{
                    "title": "🎬 Nouveau film en attente",
                    "description": f"Film : **{film['title']}**\nPosté par : **{session['user']}**",
                    "color": 15844367,
                    "thumbnail": {"url": f"https://image.tmdb.org/t/p/w500{film['poster_path']}"}
                }],
                "components": [{
                    "type": 1,
                    "components": [
                        {
                            "type": 2, 
                            "label": "✅ Approuver", 
                            "style": 5, 
                            "url": f"https://movies-for-you.onrender.com/admin/approve/{film_id}"
                        },
                        {
                            "type": 2, 
                            "label": "❌ Refuser", 
                            "style": 5, 
                            "url": f"https://movies-for-you.onrender.com/admin/deny/{film_id}"
                        }
                    ]
                }]
            }
            requests.post(WEBHOOK_AJOUTS, json=payload)
            flash("Film envoyé pour validation sur Discord !")
            return redirect(url_for('index'))
    return render_template('admin.html')


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/admin/approve/<int:movie_id>')
def admin_confirm_approve(movie_id):
    if 'user' not in session or session['user'] not in ADMINS:
        return "Accès interdit", 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("UPDATE films SET status = 'approved' WHERE id = %s", (movie_id,))
    conn.commit()
    cur.close()
    conn.close()
    return "<h1>✅ Film approuvé avec succès !</h1><p>Tu peux fermer cette fenêtre.</p>"

@app.route('/admin/deny/<int:movie_id>')
def admin_confirm_deny(movie_id):
    if 'user' not in session or session['user'] not in ADMINS:
        return "Accès interdit", 403
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM films WHERE id = %s", (movie_id,))
    conn.commit()
    cur.close()
    conn.close()
    return "<h1>❌ Film supprimé.</h1><p>Tu peux fermer cette fenêtre.</p>"

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)