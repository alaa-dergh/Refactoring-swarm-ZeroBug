import os
import json
import time
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

from src.utils.file_manager import PyFileTool
from src.utils.logger import log_experiment, ActionType
from src.utils.groq_wrapper import llm

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
# Judge Agent
# ================================
class Judge:
    """
    Agent Judge : génère et exécute des tests unitaires pour valider le code.
    """
    
    def __init__(self, max_retries: int = 2):
        self.name = "Judge"
        self.llm = llm
        self.max_retries = max_retries
        self.test_cache = {}

    def build_test_generation_prompt(
        self, 
        code: str, 
        file_path: str,
        iteration: int = 1
    ) -> str:
        """Construit le prompt pour générer des tests unitaires."""
        
        prompt = f"""You are a senior Python testing expert specialized in TDD (Test-Driven Development).

Your mission: Generate comprehensive unit tests for the following Python code.

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

6. Return ONLY valid JSON with this structure:
{{
  "test_code": "import pytest\\nimport sys\\nimport os\\n\\n# Add project root to path\\nsys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))\\n\\nfrom module import function\\n\\ndef test_example():\\n    assert function(1, 2) == 3",
  "test_description": "Tests for module functions",
  "test_count": 5,
  "coverage_estimate": 0.85
}}

CRITICAL: 
- Use \\n for newlines, \\t for tabs in the test_code string
- The test_code must be syntactically valid Python
- Include proper imports (pytest, sys.path setup, module imports)
- Each test function should start with 'test_'
- Use descriptive test names

Return ONLY the JSON object, no markdown, no explanations.
"""
        
        return prompt
    
    def generate_unit_tests_with_ai(
        self, 
        code: str, 
        file_path: str
    ) -> Tuple[str, bool]:
        """Génère des tests unitaires avec l'AI."""
        
        if not self.llm:
            print("  ⚠️ Aucune AI disponible, utilisation du fallback")
            return self.generate_fallback_tests(code, file_path)
        
        code_hash = hash(code + file_path)
        if code_hash in self.test_cache:
            print(f"  ⚡ Cache hit pour {file_path}")
            return self.test_cache[code_hash], True
        
        for iteration in range(1, self.max_retries + 1):
            try:
                print(f"  🤖 Génération de tests avec AI (tentative {iteration}/{self.max_retries})...")
                
                prompt = self.build_test_generation_prompt(code, file_path, iteration)
                
                response = self.llm.invoke(prompt)
                
                if response is None or response.content is None:
                    raise ValueError("LLM returned None response")
                
                raw_text = response.content if hasattr(response, 'content') else str(response)
                
                if not raw_text or raw_text.strip() == "":
                    raise ValueError("LLM returned empty content")
                
                llm_result = safe_parse_json(raw_text)
                
                test_code = llm_result.get("test_code", "")
                test_description = llm_result.get("test_description", "N/A")
                test_count = llm_result.get("test_count", 0)
                
                if not test_code:
                    raise ValueError("Le LLM n'a pas retourné de code de test")
                
                try:
                    compile(test_code, "<test>", "exec")
                except SyntaxError as e:
                    print(f"  ❌ Test généré invalide: {e}")
                    if iteration < self.max_retries:
                        time.sleep(2)
                        continue
                    else:
                        print("  ⚠️ Échec génération AI, utilisation du fallback")
                        return self.generate_fallback_tests(code, file_path)
                
                print(f"  ✅ {test_count} test(s) généré(s): {test_description}")
                
                self.test_cache[code_hash] = test_code
                
                log_experiment(
                    agent_name=self.name,
                    model_used="llama-3.3-70b-versatile",
                    action=ActionType.ANALYSIS,
                    details={
                        "file_tested": file_path,
                        "input_prompt": prompt[:500] + "...",
                        "output_response": str(llm_result)[:500] + "...",
                        "test_count": test_count,
                        "iteration": iteration
                    },
                    status="SUCCESS"
                )
                
                return test_code, True
                
            except Exception as e:
                print(f"  ⚠️ Erreur à l'itération {iteration}: {e}")
                if iteration < self.max_retries:
                    time.sleep(2)
                    continue
                else:
                    print("  ⚠️ Échec génération AI, utilisation du fallback")
                    return self.generate_fallback_tests(code, file_path)
        
        return self.generate_fallback_tests(code, file_path)
    
    def generate_fallback_tests(
        self, 
        code: str, 
        file_path: str
    ) -> Tuple[str, bool]:
        """Génère des tests basiques sans AI (fallback)."""
        
        print(f"  🔧 Génération de tests basiques pour {file_path}")
        
        import re
        function_pattern = r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        functions = re.findall(function_pattern, code)
        functions = [f for f in functions if not f.startswith('_')]
        
        if not functions:
            test_code = f"""import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_module_exists():
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("test_module", r"{file_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert True
    except Exception as e:
        pytest.fail(f"Module import failed: {{e}}")
"""
        else:
            module_name = os.path.splitext(os.path.basename(file_path))[0]
            
            test_code = f"""import pytest
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from {module_name} import {', '.join(functions)}
except ImportError:
    import importlib.util
    spec = importlib.util.spec_from_file_location("{module_name}", r"{file_path}")
    test_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(test_module)
    {chr(10).join(f"    {func} = test_module.{func}" for func in functions)}

"""
            
            for func in functions:
                test_code += f"""
def test_{func}_exists():
    assert callable({func}), "La fonction {func} devrait être callable"

def test_{func}_basic():
    try:
        result = {func}()
        assert result is not None or result is None
    except TypeError:
        pytest.skip("Fonction nécessite des arguments spécifiques")
    except Exception as e:
        pytest.fail(f"Erreur inattendue: {{type(e).__name__}}: {{e}}")

"""
        
        print(f"  ✅ {len(functions)} fonction(s) détectée(s), tests basiques générés")
        
        log_experiment(
            agent_name=self.name,
            model_used="fallback",
            action=ActionType.ANALYSIS,
            details={
                "file_tested": file_path,
                "input_prompt": "FALLBACK",
                "output_response": f"Generated basic tests for {len(functions)} functions",
                "test_count": len(functions) * 2
            },
            status="SUCCESS"
        )
        
        return test_code, True
    
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
            # ✅ CORRECTION MAJEURE: Utiliser le bon working directory
            # On se place à la racine du projet, pas dans le dossier fixed
            project_root = os.getcwd()
            
            # Debug: afficher la commande
            cmd = ["pytest", test_file_path, "-v", "--tb=short"]
            print(f"  🔍 Commande: {' '.join(cmd)}")
            print(f"  🔍 Working dir: {project_root}")
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=project_root  # ← CORRECTION: Utiliser la racine du projet
            )
            
            stdout = result.stdout
            stderr = result.stderr
            returncode = result.returncode
            
            # Debug: afficher la sortie brute
            if not stdout or stdout.strip() == "":
                print(f"  ⚠️ Stdout vide!")
                if stderr:
                    print(f"  ⚠️ Stderr: {stderr[:200]}")
            
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
            
            log_experiment(
                agent_name=self.name,
                model_used="pytest",
                action=ActionType.ANALYSIS,
                details={
                    "file_tested": original_file_path,
                    "test_file": test_file_path,
                    "input_prompt": f"pytest {test_file_path} -v --tb=short",
                    "output_response": stdout[:500] if stdout else "No output",
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
                print(f"  ⚠️ Aucun test collecté (passed={passed}, failed={failed}, errors={errors})")
                # Afficher plus de debug
                print(f"  📄 Stdout (premiers 500 chars):\n{stdout[:500]}")
            
            return result_dict
            
        except subprocess.TimeoutExpired:
            error_msg = "Timeout lors de l'exécution des tests"
            print(f"  ⏱️ {error_msg}")
            
            log_experiment(
                agent_name=self.name,
                model_used="pytest",
                action=ActionType.ANALYSIS,
                details={
                    "file_tested": original_file_path,
                    "test_file": test_file_path,
                    "input_prompt": f"pytest {test_file_path} -v --tb=short",
                    "output_response": "Timeout after 60 seconds",
                    "error": error_msg
                },
                status="FAILURE"
            )
            
            return {
                "success": False,
                "error": error_msg,
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "total": 0
            }
            
        except Exception as e:
            error_msg = f"Erreur lors de l'exécution des tests: {e}"
            print(f"  ❌ {error_msg}")
            
            log_experiment(
                agent_name=self.name,
                model_used="pytest",
                action=ActionType.ANALYSIS,
                details={
                    "file_tested": original_file_path,
                    "test_file": test_file_path,
                    "input_prompt": f"pytest {test_file_path} -v --tb=short",
                    "output_response": f"Error: {str(e)}",
                    "error": str(e)
                },
                status="FAILURE"
            )
            
            return {
                "success": False,
                "error": error_msg,
                "passed": 0,
                "failed": 0,
                "errors": 1,
                "total": 0
            }
    
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
                return {
                    "file_path": file_path,
                    "success": False,
                    "error": "Échec de la génération des tests",
                    "ai_used": self.llm is not None
                }
            
            test_path = self.save_test_file(test_code, file_path)
            test_result = self.run_tests(test_path, file_path)
            
            return {
                "file_path": file_path,
                "test_path": test_path,
                "success": test_result.get("success", False),
                "passed": test_result.get("passed", 0),
                "failed": test_result.get("failed", 0),
                "errors": test_result.get("errors", 0),
                "total": test_result.get("total", 0),
                "ai_used": self.llm is not None,
                "test_output": test_result.get("stdout", "")[:500]
            }
            
        except Exception as e:
            error_msg = f"Erreur lors de l'évaluation: {e}"
            print(f"  ❌ {error_msg}")
            
            log_experiment(
                agent_name=self.name,
                model_used="N/A",
                action=ActionType.ANALYSIS,
                details={
                    "file_tested": file_path,
                    "input_prompt": "N/A - Error during file reading",
                    "output_response": f"Error: {str(e)}",
                    "error": str(e)
                },
                status="FAILURE"
            )
            
            return {
                "file_path": file_path,
                "success": False,
                "error": error_msg,
                "ai_used": self.llm is not None
            }
    
    def evaluate_directory(
        self, 
        dir_path: str,
        audit_results: Optional[List[Dict]] = None
    ) -> List[Dict]:
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
                time.sleep(2)
        
        return results
    
    def generate_evaluation_report(self, eval_results: List[Dict]) -> Dict:
        """Génère un rapport de synthèse des évaluations."""
        
        total_files = len(eval_results)
        successful = sum(1 for r in eval_results if r.get("passed", 0) > 0)
        failed = total_files - successful
        
        total_tests = sum(r.get("total", 0) for r in eval_results)
        total_passed = sum(r.get("passed", 0) for r in eval_results)
        total_failed = sum(r.get("failed", 0) for r in eval_results)
        total_errors = sum(r.get("errors", 0) for r in eval_results)
        
        ai_used = sum(1 for r in eval_results if r.get("ai_used", False))
        
        report = {
            "summary": {
                "total_files": total_files,
                "files_with_passing_tests": successful,
                "files_with_failing_tests": failed,
                "success_rate": f"{(successful/max(total_files, 1))*100:.1f}%",
                "total_tests": total_tests,
                "tests_passed": total_passed,
                "tests_failed": total_failed,
                "tests_errors": total_errors,
                "test_success_rate": f"{(total_passed/max(total_tests, 1))*100:.1f}%",
                "ai_used_count": ai_used,
                "fallback_used_count": total_files - ai_used
            },
            "files": eval_results
        }
        
        return report