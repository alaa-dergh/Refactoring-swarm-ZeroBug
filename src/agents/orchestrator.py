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
    4. SI des tests échouent → Retour à l'étape 1 (max 10 itérations)
    5. Génère un rapport final complet
    """
    
    def __init__(self, max_iterations: int = 10):
        self.name = "Orchestrator"
        self.auditor = None
        self.fixer = None
        self.judge = None
        self.max_iterations = max(1, min(10, max_iterations))  # Clamp between 1-10
        # NOUVEAU: Suivi des fichiers validés pour éviter de boucler sur ce qui fonctionne déjà
        self.validated_files = set()
    def initialize_agents(self):
        """Initialize tous les agents."""
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
    
    def run_full_pipeline(
        self, 
        input_dir: str,
        output_dir: str = None,
        skip_judge: bool = False,
        auto_retry: bool = True
    ) -> Dict:
        """
        Exécute le pipeline complet avec boucle de validation et auto-healing.
        """
        start_time = time.time()
        
        print("\n" + "="*80)
        print("🚀 DÉMARRAGE DU PIPELINE COMPLET AVEC AUTO-HEALING".center(80))
        print(f"📊 Max iterations: {self.max_iterations} | Suivi d'état actif".center(80))
        print("="*80)
        
        if output_dir is None:
            output_dir = os.path.join(input_dir, "fixed")
        
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
            current_dir = input_dir
            all_tests_passing = False
            iteration = 0
            pending_audit_feedback = [] 

            while iteration < self.max_iterations and not all_tests_passing:
                iteration += 1
                
                print("\n" + "🔄"*40)
                print(f"🔄 ITÉRATION {iteration}/{self.max_iterations}".center(80))
                print("🔄"*40)
                
                iteration_results = {"iteration_number": iteration, "auditor": None, "fixer": None, "judge": None}
                
                # ================================================
                # ÉTAPE 1: AUDITOR - Analyse
                # ================================================
                print(f"\n📊 ÉTAPE 1/3: ANALYSE (AUDITOR)")
                
                if pending_audit_feedback:
                    audit_results = pending_audit_feedback
                    pending_audit_feedback = [] 
                    print(f"  ♻️  Auto-Healing: Reprise de {len(audit_results)} fichiers.")
                else:
                    all_raw_results = self.auditor.analyze_directory(current_dir)
                    audit_results = [
                        r for r in all_raw_results 
                        if os.path.basename(r.get('file_path', '')) not in self.validated_files
                        and not any(ex in r.get('file_path', '') for ex in ['test_judge', '__pycache__'])
                    ]

                if not audit_results:
                    print("✨ Tout est validé !")
                    all_tests_passing = True
                    break

                iteration_results["auditor"] = {"total_bugs": sum(len(r.get('bugs', [])) for r in audit_results)}

                # ================================================
                # ÉTAPE 2: FIXER - Correction
                # ================================================
                print(f"\n🔧 ÉTAPE 2/3: CORRECTION (FIXER)")
                fix_start = time.time()
                fix_results = self.fixer.fix_directory(audit_results, output_dir)
                fix_report = self.fixer.generate_fix_report(fix_results)
                
                iteration_results["fixer"] = {
                    "duration": round(time.time() - fix_start, 2),
                    "successful_fixes": fix_report["summary"]["successful_fixes"],
                    "total_files": fix_report["summary"]["total_files"]
                }

                # ================================================
                # ÉTAPE 3: JUDGE - Validation & Auto-Healing
                # ================================================
                if not skip_judge:
                    print(f"\n🧑‍⚖️ ÉTAPE 3/3: VALIDATION (JUDGE)")
                    judge_start = time.time()
                    
                    successful_fix_paths = [r["output_path"] for r in fix_results if r.get("success") and r.get("output_path")]
                    
                    if successful_fix_paths:
                        eval_results = []
                        files_status = {}
                        
                        for path in successful_fix_paths:
                            f_name = os.path.basename(path)
                            eval_data = self.judge.evaluate_file(path)
                            eval_results.append(eval_data)
                            
                            is_valid = eval_data.get("success", False)
                            files_status[path] = {"is_valid": is_valid, "feedback": eval_data}
                            
                            if is_valid:
                                print(f"    ✅ {f_name}: OK (Whitelist)")
                                self.validated_files.add(f_name)
                            else:
                                print(f"    ❌ {f_name}: ÉCHEC")
                                # Préparation Feedback pour l'Auditor
                                orig = next((r for r in audit_results if os.path.basename(r.get("file_path", "")) == f_name), None)
                                if orig and auto_retry:
                                    orig["judge_feedback"] = eval_data
                                    pending_audit_feedback.append(orig)

                        judge_report = self.judge.generate_evaluation_report(eval_results)
                        iteration_results["judge"] = {
                            "duration": round(time.time() - judge_start, 2),
                            "files_validated": judge_report["summary"]["files_with_passing_tests"],
                            "files_evaluated": judge_report["summary"]["total_files"],
                            "files_status": files_status
                        }
                        
                        if not pending_audit_feedback and iteration_results["judge"]["files_validated"] > 0:
                             all_tests_passing = (len(self.validated_files) >= len(all_raw_results) if 'all_raw_results' in locals() else True)

                results["iterations"].append(iteration_results)
                results["final_iteration"] = iteration
                current_dir = output_dir # Le dossier de sortie devient l'entrée du tour suivant

            # Finalisation du rapport
            results["success"] = all_tests_passing or skip_judge
            results["total_duration"] = round(time.time() - start_time, 2)
            self._print_final_summary(results)
            return results

        except Exception as e:
            error_msg = f"Erreur dans le pipeline: {e}"
            print(f"\n❌ {error_msg}")
            
            results["error"] = str(e)
            results["end_time"] = datetime.now().isoformat()
            results["total_duration"] = round(time.time() - start_time, 2)
            
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

    def _print_final_summary(self, results: Dict):
        """Affiche le résumé final du pipeline avec détails auto-healing."""
        print("\n" + "="*80)
        print("📊 RÉSUMÉ FINAL DU PIPELINE".center(80))
        print("="*80)
        
        print(f"\n⏱️  Durée totale: {results['total_duration']:.2f}s")
        print(f"🔄 Nombre d'itérations: {results['final_iteration']}/{self.max_iterations}")
        
        for i, iter_result in enumerate(results.get("iterations", []), 1):
            print(f"\n📍 ITÉRATION {i}:")
            if iter_result.get("auditor"):
                print(f"  📊 Bugs détectés: {iter_result['auditor']['total_bugs']}")
            if iter_result.get("fixer"):
                print(f"  🔧 Corrections: {iter_result['fixer']['successful_fixes']}/{iter_result['fixer']['total_files']}")
            if iter_result.get("judge") and not iter_result["judge"].get("skipped"):
                print(f"  🧑‍⚖️ Validés: {iter_result['judge']['files_validated']}/{iter_result['judge']['files_evaluated']}")
                if iter_result['judge'].get("files_status"):
                    print(f"     Détail des fichiers:")
                    for filepath, status in iter_result['judge']['files_status'].items():
                        icon = "✅" if status.get('is_valid') else "❌"
                        print(f"     {icon} {os.path.basename(filepath)}")
        
        print(f"\n📁 Dossier d'entrée: {results['input_dir']}")
        print(f"📁 Dossier de sortie: {results['output_dir']}")
        
        if results.get("all_tests_passing"):
            print(f"\n🎉 SUCCÈS TOTAL - TOUS LES FICHIERS SONT 100% CORRECTS!")
        elif results.get("success"):
            print(f"\n✅ PIPELINE TERMINÉ AVEC SUCCÈS!")
        else:
            print(f"\n⚠️  PIPELINE TERMINÉ - Certains fichiers nécessitent encore des corrections")
        print("\n" + "="*80)

    def run_audit_only(self, input_dir: str) -> Dict:
        """Exécute uniquement l'Auditor."""
        print("\n🔍 Mode: AUDIT SEULEMENT\n")
        self.auditor = Auditor()
        audit_results = self.auditor.analyze_directory(input_dir)
        audit_report = self.auditor.generate_report(audit_results)
        
        os.makedirs("logs", exist_ok=True)
        report_path = os.path.join("logs", "audit_only_report.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(audit_report, f, indent=2, ensure_ascii=False)
        return audit_report

    def run_fix_only(self, input_dir: str, output_dir: str = None) -> Dict:
        """Exécute Auditor puis Fixer."""
        print("\n🔧 Mode: AUDIT + FIX\n")
        if output_dir is None:
            output_dir = os.path.join(input_dir, "fixed")
        
        self.auditor = Auditor()
        audit_results = self.auditor.analyze_directory(input_dir)
        self.fixer = Fixer()
        fix_results = self.fixer.fix_directory(audit_results, output_dir)
        return self.fixer.generate_fix_report(fix_results)

    def run_validate_only(self, input_dir: str) -> Dict:
        """Exécute uniquement le Judge sur un dossier."""
        print("\n🧑‍⚖️ Mode: VALIDATION SEULEMENT\n")
        self.judge = Judge()
        eval_results = self.judge.evaluate_directory(input_dir)
        return self.judge.generate_evaluation_report(eval_results)