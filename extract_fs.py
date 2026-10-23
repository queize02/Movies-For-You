import os
import sys
import time
import re
import json
import requests
import psycopg2
from playwright.sync_api import sync_playwright

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
if hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

TMDB_API_KEY = "9b9c266753e29e36cd97efb6b42e52eb"
PLAYERS_VALIDES = ["vidzy", "uqload", "voe", "dood", "filmmoon", "hqq", "netu", "fembed", "vidoza", "streamtape", "mixdrop"]

def get_db_conn():
    """Établit la connexion à la base de données (locale ou distante)"""
    urls = [
        os.environ.get("DATABASE_URL"),
        "postgresql://root@127.0.0.1:26257/moviesforyou?sslmode=disable",
        "postgresql://root@100.96.143.70:26257,100.77.218.85:26257/moviesforyou?sslmode=disable"
    ]
    for u in urls:
        if not u:
            continue
        try:
            return psycopg2.connect(u)
        except Exception:
            pass
    raise Exception("Impossible de se connecter à CockroachDB (127.0.0.1 / cluster)")


def prendre_screenshot(page):
    """Met à jour l'aperçu en direct pour le dashboard administrateur"""
    try:
        os.makedirs("static", exist_ok=True)
        page.screenshot(path="static/extraction_screenshot.png")
    except Exception:
        pass


def lancer_extraction(url, type_media, item_id, saison=1, nb_eps=None, logger=None):
    """Fonction principale universelle pour extraire films et séries sans doublons"""
    def log(message):
        try:
            print(f"[{time.strftime('%H:%M:%S')}] {message}")
        except Exception:
            try:
                print(f"[{time.strftime('%H:%M:%S')}] {message.encode('ascii', errors='replace').decode('ascii')}")
            except Exception:
                pass
        if logger:
            try:
                logger(f"[{time.strftime('%H:%M:%S')}] {message}")
            except Exception:
                pass

    log(f"🎯 Lancement effectif -> ID: {item_id} | Type: {type_media} | Saison: {saison} | URL: {url}")

    extension_path = os.path.abspath("ublock_extension")
    use_extension = os.path.isdir(extension_path)

    if type_media in ["film", "movie"]:
        extraire_film(item_id, url, use_extension, extension_path, log)
    else:
        extraire_serie(item_id, url, saison, nb_eps, use_extension, extension_path, log)


def setup_browser(p, use_extension, extension_path, log):
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    if use_extension:
        log("🛡️ uBlock Origin détecté, chargement de l'extension...")
        browser = p.chromium.launch_persistent_context(
            user_data_dir="./user_data",
            headless=True,
            user_agent=ua,
            args=[
                f'--load-extension={extension_path}',
                f'--disable-extensions-except={extension_path}',
                '--autoplay-policy=no-user-gesture-required'
            ],
            viewport={'width': 1280, 'height': 720}
        )
        page = browser.pages[0] if browser.pages else browser.new_page()
        ctx = browser
    else:
        log("⚠️ Pas d'extension uBlock trouvée.")
        browser = p.chromium.launch(
            headless=True,
            args=['--autoplay-policy=no-user-gesture-required']
        )
        ctx = browser.new_context(
            user_agent=ua,
            viewport={'width': 1280, 'height': 720}
        )
        page = ctx.new_page()
    
    # Fermer automatiquement les pop-ups (nouveaux onglets intrusifs)
    ctx.on("page", lambda new_page: new_page.close())
    return browser, ctx, page


def trigger_video_play(page, log):
    log("🟠 Tentative de clic sur le bouton Play...")
    try:
        for click_num in range(1, 4):
            clique = False
            
            selectors_orange = [
                ".play-btn", ".play-icon", ".play-trigger", ".player-overlay",
                "div.play", "a.play", "button.play", ".vjs-big-play-button"
            ]
            for sel in selectors_orange:
                try:
                    btn = page.locator(sel).first
                    if btn.is_visible(timeout=500):
                        btn.click(force=True)
                        log(f"   👉 Clic Play via selector '{sel}'")
                        clique = True
                        break
                except:
                    continue
            
            if not clique:
                player_selector = None
                for sel in ["#player-container", "#main-player", "#player", ".film-player", "#video-player", ".player-container", ".video-js", "iframe"]:
                    try:
                        el = page.locator(sel).first
                        if el.is_visible(timeout=500):
                            player_selector = sel
                            break
                    except:
                        continue
                
                if player_selector:
                    page.locator(player_selector).first.click(force=True)
                    log(f"   🎯 Clic au centre du lecteur '{player_selector}'")
                    clique = True
                
            if not clique:
                page.mouse.click(640, 360)
                log("   ⚠️ Clic absolu au centre de l'écran (640, 360)")
            
            time.sleep(1.5)
    except Exception as e:
        log(f"⚠️ Erreur lors du clic Play : {e}")
    time.sleep(3)


def search_iframe(page, log, seen_iframes=None):
    if seen_iframes is None:
        seen_iframes = set()
        
    log("🔍 Recherche d'un nouveau lecteur de streaming dans les frames...")
    src = None
    for attempt in range(15):
        try:
            for frame in page.frames:
                frame_url = frame.url
                if not frame_url or frame_url == "about:blank": continue
                if "youtube" in frame_url.lower() or "google" in frame_url.lower(): continue
                
                if any(player in frame_url.lower() for player in PLAYERS_VALIDES):
                    # ANTI-DOUBLON: on vérifie qu'on n'a pas déjà extrait cette iframe
                    if frame_url not in seen_iframes:
                        src = frame_url
                        seen_iframes.add(frame_url)
                        log(f"✅ Nouveau Lecteur détecté : {src[:80]}...")
                        return src
        except:
            pass
        time.sleep(1)
    
    log("❌ Aucun lecteur NOUVEAU n'a été trouvé.")
    return None


def extraire_film(film_id, url, use_extension, extension_path, log):
    with sync_playwright() as p:
        browser, ctx, page = setup_browser(p, use_extension, extension_path, log)
        log("🌐 Chargement de la page film...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            prendre_screenshot(page)
            
            trigger_video_play(page, log)
            prendre_screenshot(page)
            flux = search_iframe(page, log)
            
            if flux:
                conn = get_db_conn()
                cur = conn.cursor()
                cur.execute("UPDATE films SET lien = %s WHERE id = %s", (flux, film_id))
                conn.commit()
                cur.close()
                conn.close()
                log(f"✅ Film sauvegardé en BDD : {flux[:60]}...")
            else:
                log("❌ Aucun flux détecté pour ce film.")
                
        except Exception as e:
            log(f"❌ Erreur critique film: {e}")
        finally:
            if hasattr(browser, 'close'):
                browser.close()


def extraire_serie(serie_id, url, saison, nb_eps, use_extension, extension_path, log):
    # Extraction de l'ID d'article dans l'URL (ex: 15106271-lupin-saison-1.html)
    match_news = re.search(r'/(\d+)-', url)
    news_id = match_news.group(1) if match_news else None

    # TMDB ID éventuel
    match_tmdb = re.search(r'/(\d{4,7})-', url)
    tmdb_id = match_tmdb.group(1) if match_tmdb else None

    episodes = None
    if tmdb_id:
        try:
            resp = requests.get(
                f"https://api.themoviedb.org/3/tv/{tmdb_id}/season/{saison}?api_key={TMDB_API_KEY}&language=fr-FR",
                timeout=5
            )
            if resp.status_code == 200:
                episodes = [ep.get("episode_number") for ep in resp.json().get("episodes", [])]
                log(f"📋 TMDB ID {tmdb_id}: {len(episodes)} épisodes identifiés pour la saison {saison}.")
        except Exception:
            pass

    if not episodes:
        nb = int(nb_eps) if nb_eps else 1
        episodes = list(range(1, nb + 1))
        log(f"📋 Mode générique : préparation de {len(episodes)} épisode(s) (Saison {saison}).")

    # Initialisation des épisodes dans la base
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        for ep in episodes:
            cur.execute(
                "INSERT INTO episodes (series_id, saison, episode, lien) VALUES (%s, %s, %s, '') ON CONFLICT DO NOTHING",
                (serie_id, saison, ep)
            )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log(f"⚠️ Erreur d'initialisation en base de données : {e}")

    with sync_playwright() as p:
        browser, ctx, page = setup_browser(p, use_extension, extension_path, log)
        log("🌐 Chargement de la page série...")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            time.sleep(5)
            prendre_screenshot(page)

            # --- METHODE 1 (SUPER RAPIDE & ULTRA FIABLE) : API INTERNE DE FRENCH-STREAM ---
            log("⚡ Analyse des données de flux internes de la page...")
            eps_data = None
            if news_id:
                try:
                    eps_data = page.evaluate("""async (nid) => {
                        const urls = [
                            `/data/eps_${nid}.txt`,
                            `/assets/poster_${nid}.json`,
                            `/ep-data.php?id=${nid}&format=js`
                        ];
                        for (const u of urls) {
                            try {
                                const resp = await fetch(u);
                                if (resp.ok) {
                                    const txt = await resp.text();
                                    try { return JSON.parse(txt); } catch(e) {}
                                }
                            } catch(e) {}
                        }
                        return null;
                    }""", news_id)
                except Exception as e:
                    log(f"   (API direct non disponible : {e})")

            if eps_data and isinstance(eps_data, dict) and ("vf" in eps_data or "vostfr" in eps_data):
                log("🎉 Données officielles des épisodes trouvées directement !")
                flux_dict = eps_data.get("vf") or eps_data.get("vostfr") or {}
                
                # Mise à jour de la liste d'épisodes si le site en contient d'autres
                found_numbers = [int(k) for k in flux_dict.keys() if k.isdigit()]
                if found_numbers:
                    episodes = sorted(found_numbers)
                
                conn = get_db_conn()
                cur = conn.cursor()
                nb_succes = 0

                for ep in episodes:
                    ep_players = flux_dict.get(str(ep), {})
                    best_link = None
                    
                    # 1. Chercher parmi les lecteurs préférés
                    for p_name in PLAYERS_VALIDES:
                        if p_name in ep_players and ep_players[p_name]:
                            best_link = ep_players[p_name]
                            break
                    
                    # 2. Sinon n'importe quel lecteur valide
                    if not best_link and ep_players:
                        for k, v in ep_players.items():
                            if v and isinstance(v, str) and v.startswith("http"):
                                best_link = v
                                break
                    
                    if best_link:
                        cur.execute(
                            "INSERT INTO episodes (series_id, saison, episode, lien) VALUES (%s, %s, %s, %s) "
                            "ON CONFLICT (series_id, saison, episode) DO UPDATE SET lien = EXCLUDED.lien",
                            (serie_id, saison, ep, best_link)
                        )
                        conn.commit()
                        log(f"✅ Épisode {ep} extrait : {best_link[:65]}...")
                        nb_succes += 1
                    else:
                        log(f"⚠️ Aucun lecteur disponible pour l'épisode {ep}")

                cur.close()
                conn.close()
                prendre_screenshot(page)
                log(f"🏆 Extraction instantanée terminée avec succès ({nb_succes}/{len(episodes)} épisodes enregistrés) !")
                return

            # --- METHODE 2 : AUTOMATISATION PAR CLICS AVEC SELECTEURS CORRIGES ---
            log("ℹ️ Passage en mode capture dynamique par le navigateur...")
            iframes_deja_vues = set()

            for ep in episodes:
                log(f"🎬 Traitement de l'épisode {ep}...")
                try:
                    # Clic précis sur l'épisode ciblé dans le DOM
                    episode_clicked = page.evaluate("""(targetEp) => {
                        // 1. Bouton direct via data-num
                        const row = document.querySelector(`.episode-row[data-num='${targetEp}'] .ep-title, [data-num='${targetEp}'].ep-title, [data-num='${targetEp}']`);
                        if (row) {
                            row.scrollIntoView({block: 'center', behavior: 'instant'});
                            row.click();
                            return true;
                        }
                        // 2. Recherche sur feuilles DOM
                        const candidates = Array.from(document.querySelectorAll('a, button, li, div.ep-title, span'));
                        for (const el of candidates) {
                            if (el.children.length <= 1) {
                                const txt = (el.innerText || '').trim();
                                const m = txt.match(/^(?:Episode|Épisode|Ep)\\s*(\\d+)$/i);
                                if (m && parseInt(m[1]) === targetEp) {
                                    el.scrollIntoView({block: 'center', behavior: 'instant'});
                                    el.click();
                                    return true;
                                }
                            }
                        }
                        return false;
                    }""", ep)

                    if episode_clicked:
                        log(f"   🔘 Bouton Épisode {ep} cliqué.")
                    else:
                        log(f"   ⚠️ Bouton Épisode {ep} non cliqué spécifiquement, clic au centre.")
                        page.mouse.click(640, 360)

                    time.sleep(4)
                    prendre_screenshot(page)

                    trigger_video_play(page, log)
                    prendre_screenshot(page)

                    flux = search_iframe(page, log, iframes_deja_vues)
                    if flux:
                        conn = get_db_conn()
                        cur = conn.cursor()
                        cur.execute(
                            "INSERT INTO episodes (series_id, saison, episode, lien) VALUES (%s, %s, %s, %s) "
                            "ON CONFLICT (series_id, saison, episode) DO UPDATE SET lien = EXCLUDED.lien",
                            (serie_id, saison, ep, flux)
                        )
                        conn.commit()
                        cur.close()
                        conn.close()
                        log(f"✅ Épisode {ep} sauvegardé en BDD : {flux[:60]}...")
                    else:
                        log(f"⚠️ Aucun flux NOUVEAU détecté pour l'épisode {ep}")

                except Exception as e:
                    log(f"❌ Erreur sur l'épisode {ep} : {e}")

        except Exception as e:
            log(f"❌ Erreur critique série : {e}")
        finally:
            if hasattr(browser, 'close'):
                browser.close()
        log("🏁 Processus d'extraction terminé.")
