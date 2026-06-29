from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import requests
import psycopg2
from psycopg2.extras import DictCursor
import hashlib
import os

# --- NOUVELLE FONCTION POUR LES NOTIFICATIONS ---
def envoyer_notification_discord(titre, media_type, user, affiche, film_id=None):
    data = {
        "titre": titre,
        "media_type": media_type, # 'movie' ou 'tv'
        "user": user,
        "affiche": affiche,
        "film_id": film_id
    }
    try:
        print(f"DEBUG: Envoi notif pour {titre} de type {media_type}")
        requests.post("http://bot_discord:10000/nouvelle-suggestion", json=data, timeout=10)
    except Exception as e:
        print(f"DEBUG: Erreur notification locale : {e}")


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
app.jinja_env.globals.update(is_admin=is_admin, TMDB_API_KEY=TMDB_API_KEY)

# --- CONNEXION NEON (PostgreSQL) ---


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Table pour les films (uniquement)
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
    
    # Nouvelle table pour les séries
    cur.execute('''CREATE TABLE IF NOT EXISTS series (
        id SERIAL PRIMARY KEY, 
        titre TEXT, 
        affiche TEXT, 
        description TEXT,
        status TEXT DEFAULT 'pending',
        categorie TEXT,
        tmdb_id INTEGER)''')
    
    cur.execute('''CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY, 
        username TEXT UNIQUE, 
        password TEXT)''')
        
    # Vérification des colonnes d'episodes pour la migration
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'episodes'")
    episodes_cols = [r[0] for r in cur.fetchall()]
    
    if not episodes_cols:
        # Si la table n'existe pas encore, on la crée liée aux séries
        cur.execute('''CREATE TABLE IF NOT EXISTS episodes (
            id SERIAL PRIMARY KEY,
            series_id INTEGER REFERENCES series(id) ON DELETE CASCADE,
            saison INTEGER,
            episode INTEGER,
            lien TEXT,
            UNIQUE(series_id, saison, episode))''')
    else:
        # Migration : si 'film_id' existe encore dans 'episodes', on migre vers 'series_id'
        if 'film_id' in episodes_cols and 'series_id' not in episodes_cols:
            print("DATABASE MIGRATION: Copie des séries vers la nouvelle table...")
            
            # Ajouter la colonne series_id temporairement
            cur.execute("ALTER TABLE episodes ADD COLUMN IF NOT EXISTS series_id INTEGER REFERENCES series(id) ON DELETE CASCADE")
            
            # Récupérer les anciennes séries de la table films
            cur.execute("SELECT id, titre, affiche, description, status, categorie, tmdb_id FROM films WHERE media_type = 'tv'")
            old_series = cur.fetchall()
            
            for s_id, titre, affiche, desc, status, cat, tmdb_id in old_series:
                # Insérer la série dans sa table dédiée
                cur.execute(
                    "INSERT INTO series (titre, affiche, description, status, categorie, tmdb_id) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                    (titre, affiche, desc, status, cat, tmdb_id)
                )
                new_series_id = cur.fetchone()[0]
                
                # Mettre à jour les épisodes associés
                cur.execute("UPDATE episodes SET series_id = %s WHERE film_id = %s", (new_series_id, s_id))
                
            # Supprimer les anciennes séries de la table films
            cur.execute("DELETE FROM films WHERE media_type = 'tv'")
            
            # Supprimer l'ancienne colonne film_id (qui supprime la contrainte UNIQUE associée)
            cur.execute("ALTER TABLE episodes DROP COLUMN film_id")
            
            # Recréer la contrainte UNIQUE sur series_id, saison, episode
            cur.execute("ALTER TABLE episodes ADD CONSTRAINT episodes_series_id_saison_episode_key UNIQUE(series_id, saison, episode)")
            print("DATABASE MIGRATION: Migration complétée avec succès !")
            
    conn.commit()
    cur.close()
    conn.close()

@app.route('/api/episodes/<int:series_id>')
def api_episodes(series_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT saison, episode, lien FROM episodes WHERE series_id = %s", (series_id,))
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
    cur = conn.cursor(cursor_factory=DictCursor)
    
    tous_les_medias = []
    if filter_type == 'movie':
        cur.execute("SELECT *, 'movie' AS media_type FROM films WHERE status = 'approved' ORDER BY id DESC")
        tous_les_medias = [dict(r) for r in cur.fetchall()]
    elif filter_type == 'tv':
        cur.execute("SELECT *, 'tv' AS media_type FROM series WHERE status = 'approved' ORDER BY id DESC")
        tous_les_medias = [dict(r) for r in cur.fetchall()]
    else:
        cur.execute("SELECT *, 'movie' AS media_type FROM films WHERE status = 'approved' ORDER BY id DESC")
        films = [dict(r) for r in cur.fetchall()]
        cur.execute("SELECT *, 'tv' AS media_type FROM series WHERE status = 'approved' ORDER BY id DESC")
        series = [dict(r) for r in cur.fetchall()]
        tous_les_medias = films + series
        # Trier pour afficher les plus récents en premier
        tous_les_medias.sort(key=lambda x: x['id'], reverse=True)
        
    cur.close()
    conn.close()
    
    films_par_categorie = {}
    for film in tous_les_medias:
        cat = film['categorie'] if film['categorie'] else "Autre"
        if cat not in films_par_categorie:
            films_par_categorie[cat] = []
        films_par_categorie[cat].append(film)
        
    return render_template('index.html', catalogue_categories=films_par_categorie)

@app.route('/admin_ajouter', methods=['GET', 'POST'])
def admin_ajouter():
    # 1. Gestion de l'affichage du formulaire (GET)
    if request.method == 'GET':
        return render_template('admin.html')

    # 2. Traitement de l'envoi du formulaire (POST)
    try:
        # Récupération des données du formulaire
        titre = request.form.get('titre')
        # Si 'type' et 'affiche' sont absents du HTML, on leur donne une valeur par défaut
        media_type = request.form.get('type', 'movie') 
        affiche_url = request.form.get('affiche', '') 
        user = session.get('username', 'Utilisateur')

        # Insertion en base de données
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO suggestions (titre, type, affiche, utilisateur) VALUES (%s, %s, %s, %s)",
            (titre, media_type, affiche_url, user)
        )
        conn.commit()
        cur.close()
        conn.close()

        # Envoi de la notification Discord
        # On utilise le nom de service 'bot_discord' défini dans ton docker-compose
        envoyer_notification_discord(titre, media_type, user, affiche_url)

        flash(f"✅ Merci ! La suggestion pour {titre} a été ajoutée.")
        return redirect(url_for('admin_ajouter'))

    except Exception as e:
        print(f"DEBUG: Erreur dans admin_ajouter : {e}")
        flash("❌ Une erreur est survenue lors de l'ajout.")
        return redirect(url_for('admin_ajouter'))

@app.route('/admin_manuel', methods=['GET', 'POST'])
def admin_manuel():
    current_user = session.get('user', '').lower()
    admins_lower = [a.lower() for a in ADMINS]

    if 'user' not in session or current_user not in admins_lower:
        flash(f"Accès refusé pour {session.get('user')}.")
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        titre = request.form.get('titre')
        lien = request.form.get('lien')
        
        titre_propre = titre.replace(" :", ":").strip()
        params = {"api_key": TMDB_API_KEY, "query": titre_propre, "language": "fr-FR"}
        
        try:
            response = requests.get("https://api.themoviedb.org/3/search/multi", params=params).json()
            results = [r for r in response.get('results', []) if r.get('media_type') in ['movie', 'tv']]
            if results:
                film = results[0]
                media_type = film['media_type']
                titre_clean = film.get('title') or film.get('name')
                categorie_auto = recuperer_categorie_film(titre_clean, media_type)

                conn = get_db_connection()
                cur = conn.cursor()
                if media_type == 'tv':
                    cur.execute("INSERT INTO series (titre, affiche, description, status, categorie, tmdb_id) VALUES (%s, %s, %s, 'approved', %s, %s)", 
                                 (titre_clean, f"https://image.tmdb.org/t/p/w500{film['poster_path']}", film.get('overview', ''), categorie_auto, film['id']))
                else:
                    cur.execute("INSERT INTO films (titre, affiche, lien, description, status, categorie, tmdb_id, media_type) VALUES (%s, %s, %s, %s, 'approved', %s, %s, 'movie')", 
                                 (titre_clean, f"https://image.tmdb.org/t/p/w500{film['poster_path']}", lien, film.get('overview', ''), categorie_auto, film['id']))
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


@app.route('/admin_approuver/<string:media_type>/<int:media_id>', methods=['GET', 'POST'])
def admin_approuver_request(media_type, media_id):
    if 'user' not in session or not is_admin():
        return "Accès refusé", 403

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)

    table = 'series' if media_type == 'tv' else 'films'
    cur.execute(f"SELECT * FROM {table} WHERE id = %s", (media_id,))
    film = cur.fetchone()

    if request.method == 'POST':
        lien_final = request.form.get('lien_final')
        
        if film:
            categorie_auto = recuperer_categorie_film(film['titre'], media_type)
            if media_type == 'tv':
                cur.execute(
                    "UPDATE series SET status = 'approved', categorie = %s WHERE id = %s",
                    (categorie_auto, media_id)
                )
            else:
                cur.execute(
                    "UPDATE films SET status = 'approved', lien = %s, categorie = %s WHERE id = %s",
                    (lien_final, categorie_auto, media_id)
                )
            conn.commit()

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

    return render_template('approve_form.html', movie_id=media_id, tmdb_id=film['tmdb_id'], media_type=media_type)
 
@app.route('/admin_supprimer/<string:media_type>/<int:media_id>', methods=['POST'])
def admin_supprimer(media_type, media_id):
    if 'user' not in session or not is_admin():
        flash("🔴 Accès refusé.")
        return redirect(url_for('index'))
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        table = 'series' if media_type == 'tv' else 'films'
        cur.execute(f"DELETE FROM {table} WHERE id = %s", (media_id,))
        conn.commit()
        cur.close()
        conn.close()
        flash("🗑️ Le média a été supprimé.")
    except Exception as e:
        flash(f"Erreur : {e}")
    return redirect(url_for('index'))

@app.route('/movie/<int:movie_id>')
def voir_film(movie_id):
    if 'user' not in session: 
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT *, 'movie' AS media_type FROM films WHERE id = %s", (movie_id,))
    film = cur.fetchone()
    cur.close()
    conn.close()
    
    if film:
        return render_template('movie_detail.html', film=dict(film))
    else:
        flash("Film introuvable.")
        return redirect(url_for('index'))

@app.route('/series/<int:series_id>')
def voir_series(series_id):
    if 'user' not in session: 
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT *, 'tv' AS media_type FROM series WHERE id = %s", (series_id,))
    series = cur.fetchone()
    cur.close()
    conn.close()
    
    if series:
        return render_template('series_detail.html', film=dict(series))
    else:
        flash("Série introuvable.")
        return redirect(url_for('index'))

@app.route('/api/discord_suggerer', methods=['POST'])
def api_discord_suggerer():
    data = request.json
    titre_film = data.get('titre')
    user = data.get('user')
    
    params = {"api_key": TMDB_API_KEY, "query": titre_film, "language": "fr-FR"}
    response = requests.get("https://api.themoviedb.org/3/search/multi", params=params).json()
    results = [r for r in response.get('results', []) if r.get('media_type') in ['movie', 'tv']]
    
    if results:
        film = results[0]
        media_type = film['media_type']
        titre = film.get('title') or film.get('name')
        categorie_auto = recuperer_categorie_film(titre, media_type)
        
        conn = get_db_connection()
        cur = conn.cursor()
        if media_type == 'tv':
            cur.execute("""
                INSERT INTO series (titre, affiche, description, status, categorie, tmdb_id)
                VALUES (%s, %s, %s, 'pending', %s, %s) RETURNING id
            """, (titre, f"https://image.tmdb.org/t/p/w500{film['poster_path']}", film.get('overview', ''), categorie_auto, film['id']))
        else:
            cur.execute("""
                INSERT INTO films (titre, affiche, lien, description, status, categorie, tmdb_id, media_type)
                VALUES (%s, %s, 'auto', %s, 'pending', %s, %s, 'movie') RETURNING id
            """, (titre, f"https://image.tmdb.org/t/p/w500{film['poster_path']}", "auto", film.get('overview', ''), categorie_auto, film['id']))
        film_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
        
        # Appel à la nouvelle fonction générique
        envoyer_notification_discord(titre, media_type, user, f"https://image.tmdb.org/t/p/w500{film['poster_path']}", film_id)
        
        return jsonify({"status": "success", "message": "Suggestion ajoutée"}), 200
    
    return jsonify({"status": "error", "message": "Film introuvable"}), 404

@app.route('/admin/dashboard', methods=['GET', 'POST'])
def admin_dashboard():
    if not is_admin(): return "Accès refusé", 403
    
    results = None
    if request.method == 'POST' and 'search_titre' in request.form:
        titre = request.form.get('search_titre')
        params = {"api_key": TMDB_API_KEY, "query": titre, "language": "fr-FR"}
        resp = requests.get("https://api.themoviedb.org/3/search/multi", params=params).json()
        results = [r for r in resp.get('results', []) 
                   if r.get('media_type') in ['movie', 'tv'] and r.get('poster_path')][:3]

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=DictCursor)
    cur.execute("SELECT *, 'movie' AS media_type FROM films WHERE status = 'pending' ORDER BY id DESC")
    pending_films = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT *, 'tv' AS media_type FROM series WHERE status = 'pending' ORDER BY id DESC")
    pending_series = [dict(r) for r in cur.fetchall()]
    films_attente = pending_films + pending_series
    films_attente.sort(key=lambda x: x['id'], reverse=True)
    cur.close()
    conn.close()
    
    return render_template('admin_dashboard.html', films=films_attente, search_results=results)

@app.route('/admin_valider_choix', methods=['POST'])
def admin_valider_choix():
    tmdb_id = request.form.get('tmdb_id')
    media_type = request.form.get('media_type')
    
    url = f"https://api.themoviedb.org/3/{media_type}/{tmdb_id}?api_key={TMDB_API_KEY}&language=fr-FR"
    film = requests.get(url).json()
    titre = film.get('title') or film.get('name')
    cat = recuperer_categorie_film(titre, media_type)
    
    conn = get_db_connection()
    cur = conn.cursor()
    if media_type == 'tv':
        cur.execute("""
            INSERT INTO series (titre, affiche, description, status, categorie, tmdb_id)
            VALUES (%s, %s, %s, 'pending', %s, %s)
        """, (titre, f"https://image.tmdb.org/t/p/w500{film['poster_path']}", film.get('overview', ''), cat, tmdb_id))
    else:
        cur.execute("""
            INSERT INTO films (titre, affiche, lien, description, status, categorie, tmdb_id, media_type)
            VALUES (%s, %s, 'pending', %s, 'pending', %s, %s, 'movie')
        """, (titre, f"https://image.tmdb.org/t/p/w500{film['poster_path']}", film.get('overview', ''), cat, tmdb_id))
    conn.commit()
    cur.close()
    conn.close()
    
    flash(f"✅ {titre} ajouté aux suggestions !")
    return redirect(url_for('admin_dashboard'))


import subprocess
import threading
import time

@app.route('/git-webhook', methods=['POST'])
def git_webhook():
    token = request.args.get('token')
    if token != "moviesforyousecret":
        return jsonify({"status": "error", "message": "Token invalide"}), 401
        
    try:
        repo_dir = os.path.dirname(os.path.abspath(__file__))
        result = subprocess.run(["git", "pull", "origin", "main"], cwd=repo_dir, capture_output=True, text=True)
        
        if result.returncode == 0:
            def restart():
                time.sleep(2)
                print("WEBHOOK: Arrêt du conteneur pour redémarrage automatique...")
                os._exit(0)
            threading.Thread(target=restart).start()
            return jsonify({"status": "success", "message": "Git pull réussi ! Redémarrage du conteneur en cours..."}), 200
        else:
            return jsonify({"status": "error", "message": f"Git pull a échoué : {result.stderr}"}), 500
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "La commande 'git' n'est pas installée dans le conteneur Docker."}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)