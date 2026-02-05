import os
import json
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from dotenv import load_dotenv
import requests
from src.utils.file_manager import PyFileTool
from src.utils.fixer_tools import FixerTools
from src.utils.logger import log_experiment, ActionType
from src.utils.groq_wrapper import llm

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

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

def call_openrouter(prompt: str) -> str:
    """Appelle OpenRouter comme fallback LLM."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set in environment")
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://github.com/yourusername/refactoring-swarm",
        "X-Title": "Refactoring Swarm",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "meta-llama/llama-3.1-70b-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 2048
    }
    try:
        response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        raise ValueError(f"OpenRouter API error: {e}")

class Fixer:
    """Agent Fixer : corrige le code Python basé sur le rapport de l'Auditor."""
    
    def __init__(self, max_retries: int = 3):
        self.name = "Fixer"
        self.llm = llm
        self.max_retries = max_retries
        self.tools = FixerTools()
        self.llm_cache = {}
        self.rate_limit_reset = None
        
    def build_fix_prompt(self, file_path: str, code: str, audit_report: Dict, iteration: int = 1, previous_error: Optional[str] = None) -> str:
        """Construit le prompt pour corriger le code (tokens optimisés)."""
        bugs = audit_report.get("bugs", [])[:3]
        quality_issues = audit_report.get("quality_issues", [])[:2]
        refactoring_plan = audit_report.get("refactoring_plan", [])[:3]
        
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
- Style issues: {len(audit_report.get("style_issues", []))}

DETAILED ISSUES:
"""
        if bugs:
            prompt += "\n🐛 BUGS (HIGH PRIORITY):\n"
            for bug in bugs:
                prompt += f"  Line {bug.get('line', '?')}: {bug.get('description', 'N/A')}\n"
                prompt += f"  Suggestion: {bug.get('suggestion', 'N/A')}\n\n"
        
        if quality_issues:
            prompt += "\n⚠️ QUALITY ISSUES:\n"
            for issue in quality_issues:
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

Return ONLY valid JSON with this structure:
{
  "fixed_code": "def example():\\n    return 42",
  "changes_made": ["Added zero check"],
  "confidence": 0.95
}
CRITICAL: Use \\n for newlines, \\t for tabs in the fixed_code string.

The fixed_code must be:
- Syntactically valid Python
- All bugs fixed
- All critical issues resolved
- Well-formatted (PEP8)
- With proper docstrings

DO NOT include markdown backticks in the JSON response.
DO NOT add explanations outside the JSON.
Return ONLY the JSON object.
"""
        
        return prompt.strip()

    def validate_fixed_code(self, code: str, file_path: str) -> Dict:
        """Valide que le code corrigé est syntaxiquement correct."""
        return self.tools.check_syntax(code, file_path)

    def apply_basic_fixes(self, code: str) -> str:
        """Minimal fallback modifications."""
        if not isinstance(code, str):
            return ""
        c = code.replace("\r\n", "\n").replace("\r", "\n")
        c = c.replace("\t", "    ")
        c = c.replace("\x00", "")
        lines = c.split("\n")
        cleaned = [ln.rstrip() for ln in lines]
        out = "\n".join(cleaned).rstrip() + "\n"
        return out

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
        last_exception = None
        prompt = "(not generated)"
        use_openrouter = False
        
        for iteration in range(1, self.max_retries + 1):
            try:
                # Support cached entries that include both prompt and result
                if cache_key in self.llm_cache and iteration == 1:
                    print(f"  ⚡ Cache hit pour {file_path}")
                    cache_entry = self.llm_cache[cache_key]
                    prompt = cache_entry.get("prompt", "(cached_result)")
                    llm_result = cache_entry.get("result", {})
                else:
                    prompt = self.build_fix_prompt(
                        file_path, 
                        original_code, 
                        audit_report,
                        iteration,
                        previous_error
                    )
                    
                    print(f"  🔧 Tentative {iteration}/{self.max_retries} pour {file_path}")
                    
                    if use_openrouter:
                        print(f"  🔌 Utilisation d'OpenRouter (fallback)")
                        raw_text = call_openrouter(prompt)
                    else:
                        response = self.llm.invoke(prompt)
                        raw_text = response.content if hasattr(response, 'content') else str(response)
                    
                    llm_result = safe_parse_json(raw_text)
                    
                    if iteration == 1:
                        # Store both prompt and result so future cache hits include the prompt
                        self.llm_cache[cache_key] = {"prompt": prompt, "result": llm_result}
                
                # Ensure llm_result is a dict even if cache produced None
                if not isinstance(llm_result, dict):
                    raise ValueError("Le LLM n'a pas retourné un JSON valide")
                
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
                
                safe_input_prompt = prompt if isinstance(prompt, str) else "(generated prompt)"
                safe_output_response = str(llm_result) if llm_result is not None else ""
                model_used = "openrouter" if use_openrouter else "llama-3.3-70b-versatile"
                
                log_experiment(
                    agent_name=self.name,
                    model_used=model_used,
                    action=ActionType.FIX,
                    details={
                        "file_fixed": file_path,
                        "input_prompt": safe_input_prompt[:500] + ("..." if len(safe_input_prompt) > 500 else ""),
                        "output_response": safe_output_response[:500] + ("..." if len(safe_output_response) > 500 else ""),
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
                last_exception = e
                err_str = str(e)
                print(f"  ⚠️ Erreur à l'itération {iteration}: {err_str}")
                
                if not use_openrouter and iteration == 2:
                    print(f"  🔌 Basculement vers OpenRouter")
                    use_openrouter = True
                    previous_error = err_str
                    time.sleep(2)
                    continue
                
                if iteration < self.max_retries:
                    previous_error = err_str
                    time.sleep(2)
                    continue
                else:
                    fallback_code = self.apply_basic_fixes(original_code)
                    validation = self.validate_fixed_code(fallback_code, file_path)
                    if validation.get("valid", False):
                        if output_dir:
                            output_path = self.tools.save_fixed_file(fallback_code, file_path, output_dir)
                        else:
                            with open(file_path, 'w', encoding='utf-8') as f:
                                f.write(fallback_code)
                            output_path = file_path
                        
                        log_experiment(
                            agent_name=self.name,
                            model_used="fallback",
                            action=ActionType.FIX,
                            details={
                                "file_fixed": file_path,
                                "input_prompt": prompt if isinstance(prompt, str) else "(generated prompt)",
                                "output_response": "Basic fallback fixes applied",
                                "error": err_str
                            },
                            status="SUCCESS"
                        )
                        
                        return {
                            "file_path": file_path,
                            "output_path": output_path,
                            "success": True,
                            "original_code": original_code,
                            "fixed_code": fallback_code,
                            "changes_made": ["basic_fallback_fixed"],
                            "confidence": 0.0
                        }
                    
                    log_experiment(
                        agent_name=self.name,
                        model_used="fallback",
                        action=ActionType.FIX,
                        details={
                            "file_fixed": file_path,
                            "input_prompt": "Multiple attempts and fallback failed",
                            "output_response": err_str,
                            "error": str(e),
                            "iterations": iteration
                        },
                        status="FAILURE"
                    )
                    
                    return {
                        "file_path": file_path,
                        "success": False,
                        "error": err_str,
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