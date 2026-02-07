import os
import json
import time
from typing import Dict, List, Optional
from datetime import datetime
from dotenv import load_dotenv

from src.agents.auditor_agent import Auditor
from src.agents.fixer_agent import Fixer
from src.agents.judge_agent import Judge
from src.utils.file_manager import PyFileTool
from src.utils.logger import log_experiment, ActionType

load_dotenv()

# ================================
# Orchestrator Agent avec Boucle Auto-Correction
# ================================
class Orchestrator:
    """
    Agent Orchestrator : Coordonne le workflow complet du système.

    Workflow avec boucle:
    1. Auditor → Analyse et détecte les bugs
    2. Fixer → Corrige les bugs détectés
    3. Judge → Valide les corrections avec des tests
    4. Si des tests échouent → Retour à l'étape 1 (max 10 itérations)
    5. Génère un rapport final complet
    """

    def __init__(self, max_iterations: int = 10):
        self.name = "Orchestrator"
        self.auditor: Optional[Auditor] = None
        self.fixer: Optional[Fixer] = None
        self.judge: Optional[Judge] = None
        self.max_iterations = max(1, min(10, max_iterations))
        self.validated_files = set()

    # -------------------------------
    # Initialisation des agents
    # -------------------------------
    def initialize_agents(self):
        print("🔧 Initialisation des agents...")

        try:
            self.auditor = Auditor()
            print("  ✅ Auditor initialisé")
        except Exception as e:
            print(f"  ⚠️ Erreur Auditor: {e}")
            self.auditor = None

        try:
            self.fixer = Fixer()
            print("  ✅ Fixer initialisé")
        except Exception as e:
            print(f"  ⚠️ Erreur Fixer: {e}")
            self.fixer = None

        try:
            self.judge = Judge()
            print("  ✅ Judge initialisé")
        except Exception as e:
            print(f"  ⚠️ Erreur Judge: {e}")
            self.judge = None

        if not all([self.auditor, self.fixer, self.judge]):
            raise RuntimeError("Certains agents n'ont pas pu être initialisés")

    # -------------------------------
    # Pipeline complet avec boucle auto-healing
    # -------------------------------
    def run_full_pipeline(
        self,
        input_dir: str,
        output_dir: str = None,
        skip_judge: bool = False,
        auto_retry: bool = True
    ) -> Dict:

        start_time = time.time()
        output_dir = output_dir or os.path.join(input_dir, "fixed")
        os.makedirs(output_dir, exist_ok=True)

        results = {
            "input_dir": input_dir,
            "output_dir": output_dir,
            "start_time": datetime.now().isoformat(),
            "iterations": [],
            "success": False,
            "error": None,
            "final_iteration": 0,
            "validated_files": []
        }

        try:
            self.initialize_agents()

            iteration = 0
            all_tests_passing = False
            pending_audit_feedback = []
            total_initial_files = None
            current_dir = input_dir

            while iteration < self.max_iterations and not all_tests_passing:
                iteration += 1
                print("\n" + "🔄" * 40)
                print(f"🔄 ITÉRATION {iteration}/{self.max_iterations}".center(80))
                print("🔄" * 40)

                iteration_results = {"iteration_number": iteration, "auditor": None, "fixer": None, "judge": None}

                # -------------------------------
                # Étape 1 : Auditor
                # -------------------------------
                print("\n📊 ÉTAPE 1/3: ANALYSE (AUDITOR)")
                if pending_audit_feedback:
                    audit_results = pending_audit_feedback
                    pending_audit_feedback = []
                    print(f"  ♻️ Auto-Healing: Reprise de {len(audit_results)} fichiers.")
                else:
                    all_raw_results = self.auditor.analyze_directory(current_dir)
                    if total_initial_files is None:
                        total_initial_files = len(all_raw_results)
                    audit_results = [
                        r for r in all_raw_results
                        if os.path.basename(r.get("file_path", "")) not in self.validated_files
                        and not any(ex in r.get("file_path", "") for ex in ["test_judge", "__pycache__"])
                    ]

                if not audit_results:
                    print("✨ Aucun bug restant à corriger.")
                    all_tests_passing = True
                    break

                iteration_results["auditor"] = {"total_bugs": sum(len(r.get("bugs", [])) for r in audit_results)}

                # -------------------------------
                # Étape 2 : Fixer
                # -------------------------------
                print("\n🔧 ÉTAPE 2/3: CORRECTION (FIXER)")
                fix_start = time.time()
                fix_results = self.fixer.fix_directory(audit_results, output_dir)
                fix_report = self.fixer.generate_fix_report(fix_results)
                iteration_results["fixer"] = {
                    "duration": round(time.time() - fix_start, 2),
                    "successful_fixes": fix_report["summary"]["successful_fixes"],
                    "total_files": fix_report["summary"]["total_files"]
                }

                # -------------------------------
                # Étape 3 : Judge
                # -------------------------------
                if not skip_judge:
                    print("\n🧑‍⚖️ ÉTAPE 3/3: VALIDATION (JUDGE)")
                    judge_start = time.time()
                    files_status = {}
                    successful_fix_paths = [r["output_path"] for r in fix_results if r.get("success")]

                    for path in successful_fix_paths:
                        f_name = os.path.basename(path)
                        eval_data = self.judge.evaluate_file(path)
                        files_status[path] = {"is_valid": eval_data.get("success", False), "feedback": eval_data}

                        if eval_data.get("success"):
                            print(f"    ✅ {f_name}: OK (Whitelist)")
                            self.validated_files.add(f_name)
                        elif auto_retry:
                            print(f"    ❌ {f_name}: ÉCHEC")
                            orig = next((r for r in audit_results if os.path.basename(r.get("file_path", "")) == f_name), None)
                            if orig:
                                orig["judge_feedback"] = eval_data
                                pending_audit_feedback.append(orig)

                    judge_report = self.judge.generate_evaluation_report([files_status[path]["feedback"] for path in files_status])
                    iteration_results["judge"] = {
                        "duration": round(time.time() - judge_start, 2),
                        "files_validated": judge_report["summary"]["files_with_passing_tests"],
                        "files_evaluated": judge_report["summary"]["total_files"],
                        "files_status": files_status
                    }

                    if total_initial_files is not None:
                        all_tests_passing = len(self.validated_files) >= total_initial_files

                results["iterations"].append(iteration_results)
                results["final_iteration"] = iteration
                current_dir = output_dir

            results["success"] = all_tests_passing or skip_judge
            results["validated_files"] = list(self.validated_files)
            results["total_duration"] = round(time.time() - start_time, 2)

            self._print_final_summary(results)
            return results

        except Exception as e:
            error_msg = f"Erreur dans le pipeline: {e}"
            print(f"\n❌ {error_msg}")
            results.update({"error": str(e), "end_time": datetime.now().isoformat(), "total_duration": round(time.time() - start_time, 2)})

            log_experiment(
                agent_name=self.name,
                model_used="N/A",
                action=ActionType.ANALYSIS,
                details={
                    "input_prompt": f"Run pipeline on {input_dir}",
                    "output_response": f"Pipeline error after {results.get('final_iteration', 0)} iterations",
                    "error": str(e)
                },
                status="FAILURE"
            )
            return results

    # -------------------------------
    # Affichage résumé final
    # -------------------------------
    def _print_final_summary(self, results: Dict):
        print("\n" + "=" * 80)
        print("📊 RÉSUMÉ FINAL DU PIPELINE".center(80))
        print("=" * 80)
        print(f"\n⏱️ Durée totale: {results['total_duration']:.2f}s")
        print(f"🔄 Itérations: {results['final_iteration']}/{self.max_iterations}")

        for i, iter_result in enumerate(results.get("iterations", []), 1):
            print(f"\n📍 ITÉRATION {i}:")
            if iter_result.get("auditor"):
                print(f"  📊 Bugs: {iter_result['auditor']['total_bugs']}")
            if iter_result.get("fixer"):
                print(f"  🔧 Corrections: {iter_result['fixer']['successful_fixes']}/{iter_result['fixer']['total_files']}")
            if iter_result.get("judge"):
                print(f"  🧑‍⚖️ Validés: {iter_result['judge']['files_validated']}/{iter_result['judge']['files_evaluated']}")

        print(f"\n📁 Entrée: {results['input_dir']}")
        print(f"📁 Sortie: {results['output_dir']}")
        print("\n✅ PIPELINE TERMINÉ AVEC SUCCÈS" if results.get("success") else "\n⚠️ PIPELINE TERMINÉ - Corrections restantes")
        print("\n" + "=" * 80)

    # -------------------------------
    # Modes spécialisés
    # -------------------------------
    def run_audit_only(self, input_dir: str) -> Dict:
        print("\n🔍 Mode: AUDIT SEULEMENT\n")
        self.auditor = Auditor()
        audit_results = self.auditor.analyze_directory(input_dir)
        return self.auditor.generate_report(audit_results)

    def run_fix_only(self, input_dir: str, output_dir: str = None) -> Dict:
        print("\n🔧 Mode: AUDIT + FIX\n")
        output_dir = output_dir or os.path.join(input_dir, "fixed")
        self.auditor = Auditor()
        audit_results = self.auditor.analyze_directory(input_dir)
        self.fixer = Fixer()
        fix_results = self.fixer.fix_directory(audit_results, output_dir)
        return self.fixer.generate_fix_report(fix_results)

    def run_validate_only(self, input_dir: str) -> Dict:
        print("\n🧑‍⚖️ Mode: VALIDATION SEULEMENT\n")
        self.judge = Judge()
        eval_results = self.judge.evaluate_directory(input_dir)
        return self.judge.generate_evaluation_report(eval_results)
