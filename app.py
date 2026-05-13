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
    # Table des films
    with sqlite3.connect(DB_FILMS) as conn_f:
        conn_f.execute('CREATE TABLE IF NOT EXISTS films (id INTEGER PRIMARY KEY AUTOINCREMENT, titre TEXT, affiche TEXT, lien TEXT)')
        # Ajout automatique de la colonne description si elle manque (Étape A)
        try:
            conn_f.execute('ALTER TABLE films ADD COLUMN description TEXT')
        except sqlite3.OperationalError:
            pass  # La colonne existe déjà
            
    # Table des utilisateurs
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
            # On renvoie la page login avec un paramètre 'success'
            return render_template('login.html', success=True)
        else:
            flash("Identifiants incorrects")
            
    return render_template('login.html', success=False)

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
def demander_film():
    if 'user' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        nom_film = request.form['nom_film']
        data = {"content": f"📢 **Nouvelle demande de : {session['user']}**\n🎬 Film : {nom_film}"}
        requests.post(WEBHOOK_DEMANDES, json=data)
        flash("Demande envoyée !")
        return redirect(url_for('index'))
    return render_template('request.html')

# --- ROUTE DÉTAIL DU FILM (DESIGN NETFLIX) ---
@app.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    if 'user' not in session: return redirect(url_for('login'))
    with sqlite3.connect(DB_FILMS) as conn:
        cursor = conn.cursor()
        # On récupère : id(0), titre(1), affiche(2), lien(3), description(4)
        cursor.execute("SELECT id, titre, affiche, lien, description FROM films WHERE id = ?", (movie_id,))
        movie = cursor.fetchone()
    
    if movie:
        return render_template('movie_detail.html', movie=movie)
    return "Film introuvable", 404

# --- ROUTE ADMINISTRATION ---
@app.route('/admin_ajouter', methods=['GET', 'POST'])
def admin_ajouter():
    # Vérification que c'est bien toi l'admin
    if 'user' not in session or session['user'] != "wQueize_":
        return "Accès interdit", 403

    if request.method == 'POST':
        titre_film = request.form['titre']
        lien_video = request.form['lien']
        
        # Recherche sur TMDB pour les infos (Affiche + Description)
        params = {"api_key": TMDB_API_KEY, "query": titre_film, "language": "fr-FR"}
        response = requests.get("https://api.themoviedb.org/3/search/movie", params=params).json()
        
        if response.get('results'):
            film = response['results'][0]
            with sqlite3.connect(DB_FILMS) as conn:
                cursor = conn.cursor()
                # Insertion avec la description (overview)
                cursor.execute("INSERT INTO films (titre, affiche, lien, description) VALUES (?, ?, ?, ?)", 
                             (film['title'], f"https://image.tmdb.org/t/p/w500{film['poster_path']}", lien_video, film['overview']))
                film_id = cursor.lastrowid
            
            # Notification Discord
            lien_site = f"{request.host_url}movie/{film_id}"
            data = {
                "embeds": [{
                    "title": "🎬 Nouveau film !",
                    "description": f"**{film['title']}** est maintenant disponible.\n\n{film['overview'][:150]}...",
                    "thumbnail": {"url": f"https://image.tmdb.org/t/p/w500{film['poster_path']}"},
                    "color": 15158332,
                    "fields": [{"name": "Lien direct", "value": f"[Regarder sur MFY]({lien_site})"}]
                }]
            }
            requests.post(WEBHOOK_AJOUTS, json=data)
            flash("Film ajouté avec succès !")
            return redirect(url_for('index'))
            
    return render_template('admin.html')

if __name__ == '__main__':
    app.run(debug=True)