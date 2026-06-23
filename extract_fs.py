from playwright.sync_api import sync_playwright
import time
import psycopg2
import sys
import os

# Configuration BDD
DB_URL = 'postgresql://admin:02082008@192.168.1.13:5432/neondb'

def save_to_db(series_id, saison, episode, lien):
    if not lien: return
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
        print(f"  💾 Sauvegardé en BDD : S{saison}E{episode}")
    except Exception as e:
        print(f"  ❌ Erreur BDD : {e}")

def fermer_popups(page, context):
    """Ferme les onglets pub ouverts et les modales."""
    # Fermer les onglets en trop
    for p in context.pages:
        if p != page:
            try: p.close()
            except: pass
    # Appuyer sur Escape pour les modales
    try: page.keyboard.press("Escape")
    except: pass

def quitter_plein_ecran(page):
    """Sort du plein écran si actif."""
    try:
        page.evaluate("if(document.fullscreenElement) document.exitFullscreen();")
        time.sleep(0.3)
    except: pass
    try: page.keyboard.press("Escape")
    except: pass

def cliquer_episode_vf(page, context, episode_num):
    """
    Clique sur l'épisode VF en utilisant les vrais sélecteurs de French Stream.
    La liste VF est dans #vf-episodes, les épisodes sont ajoutés dynamiquement par JS.
    """
    print(f"  📺 Sélection de l'épisode {episode_num} (VF)...")
    
    fermer_popups(page, context)
    time.sleep(0.5)
    
    # Les épisodes dans la section VF (#vf-episodes) sont des éléments cliquables
    # générés par le script serie-player12.js du site.
    # On utilise JavaScript pour cliquer sur le bon dans la colonne VF.
    try:
        clicked = page.evaluate(f"""
            () => {{
                // Cibler la section VF spécifiquement
                const vfSection = document.getElementById('vf-episodes');
                if (!vfSection) return 'NO_VF_SECTION';
                
                // Chercher dans les enfants de la section VF
                const items = vfSection.querySelectorAll('*');
                for (const el of items) {{
                    const txt = el.textContent.trim();
                    // Chercher les éléments qui contiennent exactement "Episode X"
                    // Le texte peut être "► Episode 2" ou "Episode 2" ou contenir des icônes
                    if (txt.includes('Episode {episode_num}') && !txt.includes('Episode {episode_num}0')) {{
                        // Vérifier que c'est un élément cliquable (pas un conteneur parent)
                        const rect = el.getBoundingClientRect();
                        if (rect.width > 0 && rect.height > 0 && el.childElementCount < 5) {{
                            el.click();
                            return 'CLICKED: ' + el.tagName + '.' + el.className + ' => ' + txt.substring(0, 50);
                        }}
                    }}
                }}
                
                // Fallback : essayer de chercher un élément avec data-episode
                const dataEp = vfSection.querySelector('[data-episode="{episode_num}"]');
                if (dataEp) {{
                    dataEp.click();
                    return 'CLICKED_DATA: ' + dataEp.tagName;
                }}
                
                return 'NOT_FOUND';
            }}
        """)
        
        if clicked and clicked.startswith('CLICKED'):
            print(f"  ✅ {clicked}")
            time.sleep(1)
            fermer_popups(page, context)
            return True
        elif clicked == 'NO_VF_SECTION':
            print(f"  ⚠️ Section #vf-episodes non trouvée dans le DOM.")
        else:
            print(f"  ⚠️ Épisode {episode_num} non trouvé dans la section VF.")
            # Debug : lister ce qu'il y a dans #vf-episodes
            debug = page.evaluate("""
                () => {
                    const vf = document.getElementById('vf-episodes');
                    if (!vf) return 'VF section absente';
                    return 'Contenu VF: ' + vf.innerHTML.substring(0, 300);
                }
            """)
            print(f"  🔍 DEBUG : {debug}")
            
    except Exception as e:
        print(f"  ❌ Erreur JS épisode : {e}")
    
    return False

def extraire_iframe(page):
    """
    Extrait le src de l'iframe #seriePlayer (le vrai ID sur French Stream).
    """
    print("  🔍 Extraction de l'iframe #seriePlayer...")
    
    # Attendre que l'iframe soit chargée avec un src non vide
    for _ in range(15):
        try:
            src = page.evaluate("""
                () => {
                    const iframe = document.getElementById('seriePlayer');
                    if (iframe && iframe.src && iframe.src !== '' && iframe.src !== 'about:blank') {
                        return iframe.src;
                    }
                    return null;
                }
            """)
            if src:
                print(f"  ✅ Iframe trouvée : {src[:80]}...")
                return src
        except: pass
        time.sleep(1)
    
    # Fallback : essayer n'importe quelle iframe
    try:
        iframe = page.locator("iframe").first
        src = iframe.get_attribute("src")
        if src and src != "" and src != "about:blank":
            print(f"  ✅ Iframe fallback : {src[:80]}...")
            return src
    except: pass
    
    print("  ❌ Aucune iframe avec un lien trouvée.")
    return None

def extract_episode(page, context, episode_num):
    """Extrait l'iframe pour un épisode donné."""
    print(f"\n{'='*50}")
    print(f"🚀 Épisode {episode_num}")
    print(f"{'='*50}")
    
    try:
        # 1. Sortir du plein écran si actif
        quitter_plein_ecran(page)
        
        # 2. Fermer les pop-ups
        fermer_popups(page, context)
        
        # 3. Scroller vers la liste des épisodes pour qu'ils soient visibles
        page.evaluate("document.getElementById('vf-episodes')?.scrollIntoView({behavior:'smooth', block:'center'})")
        time.sleep(1)
        
        # 4. Cliquer sur l'épisode VF
        if not cliquer_episode_vf(page, context, episode_num):
            print(f"  ⚠️ Impossible de cliquer sur l'épisode {episode_num}. On tente quand même d'extraire l'iframe.")
        
        time.sleep(3)
        
        # 5. Fermer les pop-ups qui se sont ouvertes
        fermer_popups(page, context)
        
        # 6. Extraire l'iframe
        src = extraire_iframe(page)
        
        # 7. Sortir du plein écran
        quitter_plein_ecran(page)
        
        if src:
            print(f"  🔗 Lien final : {src}")
        else:
            print(f"  ❌ Pas de lien trouvé pour l'épisode {episode_num}")
        
        return src
        
    except Exception as e:
        print(f"  ❌ Erreur : {e}")
        quitter_plein_ecran(page)
        return None

if __name__ == "__main__":
    print("="*60)
    print("🤖 EXTRACTEUR DE SÉRIES — FRENCH STREAM (fs15.lol)")
    print("="*60)
    
    url = input("👉 URL de la série (ex: https://fs15.lol/123-titre-saison-1.html) : ").strip()
    if not url:
        print("Annulé.")
        sys.exit()
    
    saison   = int(input("👉 Numéro de saison : ").strip())
    nb_eps   = int(input("👉 Nombre d'épisodes à extraire : ").strip())
    series_id  = int(input("👉 ID de la série en base de données : ").strip())
    
    # Vérifier si l'extension uBlock existe
    extension_path = os.path.abspath("ublock_extension")
    use_extension = os.path.isdir(extension_path)
    
    with sync_playwright() as p:
        if use_extension:
            print(f"\n🛡️ uBlock Origin détecté, chargement de l'extension...")
            browser = p.chromium.launch_persistent_context(
                user_data_dir="./user_data",
                headless=False,
                args=[
                    f'--load-extension={extension_path}',
                    f'--disable-extensions-except={extension_path}'
                ],
                viewport={'width': 1280, 'height': 720}
            )
            page = browser.pages[0]
        else:
            print(f"\n⚠️ Pas d'extension uBlock trouvée, lancement sans bloqueur de pub.")
            browser = p.chromium.launch(headless=False)
            context = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1280, 'height': 720}
            )
            page = context.new_page()
        
        # Fermer automatiquement les pop-ups (nouveaux onglets)
        ctx = browser if use_extension else context
        ctx.on("page", lambda new_page: new_page.close())
        
        print(f"\n🌐 Chargement de la page...")
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        
        # Attendre que le script du site charge les épisodes
        print("⏳ Attente du chargement des épisodes...")
        time.sleep(5)
        
        # Debug : vérifier que les épisodes sont bien chargés
        nb_found = page.evaluate("""
            () => {
                const vf = document.getElementById('vf-episodes');
                return vf ? vf.children.length : -1;
            }
        """)
        print(f"📋 Épisodes VF détectés dans le DOM : {nb_found}")
        
        if nb_found <= 0:
            print("⚠️ Les épisodes ne sont pas encore chargés. Attente supplémentaire de 5s...")
            time.sleep(5)
        
        for ep in range(1, nb_eps + 1):
            iframe_src = extract_episode(page, ctx, ep)
            save_to_db(series_id, saison, ep, iframe_src)
            time.sleep(2)
        
        browser.close()
        print("\n✨ Extraction terminée !")
