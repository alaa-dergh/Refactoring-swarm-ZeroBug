"""
Wrapper pour Groq - ULTRA RAPIDE et GRATUIT
Remplace complètement Google Gemini
Compatible avec les agents Auditor, Fixer, Judge

Installation:
pip install groq

API Key gratuite: https://console.groq.com/
Limite: 30 requêtes/minute (vs 15 pour Gemini)
"""

import os
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class GeminiWrapper:  # ← Garde le même nom pour compatibilité!
    """
    Wrapper Groq déguisé en GeminiWrapper.
    100% compatible - aucun changement de code nécessaire.
    """
    
    def __init__(
        self,
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0,
        api_key: Optional[str] = None
    ):
        """
        Initialise le wrapper Groq.
        
        Args:
            model: Modèle à utiliser
                - llama-3.3-70b-versatile (RECOMMANDÉ - le meilleur)
                - mixtral-8x7b-32768 (très rapide)
                - llama-3.1-70b-versatile (alternative)
            temperature: Contrôle de la créativité (0 = déterministe)
            api_key: Clé API Groq (ou depuis .env)
        """
        try:
            from groq import Groq
        except ImportError:
            raise ImportError(
                "\n❌ Package 'groq' non installé.\n"
                "   Exécutez: pip install groq\n"
            )
        
        self.model_name = model
        self.temperature = temperature
        
        # Récupérer la clé API
        api_key = api_key or os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError(
                "\n❌ GROQ_API_KEY non trouvée dans .env\n"
                "   1. Créez une clé gratuite: https://console.groq.com/\n"
                "   2. Ajoutez dans .env: GROQ_API_KEY=votre_clé_ici\n"
            )
        
        # Créer le client Groq
        self.client = Groq(api_key=api_key)
        
        print(f"✅ Groq initialisé: {self.model_name}")
    
    def invoke(self, prompt: str) -> 'GeminiResponse':
        """
        Méthode compatible avec LangChain et GeminiWrapper.
        
        Args:
            prompt: Le prompt à envoyer
            
        Returns:
            GeminiResponse: Objet compatible
        """
        try:
            # Appeler Groq
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=self.temperature,
                max_tokens=8192
            )
            
            # Extraire le texte
            text = response.choices[0].message.content
            
            if not text:
                raise ValueError("Groq a retourné une réponse vide")
            
            # Retourner un objet compatible
            return GeminiResponse(text)
            
        except Exception as e:
            raise Exception(f"Erreur Groq: {e}")
    
    def _stream(self, *args, **kwargs):
        """Compatibilité avec NonStreamingChatOpenAI."""
        raise NotImplementedError("Streaming non supporté dans ce wrapper")
    
    def _generate(self, messages, *args, **kwargs):
        """Compatibilité avec NonStreamingChatOpenAI."""
        if messages and len(messages) > 0:
            prompt = messages[0] if isinstance(messages[0], str) else str(messages[0])
            return self.invoke(prompt)
        raise ValueError("Messages vides")


class GeminiResponse:
    """
    Objet de réponse compatible avec LangChain.
    """
    
    def __init__(self, text: str):
        self.text = text
        self.content = text
        self.additional_kwargs = {}
        self.id = None
    
    def __str__(self):
        return self.text
    
    def __repr__(self):
        return f"GeminiResponse(text={self.text[:50]}...)"


# ================================
# Factory pour créer le LLM
# ================================

def create_llm(
    use_gemini: bool = True,
    model: str = None,
    temperature: float = 0
):
    """
    Factory pour créer le LLM.
    Utilise maintenant Groq par défaut.
    
    Args:
        use_gemini: Ignoré - utilise toujours Groq
        model: Nom du modèle (auto si None)
        temperature: Température (0 = déterministe)
        
    Returns:
        Instance du LLM configuré
    """
    model = model or "llama-3.3-70b-versatile"
    return GeminiWrapper(
        model=model,
        temperature=temperature
    )


# ================================
# Instance globale (à utiliser dans les agents)
# ================================

try:
    llm = create_llm(use_gemini=True)
    print("🚀 LLM configuré: Groq (ULTRA RAPIDE + GRATUIT)")
except Exception as e:
    print(f"❌ Échec LLM: {e}")
    llm = None


# ================================
# Test rapide
# ================================

if __name__ == "__main__":
    print("\n" + "="*70)
    print("🧪 TEST DU WRAPPER GROQ")
    print("="*70 + "\n")
    
    try:
        wrapper = GeminiWrapper()
        print("✅ Connexion réussie!\n")
        
        print("📤 Envoi d'un test simple...")
        response = wrapper.invoke("Réponds juste: OK")
        print(f"📥 Réponse reçue: {response.text}\n")
        
        print("="*70)
        print("✅ GROQ FONCTIONNE PARFAITEMENT!")
        print("="*70)
        
    except Exception as e:
        print("="*70)
        print("❌ ERREUR")
        print("="*70)
        print(f"\n{str(e)}\n")
        print("💡 Vérifications:")
        print("   1. pip install groq")
        print("   2. GROQ_API_KEY dans votre .env")
        print("   3. Clé valide de: https://console.groq.com/\n")