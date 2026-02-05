"""
Script pour mettre à jour les noms de modèles dans tous les fichiers d'agents.
Remplace "gemini-1.5-flash" par "llama-3.3-70b-versatile"
"""

import os

def update_model_names():
    """Met à jour les noms de modèles dans les fichiers d'agents."""
    
    files_to_update = [
        "src/agents/auditor_agent.py",
        "src/agents/fixer_agent.py",
        "src/agents/judge_agent.py"
    ]
    
    print("="*70)
    print("🔧 MISE À JOUR DES NOMS DE MODÈLES")
    print("="*70)
    print()
    
    updated_count = 0
    
    for filepath in files_to_update:
        if not os.path.exists(filepath):
            print(f"⚠️  Fichier non trouvé: {filepath}")
            continue
        
        print(f"📝 Traitement de: {filepath}")
        
        try:
            # Lire le fichier
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Compter les occurrences
            old_pattern = 'model_used="gemini-1.5-flash"'
            new_pattern = 'model_used="llama-3.3-70b-versatile"'
            
            count = content.count(old_pattern)
            
            if count == 0:
                print(f"   ✅ Déjà à jour")
            else:
                # Remplacer
                new_content = content.replace(old_pattern, new_pattern)
                
                # Sauvegarder
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                
                print(f"   ✅ {count} occurrence(s) mise(s) à jour")
                updated_count += 1
        
        except Exception as e:
            print(f"   ❌ Erreur: {e}")
    
    print()
    print("="*70)
    print("📊 RÉSUMÉ")
    print("="*70)
    print(f"✅ {updated_count} fichier(s) mis à jour")
    print()
    
    if updated_count > 0:
        print("🎯 PROCHAINES ÉTAPES:")
        print("   1. Vérifiez que GROQ_API_KEY est dans votre .env")
        print("   2. Lancez: python main.py")
    
    print()

if __name__ == "__main__":
    update_model_names()