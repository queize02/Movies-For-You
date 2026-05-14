from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
import requests
import psycopg2
from psycopg2.extras import DictCursor
import hashlib
import os

app = Flask(__name__)
app.secret_key = "user_securited"

ADMINS = ["wqueize_", "tenoste"]

def is_admin():
    if 'user' not in session:
        return False
    return session['user'].lower() in ADMINS

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
TMDB_API_KEY = "1dfef7dd68067ec8b05e87b494b9a7f4"

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
            # On retourne la page avec success=True pour afficher ton animation verte actuelle
            return render_template('login.html', success=True)
        else:
            # --- AJOUT ICI : Le message d'erreur ---
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
        lien_temporaire = "À définir par l'admin"
        
        params = {"api_key": TMDB_API_KEY, "query": titre_film, "language": "fr-FR"}
        try:
            response = requests.get("https://api.themoviedb.org/3/search/movie", params=params, timeout=5).json()
            
            # 1. On vérifie si TMDB a trouvé quelque chose
            if response.get('results'):
                film = response['results'][0]
                
                # Log de succès dans la console Render
                print(f"🎬 Film trouvé sur TMDB : {film['title']}")

                # 2. On enregistre dans la base de données
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute("INSERT INTO films (titre, affiche, lien, description, status) VALUES (%s, %s, %s, %s, 'pending') RETURNING id", 
                             (film['title'], f"https://image.tmdb.org/t/p/w500{film['poster_path']}", lien_temporaire, film['overview']))
                film_id = cur.fetchone()[0]
                conn.commit()
                cur.close()
                conn.close()

                # 3. On envoie au BOT Discord
                data_pour_bot = {
                    "titre": film['title'],
                    "user": session['user'],
                    "affiche": f"https://image.tmdb.org/t/p/w500{film['poster_path']}",
                    "film_id": film_id
                }
                
                try:
                    render_url = "https://bot-js-l8hi.onrender.com/nouvelle-suggestion"
                    requests.post(render_url, json=data_pour_bot, timeout=20)
                except Exception as e:
                    print(f"Erreur d'envoi au Bot : {e}")

                flash("Merci ! Ta suggestion a été envoyée.")
                return render_template('admin.html')
            else:
                # --- C'EST ICI QUE ÇA S'AFFICHE SI LE NOM EST MAUVAIS ---
                print(f"❌ Aucun film trouvé pour : {titre_film}")
                flash("Film introuvable sur TMDB. Vérifie l'orthographe !")

        except Exception as e:
            print(f"Erreur générale : {e}")
            flash("Une erreur est survenue lors de l'ajout.")
            
    return render_template('admin.html')

@app.route('/admin_manuel', methods=['GET', 'POST'])
def admin_manuel():
    # On récupère le pseudo en minuscules
    current_user = session.get('user', '').lower()
    # On met aussi la liste des admins en minuscules pour comparer
    admins_lower = [a.lower() for a in ADMINS]

    if 'user' not in session or current_user not in admins_lower:
        # Ajoute ce flash pour voir si c'est bien un problème de droit
        flash(f"Accès refusé pour {session.get('user')}. Tu n'es pas dans la liste admin.")
        return redirect(url_for('index'))
    
    # ... reste du code
    # ... reste du code (if request.method == 'POST' etc.)
    if request.method == 'POST':
        titre = request.form.get('titre')
        lien = request.form.get('lien')
        
        # On récupère automatiquement l'affiche sur TMDB
        params = {"api_key": TMDB_API_KEY, "query": titre, "language": "fr-FR"}
        try:
            response = requests.get("https://api.themoviedb.org/3/search/movie", params=params).json()
            if response.get('results'):
                film = response['results'][0]
                conn = get_db_connection()
                cur = conn.cursor()
                # On insère DIRECTEMENT en 'approved'
                cur.execute("INSERT INTO films (titre, affiche, lien, description, status) VALUES (%s, %s, %s, %s, 'approved')", 
                             (film['title'], f"https://image.tmdb.org/t/p/w500{film['poster_path']}", lien, film['overview']))
                conn.commit()
                cur.close()
                conn.close()
                flash(f"✅ Film '{film['title']}' ajouté directement !")
                return redirect(url_for('index'))
        except Exception as e:
            flash(f"Erreur : {e}")
            
    # Formulaire simple pour l'admin
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
    if not is_admin():
        return "Accès interdit", 403
    # ... reste du code inchangé ...
    
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

@app.route('/movie/<int:movie_id>')
def movie_detail(movie_id):
    if 'user' not in session: 
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM films WHERE id = %s", (movie_id,))
    film = cur.fetchone()
    cur.close()
    conn.close()
    
    if film:
        # Assure-toi d'avoir un fichier movie_detail.html dans ton dossier templates
        return render_template('movie_detail.html', film=film)
    else:
        flash("Film introuvable.")
        return redirect(url_for('index'))


if __name__ == '__main__':
    with app.app_context():
        init_db()
    app.run(debug=True)