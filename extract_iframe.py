from playwright.sync_api import sync_playwright
import time
import os
import psycopg2

# Configuration BDD (à ajuster si besoin)
DB_URL = 'postgresql://admin:02082008@192.168.1.13:5432/neondb'

def save_iframe_url(film_id, iframe_src):
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        # Mise à jour avec le lien récupéré
        cur.execute("UPDATE films SET lien = %s, status = 'approved' WHERE id = %s", (iframe_src, film_id))
        conn.commit()
        cur.close()
        conn.close()
        print(f"✅ Succès : Iframe {iframe_src} enregistrée en BDD pour l'ID {film_id}.")
    except Exception as e:
        print(f"❌ Erreur BDD : {e}")

def extraire_et_sauvegarder(url, film_id):
    extension_path = os.path.abspath("ublock_extension") # Ton dossier d'extension

    with sync_playwright() as p:
        args = [f'--load-extension={extension_path}', f'--disable-extensions-except={extension_path}']
        
        browser = p.chromium.launch_persistent_context(
            user_data_dir="./user_data",
            headless=False,
            args=args,
            viewport={'width': 1280, 'height': 720}
        )
        
        page = browser.pages[0]
        page.goto(url, wait_until="networkidle")

        # 1. Préparation (Vidzy)
        page.locator("button.player-option[data-player='ViDZY']").click(force=True)
        time.sleep(3)

        # 2. Clics (Orange puis Rouge)
       # 2. Clics (Orange puis Rouge)
        page.mouse.click(640, 360) # Orange
        time.sleep(5)
        
        # --- MODIFICATION ICI ---
        print("👉 Tentative de clic sur triangle ROUGE (si présent)...")
        try:
            frame = page.frame_locator("iframe#video-iframe")
            bouton_rouge = frame.locator(".vjs-big-play-button, .play-button").first
            
            # On vérifie la visibilité avant de cliquer
            if bouton_rouge.is_visible():
                bouton_rouge.click(force=True)
                print("✅ Clic sur triangle rouge effectué.")
            else:
                print("ℹ️ Le triangle rouge est déjà masqué (le film est peut-être déjà lancé).")
        except Exception:
            print("ℹ️ Bouton rouge indisponible, passage à l'extraction.")
        # ------------------------

        time.sleep(3)
        # 3. Extraction et Sauvegarde
        src = page.locator("iframe#video-iframe").get_attribute("src")
        if src:
            save_iframe_url(film_id, src)
        else:
            print("⚠️ Impossible d'extraire le src.")

        # 4. Fermeture
        print("👋 Fermeture de la page.")
        browser.close()

if __name__ == "__main__":
    url_source = input("URL : ").strip()
    id_film = input("ID : ").strip()
    extraire_et_sauvegarder(url_source, id_film)