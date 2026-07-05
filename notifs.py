import requests

# --- CONFIGURATION (METS TES INFOS ICI) ---
TMDB_API_KEY = "1dfef7dd68067ec8b05e87b494b9a7f4"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1500756368414605332/BqBPee66pcVIUBEfLqUe7hk4KZ0mg_hPt-4Tl81CkkKf-ts0V9YKvz-u6k_arVTBp5V_"

def envoyer_film(titre_film):
    # On construit l'URL proprement
    search_url = f"https://api.themoviedb.org/3/search/movie"
    params = {
        "api_key": TMDB_API_KEY,
        "query": titre_film,
        "language": "fr-FR"
    }
    
    # On fait la requête
    response = requests.get(search_url, params=params).json()
    
    # Vérification si TMDB a renvoyé une erreur de clé
    if 'status_message' in response:
        print(f"Erreur TMDB : {response['status_message']}")
        return

    if response.get('results'):
        film = response['results'][0]
        titre = film['title']
        date = film.get('release_date', 'Date inconnue')
        affiche = f"https://image.tmdb.org/t/p/w500{film['poster_path']}"
        
        # Préparation du message Discord
        data = {
            "embeds": [{
                "title": "📢 Nouveau film ajouté !",
                "description": f"**Titre :** {titre}\n**Date :** {date}",
                "color": 16744448,
                "thumbnail": {"url": affiche},
                "footer": {"text": "Action par Systeme FlixMovies"}
            }]
        }
        
        requests.post(DISCORD_WEBHOOK_URL, json=data)
        print(f"✅ Succès ! '{titre}' envoyé sur Discord.")
    else:
        print("❌ Film non trouvé.")

# --- TEST ---
envoyer_film("Apex")