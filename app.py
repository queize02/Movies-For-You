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

@app.route('/admin_ajouter', methods=['GET', 'POST'])
def admin_ajouter():
    if 'user' not in session: 
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        titre_film = request.form.get('titre')
        # On met un texte par défaut si le lien est vide
        lien_video = request.form.get('lien') or "Lien à définir"
        
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

            # Notification Discord
            # Notification Discord
            payload = {
                "embeds": [{
                    "title": "💡 Nouvelle suggestion de film",
                    "description": f"Film : **{film['title']}**\nProposé par : **{session['user']}**\n\n*Clique sur le bouton ci-dessous pour ajouter le lien et valider.*",
                    "color": 3447003,
                    "thumbnail": {"url": f"https://image.tmdb.org/t/p/w500{film['poster_path']}"}
                }],
                "components": [{
                    "type": 1, # Action Row
                    "components": [
                        { 
                            "components": [
    { "type": 2, "label": "Test Lien", "style": 5, "url": "https://google.com" }
]
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
            flash("Suggestion envoyée !")
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


@app.route('/admin/approve_form/<int:movie_id>', methods=['GET', 'POST'])
def admin_approve_form(movie_id):
    # Sécurité : Seuls les admins peuvent voir cette page
    if 'user' not in session or session['user'] not in ADMINS:
        return "Accès interdit", 403
    
    if request.method == 'POST':
        nouveau_lien = request.form.get('lien_final')
        conn = get_db_connection()
        cur = conn.cursor()
        # On met à jour le lien ET on passe le statut en 'approved'
        cur.execute("UPDATE films SET lien = %s, status = 'approved' WHERE id = %s", (nouveau_lien, movie_id))
        conn.commit()
        cur.close()
        conn.close()
        return "<h1>✅ Film publié avec succès !</h1><p>Tu peux fermer cette page, le film est maintenant visible sur le catalogue.</p>"

    # Si on arrive sur la page, on affiche un petit formulaire simple
    return f'''
        <body style="background: #141414; color: white; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh;">
            <form method="post" style="background: #1f1f1f; padding: 30px; border-radius: 10px; border: 1px solid #46d369; text-align: center;">
                <h2 style="color: #46d369;">Finaliser l'ajout du film</h2>
                <p>Colle le lien de la vidéo pour valider la proposition :</p>
                <input type="text" name="lien_final" placeholder="URL de la vidéo (YouTube, Embed...)" 
                       style="width: 100%; padding: 12px; margin-bottom: 20px; border-radius: 5px; border: none;" required>
                <br>
                <button type="submit" style="background: #46d369; color: black; border: none; padding: 12px 25px; border-radius: 5px; font-weight: bold; cursor: pointer;">
                    Valider et mettre en ligne
                </button>
            </form>
        </body>
    '''

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)