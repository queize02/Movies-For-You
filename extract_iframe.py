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
        
        # 2. Cliquer sur VIDZY (pour obtenir le vrai lecteur et pas fsurl.lol)
        log("📺 Sélection du lecteur VIDZY / UQLOAD...")
        try:
            vidzy_selectors = [
                "button.player-option[data-player='ViDZY']",
                "button[data-player='ViDZY']",
                "a[data-player='ViDZY']",
                "button.player-option[data-player='UQLOAD']",
            ]
            for sel in vidzy_selectors:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=2000):
                        btn.click(force=True)
                        log(f"✅ Lecteur cliqué via '{sel}'")
                        break
                except:
                    continue
        except Exception as e:
            log(f"⚠️ Erreur clic lecteur alternatif : {e}")

        time.sleep(3)

        # 3. Extraction et Sauvegarde
        src = None
        
        domaines_exclus = [
            "youtube.com", "youtu.be", "vimeo.com",
            "doubleclick.net", "google.com", "googletagmanager.com",
            "facebook.com", "twitter.com", "instagram.com",
            "fsurl.lol", "sso.php"
        ]
        
        def est_valide(url):
            if not url or not url.startswith("http"):
                return False
            if "about:blank" in url:
                return False
            for domaine in domaines_exclus:
                if domaine in url:
                    return False
            return True
        
        log("🔍 Recherche d'une iframe de streaming sur la page...")
        # Tentative : extraction du src de l'iframe
        for _ in range(15):
            try:
                # 1. Chercher id='seriePlayer' ou 'video-iframe'
                src_candidate = page.evaluate('''
                    () => {
                        let iframe = document.getElementById('seriePlayer') || document.getElementById('video-iframe');
                        if (iframe && iframe.src) return iframe.src;
                        return null;
                    }
                ''')
                if est_valide(src_candidate):
                    src = src_candidate
                    log(f"✅ Iframe trouvée par ID : {src[:80]}...")
                    break
                
                # 2. Sinon, chercher toutes les iframes
                iframes = page.locator("iframe").all()
                for iframe in iframes:
                    candidate = iframe.get_attribute("src")
                    if est_valide(candidate):
                        src = candidate
                        break
                if src:
                    log(f"✅ Iframe trouvée : {src[:80]}...")
                    break
            except:
                pass
            time.sleep(1)
            
        if src:
            save_iframe_url(film_id, src)
        else:
            log("❌ Aucune iframe de streaming trouvée sur cette page.")

        log("👋 Fermeture de la page.")
        browser.close()

if __name__ == "__main__":
    url_source = input("URL : ").strip()
    id_film = input("ID : ").strip()
    extraire_et_sauvegarder(url_source, id_film)