"""
Agent Auditor - Analyse et détection de bugs dans le code Python
VERSION CORRIGÉE - Bug cache fixé
"""

import os
import json
import time
import hashlib
from typing import List, Dict
from dotenv import load_dotenv

from src.utils.file_manager import PyFileTool
from src.utils.logger import log_experiment, ActionType
from langchain_openai import ChatOpenAI
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.messages import AIMessageChunk


# ================================
# Configuration
# ================================
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("❌ OPENROUTER_API_KEY non trouvée dans .env")


class NonStreamingChatOpenAI(ChatOpenAI):
    """Wrapper qui force le non-streaming."""

    def _stream(self, messages, stop=None, run_manager=None, **kwargs):
        kwargs.pop("stream", None)
        kwargs["stream"] = False
        result = self._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
        message = result.generations[0].message
        chunk = ChatGenerationChunk(
            message=AIMessageChunk(
                content=message.content,
                additional_kwargs=message.additional_kwargs,
                id=message.id if hasattr(message, 'id') else None,
            )
        )
        yield chunk

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        kwargs.pop("stream", None)
        kwargs["stream"] = False
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


llm = NonStreamingChatOpenAI(
    model="meta-llama/llama-3.3-70b-instruct:free",
    api_key=OPENROUTER_API_KEY,
    temperature=0,
    base_url="https://openrouter.ai/api/v1",
    streaming=False,
    model_kwargs={},
)


# ================================
# Utilitaires
# ================================
def safe_parse_json(text: str) -> dict:
    """Parse JSON même avec markdown backticks."""
    try:
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            text = text[start:end].strip()
        return json.loads(text)
    except Exception as e:
        raise ValueError(f"JSON invalide: {e}")


class CodeAnalyzer:
    """Analyse statique du code Python."""
    
    @staticmethod
    def check_syntax(file_path: str) -> dict:
        """Vérifie la syntaxe Python."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                compile(f.read(), file_path, "exec")
            return {"valid": True, "error": None, "line": None}
        except SyntaxError as e:
            return {"valid": False, "error": e.msg, "line": e.lineno}
        except Exception as e:
            return {"valid": False, "error": str(e), "line": None}


# ================================
# Agent Auditor
# ================================
class Auditor:
    """Agent d'audit de code Python."""
    
    def __init__(self):
        self.name = "Auditor"
        self.llm = llm
        self.llm_cache = {}  # ✅ Cache initialisé
        
    def build_prompt(self, file_path: str, code: str, additional_context: str = "") -> str:
        """Construit le prompt d'analyse."""
        
        prompt = f"""You are a senior Python code auditor.

Analyze the following Python file and return ONLY valid JSON with:
- bugs (list with line, severity, description, suggestion)
- quality_issues (list)
- style_issues (list)
- refactoring_plan (list of steps)
- score (number between 0 and 10)

IMPORTANT: 
- Score must be 0-10 (NOT 0-100)
- Only report bugs that ACTUALLY exist in THIS file
- Do NOT reuse issues from other files

File: {file_path}

CODE:
```python
{code}
```
"""
        
        if additional_context:
            prompt += f"\n\nADDITIONAL CONTEXT:\n{additional_context}\n"
        
        return prompt
    
    def detect_generic_patterns(self, code: str) -> List[Dict]:
        """Détecte des patterns de bugs courants."""
        
        issues = []
        lines = code.splitlines()
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            if not stripped or stripped.startswith("#"):
                continue
            
            # Pattern 1: Division par zéro
            if "/" in line and "//" not in line:
                context = "\n".join(lines[max(0, i-5):i+2])
                if "== 0" not in context and "!= 0" not in context:
                    issues.append({
                        "line": i,
                        "severity": "HIGH",
                        "description": "Division possible par zéro",
                        "suggestion": "Ajouter une vérification != 0"
                    })
            
            # Pattern 2: Argument mutable par défaut
            if "def " in line and any(x in line for x in ["=[]", "={}"]):
                issues.append({
                    "line": i,
                    "severity": "HIGH",
                    "description": "Argument mutable par défaut (antipattern)",
                    "suggestion": "Utiliser None puis initialiser"
                })
        
        return issues
    
    def create_fallback_analysis(
        self, 
        file_path: str, 
        reason: str, 
        code: str, 
        pattern_issues: List[Dict] = None
    ) -> Dict:
        """Crée une analyse de secours si le LLM échoue."""
        
        issues = pattern_issues if pattern_issues else self.detect_generic_patterns(code)
        
        log_experiment(
            agent_name=self.name,
            model_used="fallback",
            action=ActionType.ANALYSIS,
            details={
                "file_analyzed": file_path,
                "input_prompt": "FALLBACK MODE",
                "output_response": reason,
                "issues_found": len(issues)
            },
            status="SUCCESS"
        )
        
        return {
            "file_path": file_path,
            "bugs": issues,
            "quality_issues": [],
            "style_issues": [],
            "refactoring_plan": ["Corriger erreurs", "Appliquer PEP8"],
            "score": 3.0,
            "fallback_reason": reason
        }
    
    def analyze_file(self, file_path: str) -> Dict:
        """
        Analyse un fichier Python complet.
        
        Returns:
            Dict contenant le rapport d'audit complet
        """
        
        print(f"\n🔍 Analyse: {file_path}")
        
        # 1. Lecture du fichier
        try:
            code = PyFileTool.read_file(file_path)
        except Exception as e:
            return self.create_fallback_analysis(
                file_path, 
                f"Lecture échouée: {e}", 
                ""
            )
        
        # 2. Vérification syntaxe
        syntax_res = CodeAnalyzer.check_syntax(file_path)
        
        # 3. Détection de patterns
        pattern_issues = self.detect_generic_patterns(code)
        
        # 4. Contexte additionnel
        additional_context = ""
        
        if pattern_issues:
            additional_context += "PATTERNS DÉTECTÉS:\n"
            for p in pattern_issues:
                additional_context += f"Line {p['line']}: {p['description']}\n"
        
        if not syntax_res["valid"]:
            additional_context += f"\nSyntax Error Line {syntax_res['line']}: {syntax_res['error']}\n"
        
        # 5. ✅ FIX: Calculer code_hash AVANT de l'utiliser
        code_hash = hashlib.md5(code.encode()).hexdigest()
        
        # 6. Analyse LLM
        try:
            # Vérifier le cache
            if code_hash in self.llm_cache:
                print("  ⚡ Cache hit")
                llm_result = self.llm_cache[code_hash]
            else:
                # Appel LLM
                prompt = self.build_prompt(file_path, code, additional_context)
                
                response = self.llm.invoke(prompt)
                raw_text = " ".join(response.content) if isinstance(response.content, list) else str(response.content)
                
                # Parse JSON
                llm_result = safe_parse_json(raw_text)
                
                # ✅ FIX: Maintenant code_hash existe
                self.llm_cache[code_hash] = llm_result
            
            # 7. Combiner résultats
            report = {
                "file_path": file_path,
                "bugs": pattern_issues + llm_result.get("bugs", []),
                "quality_issues": llm_result.get("quality_issues", []),
                "style_issues": llm_result.get("style_issues", []),
                "refactoring_plan": llm_result.get("refactoring_plan", []),
                "score": llm_result.get("score", 3.0)
            }
            
            # 8. Logging
            log_experiment(
                agent_name=self.name,
                model_used="meta-llama/llama-3.3-70b-instruct:free",
                action=ActionType.ANALYSIS,
                details={
                    "file_analyzed": file_path,
                    "input_prompt": prompt[:500] + "...",
                    "output_response": str(llm_result)[:500] + "...",
                    "issues_found": len(report.get("bugs", []))
                },
                status="SUCCESS"
            )
            
            print(f"  ✅ Score: {report['score']}/10, Bugs: {len(report['bugs'])}")
            return report
            
        except Exception as e:
            print(f"  ❌ Erreur LLM: {e}")
            return self.create_fallback_analysis(
                file_path, 
                f"LLM failed: {e}", 
                code, 
                pattern_issues
            )
    
    def analyze_directory(self, dir_path: str) -> List[Dict]:
        """Analyse tous les fichiers Python d'un dossier."""
        
        files = PyFileTool.list_python_files(dir_path)
        
        if not files:
            print(f"⚠️ Aucun fichier Python dans {dir_path}")
            return []
        
        print(f"\n📊 Analyse de {len(files)} fichier(s)\n")
        
        results = []
        for i, file in enumerate(files, 1):
            print(f"[{i}/{len(files)}]", end=" ")
            results.append(self.analyze_file(file))
            
            # Pause pour éviter rate limiting
            if i < len(files):
                time.sleep(3)
        
        return results
    
    def generate_report(self, analyses: List[Dict]) -> Dict:
        """Génère un rapport de synthèse."""
        
        total_bugs = sum(len(a.get("bugs", [])) for a in analyses)
        total_quality = sum(len(a.get("quality_issues", [])) for a in analyses)
        avg_score = sum(a.get("score", 0) for a in analyses) / max(len(analyses), 1)
        
        return {
            "summary": {
                "total_files": len(analyses),
                "total_bugs": total_bugs,
                "total_quality_issues": total_quality,
                "average_score": round(avg_score, 2)
            },
            "files": analyses
        }