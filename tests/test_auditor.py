import sys
import os
from dotenv import load_dotenv

# --- 1️⃣ Add project root to path (NOT src!) ---
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


from src.agents.auditor_agent import Auditor
from src.utils.file_manager import PyFileTool

# --- 3️⃣ Load .env for API key ---
load_dotenv()

# --- 4️⃣ Initialize Auditor ---
auditor = Auditor()

# --- 5️⃣ Folder to analyze ---
folder_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../sandbox"))

# --- 6️⃣ List all Python files ---
python_files = PyFileTool.list_python_files(folder_path)
if not python_files:
    print("⚠️ Aucun fichier Python trouvé dans le dossier sandbox.")
else:
    print(f"🔹 {len(python_files)} fichier(s) Python trouvé(s) pour analyse.")

# --- 7️⃣ Analyze files ---
analyses = []
for file_path in python_files:
    print(f"\n🔍 Analyse de {file_path} ...")
    try:
        result = auditor.analyze_file(file_path)
        analyses.append(result)

        # Display summary
        print(f"✅ Score: {result['score']}/10 | Bugs: {len(result['bugs'])} | "
              f"Quality issues: {len(result['quality_issues'])} | "
              f"Style issues: {len(result['style_issues'])}")
        if result['refactoring_plan']:
            print("🛠️ Plan de refactoring :")
            for step in result['refactoring_plan']:
                print(f"   - {step}")

    except Exception as e:
        print(f"❌ Erreur lors de l'analyse de {file_path}: {str(e)}")

# --- 8️⃣ Generate complete report ---
report = auditor.generate_report(analyses)
print("\n" + "="*80)
print("RAPPORT COMPLET")
print("="*80)
print(report)

# --- 9️⃣ Save report to JSON ---
import json
os.makedirs("logs", exist_ok=True)
with open("logs/audit_report.json", "w", encoding="utf-8") as f:
    json.dump(report, f, indent=2, ensure_ascii=False)
print("\n💾 Rapport sauvegardé: logs/audit_report.json")