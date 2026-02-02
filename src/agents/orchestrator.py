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
    4. SI des tests échouent → Retour à l'étape 1 (max 3 itérations)
    5. Génère un rapport final complet
    """
    
    def __init__(self, max_iterations: int = 3):
        self.name = "Orchestrator"
        self.auditor = None
        self.fixer = None
        self.judge = None
        self.max_iterations = max_iterations  # Nombre max de boucles
        
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
        auto_retry: bool = True  # Nouvelle option: retry automatique
    ) -> Dict:
        """
        Exécute le pipeline complet avec boucle de validation.
        
        Args:
            input_dir: Dossier contenant les fichiers à analyser
            output_dir: Dossier de sortie (par défaut: input_dir/fixed)
            skip_judge: Si True, ne pas exécuter le Judge
            auto_retry: Si True, réessaye automatiquement si tests échouent
            
        Returns:
            Dict avec les résultats de chaque étape
        """
        
        start_time = time.time()
        
        print("\n" + "="*80)
        print("🚀 DÉMARRAGE DU PIPELINE COMPLET AVEC AUTO-RETRY".center(80))
        print("="*80)
        
        if output_dir is None:
            output_dir = os.path.join(input_dir, "fixed")
        
        os.makedirs(output_dir, exist_ok=True)
        
        results = {
            "input_dir": input_dir,
            "output_dir": output_dir,
            "start_time": datetime.now().isoformat(),
            "iterations": [],  # Liste de toutes les itérations
            "success": False,
            "error": None,
            "final_iteration": 0
        }
        
        try:
            # Initialize agents
            self.initialize_agents()
            
            # Variables pour la boucle
            current_dir = input_dir
            all_tests_passing = False
            iteration = 0
            
            # BOUCLE PRINCIPALE
            while iteration < self.max_iterations and not all_tests_passing:
                iteration += 1
                
                print("\n" + "🔄"*40)
                print(f"🔄 ITÉRATION {iteration}/{self.max_iterations}".center(80))
                print("🔄"*40)
                
                iteration_results = {
                    "iteration_number": iteration,
                    "auditor": None,
                    "fixer": None,
                    "judge": None
                }
                
                # ================================
                # ÉTAPE 1: AUDITOR - Analyse
                # ================================
                print("\n" + "─"*80)
                print(f"📊 ÉTAPE 1/3: ANALYSE (AUDITOR) - Itération {iteration}")
                print("─"*80)
                
                audit_start = time.time()
                
                # Analyser les fichiers (sur current_dir après itération 1)
                all_audit_results = self.auditor.analyze_directory(current_dir)
                
                # Filtrer: exclure fixed/ et test_judge/
                audit_results = [
                    r for r in all_audit_results 
                    if not any(excluded in r.get('file_path', '') 
                              for excluded in ['fixed', 'test_judge', '__pycache__'])
                ]
                
                print(f"\n  🔍 Fichiers trouvés: {len(all_audit_results)}")
                print(f"  ✅ Fichiers à traiter: {len(audit_results)}")
                
                audit_duration = time.time() - audit_start
                audit_report = self.auditor.generate_report(audit_results)
                
                iteration_results["auditor"] = {
                    "duration": round(audit_duration, 2),
                    "files_analyzed": audit_report["total_files"],
                    "total_bugs": audit_report["summary"]["total_bugs"],
                }
                
                print(f"\n✅ Analyse terminée en {audit_duration:.2f}s")
                print(f"  🐛 Bugs détectés: {audit_report['summary']['total_bugs']}")
                
                # ================================
                # ÉTAPE 2: FIXER - Correction
                # ================================
                print("\n" + "─"*80)
                print(f"🔧 ÉTAPE 2/3: CORRECTION (FIXER) - Itération {iteration}")
                print("─"*80)
                
                fix_start = time.time()
                fix_results = self.fixer.fix_directory(audit_results, output_dir)
                fix_duration = time.time() - fix_start
                
                fix_report = self.fixer.generate_fix_report(fix_results)
                
                iteration_results["fixer"] = {
                    "duration": round(fix_duration, 2),
                    "total_files": fix_report["summary"]["total_files"],
                    "successful_fixes": fix_report["summary"]["successful_fixes"],
                    "success_rate": fix_report["summary"]["success_rate"]
                }
                
                print(f"\n✅ Correction terminée en {fix_duration:.2f}s")
                print(f"  ✅ {fix_report['summary']['successful_fixes']}/{fix_report['summary']['total_files']} fichiers corrigés")
                
                # ================================
                # ÉTAPE 3: JUDGE - Validation
                # ================================
                if not skip_judge:
                    print("\n" + "─"*80)
                    print(f"🧑‍⚖️ ÉTAPE 3/3: VALIDATION (JUDGE) - Itération {iteration}")
                    print("─"*80)
                    
                    judge_start = time.time()
                    
                    successful_files = [
                        r["output_path"] for r in fix_results 
                        if r.get("success", False) and r.get("output_path")
                    ]
                    
                    if not successful_files:
                        print("  ⚠️ Aucun fichier corrigé à valider")
                        iteration_results["judge"] = {
                            "skipped": True,
                            "reason": "No successfully fixed files"
                        }
                        break  # Sortir de la boucle si aucun fichier corrigé
                    else:
                        eval_results = []
                        for file_path in successful_files:
                            eval_result = self.judge.evaluate_file(file_path)
                            eval_results.append(eval_result)
                        
                        judge_duration = time.time() - judge_start
                        judge_report = self.judge.generate_evaluation_report(eval_results)
                        
                        files_with_passing_tests = judge_report["summary"]["files_with_passing_tests"]
                        total_files_validated = judge_report["summary"]["total_files"]
                        
                        iteration_results["judge"] = {
                            "duration": round(judge_duration, 2),
                            "files_evaluated": total_files_validated,
                            "files_validated": files_with_passing_tests,
                            "validation_rate": judge_report["summary"]["success_rate"]
                        }
                        
                        print(f"\n✅ Validation terminée en {judge_duration:.2f}s")
                        print(f"  ✅ {files_with_passing_tests}/{total_files_validated} fichiers validés")
                        
                        # Vérifier si TOUS les tests passent
                        if files_with_passing_tests == total_files_validated:
                            print("\n🎉 TOUS LES TESTS PASSENT!")
                            all_tests_passing = True
                        else:
                            failed_files = total_files_validated - files_with_passing_tests
                            print(f"\n⚠️  {failed_files} fichier(s) avec tests échoués")
                            
                            if auto_retry and iteration < self.max_iterations:
                                print(f"🔄 Nouvelle itération pour corriger les fichiers échoués...")
                                # Pour la prochaine itération, analyser le output_dir
                                current_dir = output_dir
                            else:
                                print("❌ Nombre max d'itérations atteint ou auto-retry désactivé")
                                break
                
                # Sauvegarder les résultats de cette itération
                results["iterations"].append(iteration_results)
                results["final_iteration"] = iteration
                
                # Si Judge désactivé ou tous tests passent, sortir de la boucle
                if skip_judge or all_tests_passing:
                    break
            
            # ================================
            # RAPPORT FINAL
            # ================================
            total_duration = time.time() - start_time
            results["end_time"] = datetime.now().isoformat()
            results["total_duration"] = round(total_duration, 2)
            results["success"] = all_tests_passing or skip_judge
            results["all_tests_passing"] = all_tests_passing
            
            self._print_final_summary(results)
            
            # Log du pipeline complet
            log_experiment(
                agent_name=self.name,
                model_used="N/A",
                action=ActionType.ANALYSIS,
                details={
                    "input_prompt": f"Run pipeline on {input_dir} with {iteration} iterations",
                    "output_response": f"Pipeline completed in {total_duration:.2f}s",
                    "iterations": iteration,
                    "all_tests_passing": all_tests_passing,
                    "duration": total_duration
                },
                status="SUCCESS" if results["success"] else "PARTIAL"
            )
            
            # Sauvegarder le rapport final
            final_report_path = os.path.join("logs", "orchestrator_final_report.json")
            os.makedirs("logs", exist_ok=True)
            with open(final_report_path, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            print(f"\n💾 Rapport final sauvegardé: {final_report_path}")
            
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
                    "output_response": f"Error: {str(e)}",
                    "error": str(e)
                },
                status="FAILURE"
            )
            
            return results
    
    def _print_final_summary(self, results: Dict):
        """Affiche le résumé final du pipeline."""
        
        print("\n" + "="*80)
        print("📊 RÉSUMÉ FINAL DU PIPELINE".center(80))
        print("="*80)
        
        print(f"\n⏱️  Durée totale: {results['total_duration']:.2f}s")
        print(f"🔄 Nombre d'itérations: {results['final_iteration']}")
        
        # Résumé de chaque itération
        for i, iter_result in enumerate(results.get("iterations", []), 1):
            print(f"\n📍 ITÉRATION {i}:")
            if iter_result.get("auditor"):
                print(f"  📊 Bugs détectés: {iter_result['auditor']['total_bugs']}")
            if iter_result.get("fixer"):
                print(f"  🔧 Corrections: {iter_result['fixer']['successful_fixes']}/{iter_result['fixer']['total_files']}")
            if iter_result.get("judge") and not iter_result["judge"].get("skipped"):
                print(f"  🧑‍⚖️ Validés: {iter_result['judge']['files_validated']}/{iter_result['judge']['files_evaluated']}")
        
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
        
        print(f"✅ Audit terminé - Rapport: {report_path}")
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
        fix_report = self.fixer.generate_fix_report(fix_results)
        
        os.makedirs("logs", exist_ok=True)
        report_path = os.path.join("logs", "fix_only_report.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(fix_report, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Correction terminée - Rapport: {report_path}")
        return fix_report
    
    def run_validate_only(self, input_dir: str) -> Dict:
        """Exécute uniquement le Judge sur un dossier."""
        print("\n🧑‍⚖️ Mode: VALIDATION SEULEMENT\n")
        
        self.judge = Judge()
        eval_results = self.judge.evaluate_directory(input_dir)
        judge_report = self.judge.generate_evaluation_report(eval_results)
        
        os.makedirs("logs", exist_ok=True)
        report_path = os.path.join("logs", "validate_only_report.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(judge_report, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Validation terminée - Rapport: {report_path}")
        return judge_report
    