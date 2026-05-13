from urllib import response

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

# --- CONFIGURATION DES WEBHOOKS ET API ---
WEBHOOK_DEMANDES = "https://discord.com/api/webhooks/1500756368414605332/BqBPee66pcVIUBEfLqUe7hk4KZ0mg_hPt-4Tl81CkkKf-ts0V9YKvz-u6k_arVTBp5V_"
WEBHOOK_AJOUTS = "https://discord.com/api/webhooks/1502005094152011837/HNwcpRHhSdmd9A1VSk2IrsZ0w3Gi5dL7L7zYJspXqOUCHkgCuD4mJJrpzss5FtTUpzKk"
TMDB_API_KEY = "1dfef7dd68067ec8b05e87b494b9a7f4"

# --- INITIALISATION ET MISE À JOUR DE LA DB ---
def init_db():
    with sqlite3.connect(DB_FILMS) as conn_f:
        # Ajout de 'description TEXT' à la fin
        conn_f.execute('CREATE TABLE IF NOT EXISTS films (id INTEGER PRIMARY KEY AUTOINCREMENT, titre TEXT, affiche TEXT, lien TEXT, description TEXT)')
    with sqlite3.connect(DB_USERS) as conn_u:
        conn_u.execute('CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT)')
init_db()

# --- ROUTES AUTHENTIFICATION ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        
        with sqlite3.connect(DB_USERS) as conn:
            user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?', (username, password)).fetchone()
        
        if user:
            session['user'] = username
            # On reste sur login.html mais on envoie "success=True"
            return render_template('login.html', success=True)
        else:
            flash("Identifiants incorrects")
            return render_template('login.html', success=False)
            
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        try:
            with sqlite3.connect(DB_USERS) as conn:
                conn.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
            return redirect(url_for('login'))
        except:
            flash("Nom d'utilisateur déjà pris")
    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

# --- ROUTES PRINCIPALES ---
@app.route('/')
def index():
    if 'user' not in session: return redirect(url_for('login'))
    with sqlite3.connect(DB_FILMS) as conn:
        films = conn.execute('SELECT id, titre, affiche FROM films').fetchall()
    return render_template('index.html', films=films)

@app.route('/request', methods=['GET', 'POST'])
def page_request():
    if 'user' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        # On utilise .get() pour éviter l'erreur "Bad Request" si un champ manque
        titre_film = request.form.get('titre')
        message_utilisateur = request.form.get('description')
        
        if not titre_film:
            return "Le titre est obligatoire. <a href='/request'>Retour</a>", 400

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
                    "fields": [{"name": "Message de l'utilisateur", "value": message_utilisateur if message_utilisateur else "Aucun."}]
                }]
            }
            requests.post(WEBHOOK_DEMANDES, json=data)
            return "Votre demande a bien été envoyée ! <a href='/'>Retour au catalogue</a>"
        else:
            return "Film introuvable sur TMDB. <a href='/request'>Réessayer</a>"
            
    return render_template('request.html')

# --- ROUTE DÉTAIL DU FILM (DESIGN NETFLIX) ---
@app.route('/movie/<int:movie_id>') # On utilise 'movie' partout
def movie_detail(movie_id):
    if 'user' not in session: return redirect(url_for('login'))
    with sqlite3.connect(DB_FILMS) as conn:
        cursor = conn.cursor()
        # On récupère les 5 colonnes : id, titre, affiche, lien, description
        cursor.execute("SELECT id, titre, affiche, lien, description FROM films WHERE id = ?", (movie_id,))
        movie = cursor.fetchone()
    
    if movie:
        # On charge bien le fichier movie_detail.html que tu as créé
        return render_template('movie_detail.html', movie=movie)
    return "Film introuvable", 404

# --- ROUTE ADMINISTRATION ---
@app.route('/admin_ajouter', methods=['GET', 'POST'])
def admin_ajouter():
    if 'user' not in session or session['user'] != "wQueize_":
        return "Accès interdit", 403
    
    if request.method == 'POST':
        titre_film = request.form.get('titre')
        lien_video = request.form.get('lien')
        
        # Correction de l'alignement ici
        params = {"api_key": TMDB_API_KEY, "query": titre_film, "language": "fr-FR"}
        response = requests.get("https://api.themoviedb.org/3/search/movie", params=params).json()
        
        if response.get('results'):
            film = response['results'][0]
            with sqlite3.connect(DB_FILMS) as conn:
                cursor = conn.cursor()
                # Insertion des 4 colonnes (titre, affiche, lien, description)
                cursor.execute("INSERT INTO films (titre, affiche, lien, description) VALUES (?, ?, ?, ?)", 
                             (film['title'], f"https://image.tmdb.org/t/p/w500{film['poster_path']}", lien_video, film['overview']))
                film_id = cursor.lastrowid
            
            # Notification Discord
            data = {
                "embeds": [{
                    "title": "🎬 Nouveau film !",
                    "description": f"**{film['title']}** est dispo.\n{film['overview'][:150]}...",
                    "color": 15158332,
                    "thumbnail": {"url": f"https://image.tmdb.org/t/p/w500{film['poster_path']}"}
                }]
            }
            requests.post(WEBHOOK_AJOUTS, json=data)
            flash("Film ajouté !")
            return redirect(url_for('index'))
            
    return render_template('admin.html')

if __name__ == '__main__':
    app.run(debug=True)