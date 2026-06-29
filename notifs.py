import requests

# --- CONFIGURATION ---
TMDB_API_KEY = "1dfef7dd68067ec8b05e87b494b9a7f4"
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1500756368414605332/BqBPee66pcVIUBEfLqUe7hk4KZ0mg_hPt-4Tl81CkkKf-ts0V9YKvz-u6k_arVTBp5V_"

def envoyer_media(nom_media, type_media="film"):
    # Définition de l'URL de recherche selon le type
    search_type = "movie" if type_media.lower() == "film" else "tv"
    search_url = f"https://api.themoviedb.org/3/search/{search_type}"
    
    params = {
        "api_key": TMDB_API_KEY,
        "query": nom_media,
        "language": "fr-FR"
    }
    
    response = requests.get(search_url, params=params).json()
    
    if response.get('results'):
        data_media = response['results'][0]
        
        # Gestion des champs différents entre Film et Série
        titre = data_media.get('title') if type_media.lower() == "film" else data_media.get('name')
        date = data_media.get('release_date') if type_media.lower() == "film" else data_media.get('first_air_date')
        affiche = f"https://image.tmdb.org/t/p/w500{data_media['poster_path']}"
        
        # Texte dynamique pour le titre du message
        titre_message = "📢 Nouveau film ajouté !" if type_media.lower() == "film" else "📢 Nouvelle série ajoutée !"
        
        data = {
            "embeds": [{
                "title": titre_message,
                "description": f"**Titre :** {titre}\n**Date :** {date or 'Date inconnue'}",
                "color": 16744448 if type_media.lower() == "film" else 3066993, # Orange pour film, Vert pour série
                "thumbnail": {"url": affiche},
                "footer": {"text": "Action par Systeme FlixMovies"}
            }]
        }
        
        requests.post(DISCORD_WEBHOOK_URL, json=data)
        print(f"    ✅ Succès ! '{titre}' ({type_media}) envoyé sur Discord.")
    else:
        print(f"❌ {type_media.capitalize()} non trouvé.")

# --- TESTS ---
# envoyer_media("Apex", type_media="film")
# envoyer_media("Euphoria", type_media="série")