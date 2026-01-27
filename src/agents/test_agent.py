"""
Agent Tester - Génération automatique de tests unitaires (TDD)

Responsabilités:
1. Analyser le code et générer des tests pytest
2. S'assurer que les tests ÉCHOUENT d'abord (TDD)
3. Après correction, vérifier que les tests PASSENT
4. Logger toutes les opérations
"""

import os
import json
import time
import subprocess
from typing import Dict, List
from dotenv import load_dotenv

from src.utils.file_manager import PyFileTool
from src.utils.logger import log_experiment, ActionType
from langchain_openai import ChatOpenAI
from langchain_core.outputs import ChatGenerationChunk
from langchain_core.messages import AIMessageChunk


load_dotenv()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError("❌ OPENROUTER_API_KEY non trouvée")


class NonStreamingChatOpenAI(ChatOpenAI):
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


class Tester:
    """
    Agent de génération de tests unitaires.
    
    Workflow TDD:
    1. Analyser le code buggy
    2. Générer des tests qui ÉCHOUENT
    3. Après correction, vérifier que les tests PASSENT
    """
    
    def __init__(self):
        self.name = "Tester"
        self.llm = llm
        
    def build_test_prompt(self, file_path: str, code: str, audit_report: Dict = None) -> str:
        """Construit le prompt pour générer les tests."""
        
        prompt = f"""You are an expert Python test engineer specializing in pytest.

Generate comprehensive unit tests for the following Python code.

CRITICAL REQUIREMENTS:
1. Use pytest framework
2. Test ALL functions and edge cases
3. Include tests that will FAIL on buggy code (TDD approach)
4. Use descriptive test names
5. Add docstrings to tests

File: {file_path}

CODE TO TEST:
```python
{code}
```
"""
        
        if audit_report:
            bugs = audit_report.get("bugs", [])
            if bugs:
                prompt += "\n\nKNOWN BUGS TO TEST:\n"
                for bug in bugs[:5]:
                    prompt += f"- Line {bug.get('line')}: {bug.get('description')}\n"
        
        prompt += """

Return ONLY valid JSON with this structure:
{
  "test_code": "complete pytest test file content here",
  "test_cases": [
    {
      "name": "test_division_by_zero",
      "description": "Tests division by zero handling",
      "should_fail_on_buggy_code": true
    }
  ],
  "coverage_estimate": 0.85
}

The test_code must be complete, runnable pytest code with:
- Proper imports
- Test class or functions
- All edge cases
- Clear assertions
"""
        
        return prompt
    
    def generate_tests(self, file_path: str, audit_report: Dict = None, output_dir: str = "outputs/tests") -> Dict:
        """
        Génère des tests pytest pour un fichier.
        
        Args:
            file_path: Chemin du fichier à tester
            audit_report: Rapport d'audit (optionnel)
            output_dir: Dossier de sortie des tests
            
        Returns:
            Dict avec le code de test et métadonnées
        """
        
        print(f"\n🧪 Génération de tests pour: {file_path}")
        
        # Lire le code
        try:
            code = PyFileTool.read_file(file_path)
        except Exception as e:
            error_msg = f"Impossible de lire {file_path}: {e}"
            log_experiment(
                agent_name=self.name,
                model_used="N/A",
                action=ActionType.GENERATION,
                details={
                    "file_tested": file_path,
                    "input_prompt": "N/A",
                    "output_response": error_msg,
                    "error": str(e)
                },
                status="FAILURE"
            )
            return {"success": False, "error": error_msg}
        
        # Générer le prompt
        prompt = self.build_test_prompt(file_path, code, audit_report)
        
        try:
            # Appel LLM
            response = self.llm.invoke(prompt)
            raw_text = " ".join(response.content) if isinstance(response.content, list) else str(response.content)
            
            # Parse JSON
            result = safe_parse_json(raw_text)
            
            test_code = result.get("test_code", "")
            test_cases = result.get("test_cases", [])
            coverage = result.get("coverage_estimate", 0.0)
            
            if not test_code:
                raise ValueError("Le LLM n'a pas généré de code de test")
            
            # Sauvegarder le fichier de test
            os.makedirs(output_dir, exist_ok=True)
            
            file_name = os.path.basename(file_path)
            test_file_name = f"test_{file_name}"
            test_file_path = os.path.join(output_dir, test_file_name)
            
            with open(test_file_path, 'w', encoding='utf-8') as f:
                f.write(test_code)
            
            print(f"  ✅ Tests générés: {test_file_path}")
            print(f"  📊 Cas de test: {len(test_cases)}")
            print(f"  📈 Couverture estimée: {coverage*100:.1f}%")
            
            # Logging
            log_experiment(
                agent_name=self.name,
                model_used="meta-llama/llama-3.3-70b-instruct:free",
                action=ActionType.GENERATION,
                details={
                    "file_tested": file_path,
                    "input_prompt": prompt[:500] + "...",
                    "output_response": str(result)[:500] + "...",
                    "test_file": test_file_path,
                    "test_cases_count": len(test_cases),
                    "coverage_estimate": coverage
                },
                status="SUCCESS"
            )
            
            return {
                "success": True,
                "file_path": file_path,
                "test_file_path": test_file_path,
                "test_code": test_code,
                "test_cases": test_cases,
                "coverage_estimate": coverage
            }
            
        except Exception as e:
            error_msg = f"Erreur génération tests: {e}"
            print(f"  ❌ {error_msg}")
            
            log_experiment(
                agent_name=self.name,
                model_used="meta-llama/llama-3.3-70b-instruct:free",
                action=ActionType.GENERATION,
                details={
                    "file_tested": file_path,
                    "input_prompt": prompt[:500] + "...",
                    "output_response": error_msg,
                    "error": str(e)
                },
                status="FAILURE"
            )
            
            return {"success": False, "error": error_msg}
    
    def run_tests(self, test_file_path: str, target_file: str = None) -> Dict:
        """
        Exécute les tests pytest.
        
        Args:
            test_file_path: Chemin du fichier de test
            target_file: Fichier cible testé (pour le contexte)
            
        Returns:
            Dict avec les résultats des tests
        """
        
        print(f"\n🏃 Exécution des tests: {test_file_path}")
        
        try:
            # Exécuter pytest avec sortie verbale
            result = subprocess.run(
                ["pytest", test_file_path, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=60
            )
            
            stdout = result.stdout
            stderr = result.stderr
            returncode = result.returncode
            
            # Parser les résultats
            passed = stdout.count(" PASSED")
            failed = stdout.count(" FAILED")
            errors = stdout.count(" ERROR")
            
            success = returncode == 0
            
            status_emoji = "✅" if success else "❌"
            print(f"  {status_emoji} Tests: {passed} PASSED, {failed} FAILED, {errors} ERROR")
            
            # Logging
            log_experiment(
                agent_name=self.name,
                model_used="pytest",
                action=ActionType.DEBUG,
                details={
                    "test_file": test_file_path,
                    "target_file": target_file or "unknown",
                    "input_prompt": f"Run tests on {test_file_path}",
                    "output_response": stdout[:1000],
                    "passed": passed,
                    "failed": failed,
                    "errors": errors,
                    "success": success
                },
                status="SUCCESS" if success else "FAILURE"
            )
            
            return {
                "success": success,
                "passed": passed,
                "failed": failed,
                "errors": errors,
                "stdout": stdout,
                "stderr": stderr,
                "returncode": returncode
            }
            
        except subprocess.TimeoutExpired:
            error_msg = "Tests timeout (>60s)"
            print(f"  ⏰ {error_msg}")
            return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"Erreur exécution tests: {e}"
            print(f"  ❌ {error_msg}")
            return {"success": False, "error": error_msg}
    
    def generate_tests_for_directory(
        self, 
        audit_results: List[Dict], 
        output_dir: str = "outputs/tests"
    ) -> List[Dict]:
        """Génère des tests pour tous les fichiers d'un dossier."""
        
        print(f"\n🧪 Génération de tests pour {len(audit_results)} fichier(s)...\n")
        
        results = []
        for i, audit_report in enumerate(audit_results, 1):
            file_path = audit_report.get("file_path")
            
            if not file_path:
                print(f"⚠️ [{i}/{len(audit_results)}] Rapport sans file_path")
                continue
            
            print(f"[{i}/{len(audit_results)}]", end=" ")
            result = self.generate_tests(file_path, audit_report, output_dir)
            results.append(result)
            
            # Pause
            if i < len(audit_results):
                time.sleep(3)
        
        return results
    
    def generate_report(self, test_results: List[Dict]) -> Dict:
        """Génère un rapport de synthèse."""
        
        total_files = len(test_results)
        successful = sum(1 for r in test_results if r.get("success", False))
        failed = total_files - successful
        
        total_test_cases = sum(len(r.get("test_cases", [])) for r in test_results)
        avg_coverage = sum(r.get("coverage_estimate", 0) for r in test_results) / max(total_files, 1)
        
        return {
            "summary": {
                "total_files": total_files,
                "successful_generation": successful,
                "failed_generation": failed,
                "total_test_cases": total_test_cases,
                "average_coverage": round(avg_coverage, 2)
            },
            "files": test_results
        }