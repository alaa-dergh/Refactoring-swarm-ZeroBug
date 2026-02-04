import sys
import os
from dotenv import load_dotenv

# --- 1️⃣ Ajouter src/ au path ---
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from src.agents.auditor_agent import Auditor
from src.utils.file_manager import PyFileTool

# --- 2️⃣ Charger .env pour la clé Gemini ---
load_dotenv()

# --- 3️⃣ Initialiser l'Auditor ---
auditor = Auditor()

# --- 4️⃣ Dossier à analyser ---
folder_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../sandbox"))

# --- 5️⃣ Lister tous les fichiers Python ---
python_files = PyFileTool.list_python_files(folder_path)
if not python_files:
    print("⚠️ Aucun fichier Python trouvé dans le dossier sandbox.")
else:
    print(f"🔹 {len(python_files)} fichier(s) Python trouvé(s) pour analyse.")

# --- 6️⃣ Analyser les fichiers avec Gemini ---
analyses = []
for file_path in python_files:
    print(f"\n🔍 Analyse de {file_path} ...")
    try:
        result = auditor.analyze_file(file_path)
        analyses.append(result)

        # Affichage résumé
        print(f"✅ Score: {result['score']}/10 | Bugs: {len(result['bugs'])} | "
              f"Quality issues: {len(result['quality_issues'])} | "
              f"Style issues: {len(result['style_issues'])}")
        if result['refactoring_plan']:
            print("🛠️ Plan de refactoring :")
            for step in result['refactoring_plan']:
                print(f"   - {step}")

    except Exception as e:
        print(f"❌ Erreur lors de l'analyse de {file_path}: {str(e)}")

# --- 7️⃣ Générer rapport complet ---
report = auditor.generate_report(analyses)
print("\n" + "="*80)
print("RAPPORT COMPLET")
print("="*80)
print(report)