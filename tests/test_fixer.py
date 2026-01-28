#!/usr/bin/env python3
"""
Test du Judge Agent avec AI
Usage: python tests/test_judge.py
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

def test_simple_ai_generation():
    """Test simple de génération de tests avec AI."""
    
    print("\n" + "="*80)
    print("🤖 TEST DE GÉNÉRATION DE TESTS AVEC AI")
    print("="*80)
    
    load_dotenv()
    
    # Obtenez une clé Google Gemini gratuite: https://makersuite.google.com/app/apikey
    # Ajoutez dans .env: GOOGLE_API_KEY=votre_clé
    
    google_api_key = os.getenv("GOOGLE_API_KEY")
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    
    if not google_api_key and not openrouter_api_key:
        print("⚠️ Aucune clé API trouvée. Solutions gratuites:")
        print("   1. Google Gemini (recommandé): https://makersuite.google.com/app/apikey")
        print("   2. OpenRouter: https://openrouter.ai/")
        print("\nPour continuer sans AI, des tests basiques seront générés.")
    
    try:
        # Initialiser le Judge
        judge = Judge()
        
        # Code de test simple
        test_code = """
def add(a, b):
    '''Additionne deux nombres.'''
    return a + b

def divide(a, b):
    '''Divise a par b.'''
    return a / b

def safe_divide(a, b):
    '''Divise a par b avec vérification.'''
    if b == 0:
        raise ValueError("Division by zero")
    return a / b
"""
        
        # Sauvegarder dans un fichier temporaire
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(test_code)
            temp_file = f.name
        
        try:
            print(f"📄 Fichier de test: {temp_file}")
            
            # Tester la génération de tests
            if judge.llm:
                print("✅ AI disponible, génération de tests avec AI...")
                test_code, success = judge.generate_unit_tests_with_ai(test_code, temp_file)
            else:
                print("⚠️ AI non disponible, génération de tests basiques...")
                test_code, success = judge.generate_fallback_tests(test_code, temp_file)
            
            if success:
                print(f"✅ Tests générés avec succès!")
                print(f"📝 Code de test généré (premières 20 lignes):")
                lines = test_code.split('\n')
                for i, line in enumerate(lines[:20], 1):
                    print(f"  {i:2d}: {line}")
                if len(lines) > 20:
                    print(f"  ... ({len(lines)-20} lignes supplémentaires)")
                
                # Sauvegarder et exécuter
                test_path = judge.save_test_file(test_code, temp_file)
                print(f"\n💾 Tests sauvegardés: {test_path}")
                
                # Exécuter les tests
                print("🚀 Exécution des tests...")
                result = judge.run_tests(test_path, temp_file)
                
                print(f"\n📊 Résultat: {'✅ SUCCÈS' if result['success'] else '❌ ÉCHEC'}")
                if result.get('stdout'):
                    print(f"📋 Sortie des tests:")
                    print(result['stdout'][:500])
            else:
                print("❌ Échec de la génération des tests")
                
        finally:
            # Nettoyer
            os.unlink(temp_file)
            
    except Exception as e:
        print(f"❌ Erreur lors du test: {e}")
        import traceback
        traceback.print_exc()

def test_on_fixed_files():
    """Test sur les fichiers corrigés par le Fixer."""
    
    print("\n" + "="*80)
    print("🔍 TEST SUR LES FICHIERS CORRIGÉS")
    print("="*80)
    
    load_dotenv()
    
    # Chemin vers les fichiers corrigés
    script_dir = os.path.dirname(__file__)
    fixed_dir = os.path.abspath(os.path.join(script_dir, "../sandbox/fixed"))
    
    if not os.path.exists(fixed_dir):
        print("❌ Aucun dossier 'fixed' trouvé.")
        print("💡 Exécutez d'abord le Fixer: python tests/test_fixer.py (choisissez option 2)")
        return
    
    # Lister les fichiers Python
    python_files = PyFileTool.list_python_files(fixed_dir)
    
    if not python_files:
        print("❌ Aucun fichier Python trouvé dans 'fixed/'")
        return
    
    print(f"📁 Dossier: {fixed_dir}")
    print(f"🔍 {len(python_files)} fichier(s) trouvé(s)")
    
    # Initialiser le Judge
    try:
        judge = Judge()
        
        if judge.llm:
            print("🤖 Mode: Génération de tests avec AI")
        else:
            print("⚠️ Mode: Génération de tests basiques (AI non disponible)")
            print("💡 Pour activer l'AI, ajoutez une clé Google Gemini dans .env")
        
        results = []
        
        for i, file_path in enumerate(python_files, 1):
            print(f"\n[{i}/{len(python_files)}] Traitement: {os.path.basename(file_path)}")
            
            try:
                result = judge.evaluate_file(file_path)
                results.append(result)
                
                status = "✅" if result.get('success') else "❌"
                print(f"  {status} {'Tests passés' if result.get('success') else 'Tests échoués'}")
                
                if result.get('ai_used') is not None:
                    print(f"  🤖 AI utilisée: {'OUI' if result['ai_used'] else 'NON'}")
                
            except Exception as e:
                print(f"  ⚠️ Erreur: {e}")
                results.append({
                    "file": file_path,
                    "success": False,
                    "error": str(e)
                })
        
        # Rapport
        successful = sum(1 for r in results if r.get("success", False))
        total = len(results)
        
        print(f"\n📊 RAPPORT FINAL:")
        print(f"  📈 Total fichiers: {total}")
        print(f"  ✅ Tests réussis: {successful}")
        print(f"  ❌ Tests échoués: {total - successful}")
        print(f"  🎯 Taux de réussite: {(successful/max(total, 1))*100:.1f}%")
        
        # Sauvegarder le rapport
        os.makedirs("logs", exist_ok=True)
        report_path = os.path.join("logs", "judge_test_results.json")
        
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "directory": fixed_dir,
            "summary": {
                "total_files": total,
                "successful_tests": successful,
                "failed_tests": total - successful,
                "success_rate": f"{(successful/max(total, 1))*100:.1f}%"
            },
            "files": results
        }
        
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2)
        
        print(f"\n💾 Rapport sauvegardé: {report_path}")
        
    except Exception as e:
        print(f"❌ Erreur lors du test: {e}")

def main():
    """Menu principal de test."""
    
    print("\n" + "="*80)
    print("🧑‍⚖️ MENU DE TEST DU JUDGE AGENT")
    print("="*80)
    
    load_dotenv()
    
    # Vérifier les clés API
    google_api_key = os.getenv("GOOGLE_API_KEY")
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    
    print("\n🔑 ÉTAT DES CLÉS API:")
    if google_api_key:
        print("  ✅ Google Gemini API: Configurée")
    else:
        print("  ❌ Google Gemini API: Non configurée")
        print("     💡 Obtenez une clé gratuite: https://makersuite.google.com/app/apikey")
    
    if openrouter_api_key:
        print("  ✅ OpenRouter API: Configurée")
    else:
        print("  ❌ OpenRouter API: Non configurée")
        print("     💡 Créez un compte: https://openrouter.ai/")
    
    if not google_api_key and not openrouter_api_key:
        print("\n⚠️ ATTENTION: Aucune clé API configurée!")
        print("Le Judge fonctionnera en mode basique sans AI.")
    
    print("\n📋 OPTIONS DE TEST:")
    print("1. Test simple de génération de tests avec AI")
    print("2. Test sur les fichiers corrigés (dossier 'fixed/')")
    print("3. Quitter")
    
    choice = input("\n👉 Votre choix (1-3): ").strip()
    
    if choice == "1":
        test_simple_ai_generation()
    elif choice == "2":
        test_on_fixed_files()
    elif choice == "3":
        print("\n👋 Au revoir!")
        return
    else:
        print("❌ Choix invalide")
    
    print("\n" + "="*80)
    print("✨ TEST TERMINÉ!")
    print("="*80)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⏹️  Test interrompu par l'utilisateur")
    except Exception as e:
        print(f"\n❌ Erreur inattendue: {e}")
        import traceback
        traceback.print_exc()