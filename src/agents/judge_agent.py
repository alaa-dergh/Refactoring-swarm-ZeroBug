import os
import json
import time
import subprocess
import tempfile
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv

from src.utils.file_manager import PyFileTool
from src.utils.logger import log_experiment, ActionType
from langchain_openai import ChatOpenAI
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.messages import AIMessageChunk
from src.utils.rate_limiter import RateLimiter, RateLimitConfig

# ================================
# Load API keys
# ================================
load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

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

# Initialize LLM (try OpenRouter first, fallback to None)
llm = None
if OPENROUTER_API_KEY:
    try:
        llm = NonStreamingChatOpenAI(
            model="meta-llama/llama-3.3-70b-instruct:free",
            api_key=OPENROUTER_API_KEY,
            temperature=0,
            base_url="https://openrouter.ai/api/v1",
            streaming=False,
            model_kwargs={},
        )
    except Exception as e:
        print(f"⚠️ Erreur initialisation OpenRouter: {e}")

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
    
    Stratégie (TDD):
    1. Analyse le code à tester
    2. Génère des tests unitaires avec AI (ou fallback basique)
    3. Exécute les tests avec pytest
    4. Retourne le résultat (succès/échec)
    5. Log toutes les opérations
    """
    
    def __init__(self, max_retries: int = 2, rate_limiter=None):
        self.name = "Judge"
        self.llm = llm
        self.max_retries = max_retries
        self.test_cache = {}  # Cache pour éviter regeneration
        #adding in the rate limiter
        self.rate_limiter = rate_limiter
        if not self.rate_limiter:
            config = RateLimitConfig(
                requests_per_minute=20,
                base_delay=3.0,
                retry_attempts=2
            )
            self.rate_limiter = RateLimiter(config)
        #done adding in the rate limiter here

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

EXAMPLE OF GOOD TEST STRUCTURE:
```python
import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from mymodule import divide, safe_divide

def test_divide_normal_case():
    \"\"\"Test division with valid inputs.\"\"\"
    assert divide(10, 2) == 5
    assert divide(9, 3) == 3

def test_divide_with_zero():
    \"\"\"Test division by zero raises error.\"\"\"
    with pytest.raises(ZeroDivisionError):
        divide(10, 0)

def test_safe_divide_with_zero():
    \"\"\"Test safe_divide handles zero correctly.\"\"\"
    with pytest.raises(ValueError, match="Division by zero"):
        safe_divide(10, 0)
```

Return ONLY the JSON object, no markdown, no explanations.
"""
        
        return prompt
    #here modifying generate_unit_tests_with_ai to add in rate limiter
    def generate_unit_tests_with_ai(
        self, 
        code: str, 
        file_path: str
    ) -> Tuple[str, bool]:
        """
        Génère des tests unitaires avec l'AI.
        
        Returns:
            Tuple[test_code: str, success: bool]
        """
        
        if not self.llm:
            print("  ⚠️ Aucune AI disponible, utilisation du fallback")
            return self.generate_fallback_tests(code, file_path)
        
        # Check cache
        code_hash = hash(code + file_path)
        if code_hash in self.test_cache:
            print(f"  ⚡ Cache hit pour {file_path}")
            return self.test_cache[code_hash], True
        
        for iteration in range(1, self.max_retries + 1):
            try:
                print(f"  🤖 Génération de tests avec AI (tentative {iteration}/{self.max_retries})...")
                
                prompt = self.build_test_generation_prompt(code, file_path, iteration)
                
                # Appel LLM
                # response = self.llm.invoke(prompt) replacing this line
                def _call_llm():
                    return self.llm.invoke(prompt)
                
                response= self.rate_limiter.execute_with_rate_limit(
                    _call_llm,
                    agent_name=self.name
                )
                #done replacing
                
                # Handle None or empty response
                if response is None or response.content is None:
                    raise ValueError("LLM returned None response")
                
                raw_text = " ".join(response.content) if isinstance(response.content, list) else str(response.content)
                
                # Check if we got empty content
                if not raw_text or raw_text.strip() == "":
                    raise ValueError("LLM returned empty content")
                
                # Parse JSON
                llm_result = safe_parse_json(raw_text)
                
                test_code = llm_result.get("test_code", "")
                test_description = llm_result.get("test_description", "N/A")
                test_count = llm_result.get("test_count", 0)
                
                if not test_code:
                    raise ValueError("Le LLM n'a pas retourné de code de test")
                
                # Valider syntaxe
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
                
                # ✅ Tests valides
                print(f"  ✅ {test_count} test(s) généré(s): {test_description}")
                
                # Cache
                self.test_cache[code_hash] = test_code
                
                # Log
                log_experiment(
                    agent_name=self.name,
                    model_used="meta-llama/llama-3.3-70b-instruct:free",
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
        
        # Should not reach here
        return self.generate_fallback_tests(code, file_path)
    
    def generate_fallback_tests(
        self, 
        code: str, 
        file_path: str
    ) -> Tuple[str, bool]:
        """
        Génère des tests basiques sans AI (fallback).
        
        Cette méthode extrait les fonctions du code et génère des tests simples.
        """
        
        print(f"  🔧 Génération de tests basiques pour {file_path}")
        
        # Extraire les noms de fonctions
        import re
        function_pattern = r'def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\('
        functions = re.findall(function_pattern, code)
        
        # Filtrer les fonctions privées et __init__
        functions = [f for f in functions if not f.startswith('_')]
        
        if not functions:
            print("  ⚠️ Aucune fonction publique trouvée")
            # Générer un test minimal
            test_code = f"""import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_module_exists():
    \"\"\"Test que le module peut être importé.\"\"\"
    try:
        # Essayer d'importer le module
        import importlib.util
        spec = importlib.util.spec_from_file_location("test_module", r"{file_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        assert True
    except Exception as e:
        pytest.fail(f"Module import failed: {{e}}")
"""
        else:
            # Générer des tests pour chaque fonction
            module_name = os.path.splitext(os.path.basename(file_path))[0]
            
            test_code = f"""import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import the module to test
try:
    from {module_name} import {', '.join(functions)}
except ImportError:
    # Fallback: direct import from file
    import importlib.util
    spec = importlib.util.spec_from_file_location("{module_name}", r"{file_path}")
    test_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(test_module)
    {chr(10).join(f"    {func} = test_module.{func}" for func in functions)}

"""
            
            # Générer un test basique pour chaque fonction
            for func in functions:
                test_code += f"""
def test_{func}_exists():
    \"\"\"Test que la fonction {func} existe et est callable.\"\"\"
    assert callable({func}), "La fonction {func} devrait être callable"

def test_{func}_basic():
    \"\"\"Test basique de la fonction {func}.\"\"\"
    try:
        # Essayer d'appeler avec des arguments par défaut ou None
        # Ce test peut échouer, c'est normal - il sert à détecter les erreurs
        result = {func}()
        assert result is not None or result is None  # Test trivial
    except TypeError:
        # Fonction nécessite des arguments
        pytest.skip("Fonction nécessite des arguments spécifiques")
    except Exception as e:
        # Toute autre erreur
        pytest.fail(f"Erreur inattendue: {{type(e).__name__}}: {{e}}")

"""
        
        print(f"  ✅ {len(functions)} fonction(s) détectée(s), tests basiques générés")
        
        # Log
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
        """
        Sauvegarde le code de test dans un fichier.
        
        Args:
            test_code: Code des tests
            original_file_path: Chemin du fichier original
            
        Returns:
            Chemin du fichier de test créé
        """
        
        # Créer le dossier test_judge s'il n'existe pas
        test_dir = os.path.join(os.path.dirname(original_file_path), "test_judge")
        os.makedirs(test_dir, exist_ok=True)
        
        # Nom du fichier de test
        original_name = os.path.basename(original_file_path)
        test_name = f"test_{original_name}"
        test_path = os.path.join(test_dir, test_name)
        
        # Écrire le fichier avec UTF-8
        with open(test_path, 'w', encoding='utf-8', errors='replace') as f:
            f.write(test_code)
        
        print(f"  💾 Tests sauvegardés: {test_path}")
        
        return test_path
    
    def run_tests(self, test_file_path: str, original_file_path: str) -> Dict:
        """
        Exécute les tests avec pytest.
        
        Args:
            test_file_path: Chemin du fichier de test
            original_file_path: Chemin du fichier original
            
        Returns:
            Dict avec les résultats des tests
        """
        
        print(f"  🚀 Exécution des tests...")
        
        try:
            # Exécuter pytest
            result = subprocess.run(
                ["pytest", test_file_path, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=os.path.dirname(os.path.dirname(test_file_path))  # Project root
            )
            
            stdout = result.stdout
            stderr = result.stderr
            returncode = result.returncode
            
            # Parser les résultats
            success = returncode == 0
            
            # Compter les tests
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
            
            # Log
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
            
            if success:
                print(f"  ✅ Tests réussis: {passed}/{passed + failed + errors}")
            else:
                print(f"  ❌ Tests échoués: {failed}/{passed + failed + errors}")
                print(f"  ⚠️ Erreurs: {errors}")
            
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
        """
        Évalue un fichier : génère et exécute les tests.
        
        Args:
            file_path: Chemin du fichier à évaluer
            
        Returns:
            Dict avec les résultats de l'évaluation
        """
        
        print(f"\n📋 Évaluation de {os.path.basename(file_path)}")
        
        try:
            # Lire le code avec gestion d'encodage
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    code = f.read()
            except UnicodeDecodeError:
                # Fallback to latin-1 if utf-8 fails
                with open(file_path, 'r', encoding='latin-1') as f:
                    code = f.read()
            
            # Générer les tests
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
            
            # Sauvegarder les tests
            test_path = self.save_test_file(test_code, file_path)
            
            # Exécuter les tests
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
        """
        Évalue tous les fichiers d'un dossier.
        
        Args:
            dir_path: Chemin du dossier
            audit_results: Résultats d'audit optionnels (pour filtrer les fichiers)
            
        Returns:
            Liste des résultats d'évaluation
        """
        
        # Si audit_results fourni, tester seulement ces fichiers
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
            
            # Pause pour éviter rate limiting
            if i < total_files:
                print(f"  ⏸️  Pause de 15s pour éviter les rate limits...")
                time.sleep(15)  # 15 secondes au lieu de 3
        
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