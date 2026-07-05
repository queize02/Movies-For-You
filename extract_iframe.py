from playwright.sync_api import sync_playwright
import time
import os
import psycopg2

import datetime
from extract_fs import extraction_logs

def log(msg):
    print(msg)
    extraction_logs.append(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")

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
        log(f"✅ Succès : Iframe {iframe_src} enregistrée en BDD pour l'ID {film_id}.")
    except Exception as e:
        log(f"❌ Erreur BDD : {e}")

def extraire_et_sauvegarder(url, film_id):
    extraction_logs.clear()
    log('='*60)
    log('🤖 EXTRACTEUR DE FILMS')
    log('='*60)
    extension_path = os.path.abspath("ublock_extension") # Ton dossier d'extension

    with sync_playwright() as p:
        args = [f'--load-extension={extension_path}', f'--disable-extensions-except={extension_path}']
        
        browser = p.chromium.launch_persistent_context(
            user_data_dir="./user_data",
            headless=True,
            args=args,
            viewport={'width': 1280, 'height': 720}
        )
        
        page = browser.pages[0]
        page.goto(url, wait_until="networkidle")

        # 1. Préparation (Vidzy)
        page.locator("button.player-option[data-player='ViDZY']").click(force=True)
        time.sleep(2)

        # 2. Clics (Orange puis Rouge)
       # 2. Clics (Orange puis Rouge)
        page.mouse.click(640, 360) # Orange
        time.sleep(3)
        
        # --- MODIFICATION ICI ---
        log("👉 Tentative de clic sur triangle ROUGE (si présent)...")
        try:
            frame = page.frame_locator("iframe#video-iframe")
            bouton_rouge = frame.locator(".vjs-big-play-button, .play-button").first
            
            # On vérifie la visibilité avant de cliquer
            if bouton_rouge.is_visible():
                bouton_rouge.click(force=True)
                log("✅ Clic sur triangle rouge effectué.")
            else:
                log("ℹ️ Le triangle rouge est déjà masqué (le film est peut-être déjà lancé).")
        except Exception:
            log("ℹ️ Bouton rouge indisponible, passage à l'extraction.")
        # ------------------------

        time.sleep(2)
        # 3. Extraction et Sauvegarde — logique flexible
        src = None
        
        # Tentative 1 : sélecteur classique iframe#video-iframe
        try:
            src = page.locator("iframe#video-iframe").get_attribute("src", timeout=5000)
            if src:
                log(f"✅ Iframe trouvée via #video-iframe : {src[:80]}...")
        except:
            pass
        
        # Tentative 2 : toutes les iframes de la page
        if not src:
            log("🔍 Recherche de n'importe quelle iframe sur la page...")
            try:
                iframes = page.locator("iframe").all()
                for iframe in iframes:
                    candidate = iframe.get_attribute("src")
                    if candidate and candidate.startswith("http") and "about:blank" not in candidate:
                        src = candidate
                        log(f"✅ Iframe trouvée : {src[:80]}...")
                        break
            except Exception as e:
                log(f"❌ Erreur lors de la recherche des iframes : {e}")
        
        # Tentative 3 : attendre 5s de plus et réessayer
        if not src:
            log("⏳ Attente supplémentaire de 5s et nouvelle tentative...")
            time.sleep(5)
            try:
                iframes = page.locator("iframe").all()
                for iframe in iframes:
                    candidate = iframe.get_attribute("src")
                    if candidate and candidate.startswith("http") and "about:blank" not in candidate:
                        src = candidate
                        log(f"✅ Iframe trouvée après attente : {src[:80]}...")
                        break
            except Exception as e:
                log(f"❌ Erreur : {e}")
        
        if src:
            save_iframe_url(film_id, src)
        else:
            log("❌ Aucune iframe valide trouvée sur cette page.")

        # 4. Fermeture
        log("👋 Fermeture de la page.")
        browser.close()

if __name__ == "__main__":
    url_source = input("URL : ").strip()
    id_film = input("ID : ").strip()
    extraire_et_sauvegarder(url_source, id_film)