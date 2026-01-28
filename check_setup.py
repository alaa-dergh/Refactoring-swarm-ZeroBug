# check_setup.py
import sys
import os

def check_environment():
    print("🔍 Démarrage du 'Sanity Check'...\n")
    all_good = True

    # 1. Vérification Python
    version = sys.version_info
    if (version.major == 3) and (version.minor in [10, 11]):
        print(f"✅ Python Version: {version.major}.{version.minor}")
    else:
        print(f"❌ Python Version: {version.major}.{version.minor} (Requis: 3.10 ou 3.11)")
        all_good = False

    # 2. Vérification Clé API (.env)
    if os.path.exists(".env"):
        print("✅ Fichier .env détecté.")
        with open(".env", "r") as f:
            content = f.read()
            if "OPENROUTER_API_KEY" in content:
                 print("✅ Clé API présente (format non vérifié).")
            else:
                 print("❌ Aucune variable API_KEY trouvée dans .env")
                 all_good = False
    else:
        print("❌ Fichier .env manquant (Copiez .env.example).")
        all_good = False

    # 3. Vérification Logs
    if not os.path.exists("logs"):
        os.makedirs("logs")
        print("✅ Dossier logs/ créé.")

    if all_good:
        print("\n🚀 TOUT EST PRÊT ! Vous pouvez commencer.")
    else:
        print("\n⚠️ CORRIGEZ LES ERREURS AVANT DE CONTINUER.")

if __name__ == "__main__":
    check_environment()