import sqlite3
import os

# On définit le chemin vers ta base de données
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'films.db')

def update():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        # Cette ligne ajoute la colonne 'description' à ta table 'films'
        cursor.execute("ALTER TABLE films ADD COLUMN description TEXT")
        print("✅ Colonne 'description' ajoutée avec succès !")
    except sqlite3.OperationalError:
        print("⚠️ La colonne existe peut-être déjà.")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    update()