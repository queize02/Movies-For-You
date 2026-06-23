from playwright.sync_api import sync_playwright
import time
import psycopg2
import sys

# URL de connexion à la base de données (identique à app.py)
DB_URL = 'postgresql://admin:02082008@localhost:5432/neondb'
def extract_episode(page, url):
    print(f"\nChargement de : {url} ...")
    try:
        page.goto(url, timeout=60000)
        
        print("⏳ Étape 1 : Recherche du bouton publicitaire...")
        try:
            bouton_pub = page.locator("button:has-text('Voir une publicité')")
            bouton_pub.wait_for(timeout=5000)
            print("👉 Bouton trouvé ! Clic...")
            bouton_pub.click(force=True)
            time.sleep(2)
        except Exception:
            pass

        print("⏳ Étape 2 : Recherche du bouton Lecture...")
        try:
            bouton_lecture = page.locator("button:has-text('Lecture')")
            bouton_lecture.wait_for(timeout=5000)
            print("👉 Bouton 'Lecture' trouvé ! Clic...")
            bouton_lecture.click(force=True)
            time.sleep(2)
        except Exception:
            pass

        print("⏳ Étape 3 : Attente de l'iframe de la vidéo...")
        try:
            page.wait_for_selector("iframe", timeout=15000)
        except:
            pass
        
        iframe_element = page.query_selector("iframe")
        if iframe_element:
            src = iframe_element.get_attribute("src")
            if src:
                print(f"✅ Iframe extraite avec succès : {src}")
                return src
        print("❌ Aucune iframe trouvée.")
        return None
            
    except Exception as e:
        print(f"❌ Erreur lors de l'extraction : {e}")
        return None

def save_to_db(series_id, saison, episode, lien):
    if not lien:
        return
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO episodes (series_id, saison, episode, lien) 
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (series_id, saison, episode) 
            DO UPDATE SET lien = EXCLUDED.lien
        """, (series_id, saison, episode, lien))
        conn.commit()
        cur.close()
        conn.close()
        print(f"💾 Sauvegardé dans la base de données (S{saison}E{episode}).")
    except Exception as e:
        print(f"❌ Erreur BDD : {e}")

if __name__ == "__main__":
    print("="*60)
    print("🤖 EXTRACTEUR AUTOMATIQUE DE SAISONS MOVIX")
    print("="*60)
    
    base_url = input("👉 Collez le lien de base Movix (ex: https://movix.golf/watch/tv/... ) : ").strip()
    if not base_url:
        print("Annulé.")
        sys.exit()
        
    saison = int(input("👉 Numéro de la saison à extraire (ex: 1) : ").strip())
    nb_episodes = int(input("👉 Nombre d'épisodes dans cette saison (ex: 8) : ").strip())
    series_id = int(input("👉 ID de la série sur VOTRE site (le numéro dans l'URL de votre site) : ").strip())
    
    # Nettoyage de l'URL si elle contient déjà /s/1/e/1
    if "/s/" in base_url:
        base_url = base_url.split("/s/")[0]
        
    print("\n🚀 Démarrage de l'extraction...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()
        page.on("popup", lambda popup: popup.close())
        
        for ep in range(1, nb_episodes + 1):
            url_episode = f"{base_url}/s/{saison}/e/{ep}"
            print(f"\n--- TRAITEMENT ÉPISODE {ep}/{nb_episodes} ---")
            iframe_src = extract_episode(page, url_episode)
            save_to_db(series_id, saison, ep, iframe_src)
            
        browser.close()
        
    print("\n✨ Extraction de la saison terminée avec succès !")
