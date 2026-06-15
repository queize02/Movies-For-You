from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import requests
import psycopg2
from psycopg2.extras import DictCursor
import hashlib
import os
DATABASE_URL = "postgresql://admin:02082008@192.168.1.13:5432/neondb"
def get_db_connection():
    # On cherche la variable, si elle n'existe pas, on prend DATABASE_URL définie en haut
    database_url = os.environ.get('DATABASE_URL', DATABASE_URL)
    return psycopg2.connect(database_url)
app = Flask(__name__)
 
@app.route('/health')
def health():
    return "OK", 200
TMDB_API_KEY = "1dfef7dd68067ec8b05e87b494b9a7f4"
    

def recuperer_categorie_film(titre_film, media_type='movie'):
    titre_propre = titre_film.replace(" :", ":").strip()
    # On cherche d'abord pour obtenir l'ID
    try:
        if media_type == 'tv':
            url_recherche = f"https://api.themoviedb.org/3/search/tv?api_key={TMDB_API_KEY}&query={requests.utils.quote(titre_propre)}&language=fr-FR"
        else:
            url_recherche = f"https://api.themoviedb.org/3/search/movie?api_key={TMDB_API_KEY}&query={requests.utils.quote(titre_propre)}&language=fr-FR"
            
        reponse = requests.get(url_recherche).json()
        if reponse.get('results'):
            film = reponse['results'][0]
            film_id = film['id']
            # On récupère les détails complets
            if media_type == 'tv':
                url_details = f"https://api.themoviedb.org/3/tv/{film_id}?api_key={TMDB_API_KEY}&language=fr-FR"
            else:
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
        
    cur.execute('''
        DO $$ 
        BEGIN 
            BEGIN
                ALTER TABLE films ADD COLUMN media_type TEXT DEFAULT 'movie';
            EXCEPTION
                WHEN duplicate_column THEN RAISE NOTICE 'column media_type already exists in films.';
            END;
        END; 
        $$
    ''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY, 
        username TEXT UNIQUE, 
        password TEXT)''')
        
    cur.execute('''CREATE TABLE IF NOT EXISTS episodes (
        id SERIAL PRIMARY KEY,
        film_id INTEGER REFERENCES films(id) ON DELETE CASCADE,
        saison INTEGER,
        episode INTEGER,
        lien TEXT,
        UNIQUE(film_id, saison, episode))''')
        
    conn.commit()
    cur.close()
    conn.close()

@app.route('/api/episodes/<int:movie_id>')
def api_episodes(movie_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT saison, episode, lien FROM episodes WHERE film_id = %s", (movie_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    episodes_dict = {}
    for row in rows:
        key = f"{row['saison']}-{row['episode']}"
        episodes_dict[key] = row['lien']
        
    return jsonify(episodes_dict)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        hashed_password = hashlib.sha256(password.encode()).hexdigest()

        conn = get_db_connection()
        # MODIFICATION ICI : Ajoute cursor_factory=DictCursor
        cur = conn.cursor(cursor_factory=DictCursor) 
        cur.execute("SELECT * FROM users WHERE username = %s AND password = %s", (username, hashed_password))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user:
            # Maintenant que le curseur est DictCursor, cela fonctionnera :
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
    filter_type = request.args.get('filter')
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor) # FIX
    if filter_type in ['movie', 'tv']:
        cur.execute("SELECT * FROM films WHERE status = 'approved' AND media_type = %s ORDER BY id DESC", (filter_type,))
    else:
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
    if 'user' not in session: return redirect(url_for('login'))
    
    if request.method == 'POST':
        titre_film = request.form.get('titre')
        params = {"api_key": TMDB_API_KEY, "query": titre_film.strip(), "language": "fr-FR"}
        try:
            response = requests.get("https://api.themoviedb.org/3/search/multi", params=params, timeout=5).json()
            # Filtrer pour ne garder que les 'movie' ou 'tv' qui ont une image et une date de sortie
            results = [r for r in response.get('results', []) 
                       if r.get('media_type') in ['movie', 'tv'] 
                       and r.get('poster_path')]
            
            # Trier les résultats par popularité pour avoir le plus probable en premier
            results.sort(key=lambda x: x.get('popularity', 0), reverse=True)

            if results:
                film = results[0] # Le plus populaire sera le 1er
                media_type = film['media_type']
                titre = film.get('title') or film.get('name')
                
                # ... (le reste de ton code d'insertion reste identique)
                categorie_auto = recuperer_categorie_film(titre, media_type)
                
                conn = get_db_connection()
                cur = conn.cursor(cursor_factory=DictCursor)
                cur.execute("""
                    INSERT INTO films (titre, affiche, lien, description, status, categorie, tmdb_id, media_type)
                    VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s) RETURNING id
                """, (titre, f"https://image.tmdb.org/t/p/w500{film['poster_path']}", "auto", film.get('overview', ''), categorie_auto, film['id'], media_type))
                
                film_id = cur.fetchone()['id'] # Utilisation du dictionnaire
                conn.commit()
                cur.close()
                conn.close()

                # Appel au Bot
                titre_discord = titre if media_type == 'movie' else f"(SÉRIE) {titre}"
                requests.post("https://bot-js-l8hi.onrender.com/nouvelle-suggestion", json={
                    "titre": titre_discord,
                    "user": session['user'],
                    "affiche": f"https://image.tmdb.org/t/p/w500{film['poster_path']}"
                }, timeout=10)
                
                flash("Merci ! Ta suggestion a été envoyée.")
                return render_template('admin.html')
        except Exception as e:
            print(f"DEBUG: Erreur ajout : {e}")
            flash("Une erreur est survenue.")
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
            response = requests.get("https://api.themoviedb.org/3/search/multi", params=params).json()
            results = [r for r in response.get('results', []) if r.get('media_type') in ['movie', 'tv']]
            if results:
                film = results[0]
                media_type = film['media_type']
                titre_clean = film.get('title') or film.get('name')
                categorie_auto = recuperer_categorie_film(titre_clean, media_type) # <--- OBLIGATOIRE

                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO films (titre, affiche, lien, description, status, categorie, tmdb_id, media_type) VALUES (%s, %s, %s, %s, 'approved', %s, %s, %s)", 
                             (titre_clean, f"https://image.tmdb.org/t/p/w500{film['poster_path']}", lien, film.get('overview', ''), categorie_auto, film['id'], media_type))
                conn.commit()
                cur.close()
                conn.close()
                flash(f"✅ Média '{titre_clean}' ({categorie_auto}) ajouté directement !")
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
            media_type = film.get('media_type', 'movie')
            categorie_auto = recuperer_categorie_film(film['titre'], media_type)
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

    return render_template('approve_form.html', movie_id=movie_id, tmdb_id=film['tmdb_id'], media_type=film.get('media_type', 'movie'))
 
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
    response = requests.get("https://api.themoviedb.org/3/search/multi", params=params).json()
    results = [r for r in response.get('results', []) if r.get('media_type') in ['movie', 'tv']]
    
    if results:
        film = results[0]
        media_type = film['media_type']
        titre = film.get('title') or film.get('name')
        categorie_auto = recuperer_categorie_film(titre, media_type)
        
        # Insertion dans Neon
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO films (titre, affiche, lien, description, status, categorie, tmdb_id, media_type)
            VALUES (%s, %s, %s, %s, 'pending', %s, %s, %s) RETURNING id
        """, (titre, f"https://image.tmdb.org/t/p/w500{film['poster_path']}", "auto", film.get('overview', ''), categorie_auto, film['id'], media_type))
        film_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        # Envoi de la notification au bot (via ta route existante)
        titre_discord = titre if media_type == 'movie' else f"(SÉRIE) {titre}"
        requests.post("https://bot-js-l8hi.onrender.com/nouvelle-suggestion", json={
            "titre": titre_discord,
            "user": user,
            "affiche": f"https://image.tmdb.org/t/p/w500{film['poster_path']}",
            "film_id": film_id
        })
        
        return jsonify({"status": "success", "message": "Suggestion ajoutée"}), 200
    
    return jsonify({"status": "error", "message": "Film introuvable"}), 404

@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if not is_admin(): return "Accès refusé", 403
    
    results = None
    if request.method == 'POST' and 'search_titre' in request.form:
        titre = request.form.get('search_titre')
        # Recherche multi-critères via TMDB
        params = {"api_key": TMDB_API_KEY, "query": titre, "language": "fr-FR"}
        resp = requests.get("https://api.themoviedb.org/3/search/multi", params=params).json()
        # On filtre pour ne garder que les résultats pertinents (films/séries avec affiche)
        results = [r for r in resp.get('results', []) 
                   if r.get('media_type') in ['movie', 'tv'] and r.get('poster_path')][:3]

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT * FROM films WHERE status = 'pending' ORDER BY id DESC")
    films_attente = cur.fetchall()
    cur.close()
    conn.close()
    
    return render_template('admin_dashboard.html', films=films_attente, search_results=results)

@app.route('/admin_valider_choix', methods=['POST'])
def admin_valider_choix():
    tmdb_id = request.form.get('tmdb_id')
    media_type = request.form.get('media_type')
    
    # Récupérer les détails complets
    url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={TMDB_API_KEY}&language=fr-FR"
    film = requests.get(url).json()
    titre = film.get('title') or film.get('name')
    cat = recuperer_categorie_film(titre, media_type)
    
    # Insertion en BDD
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO films (titre, affiche, lien, description, status, categorie, tmdb_id, media_type)
        VALUES (%s, %s, 'pending', %s, 'pending', %s, %s, %s)
    """, (titre, f"https://image.tmdb.org/t/p/w500{film['poster_path']}", film.get('overview', ''), cat, tmdb_id, media_type))
    conn.commit()
    cur.close()
    conn.close()
    
    flash(f"✅ {titre} ajouté aux suggestions !")
    return redirect(url_for('admin_dashboard'))


if __name__ == '__main__':
    with app.app_context():
        init_db()
app.run(host='0.0.0.0', port=5000, debug=True)