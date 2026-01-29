import os
import json
import time
from typing import Dict, List, Optional
from dotenv import load_dotenv

from src.utils.file_manager import PyFileTool
from src.utils.fixer_tools import FixerTools
from src.utils.logger import log_experiment, ActionType
from langchain_openai import ChatOpenAI
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.messages import AIMessageChunk
from src.utils.rate_limiter import RateLimiter, RateLimitConfig

# ================================
# Load API key OpenRouter
# ================================
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("❌ OPENROUTER_API_KEY non trouvée dans .env")

# ================================
# LLM Wrapper non-streaming
# ================================
class NonStreamingChatOpenAI(ChatOpenAI):
    """Wrapper qui force le non-streaming pour compatibilité outils."""

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
# JSON parser robuste
# ================================
def safe_parse_json(text: str) -> dict:
    """Parse JSON même avec markdown backticks."""
    try:
        # Enlever les balises markdown
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
        raise ValueError(f"JSON invalide: {e}\nTexte reçu: {text[:200]}...")

# ================================
# Fixer Agent
# ================================
class Fixer:
    """
    Agent Fixer : corrige le code Python basé sur le rapport de l'Auditor.
    
    Stratégie:
    1. Lit le rapport d'audit (bugs, quality_issues, refactoring_plan)
    2. Pour chaque fichier, génère une version corrigée
    3. Valide le code corrigé (syntaxe)
    4. Log toutes les opérations
    """
    
    def __init__(self, max_retries: int = 3, rate_limiter=None):
        self.name = "Fixer"
        self.llm = llm
        self.max_retries = max_retries
        self.tools = FixerTools()
        self.llm_cache = {}  # Cache pour éviter quota
        self.rate_limiter = rate_limiter
        if not self.rate_limiter:
            config = RateLimitConfig(
                requests_per_minute=20,
                base_delay=3.0,
                retry_attempts=3,
            )
            self.rate_limiter = RateLimiter(config)

    def build_fix_prompt(
        self, 
        file_path: str, 
        code: str, 
        audit_report: Dict,
        iteration: int = 1,
        previous_error: Optional[str] = None
    ) -> str:
        """Construit le prompt pour corriger le code."""
        
        bugs = audit_report.get("bugs", [])
        quality_issues = audit_report.get("quality_issues", [])
        style_issues = audit_report.get("style_issues", [])
        refactoring_plan = audit_report.get("refactoring_plan", [])
   # ===============================
   #the PROMPT PART 
   # ===============================     
        prompt = f"""You are a senior Python developer specialized in code refactoring.

Your mission: Fix the following Python file based on the audit report.

FILE: {file_path}
ITERATION: {iteration}/{self.max_retries}

ORIGINAL CODE:
```python
{code}
```

AUDIT REPORT:
- Bugs found: {len(bugs)}
- Quality issues: {len(quality_issues)}
- Style issues: {len(style_issues)}

DETAILED ISSUES:
"""
        
        # Ajouter les bugs
        if bugs:
            prompt += "\n🐛 BUGS (HIGH PRIORITY):\n"
            for bug in bugs:
                prompt += f"  Line {bug.get('line', '?')}: {bug.get('description', 'N/A')}\n"
                prompt += f"  Suggestion: {bug.get('suggestion', 'N/A')}\n\n"
        
        # Ajouter les quality issues
        if quality_issues:
            prompt += "\n⚠️ QUALITY ISSUES:\n"
            for issue in quality_issues[:5]:  # Limite à 5 pour pas surcharger
                prompt += f"  Line {issue.get('line', '?')}: {issue.get('description', 'N/A')}\n"
        
        # Ajouter le plan de refactoring
        if refactoring_plan:
            prompt += "\n📋 REFACTORING PLAN:\n"
            for i, step in enumerate(refactoring_plan, 1):
                prompt += f"  {i}. {step}\n"
        
        # Si erreur précédente (retry)
        if previous_error:
            prompt += f"\n\n❌ PREVIOUS ATTEMPT FAILED:\n{previous_error}\n"
            prompt += "Please fix this error in your new version.\n"
        
        prompt += """

REQUIREMENTS:

Step-by-step instructions for you:

a) Fix all syntax errors first (missing colons, parentheses, indentation, etc.) to make the code parseable.
b) Apply all bug fixes as suggested by the Auditor.
c) Resolve critical quality issues if possible.
d) Ensure PEP8 formatting, proper docstrings, and readability.

Output format:

Return a JSON object with the following structure:

{
"fixed_code": "<valid Python code here>",
"changes_made": ["List of changes applied, e.g., 'Added missing parenthesis', 'Fixed colon in function definition'"],
"confidence": 0.95
}

The "fixed_code" field should be valid Python code.

You can use multi-line strings or escaped newlines (\n) depending on parser requirements.

Do NOT include explanations outside the JSON.

Do NOT use markdown backticks in the JSON.

Do NOT add comments outside the "changes_made" list.

Important notes:

If the input code has syntax errors, fix them first before applying logical or semantic fixes.

Only output valid JSON. Prioritize syntactically correct Python in "fixed_code".

Keep the original functionality intact while applying the suggested fixes.

Return ONLY the JSON object as specified.
"""
        
        return prompt


        #finished prompt part
        # ===============================
    
    def validate_fixed_code(self, code: str, file_path: str) -> Dict:
        """Valide que le code corrigé est syntaxiquement correct."""
        return self.tools.check_syntax(code, file_path)
    
    def fix_file(
        self, 
        file_path: str, 
        audit_report: Dict,
        output_dir: str = None
    ) -> Dict:
        """
        Corrige un fichier basé sur le rapport d'audit.
        
        Args:
            file_path: Chemin du fichier à corriger
            audit_report: Rapport d'audit de ce fichier
            output_dir: Dossier de sortie (optionnel, sinon écrase l'original)
            
        Returns:
            Dict avec le résultat de la correction
        """
        
        # Lire le code original
        try:
            original_code = PyFileTool.read_file(file_path)
        except Exception as e:
            error_msg = f"Impossible de lire {file_path}: {e}"
            log_experiment(
                agent_name=self.name,
                model_used="N/A",
                action=ActionType.FIX,
                details={
                    "file_fixed": file_path,
                    "input_prompt": "N/A",
                    "output_response": error_msg,
                    "error": str(e)
                },
                status="FAILURE"
            )
            return {
                "file_path": file_path,
                "success": False,
                "error": error_msg,
                "original_code": "",
                "fixed_code": ""
            }
        
        # Cache key
        cache_key = hash(original_code + str(audit_report))
        
        previous_error = None
        
        # Boucle de retry
        # here modifications for the rate limiter (just added in)
        for iteration in range(1, self.max_retries + 1):
            try:
                # Vérifier le cache
                if cache_key in self.llm_cache and iteration == 1:
                    print(f"  ⚡ Cache hit pour {file_path}")
                    llm_result = self.llm_cache[cache_key]
                else:
                    # Construire le prompt
                    prompt = self.build_fix_prompt(
                        file_path, 
                        original_code, 
                        audit_report,
                        iteration,
                        previous_error
                    )
                    
                    print(f"  🔧 Tentative {iteration}/{self.max_retries} pour {file_path}")
                    
                    # Appel LLM
                    # response = self.llm.invoke(prompt) replaced this line
                    def _call_llm():
                        return self.llm.invoke(prompt)
                    
                    response= self.rate_limiter.execute_with_rate_limit(
                        _call_llm,
                        agent_name=self.name
                    )
                    #done modifying
                    raw_text = " ".join(response.content) if isinstance(response.content, list) else str(response.content)
                    
                    # Parse JSON
                    llm_result = safe_parse_json(raw_text)
                    
                    # Cache si première tentative
                    if iteration == 1:
                        self.llm_cache[cache_key] = llm_result
                
                # Extraire le code corrigé
                fixed_code = llm_result.get("fixed_code", "")
                changes_made = llm_result.get("changes_made", [])
                confidence = llm_result.get("confidence", 0.0)
                
                if not fixed_code:
                    raise ValueError("Le LLM n'a pas retourné de code corrigé")
                
                # Valider syntaxe
                validation = self.validate_fixed_code(fixed_code, file_path)
                
                if not validation["valid"]:
                    # Syntax error détectée, retry
                    previous_error = f"Syntax Error at line {validation.get('line', '?')}: {validation.get('error', 'Unknown')}"
                    print(f"  ❌ {previous_error}")
                    
                    if iteration < self.max_retries:
                        time.sleep(2)  # Pause avant retry
                        continue
                    else:
                        # Dernière tentative échouée
                        raise ValueError(f"Code invalide après {self.max_retries} tentatives: {previous_error}")
                
                # ✅ Code valide !
                
                # Sauvegarder le code corrigé
                if output_dir:
                    output_path = self.tools.save_fixed_file(
                        fixed_code, 
                        file_path, 
                        output_dir
                    )
                else:
                    # Écraser l'original (mode dangereux)
                    output_path = file_path
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(fixed_code)
                
                # Log succès
                log_experiment(
                    agent_name=self.name,
                    model_used="meta-llama/llama-3.3-70b-instruct:free",
                    action=ActionType.FIX,
                    details={
                        "file_fixed": file_path,
                        "input_prompt": prompt[:500] + "...",
                        "output_response": str(llm_result)[:500] + "...",
                        "changes_made": changes_made,
                        "confidence": confidence,
                        "iteration": iteration,
                        "output_path": output_path
                    },
                    status="SUCCESS"
                )
                
                return {
                    "file_path": file_path,
                    "output_path": output_path,
                    "success": True,
                    "original_code": original_code,
                    "fixed_code": fixed_code,
                    "changes_made": changes_made,
                    "confidence": confidence,
                    "iterations": iteration
                }
                
            except Exception as e:
                error_msg = f"Erreur à l'itération {iteration}: {e}"
                print(f"  ⚠️ {error_msg}")
                
                if iteration < self.max_retries:
                    previous_error = str(e)
                    time.sleep(2)
                    continue
                else:
                    # Échec définitif
                    log_experiment(
                        agent_name=self.name,
                        model_used="meta-llama/llama-3.3-70b-instruct:free",
                        action=ActionType.FIX,
                        details={
                            "file_fixed": file_path,
                            "input_prompt": "Multiple attempts failed",
                            "output_response": error_msg,
                            "error": str(e),
                            "iterations": iteration
                        },
                        status="FAILURE"
                    )
                    
                    return {
                        "file_path": file_path,
                        "success": False,
                        "error": error_msg,
                        "original_code": original_code,
                        "fixed_code": "",
                        "iterations": iteration
                    }
        
        # Ne devrait jamais arriver ici
        return {
            "file_path": file_path,
            "success": False,
            "error": "Max retries exceeded",
            "original_code": original_code,
            "fixed_code": ""
        }
    
    def fix_directory(
        self, 
        audit_results: List[Dict],
        output_dir: str
    ) -> List[Dict]:
        """
        Corrige tous les fichiers d'un dossier basé sur les résultats d'audit.
        
        Args:
            audit_results: Liste des rapports d'audit (depuis Auditor)
            output_dir: Dossier où sauvegarder les fichiers corrigés
            
        Returns:
            Liste des résultats de correction
        """
        
        # Créer le dossier de sortie
        os.makedirs(output_dir, exist_ok=True)
        
        results = []
        total_files = len(audit_results)
        
        print(f"\n🔧 Début de la correction de {total_files} fichier(s)...\n")
        
        for i, audit_report in enumerate(audit_results, 1):
            file_path = audit_report.get("file_path")
            
            if not file_path:
                print(f"⚠️ [{i}/{total_files}] Rapport sans file_path, ignoré")
                continue
            
            print(f"📝 [{i}/{total_files}] Correction de {file_path}")
            
            result = self.fix_file(file_path, audit_report, output_dir)
            results.append(result)
            
            # Pause pour éviter rate limiting
            if i < total_files:
                time.sleep(3)
        
        return results
    
    def generate_fix_report(self, fix_results: List[Dict]) -> Dict:
        """Génère un rapport de synthèse des corrections."""
        
        total_files = len(fix_results)
        successful = sum(1 for r in fix_results if r.get("success", False))
        failed = total_files - successful
        
        total_changes = sum(len(r.get("changes_made", [])) for r in fix_results)
        avg_confidence = sum(r.get("confidence", 0) for r in fix_results) / max(total_files, 1)
        
        report = {
            "summary": {
                "total_files": total_files,
                "successful_fixes": successful,
                "failed_fixes": failed,
                "success_rate": f"{(successful/max(total_files, 1))*100:.1f}%",
                "total_changes": total_changes,
                "average_confidence": round(avg_confidence, 2)
            },
            "files": fix_results
        }
        
        return report