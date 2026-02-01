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
            
            # Vérifier Groq (prioritaire)
            if "GROQ_API_KEY" in content:
                print("✅ Clé API Groq présente (RECOMMANDÉ)")
            else:
                print("⚠️  Aucune GROQ_API_KEY trouvée dans .env")
                print("   💡 Créez une clé gratuite: https://console.groq.com/")
                all_good = False
            
            # Vérifier Gemini (optionnel - backup)
            if "GEMINI_API_KEY" in content or "GOOGLE_API_KEY" in content:
                print("✅ Clé API Gemini présente (backup)")
    else:
        print("❌ Fichier .env manquant")
        print("   💡 Créez un fichier .env à la racine du projet")
        all_good = False

    # 3. Vérification package Groq
    try:
        import groq
        print("✅ Package 'groq' installé")
    except ImportError:
        print("❌ Package 'groq' manquant")
        print("   💡 Exécutez: pip install groq")
        all_good = False

    # 4. Vérification Logs
    if not os.path.exists("logs"):
        os.makedirs("logs")
        print("✅ Dossier logs/ créé.")
    else:
        print("✅ Dossier logs/ existe.")

    # 5. Vérification fichiers critiques
    critical_files = [
        "src/utils/groq_wrapper.py",
        "src/agents/auditor_agent.py",
        "src/agents/fixer_agent.py",
        "src/agents/judge_agent.py"
    ]
    
    missing_files = []
    for filepath in critical_files:
        if os.path.exists(filepath):
            print(f"✅ {filepath} trouvé")
        else:
            print(f"❌ {filepath} manquant")
            missing_files.append(filepath)
            all_good = False
    
    if missing_files:
        print("\n⚠️  Fichiers manquants:")
        for f in missing_files:
            print(f"   - {f}")

    print()
    print("="*70)
    
    if all_good:
        print("🚀 TOUT EST PRÊT ! Vous pouvez commencer.")
        print("\n💡 Prochaine étape: python main.py")
    else:
        print("⚠️  CORRIGEZ LES ERREURS AVANT DE CONTINUER.")
        print("\n📋 TODO:")
        if "groq" not in sys.modules:
            print("   1. pip install groq")
        if not os.path.exists(".env") or "GROQ_API_KEY" not in open(".env").read():
            print("   2. Ajoutez GROQ_API_KEY dans .env")
            print("      Clé gratuite: https://console.groq.com/")
        if missing_files:
            print("   3. Vérifiez que tous les fichiers sont présents")
    
    print("="*70)

if __name__ == "__main__":
    check_environment()