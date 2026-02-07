import os
import subprocess
import json
import time
from typing import List, Dict
from dotenv import load_dotenv
import requests

from src.utils.file_manager import PyFileTool
from src.utils.logger import log_experiment, ActionType
from src.utils.groq_wrapper import llm  # ← MODIFIÉ: Utilise Gemini

# ================================
# Load API key
# ================================
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

# ================================
# JSON parser robuste
# ================================
def safe_parse_json(text: str) -> dict:
    try:
        if "```json" in text:
            start = text.find("```json") + 7
            end = text.find("```", start)
            text = text[start:end].strip()
        elif "```python" in text:
            start = text.find("```python") + 9
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
# Code Analyzer (Pylint + Syntax)
# ================================
class CodeAnalyzer:
    @staticmethod
    def run_pylint(file_path: str) -> dict:
        try:
            result = subprocess.run(
                ["pylint", file_path, "--output-format=json"],
                capture_output=True,
                text=True,
                timeout=30
            )
            messages = []
            if result.stdout:
                try:
                    messages = json.loads(result.stdout)
                except json.JSONDecodeError:
                    pass
            score = 0.0
            text = (result.stderr or "") + "\n" + (result.stdout or "")
            for line in text.splitlines():
                if "rated at" in line.lower():
                    try:
                        score = float(line.split("rated at")[1].split("/")[0].strip())
                    except Exception:
                        pass
            return {"score": score, "messages": messages, "success": True}
        except Exception as e:
            return {"score": 0.0, "messages": [], "success": False, "error": str(e)}

    @staticmethod
    def check_syntax(file_path: str) -> dict:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                compile(f.read(), file_path, "exec")
            return {"valid": True, "error": None, "line": None}
        except SyntaxError as e:
            return {"valid": False, "error": e.msg, "line": e.lineno}
        except Exception as e:
            return {"valid": False, "error": str(e), "line": None}

# ================================
# Auditor avec AI / fallback
# ================================
class Auditor:
    def __init__(self):
        self.name = "Auditor"
        self.llm = llm
        self.llm_cache = {}

    def build_prompt(self, file_path: str, code: str, additional_context="") -> str:
        base = f"""
You are a senior Python code auditor.

Analyze the following Python file and return ONLY valid JSON with:
- bugs
- quality_issues
- style_issues
- refactoring_plan
- score

Each issue must contain: line, severity, description, suggestion.
Important: The score must be between 0 and 10 and it indicates the quality and correctness of the code
File: {file_path}

CODE:
{code}
"""
        if additional_context:
            base += f"\n\nADDITIONAL CONTEXT:\n{additional_context}\n"
        return base

    def detect_generic_patterns(self, code: str) -> List[Dict]:
        issues = []
        lines = code.splitlines()
        for i, line in enumerate(lines, 1):
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            if "/" in line and "//" not in line:
                ctx = "\n".join(lines[max(0, i-5):i+2])
                if "== 0" not in ctx and "!= 0" not in ctx:
                    issues.append({
                        "line": i,
                        "severity": "HIGH",
                        "description": "Division possible par zéro",
                        "suggestion": "Ajouter une vérification != 0"
                    })
            if "def " in line and any(x in line for x in ["=[]", "={}"]):
                issues.append({
                    "line": i,
                    "severity": "HIGH",
                    "description": "Argument mutable par défaut",
                    "suggestion": "Utiliser None puis initialiser"
                })
        return issues

    def create_fallback_analysis(self, file_path, reason, code, pylint_res=None):
        issues = self.detect_generic_patterns(code)
        score = pylint_res.get("score", 0.0) if pylint_res else 0.0
        log_experiment(
            agent_name=self.name,
            model_used="Fallback",
            action=ActionType.ANALYSIS,
            details={
                "file_analyzed": file_path,
                "input_prompt": "FALLBACK",
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
            "refactoring_plan": ["Corriger erreurs critiques", "Appliquer recommandations", "Nettoyer le code"],
            "score": score,
            "analysis_type": "Fallback"
        }

    def call_openrouter_models(self, prompt: str) -> Dict:
        if not OPENROUTER_API_KEY:
            raise ValueError("OPENROUTER_API_KEY not set")
        headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
        last_error = None
        for model_name in OPENROUTER_MODELS:
            try:
                payload = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": 2500
                }
                response = requests.post(OPENROUTER_API_URL, headers=headers, json=payload, timeout=40)
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                if not content or content.strip() == "":
                    continue
                return safe_parse_json(content)
            except Exception as e:
                last_error = e
                continue
        raise ValueError(f"All OpenRouter models failed. Last error: {last_error}")

    def analyze_file(self, file_path: str) -> Dict:
        try:
            code = PyFileTool.read_file(file_path)
        except Exception as e:
            result = self.create_fallback_analysis(file_path, f"Lecture du fichier échouée: {e}", "")
            print(f"📝 {os.path.basename(file_path)}... ❌ Fallback")
            return result

        pylint_res = CodeAnalyzer.run_pylint(file_path)
        syntax_res = CodeAnalyzer.check_syntax(file_path)
        pattern_issues = self.detect_generic_patterns(code)
        additional_context = ""
        if pattern_issues:
            additional_context += "PATTERN DETECTION:\n"
            for p in pattern_issues:
                additional_context += f"Line {p['line']}: {p['description']}\n"
        if not syntax_res["valid"]:
            additional_context += f"\nSyntax Error Line {syntax_res['line']}: {syntax_res['error']}\n"

        report = {
            "file_path": file_path,
            "bugs": pattern_issues,
            "quality_issues": [],
            "style_issues": [],
            "refactoring_plan": [],
            "score": pylint_res.get("score", 0.0)
        }

        code_hash = hash(code)
        used_type = "Fallback"
        if code_hash in self.llm_cache:
            llm_result = self.llm_cache[code_hash]
            used_type = llm_result.get("analysis_type", "AI")
        else:
            try:
                response = self.llm.invoke(self.build_prompt(file_path, code, additional_context))
                raw_text = response.content if hasattr(response, 'content') else str(response)
                llm_result = safe_parse_json(raw_text)
                llm_result["analysis_type"] = "AI"
                self.llm_cache[code_hash] = llm_result
                used_type = "AI"
            except Exception:
                try:
                    llm_result = self.call_openrouter_models(self.build_prompt(file_path, code, additional_context))
                    llm_result["analysis_type"] = "AI"
                    self.llm_cache[code_hash] = llm_result
                    used_type = "AI"
                except Exception as e:
                    reason = f"LLM + fallback failed: {e}"
                    llm_result = self.create_fallback_analysis(file_path, reason, code, pylint_res)
                    used_type = "Fallback"

        report.update(llm_result)

        # --------- PRINT SIMPLIFIÉ POUR L'UTILISATEUR ---------
        print(f"📝 {os.path.basename(file_path)}... ✅ Analyse ({used_type})" if used_type=="AI" else f"📝 {os.path.basename(file_path)}... ❌ Fallback")

        log_experiment(
            agent_name=self.name,
            model_used=report.get("analysis_type", "Fallback"),
            action=ActionType.ANALYSIS,
            details={
                "file_analyzed": file_path,
                "input_prompt": self.build_prompt(file_path, code, additional_context)[:500]+"...",
                "output_response": str(llm_result)[:500]+"...",
                "issues_found": len(report.get("bugs", []))
            },
            status="SUCCESS"
        )

        return report

    def analyze_directory(self, dir_path: str) -> List[Dict]:
        files = PyFileTool.list_python_files(dir_path)
        results = []
        total_files = len(files)
        for idx, f in enumerate(files, 1):
            result = self.analyze_file(f)
            results.append(result)
            time.sleep(1)
        return results

    def generate_report(self, analyses: List[Dict]) -> Dict:
        return {
            "total_files": len(analyses),
            "files": analyses,
            "summary": {
                "total_bugs": sum(len(a.get("bugs", [])) for a in analyses),
                "total_quality_issues": sum(len(a.get("quality_issues", [])) for a in analyses),
                "total_style_issues": sum(len(a.get("style_issues", [])) for a in analyses),
            }
        }
