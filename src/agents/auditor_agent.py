import os
import threading
import subprocess
import json
import time
from typing import List, Dict
from dotenv import load_dotenv

from src.utils.file_manager import PyFileTool
from src.utils.logger import log_experiment, ActionType
from langchain_openai import ChatOpenAI
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.messages import AIMessageChunk, AIMessage

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
# Auditor
# ================================
class Auditor:
    def __init__(self):
        self.name = "Auditor"
        self.llm = llm
        

    def build_prompt(self, file_path: str, code: str, additional_context="") -> str:
        base = f"""
You are a senior Python code auditor.

Analyze the following Python file and return ONLY valid JSON with:
- bugs
- quality_issues
- style_issues
- refactoring_plan
- score (must be a number between 0 and 10, where 10 is perfect code)

Each issue must contain: line, severity, description, suggestion.
IMPORTANT: 
- The score must be between 0 and 10 (not 0-100).
- Only report bugs that ACTUALLY exist in this file
- Do NOT reuse issues from other files
- Base your analysis strictly on the given code
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
            model_used="fallback",
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
            "fallback_reason": reason
        }

    def analyze_file(self, file_path: str) -> Dict:
        try:
            code = PyFileTool.read_file(file_path)
        except Exception as e:
            return self.create_fallback_analysis(file_path, f"Lecture du fichier échouée: {e}", "")

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

        # ----------------------------
        # Appel LLM OpenRouter (direct)
        # ----------------------------
        import hashlib

        try:
                response = self.llm.invoke(self.build_prompt(file_path, code, additional_context))
                raw_text = " ".join(response.content) if isinstance(response.content, list) else str(response.content)
                print("RAW LLM RESPONSE:", raw_text[:500], "...")  # DEBUG
                llm_result = safe_parse_json(raw_text)
                self.llm_cache[code_hash] = llm_result
        except Exception as e:
                reason = f"LLM failed: {e}"
                return self.create_fallback_analysis(file_path, reason, code, pylint_res)

        report.update(llm_result)

        log_experiment(
            agent_name=self.name,
            model_used="OpenRouter",
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
        for f in files:
            results.append(self.analyze_file(f))
            time.sleep(3)  # ⚡ pause pour limiter le quota
        return results

    def generate_report(self, analyses: List[Dict]) -> Dict:
        report = {
            "total_files": len(analyses),
            "files": analyses,
            "summary": {
                "total_bugs": sum(len(a.get("bugs", [])) for a in analyses),
                "total_quality_issues": sum(len(a.get("quality_issues", [])) for a in analyses),
                "total_style_issues": sum(len(a.get("style_issues", [])) for a in analyses),
            }
        }
        return report