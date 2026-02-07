import os
import json
import time
import textwrap
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
OPENROUTER_MODELS = [
    "meta-llama/llama-3.1-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "mistralai/mistral-7b-instruct",
    "mistralai/mixtral-8x7b-instruct",
    "google/gemma-7b-it"
]

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
    """Multi-model OpenRouter failover (silent)."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set in environment")
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "HTTP-Referer": "https://github.com/yourusername/refactoring-swarm",
        "X-Title": "Refactoring Swarm",
        "Content-Type": "application/json"
    }
    
    last_error = None
    for model_name in OPENROUTER_MODELS:
        try:
            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2048
            }
            response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 429:
                # Rate limit, try next model
                continue
                
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            if not content or content.strip() == "":
                # Empty response, try next model
                continue
                
            # Success!
            return content
            
        except Exception as e:
            last_error = e
            continue
    
    # All models failed
    raise ValueError(f"All OpenRouter models failed. Last error: {last_error}")

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
                "fixed_code": "",
                "used_ai": False
            }
        
        cache_key = hash(original_code + str(audit_report))
        previous_error = None
        prompt = "(not generated)"
        used_ai = False
        
        for iteration in range(1, self.max_retries + 1):
            try:
                if cache_key in self.llm_cache and iteration == 1:
                    cache_entry = self.llm_cache[cache_key]
                    prompt = cache_entry.get("prompt", "(cached_result)")
                    llm_result = cache_entry.get("result", {})
                    used_ai = True
                else:
                    prompt = self.build_fix_prompt(
                        file_path, 
                        original_code, 
                        audit_report,
                        iteration,
                        previous_error
                    )
                    
                    # Try main LLM first, fallback to OpenRouter on rate limit
                    try:
                        response = self.llm.invoke(prompt)
                        raw_text = response.content if hasattr(response, 'content') else str(response)
                        used_ai = True
                    except Exception as llm_error:
                        if "rate_limit" in str(llm_error).lower() or "429" in str(llm_error):
                            raw_text = call_openrouter(prompt)
                            used_ai = True
                        else:
                            raise
                    
                    llm_result = safe_parse_json(raw_text)
                    
                    if iteration == 1:
                        self.llm_cache[cache_key] = {"prompt": prompt, "result": llm_result}
                
                if not isinstance(llm_result, dict):
                    raise ValueError("Le LLM n'a pas retourné un JSON valide")
                
                fixed_code = llm_result.get("fixed_code", "")
                changes_made = llm_result.get("changes_made", [])
                
                if not fixed_code:
                    raise ValueError("Le LLM n'a pas retourné de code corrigé")
                
                validation = self.validate_fixed_code(fixed_code, file_path)
                
                if not validation["valid"]:
                    previous_error = f"Syntax Error at line {validation.get('line', '?')}: {validation.get('error', 'Unknown')}"
                    
                    if iteration < self.max_retries:
                        time.sleep(2)
                        continue
                    else:
                        raise ValueError(f"Code invalide après {self.max_retries} tentatives: {previous_error}")
                
                # Code valide!
                if output_dir:
                    output_path = self.tools.save_fixed_file(fixed_code, file_path, output_dir)
                else:
                    output_path = file_path
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(fixed_code)
                
                log_experiment(
                    agent_name=self.name,
                    model_used="Groq",
                    action=ActionType.FIX,
                    details={
                        "file_fixed": file_path,
                        "input_prompt": prompt if isinstance(prompt, str) else "(generated prompt)",
                        "output_response": str(llm_result) if llm_result is not None else "",
                        "changes_made": changes_made,
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
                    "iterations": iteration,
                    "used_ai": used_ai
                }
                
            except Exception as e:
                err_str = str(e)
                
                if iteration < self.max_retries:
                    previous_error = err_str
                    time.sleep(2)
                    continue
                else:
                    # Try fallback fixes
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
                            model_used="Fallback",
                            action=ActionType.FIX,
                            details={
                                "file_fixed": file_path,
                                "input_prompt": "Fallback mode",
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
                            "changes_made": ["basic_fallback_fixes"],
                            "used_ai": False
                        }
                    
                    log_experiment(
                        agent_name=self.name,
                        model_used="N/A",
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
                        "iterations": iteration,
                        "used_ai": False
                    }
        
        return {
            "file_path": file_path,
            "success": False,
            "error": "Max retries exceeded",
            "original_code": original_code,
            "fixed_code": "",
            "used_ai": False
        }

    def fix_directory(
        self, 
        audit_results: List[Dict],
        output_dir: str
    ) -> List[Dict]:
        """Corrige tous les fichiers d'un dossier avec affichage propre."""
        
        os.makedirs(output_dir, exist_ok=True)
        
        results = []
        total_files = len(audit_results)
        
        print(f"\n🔧 CORRECTION DE {total_files} FICHIER(S)\n")
        print("─" * 60)
        
        for i, audit_report in enumerate(audit_results, 1):
            file_path = audit_report.get("file_path")
            
            if not file_path:
                print(f"⚠️  Fichier {i}/{total_files}: Rapport invalide (ignoré)")
                continue
            
            filename = os.path.basename(file_path)
            
            print(f"📝 Fichier {i}/{total_files}: {filename}...", end=" ", flush=True)
            
            result = self.fix_file(file_path, audit_report, output_dir)
            
            # Show only the final result - AI/Fallback WITHOUT confidence
            if result.get("success", False):
                changes_count = len(result.get("changes_made", []))
                method = "AI" if result.get("used_ai", False) else "Fallback"
                print(f"✅ Corrigé ({changes_count} modifications, {method})")
            else:
                print(f"❌ Échec")
            
            results.append(result)
            
            if i < total_files:
                time.sleep(1)
        
        print("─" * 60)
        
        # Summary
        successful = sum(1 for r in results if r.get("success", False))
        ai_used = sum(1 for r in results if r.get("used_ai", False))
        print(f"\n✨ RÉSUMÉ: {successful}/{total_files} fichiers corrigés • {ai_used} corrections AI\n")
        
        return results

    def generate_fix_report(self, fix_results: List[Dict]) -> Dict:
        """Génère un rapport de synthèse des corrections."""
        
        total_files = len(fix_results)
        successful = sum(1 for r in fix_results if r.get("success", False))
        failed = total_files - successful
        
        total_changes = sum(len(r.get("changes_made", [])) for r in fix_results)
        
        report = {
            "summary": {
                "total_files": total_files,
                "successful_fixes": successful,
                "failed_fixes": failed,
                "success_rate": f"{(successful/max(total_files, 1))*100:.1f}%",
                "total_changes": total_changes
            },
            "files": fix_results
        }
        
        return report