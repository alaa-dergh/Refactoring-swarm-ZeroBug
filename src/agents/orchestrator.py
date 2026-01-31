from logging import config
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
from src.utils.rate_limiter import RateLimiter, RateLimitConfig


# modifications for rate_limiter done on class Orchestrator and adding l'affichage des statistiques a la fin du pipelie? on line: 114 



# ================================
# Orchestrator Agent
# ================================


class Orchestrator:
    """
    Agent Orchestrator : Coordonne le workflow complet du système.
    
    Workflow:
    1. Auditor → Analyse et détecte les bugs
    2. Fixer → Corrige les bugs détectés
    3. Judge → Valide les corrections avec des tests
    4. Génère un rapport final complet
    """
    
    def __init__(self):
        self.name = "Orchestrator"
        self.auditor = None
        self.fixer = None
        self.judge = None
        

        #creating a UNIQUEE shared rate limiter for all agents:
        config = RateLimitConfig(
            requests_per_minute=20,  # ← Reduced from 20
            requests_per_hour=200,   # ← Reduced from 200
            base_delay=3.0,        # ← Increased from 3.0
            retry_attempts=3,
             exponential_base=2.0
        ) 
        self.rate_limiter = RateLimiter(config)
        #done creating hehe

    def initialize_agents(self):
        """Initialize tous les agents."""
        print("🔧 Initialisation des agents...")
        #passing the rate limiter to ALL agents
        try:
            #self.auditor = Auditor()
            self.auditor = Auditor(rate_limiter=self.rate_limiter)  
            print("  ✅ Auditor initialisé")
        except Exception as e:
            print(f"  ⚠️ Erreur Auditor: {e}")
            self.auditor = None
        
        try:
            self.fixer = Fixer(rate_limiter=self.rate_limiter)
            print("  ✅ Fixer initialisé")
        except Exception as e:
            print(f"  ⚠️ Erreur Fixer: {e}")
            self.fixer = None
        
        try:
            self.judge = Judge(rate_limiter=self.rate_limiter)
            print("  ✅ Judge initialisé")
        except Exception as e:
            print(f"  ⚠️ Erreur Judge: {e}")
            self.judge = None

            #done passing
            #displaying the status of rate limter
            print("\n🛡️ Rate Limiter configuré:")
            print(f"  • RPM Limit: {config.requests_per_minute}")
            print(f"  • Base Delay: {config.base_delay}s")
            print(f"  • Retry Attempts: {config.retry_attempts}")
        #done displaying

        if not all([self.auditor, self.fixer, self.judge]):
            raise RuntimeError("Certains agents n'ont pas pu être initialisés")
    
    #adding stats for some reason
    def run_full_pipeline(
        self, 
        input_dir: str,
        output_dir: str = None,
        skip_judge: bool = False
    ) -> Dict:
        """
        Exécute le pipeline complet : Auditor → Fixer → Judge.
        
        Args:
            input_dir: Dossier contenant les fichiers à analyser
            output_dir: Dossier de sortie (par défaut: input_dir/fixed)
            skip_judge: Si True, ne pas exécuter le Judge
            
        Returns:
            Dict avec les résultats de chaque étape
        """
        
        start_time = time.time()
        
        print("\n" + "="*80)
        self.rate_limiter.print_stats() #this one
        print("🚀 DÉMARRAGE DU PIPELINE COMPLET".center(80))
        print("="*80)
        
        # Définir le dossier de sortie
        if output_dir is None:
            output_dir = os.path.join(input_dir, "fixed")
        
        os.makedirs(output_dir, exist_ok=True)
        
        results = {
            "input_dir": input_dir,
            "output_dir": output_dir,
            "start_time": datetime.now().isoformat(),
            "auditor": None,
            "fixer": None,
            "judge": None,
            "success": False,
            "error": None
        }
        
        try:
            # Initialize agents
            self.initialize_agents()
            
            # ================================
            # ÉTAPE 1: AUDITOR - Analyse
            # ================================
            print("\n" + "─"*80)
            print("📊 ÉTAPE 1/3: ANALYSE (AUDITOR)")
            print("─"*80)
            
            audit_start = time.time()
            
            # Analyser et filtrer les fichiers
            all_audit_results = self.auditor.analyze_directory(input_dir)
            
            # Filtrer: exclure fixed/ et test_judge/
            audit_results = [
                r for r in all_audit_results 
                if not any(excluded in r.get('file_path', '') 
                          for excluded in ['fixed', 'test_judge', '__pycache__'])
            ]
            
            print(f"\n  🔍 Fichiers trouvés: {len(all_audit_results)}")
            print(f"  ✅ Fichiers à traiter: {len(audit_results)}")
            if len(all_audit_results) > len(audit_results):
                print(f"  ⏭️  Fichiers exclus: {len(all_audit_results) - len(audit_results)} (fixed/, test_judge/)")
            
            audit_duration = time.time() - audit_start
            
            # Générer le rapport d'audit
            audit_report = self.auditor.generate_report(audit_results)
            
            results["auditor"] = {
                "duration": round(audit_duration, 2),
                "files_analyzed": audit_report["total_files"],
                "total_bugs": audit_report["summary"]["total_bugs"],
                "total_quality_issues": audit_report["summary"]["total_quality_issues"],
                "total_style_issues": audit_report["summary"]["total_style_issues"],
                "results": audit_results
            }
            
            print(f"\n✅ Analyse terminée en {audit_duration:.2f}s")
            print(f"  📁 Fichiers analysés: {audit_report['total_files']}")
            print(f"  🐛 Bugs détectés: {audit_report['summary']['total_bugs']}")
            print(f"  ⚠️  Issues qualité: {audit_report['summary']['total_quality_issues']}")
            
            # Sauvegarder le rapport d'audit
            os.makedirs("logs", exist_ok=True)
            audit_path = os.path.join("logs", "orchestrator_audit_report.json")
            with open(audit_path, 'w', encoding='utf-8') as f:
                json.dump(audit_report, f, indent=2, ensure_ascii=False)
            print(f"  💾 Rapport sauvegardé: {audit_path}")
            
            # ================================
            # ÉTAPE 2: FIXER - Correction
            # ================================
            print("\n" + "─"*80)
            print("🔧 ÉTAPE 2/3: CORRECTION (FIXER)")
            print("─"*80)
            
            fix_start = time.time()
            fix_results = self.fixer.fix_directory(audit_results, output_dir)
            fix_duration = time.time() - fix_start
            
            # Générer le rapport de correction
            fix_report = self.fixer.generate_fix_report(fix_results)
            
            results["fixer"] = {
                "duration": round(fix_duration, 2),
                "total_files": fix_report["summary"]["total_files"],
                "successful_fixes": fix_report["summary"]["successful_fixes"],
                "failed_fixes": fix_report["summary"]["failed_fixes"],
                "success_rate": fix_report["summary"]["success_rate"],
                "results": fix_results
            }
            
            print(f"\n✅ Correction terminée en {fix_duration:.2f}s")
            print(f"  📁 Fichiers traités: {fix_report['summary']['total_files']}")
            print(f"  ✅ Corrections réussies: {fix_report['summary']['successful_fixes']}")
            print(f"  ❌ Échecs: {fix_report['summary']['failed_fixes']}")
            print(f"  🎯 Taux de succès: {fix_report['summary']['success_rate']}")
            
            # Sauvegarder le rapport de correction
            fix_path = os.path.join("logs", "orchestrator_fix_report.json")
            with open(fix_path, 'w', encoding='utf-8') as f:
                json.dump(fix_report, f, indent=2, ensure_ascii=False)
            print(f"  💾 Rapport sauvegardé: {fix_path}")
            
            # ================================
            # ÉTAPE 3: JUDGE - Validation
            # ================================
            if not skip_judge:
                print("\n" + "─"*80)
                print("🧑‍⚖️ ÉTAPE 3/3: VALIDATION (JUDGE)")
                print("─"*80)
                
                judge_start = time.time()
                
                # Évaluer seulement les fichiers corrigés avec succès
                successful_files = [
                    r["output_path"] for r in fix_results 
                    if r.get("success", False) and r.get("output_path")
                ]
                
                if not successful_files:
                    print("  ⚠️ Aucun fichier corrigé à valider")
                    results["judge"] = {
                        "duration": 0,
                        "skipped": True,
                        "reason": "No successfully fixed files"
                    }
                else:
                    eval_results = []
                    for file_path in successful_files:
                        eval_result = self.judge.evaluate_file(file_path)
                        eval_results.append(eval_result)
                    
                    judge_duration = time.time() - judge_start
                    
                    # Générer le rapport d'évaluation
                    judge_report = self.judge.generate_evaluation_report(eval_results)
                    
                    results["judge"] = {
                        "duration": round(judge_duration, 2),
                        "files_evaluated": judge_report["summary"]["total_files"],
                        "files_validated": judge_report["summary"]["files_with_passing_tests"],
                        "files_failed": judge_report["summary"]["files_with_failing_tests"],
                        "validation_rate": judge_report["summary"]["success_rate"],
                        "total_tests": judge_report["summary"]["total_tests"],
                        "tests_passed": judge_report["summary"]["tests_passed"],
                        "results": eval_results
                    }
                    
                    print(f"\n✅ Validation terminée en {judge_duration:.2f}s")
                    print(f"  📁 Fichiers validés: {judge_report['summary']['total_files']}")
                    print(f"  ✅ Tests réussis: {judge_report['summary']['files_with_passing_tests']}")
                    print(f"  ❌ Tests échoués: {judge_report['summary']['files_with_failing_tests']}")
                    print(f"  🎯 Taux de validation: {judge_report['summary']['success_rate']}")
                    print(f"  📝 Total tests: {judge_report['summary']['total_tests']} ({judge_report['summary']['tests_passed']} passés)")
                    
                    # Sauvegarder le rapport de validation
                    judge_path = os.path.join("logs", "orchestrator_judge_report.json")
                    with open(judge_path, 'w', encoding='utf-8') as f:
                        json.dump(judge_report, f, indent=2, ensure_ascii=False)
                    print(f"  💾 Rapport sauvegardé: {judge_path}")
            else:
                print("\n⏭️  ÉTAPE 3/3: VALIDATION (JUDGE) - IGNORÉE")
                results["judge"] = {"skipped": True}
            
            # ================================
            # RAPPORT FINAL
            # ================================
            total_duration = time.time() - start_time
            results["end_time"] = datetime.now().isoformat()
            results["total_duration"] = round(total_duration, 2)
            results["success"] = True
            
            self._print_final_summary(results)
            
            # Log du pipeline complet
            log_experiment(
                agent_name=self.name,
                model_used="N/A",
                action=ActionType.ANALYSIS,
                details={
                    "input_prompt": f"Run pipeline on {input_dir}",
                    "output_response": f"Pipeline completed in {total_duration:.2f}s",
                    "input_dir": input_dir,
                    "output_dir": output_dir,
                    "files_analyzed": results["auditor"]["files_analyzed"],
                    "files_fixed": results["fixer"]["successful_fixes"],
                    "files_validated": results["judge"]["files_validated"] if results["judge"] and not results["judge"].get("skipped") else 0,
                    "duration": total_duration
                },
                status="SUCCESS"
            )
            
            # Sauvegarder le rapport final
            final_report_path = os.path.join("logs", "orchestrator_final_report.json")
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
        
        if results["auditor"]:
            print(f"\n📊 AUDITOR:")
            print(f"  • Fichiers analysés: {results['auditor']['files_analyzed']}")
            print(f"  • Bugs détectés: {results['auditor']['total_bugs']}")
            print(f"  • Durée: {results['auditor']['duration']:.2f}s")
        
        if results["fixer"]:
            print(f"\n🔧 FIXER:")
            print(f"  • Fichiers traités: {results['fixer']['total_files']}")
            print(f"  • Corrections réussies: {results['fixer']['successful_fixes']}")
            print(f"  • Taux de succès: {results['fixer']['success_rate']}")
            print(f"  • Durée: {results['fixer']['duration']:.2f}s")
        
        if results["judge"] and not results["judge"].get("skipped"):
            print(f"\n🧑‍⚖️ JUDGE:")
            print(f"  • Fichiers validés: {results['judge']['files_evaluated']}")
            print(f"  • Tests réussis: {results['judge']['files_validated']}")
            print(f"  • Taux de validation: {results['judge']['validation_rate']}")
            print(f"  • Total tests exécutés: {results['judge']['total_tests']}")
            print(f"  • Durée: {results['judge']['duration']:.2f}s")
        
        print(f"\n📁 Dossier d'entrée: {results['input_dir']}")
        print(f"📁 Dossier de sortie: {results['output_dir']}")
        
        if results["success"]:
            print(f"\n✅ PIPELINE TERMINÉ AVEC SUCCÈS!")
        else:
            print(f"\n❌ PIPELINE TERMINÉ AVEC ERREURS")
            if results.get("error"):
                print(f"  Erreur: {results['error']}")
        
        print("\n" + "="*80)
    
    def run_audit_only(self, input_dir: str) -> Dict:
        """Exécute uniquement l'Auditor."""
        print("\n🔍 Mode: AUDIT SEULEMENT\n")
        
        self.auditor = Auditor()
        audit_results = self.auditor.analyze_directory(input_dir)
        audit_report = self.auditor.generate_report(audit_results)
        
        # Sauvegarder
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
        
        # Audit
        self.auditor = Auditor()
        audit_results = self.auditor.analyze_directory(input_dir)
        
        # Fix
        self.fixer = Fixer()
        fix_results = self.fixer.fix_directory(audit_results, output_dir)
        fix_report = self.fixer.generate_fix_report(fix_results)
        
        # Sauvegarder
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
        
        # Sauvegarder
        os.makedirs("logs", exist_ok=True)
        report_path = os.path.join("logs", "validate_only_report.json")
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(judge_report, f, indent=2, ensure_ascii=False)
        
        print(f"✅ Validation terminée - Rapport: {report_path}")
        return judge_report