#!/usr/bin/env python3
"""
Test du Judge Agent - Version améliorée
Usage: python tests/test_judge.py

Ce script teste le Judge Agent qui:
1. Génère des tests unitaires (avec AI ou fallback)
2. Exécute ces tests avec pytest
3. Valide les corrections du Fixer
"""

import sys
import os
import json
import time
from pathlib import Path

# Ajouter le répertoire racine au chemin Python
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
from src.agents.judge_agent import Judge
from src.utils.file_manager import PyFileTool

def print_banner(text: str):
    """Affiche une bannière."""
    print("\n" + "="*80)
    print(text.center(80))
    print("="*80)

def print_api_status():
    """Affiche l'état des clés API."""
    load_dotenv()
    
    google_api_key = os.getenv("GOOGLE_API_KEY")
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    
    print("\n🔑 ÉTAT DES CLÉS API:")
    if openrouter_api_key:
        print("  ✅ OpenRouter API: Configurée")
    else:
        print("  ❌ OpenRouter API: Non configurée")
        print("     💡 Créez un compte: https://openrouter.ai/")
    
    if google_api_key:
        print("  ✅ Google Gemini API: Configurée")
    else:
        print("  ❌ Google Gemini API: Non configurée")
        print("     💡 Obtenez une clé gratuite: https://makersuite.google.com/app/apikey")
    
    if not google_api_key and not openrouter_api_key:
        print("\n⚠️ ATTENTION: Aucune clé API configurée!")
        print("Le Judge fonctionnera en mode basique sans AI.")
        print("Les tests seront générés automatiquement mais moins précis.")
    
    return bool(openrouter_api_key or google_api_key)

def test_simple_code():
    """Test 1: Génération de tests sur du code simple."""
    
    print_banner("TEST 1: GÉNÉRATION DE TESTS AVEC CODE SIMPLE")
    
    # Code de test simple
    test_code = """
def add(a, b):
    '''Add two numbers.'''
    return a + b

def divide(a, b):
    '''Divide a by b (no validation).'''
    return a / b

def safe_divide(a, b):
    '''Divide a by b with validation.'''
    if b == 0:
        raise ValueError("Division by zero")
    return a / b

def multiply(a, b):
    '''Multiply two numbers.'''
    return a * b
"""
    
    # Sauvegarder dans un fichier temporaire avec encodage UTF-8
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, dir='sandbox', encoding='utf-8') as f:
        f.write(test_code)
        temp_file = f.name
    
    try:
        print(f"📄 Fichier de test créé: {os.path.basename(temp_file)}")
        
        # Initialiser le Judge
        judge = Judge()
        
        # Évaluer le fichier
        result = judge.evaluate_file(temp_file)
        
        # Afficher les résultats
        if result.get('success'):
            print(f"\n✅ SUCCÈS - Tests passés!")
            print(f"   📊 Tests passés: {result.get('passed', 0)}/{result.get('total', 0)}")
            print(f"   🤖 AI utilisée: {'OUI' if result.get('ai_used') else 'NON'}")
        else:
            print(f"\n❌ ÉCHEC - Tests échoués")
            print(f"   📊 Tests échoués: {result.get('failed', 0)}/{result.get('total', 0)}")
            print(f"   ⚠️ Erreurs: {result.get('errors', 0)}")
            if result.get('error'):
                print(f"   💬 Message: {result.get('error')}")
        
        # Afficher un extrait de la sortie
        if result.get('test_output'):
            print(f"\n📋 Extrait de la sortie des tests:")
            print(result['test_output'][:300])
        
        return result
        
    finally:
        # Nettoyer
        if os.path.exists(temp_file):
            os.unlink(temp_file)
        # Nettoyer le dossier de tests s'il existe
        test_dir = os.path.join(os.path.dirname(temp_file), 'test_judge')
        if os.path.exists(test_dir):
            import shutil
            shutil.rmtree(test_dir)

def test_on_sandbox_files():
    """Test 2: Génération et exécution de tests sur les fichiers du sandbox."""
    
    print_banner("TEST 2: TESTS SUR LES FICHIERS DU SANDBOX")
    
    load_dotenv()
    
    # Chemin vers le sandbox
    script_dir = os.path.dirname(__file__)
    sandbox_dir = os.path.abspath(os.path.join(script_dir, "../sandbox"))
    
    if not os.path.exists(sandbox_dir):
        print("❌ Dossier sandbox non trouvé.")
        return None
    
    # Lister les fichiers Python (exclure les dossiers fixed et test_*)
    python_files = []
    for file_path in PyFileTool.list_python_files(sandbox_dir):
        # Exclure les fichiers dans fixed/ et test_*/
        if 'fixed' not in file_path and 'test_' not in os.path.basename(file_path):
            python_files.append(file_path)
    
    if not python_files:
        print("❌ Aucun fichier Python trouvé dans sandbox/")
        return None
    
    print(f"📁 Dossier: {sandbox_dir}")
    print(f"🔍 {len(python_files)} fichier(s) à tester")
    
    # Initialiser le Judge
    judge = Judge()
    
    if judge.llm:
        print("🤖 Mode: Génération de tests avec AI")
    else:
        print("⚠️ Mode: Génération de tests basiques (sans AI)")
    
    results = []
    
    # Limiter à 3 fichiers pour éviter de dépasser le quota
    test_files = python_files[:3]
    
    for i, file_path in enumerate(test_files, 1):
        print(f"\n{'─'*80}")
        print(f"[{i}/{len(test_files)}] {os.path.basename(file_path)}")
        
        try:
            result = judge.evaluate_file(file_path)
            results.append(result)
            
            # Afficher un résumé
            if result.get('success'):
                print(f"  ✅ Tests réussis: {result.get('passed', 0)}/{result.get('total', 0)}")
            else:
                print(f"  ❌ Tests échoués: {result.get('failed', 0)}/{result.get('total', 0)}")
                if result.get('error'):
                    print(f"  💬 Erreur: {result.get('error')}")
            
        except Exception as e:
            print(f"  ⚠️ Erreur: {e}")
            results.append({
                "file": file_path,
                "success": False,
                "error": str(e)
            })
    
    # Rapport final
    successful = sum(1 for r in results if r.get("success", False))
    total = len(results)
    
    print(f"\n{'='*80}")
    print(f"📊 RAPPORT FINAL:")
    print(f"  📈 Total fichiers testés: {total}")
    print(f"  ✅ Fichiers avec tests réussis: {successful}")
    print(f"  ❌ Fichiers avec tests échoués: {total - successful}")
    print(f"  🎯 Taux de réussite: {(successful/max(total, 1))*100:.1f}%")
    
    return results

def test_on_fixed_files():
    """Test 3: Validation des fichiers corrigés par le Fixer."""
    
    print_banner("TEST 3: VALIDATION DES FICHIERS CORRIGÉS")
    
    load_dotenv()
    
    # Chemin vers les fichiers corrigés
    script_dir = os.path.dirname(__file__)
    fixed_dir = os.path.abspath(os.path.join(script_dir, "../sandbox/fixed"))
    
    if not os.path.exists(fixed_dir):
        print("❌ Aucun dossier 'fixed' trouvé.")
        print("💡 Exécutez d'abord le Fixer pour générer des fichiers corrigés:")
        print("   python tests/test_fixer.py")
        return None
    
    # Lister les fichiers Python
    python_files = PyFileTool.list_python_files(fixed_dir)
    
    if not python_files:
        print("❌ Aucun fichier Python trouvé dans fixed/")
        return None
    
    print(f"📁 Dossier: {fixed_dir}")
    print(f"🔍 {len(python_files)} fichier(s) corrigé(s) à valider")
    
    # Initialiser le Judge
    judge = Judge()
    
    if judge.llm:
        print("🤖 Mode: Génération de tests avec AI")
    else:
        print("⚠️ Mode: Génération de tests basiques (sans AI)")
    
    results = []
    
    for i, file_path in enumerate(python_files, 1):
        print(f"\n{'─'*80}")
        print(f"[{i}/{len(python_files)}] {os.path.basename(file_path)}")
        
        try:
            result = judge.evaluate_file(file_path)
            results.append(result)
            
            # Afficher un résumé détaillé
            status = "✅" if result.get('success') else "❌"
            print(f"  {status} Résultat: {'Tests passés' if result.get('success') else 'Tests échoués'}")
            print(f"  📊 Tests: {result.get('passed', 0)} passés, {result.get('failed', 0)} échoués, {result.get('errors', 0)} erreurs")
            
            if result.get('ai_used') is not None:
                print(f"  🤖 AI utilisée: {'OUI' if result['ai_used'] else 'NON'}")
            
        except Exception as e:
            print(f"  ⚠️ Erreur: {e}")
            results.append({
                "file": file_path,
                "success": False,
                "error": str(e)
            })
    
    # Rapport détaillé
    successful = sum(1 for r in results if r.get("success", False))
    total = len(results)
    total_tests = sum(r.get("total", 0) for r in results)
    total_passed = sum(r.get("passed", 0) for r in results)
    
    print(f"\n{'='*80}")
    print(f"📊 RAPPORT FINAL DE VALIDATION:")
    print(f"  📈 Total fichiers: {total}")
    print(f"  ✅ Fichiers validés (tests OK): {successful}")
    print(f"  ❌ Fichiers non validés: {total - successful}")
    print(f"  🎯 Taux de validation: {(successful/max(total, 1))*100:.1f}%")
    print(f"  📝 Total tests exécutés: {total_tests}")
    print(f"  ✔️  Tests passés: {total_passed}/{total_tests}")
    
    # Sauvegarder le rapport
    os.makedirs("logs", exist_ok=True)
    report_path = os.path.join("logs", "judge_validation_report.json")
    
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "directory": fixed_dir,
        "summary": {
            "total_files": total,
            "files_validated": successful,
            "files_failed": total - successful,
            "validation_rate": f"{(successful/max(total, 1))*100:.1f}%",
            "total_tests": total_tests,
            "tests_passed": total_passed,
            "test_success_rate": f"{(total_passed/max(total_tests, 1))*100:.1f}%"
        },
        "files": results
    }
    
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n💾 Rapport détaillé sauvegardé: {report_path}")
    
    return results

def main():
    """Menu principal."""
    
    print_banner("🧑‍⚖️ TEST DU JUDGE AGENT - TDD")
    
    print("\nCe script teste le Judge Agent conformément aux exigences:")
    print("  • Génération automatique de tests unitaires (avec ou sans AI)")
    print("  • Exécution des tests avec pytest")
    print("  • Validation des corrections du Fixer")
    print("  • Approche TDD (Test-Driven Development)")
    
    # Afficher l'état des API
    has_api = print_api_status()
    
    print("\n📋 OPTIONS DE TEST:")
    print("1. Test simple (code basique avec fonctions)")
    print("2. Test sur les fichiers du sandbox (bugs originaux)")
    print("3. Test de validation (fichiers corrigés par le Fixer)")
    print("4. Tout tester (options 1, 2 et 3)")
    print("5. Quitter")
    
    choice = input("\n👉 Votre choix (1-5): ").strip()
    
    if choice == "1":
        test_simple_code()
    elif choice == "2":
        test_on_sandbox_files()
    elif choice == "3":
        test_on_fixed_files()
    elif choice == "4":
        print("\n🚀 Exécution de tous les tests...\n")
        test_simple_code()
        time.sleep(2)
        test_on_sandbox_files()
        time.sleep(2)
        test_on_fixed_files()
    elif choice == "5":
        print("\n👋 Au revoir!")
        return
    else:
        print("❌ Choix invalide")
    
    print_banner("✨ TESTS TERMINÉS")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Tests interrompus par l'utilisateur")
    except Exception as e:
        print(f"\n❌ Erreur inattendue: {e}")
        import traceback
        traceback.print_exc()