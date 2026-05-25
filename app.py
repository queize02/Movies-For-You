from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import requests
import psycopg2
from psycopg2.extras import DictCursor
import hashlib
import os

TMDB_API_KEY = "1dfef7dd68067ec8b05e87b494b9a7f4"
    

def recuperer_categorie_film(titre_film):
    titre_propre = titre_film.replace(" :", ":").strip()
    # On cherche d'abord pour obtenir l'ID
    url_recherche = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={requests.utils.quote(titre_propre)}&language=fr-FR"
    
    try:
        reponse = requests.get(url_recherche).json()
        if reponse.get('results'):
            film_id = reponse['results'][0]['id']
            # On récupère les détails complets
            url_details = f"https://api.themoviedb.org/3/movie/{film_id}?api_key={TMDB_API_KEY}&language=fr-FR"
            details = requests.get(url_details).json()
            
            genres = details.get('genres', [])
            if genres:
                # LISTE DES GENRES À ÉVITER COMME PREMIER CHOIX SI POSSIBLE
                # Parfois "Drame" est mis par défaut. On peut choisir le 2ème s'il existe.
                if len(genres) > 1 and genres[0]['name'] == "Drame":
                    return genres[1]['name']
                return genres[0]['name']
                
    except Exception as e:
        print(f"DEBUG: Erreur catégorie : {e}")
    return "Autre"

app = Flask(__name__)
app.secret_key = "user_securited"

ADMINS = ["wqueize_", "tenoste", "Wqueize_", "Tenoste"]

def is_admin():
    if 'user' not in session or not session['user']:
        return False
    return str(session['user']).lower().strip() in [a.lower() for a in ADMINS]

# Rend la fonction accessible dans index.html
app.jinja_env.globals.update(is_admin=is_admin)

# --- CONNEXION NEON (PostgreSQL) ---
DB_URL = "postgresql://neondb_owner:npg_jQVktANW7Y8e@ep-gentle-glitter-aldcjmmp-pooler.c-3.eu-central-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
def get_db_connection():
    return psycopg2.connect(DB_URL, cursor_factory=DictCursor)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Table unique avec toutes les colonnes nécessaires
    cur.execute('''CREATE TABLE IF NOT EXISTS films (
        id SERIAL PRIMARY KEY, 
        titre TEXT, 
        affiche TEXT, 
        lien TEXT, 
        description TEXT,
        status TEXT DEFAULT 'pending',
        categorie TEXT,
        tmdb_id INTEGER)''') 
    
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY, 
        username TEXT UNIQUE, 
        password TEXT)''')
    conn.commit()
    cur.close()
    conn.close()

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        hashed_password = hashlib.sha256(password.encode()).hexdigest()

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, hashed_password))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            session['user'] = user['username']
            return render_template('login.html', success=True)
        else:
            flash("Identifiant ou mot de passe incorrect.")
            return redirect(url_for('login'))
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
            return render_template('register.html', success=True)
        except:
            flash("Nom d'utilisateur déjà pris")
    return render_template('register.html')

@app.route('/')
def index():
    if 'user' not in session: return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM films WHERE status = 'approved' ORDER BY id DESC")
    tous_les_films = cur.fetchall()
    cur.close()
    conn.close()
    
    films_par_categorie = {}
    for film in tous_les_films:
        cat = film['categorie'] if film['categorie'] else "Autre"
        if cat not in films_par_categorie:
            films_par_categorie[cat] = []
        films_par_categorie[cat].append(film)
        
    return render_template('index.html', catalogue_categories=films_par_categorie)

@app.route('/admin_ajouter', methods=['GET', 'POST'])
def admin_ajouter():
    print("DEBUG: Je suis bien dans la fonction admin_ajouter") # AJOUTE CECI
    if 'user' not in session: 
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        titre_film = request.form.get('titre')
        print(f"DEBUG: Titre reçu : {titre_film}") # Remplace 'titre' par 'titre_film'# AJOUTE CECI
        lien_temporaire = "À définir par l'admin"
        
        # Ajoute le nettoyage ici aussi
        titre_propre = titre_film.replace(" :", ":").strip()
        params = {"api_key": TMDB_API_KEY, "query": titre_propre, "language": "fr-FR"}
        try:
            response = requests.get("https://api.themoviedb.org/3/search/movie", params=params, timeout=5).json()
            if response.get('results'):
                film = response['results'][0]
                categorie_auto = recuperer_categorie_film(film['title'])
                
                # --- MODIFICATION ICI ---
                conn = get_db_connection()
                cur = conn.cursor()
                # Dans ton bloc INSERT, ajoute la colonne tmdb_id et la valeur film['id']
                cur.execute("""
                    INSERT INTO films (titre, affiche, lien, description, status, categorie, tmdb_id)
                    VALUES (%s, %s, %s, %s, 'pending', %s, %s) RETURNING id
                """, (film['title'], f"https://image.tmdb.org/t/p/w500{film['poster_path']}", "auto", film['overview'], categorie_auto, film['id']))

                film_id = cur.fetchone()[0] # Aligné correctement
                conn.commit()
                cur.close()
                conn.close()
                # ------------------------

                data_pour_bot = {
                    "titre": film['title'],
                    "user": session['user'],
                    "affiche": f"https://image.tmdb.org/t/p/w500{film['poster_path']}",
                    "film_id": film_id
                }
                # ... le reste du code (requests.post) reste identique ...
                try:
                    render_url = "https://bot-js-l8hi.onrender.com/nouvelle-suggestion"
                    requests.post(render_url, json=data_pour_bot, timeout=20)
                except Exception as e:
                    print(f"Erreur d'envoi au Bot : {e}")

                flash("Merci ! Ta suggestion a été envoyée.")
                return render_template('admin.html')
            else:
                flash("Film introuvable sur TMDB. Vérifie l'orthographe !")
        except Exception as e:
            flash("Une erreur est survenue lors de l'ajout.")
    return render_template('admin.html')

@app.route('/admin_manuel', methods=['GET', 'POST'])
def admin_manuel():
    current_user = session.get('user', '').lower()
    admins_lower = [a.lower() for a in ADMINS]

    if 'user' not in session or current_user not in admins_lower:
        flash(f"Accès refusé pour {session.get('user')}.")
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        titre = request.form.get('titre') # Variable définie ici
        lien = request.form.get('lien')
        
        # Corrige ici : utilise 'titre' au lieu de 'titre_film'
        titre_propre = titre.replace(" :", ":").strip()
        params = {"api_key": TMDB_API_KEY, "query": titre_propre, "language": "fr-FR"}
        
        try:
            response = requests.get("https://api.themoviedb.org/3/search/movie", params=params).json()
            if response.get('results'):
                film = response['results'][0]
                categorie_auto = recuperer_categorie_film(film['title']) # <--- OBLIGATOIRE

                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO films (titre, affiche, lien, description, status, categorie) VALUES (%s, %s, %s, %s, 'approved', %s)", 
                             (film['title'], f"https://image.tmdb.org/t/p/w500{film['poster_path']}", lien, film['overview'], categorie_auto))
                conn.commit()
                cur.close()
                conn.close()
                flash(f"✅ Film '{film['title']}' ({categorie_auto}) ajouté directement !")
                return redirect(url_for('index'))
        except Exception as e:
            flash(f"Erreur : {e}")
            
    return '''
        <body style="background: #141414; color: white; font-family: sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh;">
            <form method="post" style="background: #1f1f1f; padding: 30px; border-radius: 10px; border: 1px solid #e50914; text-align: center; width: 400px;">
                <h2 style="color: #e50914;">Ajout Manuel (Admin)</h2>
                <input type="text" name="titre" placeholder="Titre du film" style="width: 100%; padding: 12px; margin-bottom: 10px;" required>
                <input type="text" name="lien" placeholder="Lien de la vidéo" style="width: 100%; padding: 12px; margin-bottom: 20px;" required>
                <button type="submit" style="background: #e50914; color: white; border: none; padding: 12px; width: 100%; cursor: pointer; font-weight: bold;">PUBLIER DIRECTEMENT</button>
                <br><br><a href="/" style="color: gray; text-decoration: none;">Retour</a>
            </form>
        </body>
    '''

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


@app.route('/admin_approuver/<int:movie_id>', methods=['GET', 'POST'])
def admin_approuver_request(movie_id):
    if 'user' not in session or not is_admin():
        return "Accès refusé", 403

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    # 1. On récupère le film pour avoir son tmdb_id
    cur.execute("SELECT * FROM films WHERE id = %s", (movie_id,))
    film = cur.fetchone()

    if request.method == 'POST':
        lien_final = request.form.get('lien_final')
        
        if film:
            categorie_auto = recuperer_categorie_film(film['titre'])
            cur.execute(
                "UPDATE films SET status = 'approved', lien = %s, categorie = %s WHERE id = %s",
                (lien_final, categorie_auto, movie_id)
            )
            conn.commit()

            # Notification Bot
            print("DEBUG: Tentative d'envoi de la notification au bot...")
            try:
                reponse = requests.post("https://bot-js-l8hi.onrender.com/admin_manuel", json={
                    "titre": film['titre'],
                    "affiche": film['affiche']
                }, timeout=10)
                print(f"DEBUG: Réponse du bot : {reponse.status_code}")
            except Exception as e:
                print(f"DEBUG: Erreur envoi : {e}")
        cur.close()
        conn.close()
        return redirect(url_for('index'))

    return render_template('approve_form.html', movie_id=movie_id, tmdb_id=film['tmdb_id'])      
 
@app.route('/admin_supprimer/<int:movie_id>', methods=['POST'])
def admin_supprimer(movie_id):
    if 'user' not in session or not is_admin():
        flash("🔴 Accès refusé.")
        return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM films WHERE id = %s", (movie_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("🗑️ Le film a été supprimé.")
    except Exception as e:
        flash(f"Erreur : {e}")
    return redirect(url_for('index'))

@app.route('/movie/<int:movie_id>')
def voir_film(movie_id):
    if 'user' not in session: 
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    # ✅ On utilise directement DictCursor puisqu'il est déjà importé en haut du fichier !
    cur = conn.cursor(cursor_factory=DictCursor)
    
    cur.execute("SELECT * FROM films WHERE id = %s", (movie_id,))
    film = cur.fetchone()
    
    cur.close()
    conn.close()
    
    if film:
        return render_template('movie_detail.html', film=film)
    else:
        flash("Film introuvable.")
        return redirect(url_for('index'))
# Ajoute ceci dans app.py
@app.route('/api/discord_suggerer', methods=['POST'])
def api_discord_suggerer():
    data = request.json
    titre_film = data.get('titre')
    user = data.get('user')
    
    # Recherche TMDB (copie de la logique de admin_ajouter)
    params = {"api_key": TMDB_API_KEY, "query": titre_film, "language": "fr-FR"}
    response = requests.get("https://api.themoviedb.org/3/search/movie", params=params).json()
    
    if response.get('results'):
        film = response['results'][0]
        categorie_auto = recuperer_categorie_film(film['title'])
        
        # Insertion dans Neon
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO films (titre, affiche, lien, description, status, categorie, tmdb_id)
            VALUES (%s, %s, %s, %s, 'pending', %s, %s) RETURNING id
        """, (film['title'], f"https://image.tmdb.org/t/p/w500{film['poster_path']}", "auto", film['overview'], categorie_auto, film['id']))
        film_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        # Envoi de la notification au bot (via ta route existante)
        requests.post("https://bot-js-l8hi.onrender.com/nouvelle-suggestion", json={
            "titre": film['title'],
            "user": user,
            "affiche": f"https://image.tmdb.org/t/p/w500{film['poster_path']}",
            "film_id": film_id
        })
        
        return jsonify({"status": "success", "message": "Suggestion ajoutée"}), 200
    
    return jsonify({"status": "error", "message": "Film introuvable"}), 404

@app.route('/admin/dashboard')
def admin_dashboard():
    if not is_admin():
        return "Accès refusé", 403
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM films WHERE status = 'pending'")
    films_attente = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('admin_dashboard.html', films=films_attente)    

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)