#!/usr/bin/env python3
"""
🚀 ZeroBug - Système de Refactoring Automatique
Point d'entrée principal du projet

Agents:
- Auditor: Analyse et détecte les bugs
- Fixer: Corrige automatiquement les bugs
- Judge: Valide les corrections avec des tests

Usage: python main.py
"""

import sys
import os
from pathlib import Path

# Ajouter le répertoire racine au chemin Python
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
from src.agents.orchestrator import Orchestrator

def print_banner():
    """Affiche la bannière du projet."""
    banner = """
    ╔══════════════════════════════════════════════════════════════════════════╗
    ║                                                                          ║
    ║                          🐛 ZEROBUG SYSTEM 🐛                           ║
    ║                   Système de Refactoring Automatique                    ║
    ║                                                                          ║
    ║  Auditor → Fixer → Judge                                                ║
    ║  Détecte, Corrige, Valide                                              ║
    ║                                                                          ║
    ╚══════════════════════════════════════════════════════════════════════════╝
    """
    print(banner)

def print_api_status():
    """Affiche l'état des clés API."""
    load_dotenv()
    
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")
    
    print("\n🔑 ÉTAT DES CLÉS API:")
    
    if openrouter_key:
        print("  ✅ OpenRouter API: Configurée")
    else:
        print("  ❌ OpenRouter API: Non configurée")
        print("     💡 Créez un compte: https://openrouter.ai/")
    
    if google_key:
        print("  ✅ Google Gemini API: Configurée")
    else:
        print("  ❌ Google Gemini API: Non configurée")
        print("     💡 Obtenez une clé gratuite: https://makersuite.google.com/app/apikey")
    
    if not openrouter_key and not google_key:
        print("\n  ⚠️ ATTENTION: Aucune clé API configurée!")
        print("  Les agents fonctionneront en mode fallback (basique)")
    
    return bool(openrouter_key or google_key)

def get_input_directory():
    """Demande le dossier d'entrée à l'utilisateur."""
    print("\n📁 DOSSIER D'ENTRÉE:")
    print("  Par défaut: sandbox/")
    
    choice = input("  Utiliser 'sandbox/' ? (o/n) [o]: ").strip().lower()
    
    if choice in ['n', 'non', 'no']:
        custom_dir = input("  Entrez le chemin du dossier: ").strip()
        if os.path.isdir(custom_dir):
            return custom_dir
        else:
            print(f"  ⚠️ Dossier '{custom_dir}' introuvable, utilisation de 'sandbox/'")
            return "sandbox"
    else:
        return "sandbox"

def run_full_pipeline():
    """Exécute le pipeline complet : Auditor → Fixer → Judge."""
    print("\n" + "="*80)
    print("🚀 PIPELINE COMPLET: AUDITOR → FIXER → JUDGE")
    print("="*80)
    
    input_dir = get_input_directory()
    
    if not os.path.isdir(input_dir):
        print(f"\n❌ Erreur: Le dossier '{input_dir}' n'existe pas")
        return
    
    # Demander le dossier de sortie
    print(f"\n📁 DOSSIER DE SORTIE:")
    print(f"  Par défaut: {input_dir}/fixed/")
    
    choice = input(f"  Utiliser '{input_dir}/fixed/' ? (o/n) [o]: ").strip().lower()
    
    if choice in ['n', 'non', 'no']:
        output_dir = input("  Entrez le chemin du dossier de sortie: ").strip()
    else:
        output_dir = os.path.join(input_dir, "fixed")
    
    # Demander si on veut ignorer le Judge
    print("\n🧑‍⚖️ VALIDATION:")
    skip_judge_choice = input("  Ignorer l'étape de validation (Judge) ? (o/n) [n]: ").strip().lower()
    skip_judge = skip_judge_choice in ['o', 'oui', 'y', 'yes']
    
    # Confirmation
    print("\n" + "─"*80)
    print("📋 RÉCAPITULATIF:")
    print(f"  • Dossier d'entrée: {input_dir}")
    print(f"  • Dossier de sortie: {output_dir}")
    print(f"  • Étapes: Auditor → Fixer" + ("" if skip_judge else " → Judge"))
    print("─"*80)
    
    confirm = input("\n▶️  Lancer le pipeline ? (o/n) [o]: ").strip().lower()
    
    if confirm in ['n', 'non', 'no']:
        print("❌ Pipeline annulé")
        return
    
    # Exécuter le pipeline
    orchestrator = Orchestrator()
    results = orchestrator.run_full_pipeline(
        input_dir=input_dir,
        output_dir=output_dir,
        skip_judge=skip_judge
    )
    
    # Résumé
    if results.get("success"):
        print("\n✅ Pipeline terminé avec succès!")
        print(f"📁 Fichiers corrigés disponibles dans: {output_dir}")
    else:
        print("\n❌ Pipeline terminé avec erreurs")
        if results.get("error"):
            print(f"  Erreur: {results['error']}")

def run_audit_only():
    """Exécute uniquement l'analyse (Auditor)."""
    print("\n" + "="*80)
    print("📊 MODE: ANALYSE SEULEMENT (AUDITOR)")
    print("="*80)
    
    input_dir = get_input_directory()
    
    if not os.path.isdir(input_dir):
        print(f"\n❌ Erreur: Le dossier '{input_dir}' n'existe pas")
        return
    
    print(f"\n▶️  Analyse du dossier: {input_dir}")
    
    orchestrator = Orchestrator()
    report = orchestrator.run_audit_only(input_dir)
    
    print("\n✅ Analyse terminée!")
    print(f"  📊 Fichiers analysés: {report['total_files']}")
    print(f"  🐛 Bugs détectés: {report['summary']['total_bugs']}")
    print(f"  ⚠️  Issues qualité: {report['summary']['total_quality_issues']}")
    print(f"  💾 Rapport: logs/audit_only_report.json")

def run_fix_only():
    """Exécute l'analyse et la correction (Auditor + Fixer)."""
    print("\n" + "="*80)
    print("🔧 MODE: ANALYSE + CORRECTION (AUDITOR + FIXER)")
    print("="*80)
    
    input_dir = get_input_directory()
    
    if not os.path.isdir(input_dir):
        print(f"\n❌ Erreur: Le dossier '{input_dir}' n'existe pas")
        return
    
    output_dir = os.path.join(input_dir, "fixed")
    
    print(f"\n▶️  Dossier d'entrée: {input_dir}")
    print(f"▶️  Dossier de sortie: {output_dir}")
    
    orchestrator = Orchestrator()
    report = orchestrator.run_fix_only(input_dir, output_dir)
    
    print("\n✅ Correction terminée!")
    print(f"  📊 Fichiers traités: {report['summary']['total_files']}")
    print(f"  ✅ Corrections réussies: {report['summary']['successful_fixes']}")
    print(f"  🎯 Taux de succès: {report['summary']['success_rate']}")
    print(f"  💾 Rapport: logs/fix_only_report.json")
    print(f"  📁 Fichiers corrigés: {output_dir}")

def run_validate_only():
    """Exécute uniquement la validation (Judge)."""
    print("\n" + "="*80)
    print("🧑‍⚖️ MODE: VALIDATION SEULEMENT (JUDGE)")
    print("="*80)
    
    input_dir = get_input_directory()
    
    if not os.path.isdir(input_dir):
        print(f"\n❌ Erreur: Le dossier '{input_dir}' n'existe pas")
        return
    
    print(f"\n▶️  Validation du dossier: {input_dir}")
    
    orchestrator = Orchestrator()
    report = orchestrator.run_validate_only(input_dir)
    
    print("\n✅ Validation terminée!")
    print(f"  📊 Fichiers validés: {report['summary']['total_files']}")
    print(f"  ✅ Tests réussis: {report['summary']['files_with_passing_tests']}")
    print(f"  🎯 Taux de validation: {report['summary']['success_rate']}")
    print(f"  💾 Rapport: logs/validate_only_report.json")

def show_logs():
    """Affiche la liste des logs disponibles."""
    print("\n" + "="*80)
    print("📋 LOGS DISPONIBLES")
    print("="*80)
    
    logs_dir = "logs"
    
    if not os.path.isdir(logs_dir):
        print("\n❌ Aucun dossier 'logs/' trouvé")
        return
    
    log_files = [f for f in os.listdir(logs_dir) if f.endswith('.json')]
    
    if not log_files:
        print("\n❌ Aucun fichier de log trouvé dans 'logs/'")
        return
    
    print(f"\n📁 Dossier: {logs_dir}/")
    print(f"🔍 {len(log_files)} fichier(s) trouvé(s):\n")
    
    for i, log_file in enumerate(sorted(log_files), 1):
        file_path = os.path.join(logs_dir, log_file)
        file_size = os.path.getsize(file_path)
        
        # Format size
        if file_size < 1024:
            size_str = f"{file_size} B"
        elif file_size < 1024 * 1024:
            size_str = f"{file_size / 1024:.1f} KB"
        else:
            size_str = f"{file_size / (1024 * 1024):.1f} MB"
        
        print(f"  {i}. {log_file} ({size_str})")
    
    print(f"\n💡 Pour voir un log: cat logs/<nom_fichier>")
    print(f"💡 Pour voir tous les logs: ls -lh logs/")

def main():
    """Point d'entrée principal."""
    
    # Charger les variables d'environnement
    load_dotenv()
    
    # Afficher la bannière
    print_banner()
    
    # Afficher l'état des API
    has_api = print_api_status()
    
    while True:
        print("\n" + "="*80)
        print("📋 MENU PRINCIPAL")
        print("="*80)
        print("\n🚀 MODES D'EXÉCUTION:")
        print("  1. Pipeline complet (Auditor → Fixer → Judge)")
        print("  2. Analyse seulement (Auditor)")
        print("  3. Analyse + Correction (Auditor + Fixer)")
        print("  4. Validation seulement (Judge)")
        print("\n📊 AUTRES OPTIONS:")
        print("  5. Voir les logs disponibles")
        print("  6. Quitter")
        
        choice = input("\n👉 Votre choix (1-6): ").strip()
        
        if choice == "1":
            run_full_pipeline()
        elif choice == "2":
            run_audit_only()
        elif choice == "3":
            run_fix_only()
        elif choice == "4":
            run_validate_only()
        elif choice == "5":
            show_logs()
        elif choice == "6":
            print("\n👋 Au revoir!")
            break
        else:
            print("\n❌ Choix invalide. Veuillez choisir entre 1 et 6.")
        
        # Pause avant de revenir au menu
        input("\n⏸️  Appuyez sur Entrée pour revenir au menu...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Programme interrompu par l'utilisateur")
        print("👋 Au revoir!")
    except Exception as e:
        print(f"\n❌ Erreur inattendue: {e}")
        import traceback
        traceback.print_exc()