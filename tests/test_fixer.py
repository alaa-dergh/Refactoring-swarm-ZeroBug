import sys
import os
import json
from dotenv import load_dotenv

# --- 1️⃣ Ajouter src/ au path ---
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

from src.agents.fixer_agent import Fixer
from src.utils.file_manager import PyFileTool

# --- 2️⃣ Charger .env pour la clé OpenRouter ---
load_dotenv()

# --- 3️⃣ Vérifier la clé API ---
if not os.getenv("OPENROUTER_API_KEY"):
    print("❌ ERREUR: OPENROUTER_API_KEY non trouvée dans .env")
    exit(1)

# --- 4️⃣ Chemins des dossiers ---
script_dir = os.path.dirname(__file__)
sandbox_dir = os.path.abspath(os.path.join(script_dir, "../sandbox"))
output_dir = os.path.abspath(os.path.join(script_dir, "../sandbox/fixed"))
audit_report_path = os.path.abspath(os.path.join(script_dir, "../logs/audit_report.json"))

print("="*80)
print("🔧 TEST DU FIXER AGENT")
print("="*80)
print(f"📁 Dossier sandbox: {sandbox_dir}")
print(f"📁 Dossier output: {output_dir}")
print(f"📄 Rapport d'audit: {audit_report_path}")
print("="*80)

# --- 5️⃣ Charger le rapport d'audit ---
if not os.path.exists(audit_report_path):
    print("\n⚠️ ATTENTION: Aucun rapport d'audit trouvé.")
    print("💡 Vous devez d'abord exécuter test_auditor.py pour générer le rapport.")
    print("\nCréation d'un rapport de test minimal...\n")
    
    # Créer un rapport de test minimal
    python_files = PyFileTool.list_python_files(sandbox_dir)
    
    if not python_files:
        print("❌ Aucun fichier Python trouvé dans sandbox/")
        exit(1)
    
    audit_results = []
    for py_file in python_files:
        audit_results.append({
            "file_path": py_file,
            "bugs": [
                {
                    "line": 1,
                    "severity": "MEDIUM",
                    "description": "Missing docstring",
                    "suggestion": "Add module-level docstring"
                }
            ],
            "quality_issues": [
                {
                    "line": 5,
                    "severity": "LOW",
                    "description": "Variable name too short",
                    "suggestion": "Use descriptive variable names"
                }
            ],
            "style_issues": [],
            "refactoring_plan": [
                "Add docstrings",
                "Improve variable names",
                "Add type hints"
            ],
            "score": 5.0
        })
else:
    # Charger le vrai rapport d'audit
    try:
        with open(audit_report_path, 'r', encoding='utf-8') as f:
            audit_data = json.load(f)
            audit_results = audit_data.get("files", [])
        
        print(f"✅ Rapport d'audit chargé: {len(audit_results)} fichier(s)\n")
    except Exception as e:
        print(f"❌ Erreur lors du chargement du rapport: {e}")
        exit(1)

# --- 6️⃣ Initialiser le Fixer ---
fixer = Fixer(max_retries=3)

# --- 7️⃣ Mode de test ---
print("\nChoisissez le mode de test:")
print("1. Corriger UN seul fichier (rapide)")
print("2. Corriger TOUS les fichiers (complet)")
choice = input("Votre choix (1 ou 2): ").strip()

if choice == "1":
    # --- MODE FICHIER UNIQUE ---
    if not audit_results:
        print("❌ Aucun fichier à corriger")
        exit(1)
    
    # Prendre le premier fichier
    first_audit = audit_results[0]
    file_path = first_audit.get("file_path")
    
    print(f"\n🔍 Fichier sélectionné: {file_path}")
    print(f"📊 Score actuel: {first_audit.get('score', 0)}/10")
    print(f"🐛 Bugs: {len(first_audit.get('bugs', []))}")
    print(f"⚠️ Quality issues: {len(first_audit.get('quality_issues', []))}")
    
    print("\n🔧 Début de la correction...\n")
    
    result = fixer.fix_file(file_path, first_audit, output_dir)
    
    # Afficher le résultat
    print("\n" + "="*80)
    print("RÉSULTAT DE LA CORRECTION")
    print("="*80)
    
    if result["success"]:
        print("✅ Correction réussie!")
        print(f"📄 Fichier sauvegardé: {result['output_path']}")
        print(f"🔄 Nombre d'itérations: {result.get('iterations', 1)}")
        print(f"💯 Confiance: {result.get('confidence', 0)*100:.1f}%")
        
        if result.get("changes_made"):
            print("\n📝 Changements appliqués:")
            for i, change in enumerate(result["changes_made"], 1):
                print(f"  {i}. {change}")
    else:
        print("❌ Échec de la correction")
        print(f"Erreur: {result.get('error', 'Unknown')}")

elif choice == "2":
    # --- MODE COMPLET ---
    if not audit_results:
        print("❌ Aucun fichier à corriger")
        exit(1)
    
    print(f"\n🚀 Correction de {len(audit_results)} fichier(s)...\n")
    
    results = fixer.fix_directory(audit_results, output_dir)
    
    # Générer le rapport
    report = fixer.generate_fix_report(results)
    
    # Afficher le rapport
    print("\n" + "="*80)
    print("RAPPORT DE CORRECTION COMPLET")
    print("="*80)
    
    summary = report["summary"]
    print(f"📊 Fichiers traités: {summary['total_files']}")
    print(f"✅ Corrections réussies: {summary['successful_fixes']}")
    print(f"❌ Échecs: {summary['failed_fixes']}")
    print(f"📈 Taux de réussite: {summary['success_rate']}")
    print(f"🔧 Total de changements: {summary['total_changes']}")
    print(f"💯 Confiance moyenne: {summary['average_confidence']*100:.1f}%")
    
    print("\n📋 Détails par fichier:")
    for i, res in enumerate(results, 1):
        status = "✅" if res.get("success", False) else "❌"
        file_name = os.path.basename(res.get("file_path", "unknown"))
        print(f"  {status} [{i}] {file_name}")
        if res.get("success"):
            confidence = res.get("confidence", 0)
            changes = len(res.get("changes_made", []))
            print(f"      💯 {confidence*100:.0f}% confiance | 🔧 {changes} changements")
        else:
            error = res.get("error", "Unknown")[:50]
            print(f"      ⚠️ {error}...")
    
    # Sauvegarder le rapport
    report_path = os.path.join("logs", "fix_report.json")
    os.makedirs("logs", exist_ok=True)
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Rapport complet sauvegardé: {report_path}")

else:
    print("❌ Choix invalide")

print("\n" + "="*80)
print("✨ Test terminé!")
print("="*80)