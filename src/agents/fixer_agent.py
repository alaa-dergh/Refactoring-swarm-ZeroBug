import os
import json
import time
from typing import Dict, List, Optional
from dotenv import load_dotenv

from src.utils.file_manager import PyFileTool
from src.utils.fixer_tools import FixerTools
from src.utils.logger import log_experiment, ActionType
from src.utils.groq_wrapper import llm  # ← MODIFIÉ: Utilise Gemini

# ================================
# Load environment
# ================================
load_dotenv()

# ================================
# JSON parser robuste
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
        raise ValueError(f"JSON invalide: {e}\nTexte reçu: {text[:200]}...")

# ================================
# Fixer Agent
# ================================
class Fixer:
    """
    Agent Fixer : corrige le code Python basé sur le rapport de l'Auditor.
    """
    
    def __init__(self, max_retries: int = 3):
        self.name = "Fixer"
        self.llm = llm  # ← MODIFIÉ: Utilise Gemini wrapper
        self.max_retries = max_retries
        self.tools = FixerTools()
        self.llm_cache = {}
        
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
        
        if bugs:
            prompt += "\n🐛 BUGS (HIGH PRIORITY):\n"
            for bug in bugs:
                prompt += f"  Line {bug.get('line', '?')}: {bug.get('description', 'N/A')}\n"
                prompt += f"  Suggestion: {bug.get('suggestion', 'N/A')}\n\n"
        
        if quality_issues:
            prompt += "\n⚠️ QUALITY ISSUES:\n"
            for issue in quality_issues[:5]:
                prompt += f"  Line {issue.get('line', '?')}: {issue.get('description', 'N/A')}\n"
        
        if refactoring_plan:
            prompt += "\n📋 REFACTORING PLAN:\n"
            for i, step in enumerate(refactoring_plan, 1):
                prompt += f"  {i}. {step}\n"
        
        if previous_error:
            prompt += f"\n\n❌ PREVIOUS ATTEMPT FAILED:\n{previous_error}\n"
            prompt += "Please fix this error in your new version.\n"
        
        prompt += """

REQUIREMENTS:

1. Return ONLY valid JSON with this structure:
{
  "fixed_code": "def example():\\n    return 42",
  "changes_made": ["Added zero check"],
  "confidence": 0.95
}

CRITICAL: Use \\n for newlines, \\t for tabs in the fixed_code string.

2. The fixed_code must be:
   - Syntactically valid Python
   - All bugs fixed
   - All critical issues resolved
   - Well-formatted (PEP8)
   - With proper docstrings

3. DO NOT include markdown backticks in the JSON response
4. DO NOT add explanations outside the JSON

Return ONLY the JSON object.
"""
        
        return prompt
    
    def validate_fixed_code(self, code: str, file_path: str) -> Dict:
        """Valide que le code corrigé est syntaxiquement correct."""
        return self.tools.check_syntax(code, file_path)
    
    def fix_file(
        self, 
        file_path: str, 
        audit_report: Dict,
        output_dir: str = None
    ) -> Dict:
        """Corrige un fichier basé sur le rapport d'audit."""
        
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
        
        cache_key = hash(original_code + str(audit_report))
        previous_error = None
        
        for iteration in range(1, self.max_retries + 1):
            try:
                if cache_key in self.llm_cache and iteration == 1:
                    print(f"  ⚡ Cache hit pour {file_path}")
                    llm_result = self.llm_cache[cache_key]
                else:
                    prompt = self.build_fix_prompt(
                        file_path, 
                        original_code, 
                        audit_report,
                        iteration,
                        previous_error
                    )
                    
                    print(f"  🔧 Tentative {iteration}/{self.max_retries} pour {file_path}")
                    
                    # Appel LLM (Gemini)
                    response = self.llm.invoke(prompt)
                    raw_text = response.content if hasattr(response, 'content') else str(response)
                    
                    llm_result = safe_parse_json(raw_text)
                    
                    if iteration == 1:
                        self.llm_cache[cache_key] = llm_result
                
                fixed_code = llm_result.get("fixed_code", "")
                changes_made = llm_result.get("changes_made", [])
                confidence = llm_result.get("confidence", 0.0)
                
                if not fixed_code:
                    raise ValueError("Le LLM n'a pas retourné de code corrigé")
                
                validation = self.validate_fixed_code(fixed_code, file_path)
                
                if not validation["valid"]:
                    previous_error = f"Syntax Error at line {validation.get('line', '?')}: {validation.get('error', 'Unknown')}"
                    print(f"  ❌ {previous_error}")
                    
                    if iteration < self.max_retries:
                        time.sleep(2)
                        continue
                    else:
                        raise ValueError(f"Code invalide après {self.max_retries} tentatives: {previous_error}")
                
                # Code valide!
                if output_dir:
                    output_path = self.tools.save_fixed_file(
                        fixed_code, 
                        file_path, 
                        output_dir
                    )
                else:
                    output_path = file_path
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(fixed_code)
                
                log_experiment(
                    agent_name=self.name,
                    model_used="llama-3.3-70b-versatile",
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
                    log_experiment(
                        agent_name=self.name,
                        model_used="llama-3.3-70b-versatile",
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
        """Corrige tous les fichiers d'un dossier."""
        
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
            
            if i < total_files:
                time.sleep(2)  # Pause raisonnable (Gemini est généreux)
        
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