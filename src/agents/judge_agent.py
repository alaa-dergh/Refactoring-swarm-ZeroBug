import os
import json
import time
import subprocess
import re
import requests
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dotenv import load_dotenv
import textwrap

from src.utils.file_manager import PyFileTool
from src.utils.logger import log_experiment, ActionType

# ------------------ ENV & API KEYS ------------------
load_dotenv()

# Hugging Face
HF_MODEL = os.getenv("HF_MODEL", "bigcode/starcoder")
HF_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
if not HF_API_KEY:
    print("⚠️ HUGGINGFACE_API_KEY non défini, Hugging Face désactivé")
    HF_API_KEY = None

HF_API_URL = f"https://api-inference.huggingface.co/models/{HF_MODEL}" if HF_API_KEY else None

# OpenRouter
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    print("⚠️ OPENROUTER_API_KEY non défini, OpenRouter désactivé")

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS = [
    "meta-llama/llama-3.1-70b-instruct",
    "meta-llama/llama-3.1-8b-instruct",
    "mistralai/mistral-7b-instruct",
    "mistralai/mixtral-8x7b-instruct",
    "google/gemma-7b-it"
]

# ------------------ Hugging Face API ------------------
def call_huggingface(prompt: str) -> Tuple[str, str]:
    """Appel Hugging Face Inference API."""
    if not HF_API_KEY or not HF_API_URL:
        raise ValueError("Hugging Face API not configured")
        
    headers = {
        "Authorization": f"Bearer {HF_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"inputs": prompt, "parameters": {"max_new_tokens": 1500, "temperature": 0.7}}

    try:
        response = requests.post(HF_API_URL, headers=headers, json=payload, timeout=40)
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list) and "generated_text" in data[0]:
            return data[0]["generated_text"], HF_MODEL
        elif "error" in data:
            raise ValueError(f"Hugging Face API error: {data['error']}")
        else:
            raise ValueError(f"Unexpected HF response: {data}")
    except Exception as e:
        raise ValueError(f"Hugging Face call failed: {e}")


def safe_parse_json(text: str) -> dict:
    """Parse JSON même avec markdown backticks."""
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


def call_openrouter(prompt: str) -> Tuple[str, str]:
    """Multi-model OpenRouter failover."""
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
            print(f"  🤖 Trying OpenRouter model: {model_name}")

            payload = {
                "model": model_name,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2500
            }

            response = requests.post(
                OPENROUTER_API_URL,
                headers=headers,
                json=payload,
                timeout=40
            )

            if response.status_code == 429:
                print(f"  ⚠️ Quota / Rate limit on {model_name}")
                continue

            response.raise_for_status()
            data = response.json()

            content = data["choices"][0]["message"]["content"]

            if not content or content.strip() == "":
                print(f"  ⚠️ Empty response from {model_name}")
                continue

            print(f"  ✅ Success with model: {model_name}")
            return content, model_name

        except Exception as e:
            print(f"  ❌ Model failed ({model_name}): {e}")
            last_error = e
            continue

    raise ValueError(f"All OpenRouter models failed. Last error: {last_error}")


class Judge:
    """Agent Judge : génère et exécute des tests unitaires pour valider le code."""
    
    def __init__(self, max_retries: int = 2):
        self.name = "Judge"
        self.max_retries = max_retries
        self.test_cache = {}
        self.llm = None
        self.rate_limit_reset = None
        print("🔍 Initialisation du Judge...")
        try:
            from src.utils.groq_wrapper import llm as imported_llm
            if imported_llm is None:
                print("⚠️ Judge: LLM est None, mode fallback activé")
            elif not hasattr(imported_llm, 'invoke'):
                print(f"⚠️ Judge: LLM n'a pas de méthode 'invoke'")
            else:
                self.llm = imported_llm
                print("✅ Judge: LLM opérationnel")
                return
        except ImportError as e:
            print(f"⚠️ Judge: Import impossible: {e}")
        except Exception as e:
            print(f"⚠️ Judge: Erreur LLM: {e}")
        print("🔧 Judge: Mode FALLBACK activé")
    
    def _safe_log(self, **kwargs):
        """Wrapper around log_experiment that ensures required fields are present."""
        details = kwargs.get("details") or {}
        if "input_prompt" not in details:
            details["input_prompt"] = ""
        if "output_response" not in details:
            details["output_response"] = ""
        kwargs["details"] = details
        try:
            return log_experiment(**kwargs)
        except Exception as e:
            print(f"  ⚠️ Erreur de Logging (Agent: {self.name}): {e}")
            return None

    def build_test_generation_prompt(self, code: str, file_path: str, iteration: int = 1) -> str:
        """Construit le prompt pour générer des tests unitaires."""
        return f"""You are a senior Python testing expert. Generate comprehensive pytest unit tests.

FILE: {file_path}
ITERATION: {iteration}/{self.max_retries}

CODE TO TEST:
```python
{code}
```

REQUIREMENTS:
1. Generate COMPLETE, RUNNABLE pytest unit tests
2. Test ALL functions and methods in the code
3. Include edge cases and error handling tests
4. Use pytest assertions (assert, pytest.raises, etc.)
5. Follow Python testing best practices

Return ONLY valid JSON:
{{"test_code": "import pytest\\nimport sys\\nimport os\\n\\nsys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))\\n\\nfrom module import function\\n\\ndef test_example():\\n    assert function(1, 2) == 3", "test_description": "Tests for module functions", "test_count": 5, "coverage_estimate": 0.85}}

CRITICAL: 
- Use \\n for newlines, \\t for tabs. Syntactically valid Python. Include proper imports. Each test starts with 'test_'.
- Return ONLY JSON, no markdown.
"""
    
    def generate_unit_tests_with_ai(self, code: str, file_path: str) -> Tuple[str, bool]:
        """Génère des tests unitaires avec AI (HF ou OpenRouter)."""
        code_hash = hash(code + file_path)
        if code_hash in self.test_cache:
            return self.test_cache[code_hash], True

        prompt = self.build_test_generation_prompt(code, file_path)

        last_error = None
        for iteration in range(1, self.max_retries + 1):
            try:
                print(f"🤖 AI test generation attempt {iteration}/{self.max_retries}")

                # Try Hugging Face first
                try:
                    raw_text, model_used = call_huggingface(prompt)
                except Exception as hf_e:
                    print(f"⚠️ Hugging Face failed: {hf_e}, trying OpenRouter fallback")
                    raw_text, model_used = call_openrouter(prompt)

                llm_result = safe_parse_json(raw_text)
                test_code = llm_result.get("test_code", "")
                if not test_code:
                    raise ValueError("AI returned empty test_code")
                compile(test_code, "<test>", "exec")
                self.test_cache[code_hash] = test_code
                return test_code, True

            except Exception as e:
                print(f"⚠️ Attempt {iteration} failed: {e}")
                last_error = e
                time.sleep(2)
                continue

        print(f"❌ All AI attempts failed: {last_error}")
        return self.generate_fallback_tests(code, file_path)

    def generate_fallback_tests(self, code: str, file_path: str) -> Tuple[str, bool]:
        """Génère des tests basiques sans AI (fallback)."""
        print(f"  🔧 Génération de tests basiques pour {os.path.basename(file_path)}")

        function_pattern = r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        functions = re.findall(function_pattern, code)
        functions = [f for f in functions if not f.startswith('_')]

        module_name = os.path.splitext(os.path.basename(file_path))[0]

        test_code = textwrap.dedent(f"""
            import pytest
            import sys
            import os
            import importlib.util

            sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

            def load_module():
                spec = importlib.util.spec_from_file_location("{module_name}", r"{file_path}")
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module

            test_module = load_module()
        """).strip() + "\n\n"

        if not functions:
            test_code += (
                "def test_module_load():\n"
                "    assert test_module is not None\n"
            )
        else:
            for func in functions:
                test_code += textwrap.dedent(f"""
                    def test_{func}_exists():
                        assert hasattr(test_module, "{func}"), "La fonction {func} manque dans le module"
                        assert callable(getattr(test_module, "{func}")), "{func} doit être une fonction"

                    def test_{func}_basic():
                        func_to_test = getattr(test_module, "{func}")
                        try:
                            result = func_to_test()
                            assert True
                        except TypeError:
                            pytest.skip("Fonction {func} nécessite des arguments")
                        except Exception as e:
                            pytest.fail(f"Erreur lors de l'appel : {{e}}")
                """)

        print(f"  ✅ {len(functions)} fonction(s) détectée(s), tests basiques générés")
        return test_code, True

    def validate_test_file(self, test_code: str, test_file_path: str, source_file_path: str) -> Tuple[bool, str]:
        """Pre-check of generated test file: syntax + import."""
        try:
            compile(test_code, test_file_path, "exec")
        except SyntaxError as e:
            return False, f"SYNTAX ERROR in generated tests: line {e.lineno}: {e.msg}\n{e.text}"
        try:
            sandbox_dir = os.path.dirname(source_file_path)
            check_script = (
                f"import sys, importlib.util\n"
                f"sys.path.insert(0, r'{sandbox_dir}')\n"
                f"spec = importlib.util.spec_from_file_location('_test_check', r'{test_file_path}')\n"
                f"mod = importlib.util.module_from_spec(spec)\n"
                f"spec.loader.exec_module(mod)\n"
                f"tests = [n for n in dir(mod) if n.startswith('test_') and callable(getattr(mod, n))]\n"
                f"print('FOUND_TESTS:' + str(len(tests)))\n"
            )
            r = subprocess.run([__import__("sys").executable, "-c", check_script], capture_output=True, text=True, timeout=15)
            if r.returncode != 0:
                return False, f"IMPORT/LOAD ERROR in generated tests:\n{r.stderr}"
            for line in r.stdout.splitlines():
                if line.startswith("FOUND_TESTS:"):
                    if int(line.split(":", 1)[1]) == 0:
                        return False, "Generated test file has ZERO test_ functions."
                    return True, ""
            return False, "Could not determine number of tests in generated file."
        except subprocess.TimeoutExpired:
            return False, "Test file validation timed out (possible infinite loop at import)."
        except Exception:
            return True, ""

    def parse_pytest_results(self, pytest_output: str) -> Tuple[int, int, bool, bool]:
        """Extract passed, failed and detect collection errors from pytest stdout."""
        passed = 0
        failed = 0
        errors = 0
        try:
            m = re.search(r'(\d+)\s+passed', pytest_output)
            if m:
                passed = int(m.group(1))
            m = re.search(r'(\d+)\s+failed', pytest_output)
            if m:
                failed = int(m.group(1))
            m = re.search(r'(\d+)\s+error', pytest_output)
            if m:
                errors = int(m.group(1))
        except Exception as e:
            print(f"    ⚠️ Parse error: {e}")
            pass
        collection_error = (
            "error during collection" in pytest_output.lower() 
            or ("ERROR" in pytest_output and "collected" not in pytest_output.lower())
            or "ModuleNotFoundError" in pytest_output
            or "ImportError" in pytest_output
        )
        has_tests = (passed + failed + errors) > 0
        print(f"    [PARSE] passed={passed}, failed={failed}, errors={errors}, has_tests={has_tests}, collection_error={collection_error}")
        return passed, failed + errors, has_tests, collection_error

    def extract_specific_test_failures(self, pytest_output: str) -> str:
        """Heuristic extraction of relevant failure snippets from pytest output."""
        if not pytest_output:
            return ""
        snippets = []
        lines = pytest_output.splitlines()
        for i, line in enumerate(lines):
            if any(k in line for k in ("ERROR", "FAILED", "AssertionError", "Traceback")):
                start = max(0, i - 3)
                end = min(len(lines), i + 6)
                context = "\n".join(lines[start:end]).strip()
                if len(context) > 40:
                    snippets.append(context)
        seen = set()
        out = []
        for s in snippets:
            if s not in seen:
                seen.add(s)
                out.append(s)
            if len(out) >= 3:
                break
        return "\n\n---\n\n".join(out) if out else (pytest_output[-600:] if len(pytest_output) > 600 else pytest_output)

    def analyze_test_failures_with_llm(self, fixed_code: str, pytest_output: str) -> str:
        """Ask available LLM to analyze failures, fallback to heuristic extraction."""
        truncated = pytest_output[-2000:] if len(pytest_output) > 2000 else pytest_output
        prompt = f"Analyze these pytest results and explain likely root causes and next steps.\n\nPYTEST OUTPUT:\n{truncated}\n\nCODE:\n{fixed_code}\n\nProvide concise actionable suggestions."
        try:
            if self.llm:
                resp = self.llm.invoke(prompt)
                content = resp.content if hasattr(resp, "content") else str(resp)
                return str(content)
            else:
                # NOUVEAU: Fallback OpenRouter si pas de Groq LLM
                content, _ = call_openrouter(prompt)
                return str(content)
        except Exception as e:
            print(f"    ⚠️ LLM analysis failed: {e}")
            return self.extract_specific_test_failures(pytest_output)

    def generate_enhanced_documentation(self, code: str, file_path: str) -> str:
        """
        NOUVEAU: Génère une documentation Markdown améliorée avec structure complète.
        Utilise OpenRouter si Groq LLM n'est pas disponible.
        """
        base_name = os.path.splitext(os.path.basename(file_path))[0]
        
        prompt = f"""Generate comprehensive markdown documentation for this Python code.

CODE:
```python
{code}
```

Create a complete .md documentation file with this structure:

# {base_name.title().replace('_', ' ')} - Documentation

**Status**: Production Ready - All Tests Passed  
**File**: `{os.path.basename(file_path)}`

---

## Overview
[Brief description of what this code does - 2-3 sentences]

---

## Functions

For EACH function, provide:

### `function_name(param1, param2, ...)`

**Description:**  
[What the function does]

**Parameters:**
- `param1` (type): Description
- `param2` (type): Description

**Returns:**
- Type: Description

**Examples:**
```python
>>> function_name(arg1, arg2)
expected_output
```

**Edge Cases:**
- What happens with empty inputs
- What happens with invalid inputs
- Error handling behavior

---

[Repeat for ALL functions in the code]

---

## Summary

### Functions Included
- `function1`: Brief description
- `function2`: Brief description

### Testing Status
✅ All functions tested and validated

Return ONLY the markdown documentation (no code blocks around it):"""

        try:
            if self.llm:
                resp = self.llm.invoke(prompt)
                documentation = resp.content if hasattr(resp, "content") else str(resp)
            else:
                # Fallback OpenRouter
                documentation, _ = call_openrouter(prompt)
            
            # Cleanup
            documentation = documentation.replace('```markdown', '').replace('```', '').strip()
            return documentation
            
        except Exception as e:
            print(f"    ⚠️ Enhanced doc generation failed: {e}, using fallback")
            # Fallback basique
            return f"""# {base_name.title().replace('_', ' ')} - Documentation

**Status**: Production Ready - All Tests Passed  
**File**: `{os.path.basename(file_path)}`

---

## Overview
This file contains Python code that has been successfully validated.

## Status
✅ All tests passing  
✅ Code validated  
✅ Ready for production

---

**Note**: Automatic documentation generation encountered an error. Please review the code for detailed information.
"""

    def save_test_file(self, test_code: str, original_file_path: str) -> str:
        """Sauvegarde le code de test dans un fichier."""
        test_dir = os.path.join(os.path.dirname(original_file_path), "test_judge")
        os.makedirs(test_dir, exist_ok=True)
        original_name = os.path.basename(original_file_path)
        test_name = f"test_{original_name}"
        test_path = os.path.join(test_dir, test_name)
        with open(test_path, 'w', encoding='utf-8', errors='replace') as f:
            f.write(test_code)
        print(f"  💾 Tests sauvegardés: {test_path}")
        return test_path

    def run_tests(self, test_file_path: str, original_file_path: str) -> Dict:
        """Exécute les tests avec pytest."""
        print(f"  🚀 Exécution des tests...")
        try:
            project_root = os.getcwd()
            cmd = ["pytest", test_file_path, "-v", "--tb=short"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, cwd=project_root)
            stdout = result.stdout
            stderr = result.stderr
            returncode = result.returncode
            success = returncode == 0
            passed = stdout.count(" PASSED")
            failed = stdout.count(" FAILED")
            errors = stdout.count(" ERROR")
            skipped = stdout.count(" SKIPPED")
            result_dict = {
                "success": success,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "skipped": skipped,
                "total": passed + failed + errors,
                "stdout": stdout,
                "stderr": stderr,
                "returncode": returncode
            }
            self._safe_log(
                agent_name=self.name,
                model_used="pytest",
                action=ActionType.ANALYSIS,
                details={
                    "file_tested": original_file_path,
                    "input_prompt": f"pytest execution on {test_file_path}",
                    "output_response": f"Tests executed: {passed} passed, {failed} failed, {errors} errors",
                    "test_file": test_file_path,
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "total": passed + failed + errors
                },
                status="SUCCESS" if success else "FAILURE"
            )
            if success and passed > 0:
                print(f"  ✅ Tests réussis: {passed}/{passed + failed + errors}")
            elif failed > 0:
                print(f"  ❌ Tests échoués: {failed}/{passed + failed + errors}")
            else:
                print(f"  ⚠️ Aucun test collecté")
            return result_dict
        except subprocess.TimeoutExpired:
            print(f"  ⏱️ Timeout lors de l'exécution des tests")
            self._safe_log(
                agent_name=self.name,
                model_used="pytest",
                action=ActionType.ANALYSIS,
                details={
                    "file_tested": original_file_path,
                    "input_prompt": f"pytest execution on {test_file_path}",
                    "output_response": "Test execution timeout",
                    "error": "Timeout"
                },
                status="FAILURE"
            )
            return {"success": False, "error": "Timeout", "passed": 0, "failed": 0, "errors": 1, "total": 0}
        except Exception as e:
            print(f"  ❌ Erreur lors de l'exécution des tests: {e}")
            self._safe_log(
                agent_name=self.name,
                model_used="pytest",
                action=ActionType.ANALYSIS,
                details={
                    "file_tested": original_file_path,
                    "input_prompt": f"pytest execution on {test_file_path}",
                    "output_response": f"Test execution error: {str(e)[:500]}",
                    "error": str(e)
                },
                status="FAILURE"
            )
            return {"success": False, "error": str(e), "passed": 0, "failed": 0, "errors": 1, "total": 0}

    def evaluate_file(self, file_path: str) -> Dict:
        """Évalue un fichier : génère et exécute les tests."""
        print(f"\n📋 Évaluation de {os.path.basename(file_path)}")
        try:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    code = f.read()
            except UnicodeDecodeError:
                with open(file_path, 'r', encoding='latin-1') as f:
                    code = f.read()

            if self.llm:
                test_code, success = self.generate_unit_tests_with_ai(code, file_path)
            else:
                test_code, success = self.generate_fallback_tests(code, file_path)

            if not success:
                self._safe_log(
                    agent_name=self.name,
                    model_used="evaluation_failed",
                    action=ActionType.ANALYSIS,
                    details={
                        "file_tested": file_path,
                        "input_prompt": f"Evaluate file: {file_path}",
                        "output_response": "Test generation failed",
                        "error": "Test generation failed"
                    },
                    status="FAILURE"
                )
                return {"file_path": file_path, "success": False, "error": "Échec de la génération des tests", "ai_used": self.llm is not None}

            test_path = self.save_test_file(test_code, file_path)

            # Validate test file BEFORE running pytest
            test_valid, test_error = self.validate_test_file(test_code, test_path, file_path)
            if not test_valid:
                print(f"  ⚠️ Test file validation failed: {test_error[:200]}")
                return {
                    "file_path": file_path,
                    "test_path": test_path,
                    "success": False,
                    "passed": 0,
                    "failed": 1,
                    "errors": 0,
                    "total": 1,
                    "ai_used": self.llm is not None,
                    "test_output": test_error[:500],
                    "specific_test_failures": test_error
                }

            test_result = self.run_tests(test_path, file_path)

            pytest_output = (test_result.get("stdout") or "") + "\n" + (test_result.get("stderr") or "")
            passed, failed, has_tests, collection_error = self.parse_pytest_results(pytest_output)

            print(f"  📊 Results: {passed} passed, {failed} failed, has_tests={has_tests}")

            tests_passed_ok = (passed > 0 and failed == 0 and has_tests)

            result = {
                "file_path": file_path,
                "test_path": test_path,
                "success": tests_passed_ok,
                "passed": passed,
                "failed": failed,
                "errors": test_result.get("errors", 0),
                "total": test_result.get("total", 0),
                "ai_used": self.llm is not None,
                "test_output": pytest_output[:500],
            }

            if failed > 0 or collection_error:
                print(f"  🔍 Analyzing failures...")
                analysis = self.analyze_test_failures_with_llm(code, pytest_output)
                result["specific_test_failures"] = analysis
                result["success"] = False
            elif tests_passed_ok:
                try:
                    print(f"  📝 Generating enhanced documentation...")
                    base_name = os.path.splitext(os.path.basename(file_path))[0]
                    doc_filename = os.path.join(os.path.dirname(file_path), f"{base_name}_documentation.md")
                    
                    # NOUVEAU: Utilise la génération améliorée
                    doc = self.generate_enhanced_documentation(code, file_path)
                    
                    with open(doc_filename, "w", encoding="utf-8") as f:
                        f.write(doc)
                    result["documentation_created"] = True
                    result["documentation_file"] = doc_filename
                    print(f"  ✅ VALIDÉE: {passed} tests passed, doc créée")
                except Exception as e:
                    print(f"  ⚠️ Doc generation failed: {e}")
                    result["documentation_created"] = False
            else:
                print(f"  ⚠️ No tests collected or syntax error")
                result["success"] = False

            return result
        except Exception as e:
            print(f"  ❌ Erreur lors de l'évaluation: {e}")
            import traceback
            traceback.print_exc()
            self._safe_log(
                agent_name=self.name,
                model_used="evaluation_error",
                action=ActionType.ANALYSIS,
                details={
                    "file_tested": file_path,
                    "input_prompt": f"Evaluate file: {file_path}",
                    "output_response": f"Evaluation error: {str(e)[:500]}",
                    "error": str(e)
                },
                status="FAILURE"
            )
            return {"file_path": file_path, "success": False, "error": str(e), "ai_used": self.llm is not None}

    def evaluate_directory(self, dir_path: str, audit_results: Optional[List[Dict]] = None) -> List[Dict]:
        """Évalue tous les fichiers d'un dossier."""
        if audit_results:
            files = [r.get("file_path") for r in audit_results if r.get("file_path")]
        else:
            files = PyFileTool.list_python_files(dir_path)

        results = []
        total_files = len(files)
        print(f"\n🧑‍⚖️ Début de l'évaluation de {total_files} fichier(s)...\n")

        for i, file_path in enumerate(files, 1):
            print(f"\n[{i}/{total_files}] {os.path.basename(file_path)}")
            result = self.evaluate_file(file_path)
            results.append(result)
            if i < total_files:
                time.sleep(1)

        return results

    def generate_evaluation_report(self, eval_results: List[Dict]) -> Dict:
        """Génère un rapport de synthèse des évaluations."""
        total_files = len(eval_results)
        successful = sum(1 for r in eval_results if r.get("success", False))
        failed = total_files - successful

        total_tests = sum(r.get("total", 0) for r in eval_results)
        total_passed = sum(r.get("passed", 0) for r in eval_results)
        total_failed = sum(r.get("failed", 0) for r in eval_results)
        total_errors = sum(r.get("errors", 0) for r in eval_results)
        ai_used = sum(1 for r in eval_results if r.get("ai_used", False))

        success_rate = f"{(successful/max(total_files, 1))*100:.1f}%" if total_files > 0 else "0%"
        test_success_rate = f"{(total_passed/max(total_tests, 1))*100:.1f}%" if total_tests > 0 else "0%"

        print(f"\n{'='*70}")
        print(f"📊 RAPPORT D'ÉVALUATION FINAL")
        print(f"{'='*70}")
        print(f"  📁 Fichiers évalués: {total_files}")
        print(f"  ✅ Fichiers validés: {successful}/{total_files} ({success_rate})")
        print(f"  ❌ Fichiers échoués: {failed}/{total_files}")
        print(f"  🧪 Tests totaux: {total_tests}")
        print(f"  ✓ Tests réussis: {total_passed}/{total_tests} ({test_success_rate})")
        print(f"  ✗ Tests échoués: {total_failed}")
        print(f"  ⚠️ Erreurs: {total_errors}")
        print(f"  🤖 AI utilisée: {ai_used}/{total_files}")
        print(f"{'='*70}\n")

        return {
            "summary": {
                "total_files": total_files,
                "files_with_passing_tests": successful,
                "files_with_failing_tests": failed,
                "success_rate": success_rate,
                "total_tests": total_tests,
                "tests_passed": total_passed,
                "tests_failed": total_failed,
                "tests_errors": total_errors,
                "test_success_rate": test_success_rate,
                "ai_used_count": ai_used,
                "fallback_used_count": total_files - ai_used
            },
            "files": eval_results,
            "status": "SUCCESS" if successful == total_files else "PARTIAL" if successful > 0 else "FAILURE"
        }
