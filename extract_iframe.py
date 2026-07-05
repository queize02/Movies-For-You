from playwright.sync_api import sync_playwright
import time
import os
import psycopg2

import datetime
from extract_fs import extraction_logs

def log(msg):
    print(msg)
    extraction_logs.append(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}")

def prendre_screenshot(page):
    try:
        os.makedirs("static", exist_ok=True)
        page.screenshot(path="static/extraction_screenshot.png")
    except Exception as e:
        pass

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
        log(f"✅ Succès : Iframe {iframe_src[:60]}... enregistrée en BDD pour l'ID {film_id}.")
    except Exception as e:
        log(f"❌ Erreur BDD : {e}")

def extraire_et_sauvegarder(url, film_id):
    extraction_logs.clear()
    log('='*60)
    log('🤖 EXTRACTEUR DE FILMS')
    log('='*60)
    
    extension_path = os.path.abspath("ublock_extension")
    use_extension = os.path.isdir(extension_path)

    with sync_playwright() as p:
        if use_extension:
            log(f"🛡️ uBlock Origin détecté, chargement de l'extension...")
            browser = p.chromium.launch_persistent_context(
                user_data_dir="./user_data",
                headless=True,
                args=[
                    f'--load-extension={extension_path}',
                    f'--disable-extensions-except={extension_path}'
                ],
                viewport={'width': 1280, 'height': 720}
            )
            page = browser.pages[0]
        else:
            log(f"⚠️ Pas d'extension uBlock trouvée.")
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = context.new_page()
            
        # Fermer automatiquement les pop-ups (nouveaux onglets)
        ctx = browser if use_extension else context
        ctx.on("page", lambda new_page: new_page.close())
        
        log(f"🌐 Chargement de la page...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        prendre_screenshot(page)

        # 1. Cliquer sur le triangle ORANGE (le couvre-feu de la vidéo)
        log("🟠 Clic sur le triangle orange pour charger le lecteur...")
        try:
            selectors_orange = [
                ".play-btn", ".player-overlay", ".vjs-big-play-button",
                "button[class*='play']", ".film-player .play",
                "a[class*='play']", "#player .play",
            ]
            clique = False
            for sel in selectors_orange:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=2000):
                        btn.click(force=True)
                        log(f"✅ Triangle orange cliqué via '{sel}'")
                        clique = True
                        break
                except:
                    continue
            
            if not clique:
                log("⚠️ Sélecteur orange non trouvé, clic au centre de la page...")
                page.mouse.click(512, 300)
        except Exception as e:
            log(f"⚠️ Erreur clic orange : {e}")
        
        time.sleep(3)
        prendre_screenshot(page)

        # 2. Extraction et Sauvegarde (recherche récursive des iframes imbriquées)
        src = None
        
        # Liste des hébergeurs de vidéos valides (on cherche ces mots-clés dans les URLs des frames)
        players_valides = [
            "vidzy", "uqload", "voe", "dood", "filmmoon", "hqq", "netu", 
            "fembed", "vidoza", "streamtape", "mixdrop"
        ]
        
        log("🔍 Recherche du lecteur de streaming (vidzy, uqload, voe...) dans les frames de la page...")
        
        # On va chercher pendant 15 secondes max si l'iframe du lecteur apparaît
        for attempt in range(15):
            try:
                # page.frames contient toutes les frames de la page, y compris les iframes imbriquées !
                for frame in page.frames:
                    frame_url = frame.url
                    if not frame_url or frame_url == "about:blank":
                        continue
                    
                    # On vérifie si l'URL de cette frame appartient à un hébergeur de vidéo connu
                    for player in players_valides:
                        if player in frame_url.lower():
                            src = frame_url
                            log(f"✅ Lecteur de streaming détecté ({player}) : {src[:80]}...")
                            break
                    if src:
                        break
            except Exception as e:
                pass
                
            if src:
                break
            time.sleep(1)
            
        if src:
            save_iframe_url(film_id, src)
        else:
            log("❌ Aucun lecteur de streaming valide (vidzy, uqload, voe...) trouvé sur la page.")

        prendre_screenshot(page)
        log("👋 Fermeture de la page.")
        browser.close()

if __name__ == "__main__":
    url_source = input("URL : ").strip()
    id_film = input("ID : ").strip()
    extraire_et_sauvegarder(url_source, id_film)