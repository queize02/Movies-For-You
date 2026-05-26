from playwright.sync_api import sync_playwright
import time

def extraire_iframe(url):
    print(f"\nChargement de la page : {url} ...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        
        page = context.new_page()
        page.on("popup", lambda popup: popup.close())
        
        try:
            page.goto(url, timeout=60000)
            
            print("\n⏳ Étape 1 : Recherche du bouton publicitaire ('Voir une publicité')...")
            try:
                bouton_pub = page.locator("button:has-text('Voir une publicité')")
                bouton_pub.wait_for(timeout=10000)
                print("👉 Bouton trouvé ! Clic automatique en cours...")
                bouton_pub.click(force=True)
                time.sleep(2)
            except Exception:
                print("Pas de bouton 'Voir une publicité' détecté, on continue...")

            print("\n⏳ Étape 2 : Recherche du bouton ('Lecture')...")
            try:
                bouton_lecture = page.locator("button:has-text('Lecture')")
                bouton_lecture.wait_for(timeout=10000)
                print("👉 Bouton 'Lecture' trouvé ! Clic automatique en cours...")
                bouton_lecture.click(force=True)
                time.sleep(2)
            except Exception:
                print("Pas de bouton 'Lecture' détecté, on continue...")

            print("\n⏳ Étape 3 : Attente de l'apparition de la vidéo par défaut...")
            try:
                page.wait_for_selector("iframe", timeout=20000)
            except:
                pass
            
            # --- PAUSE INTERACTIVE POUR L'UTILISATEUR ---
            print("\n" + "="*60)
            print("⏸️ LE SCRIPT EST EN PAUSE")
            print("="*60)
            print("Si la vidéo par défaut (ex: Vidzy) ne marche pas :")
            print("1. Regardez la fenêtre du navigateur ouverte.")
            print("2. Changez de source manuellement (ex: LuluStream, VidMoly...).")
            print("3. Une fois que la vidéo fonctionne à l'écran...")
            print("="*60)
            
            input("\n👉 APPUYEZ SUR [ENTRÉE] ICI POUR EXTRAIRE LE LIEN ACTUEL : ")
            
            # On extrait l'iframe qui est PRÉSENTE MAINTENANT sur la page
            iframe_element = page.query_selector("iframe")
            
            if iframe_element:
                src = iframe_element.get_attribute("src")
                print("\n" + "="*50)
                print("✅ Iframe extraite avec succès !")
                print(f"🔗 Lien : {src}")
                print("="*50 + "\n")
                return src
            else:
                print("\n❌ Aucune iframe trouvée sur la page actuelle.")
                return None
                
        except Exception as e:
            print(f"\n❌ Erreur lors de l'extraction : {e}")
            return None
        finally:
            page.wait_for_timeout(2000) 
            browser.close()

if __name__ == "__main__":
    print("="*50)
    print("🤖 EXTRACTEUR D'IFRAME MOVIX")
    print("="*50)
    
    url_utilisateur = input("👉 Collez l'URL du film ici (puis appuyez sur Entrée) : ").strip()
    
    if url_utilisateur:
        lien_iframe = extraire_iframe(url_utilisateur)
    else:
        print("❌ Aucune URL n'a été saisie. Fin du script.")
