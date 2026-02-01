import os
import json
import time
import re
from typing import Dict, List, Optional
from dotenv import load_dotenv

from src.utils.file_manager import PyFileTool
from src.utils.fixer_tools import FixerTools
from src.utils.logger import log_experiment, ActionType
from src.utils.gemini_wrapper import llm  # Groq déguisé en Gemini

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
        elif "```" in text:
            start = text.find("```") + 3
            end = text.find("```", start)
            text = text[start:end].strip()
        
        return json.loads(text)
    except Exception as e:
        raise ValueError(f"JSON invalide: {e}\nTexte reçu: {text[:200]}...")

# ================================
# Fixer Agent avec Support Chunking
# ================================
class Fixer:
    """
    Agent Fixer : corrige le code Python basé sur le rapport de l'Auditor.
    Supporte les gros fichiers via chunking automatique.
    """
    
    def __init__(self, max_retries: int = 3):
        self.name = "Fixer"
        self.llm = llm
        self.max_retries = max_retries
        self.tools = FixerTools()
        self.llm_cache = {}
        
        # Configuration chunking
        self.max_tokens_per_request = 6000  # Limite sécurisée pour Groq
        self.chars_per_token = 4  # Approximation
    
    # ========================================
    # MÉTHODES DE CHUNKING
    # ========================================
    
    def estimate_tokens(self, text: str) -> int:
        """Estime le nombre de tokens (1 token ≈ 4 caractères)."""
        return len(text) // self.chars_per_token
    
    def should_use_chunking(self, code: str) -> bool:
        """Détermine si le fichier nécessite un découpage."""
        estimated_tokens = self.estimate_tokens(code)
        
        # Ajout de marge pour le prompt (environ 1000 tokens)
        total_estimated = estimated_tokens + 1000
        
        return total_estimated > self.max_tokens_per_request
    
    def split_by_functions(self, code: str) -> List[Dict]:
        """
        Découpe le code en chunks par fonction/classe.
        Retourne une liste de dictionnaires avec code, start_line, end_line, name.
        """
        lines = code.split('\n')
        chunks = []
        
        # Pattern pour détecter fonctions et classes
        func_class_pattern = r'^(def |class )\s*([a-zA-Z_][a-zA-Z0-9_]*)'
        
        current_chunk = {
            'lines': [],
            'start_line': 1,
            'name': 'header',
            'indent': 0
        }
        
        for i, line in enumerate(lines, 1):
            stripped = line.lstrip()
            
            # Détecter nouvelle fonction/classe
            match = re.match(func_class_pattern, stripped)
            
            if match and current_chunk['lines']:
                # Sauvegarder le chunk précédent
                chunks.append({
                    'code': '\n'.join(current_chunk['lines']),
                    'start_line': current_chunk['start_line'],
                    'end_line': i - 1,
                    'name': current_chunk['name']
                })
                
                # Nouveau chunk
                current_chunk = {
                    'lines': [line],
                    'start_line': i,
                    'name': match.group(2),
                    'indent': len(line) - len(stripped)
                }
            else:
                current_chunk['lines'].append(line)
        
        # Ajouter le dernier chunk
        if current_chunk['lines']:
            chunks.append({
                'code': '\n'.join(current_chunk['lines']),
                'start_line': current_chunk['start_line'],
                'end_line': len(lines),
                'name': current_chunk['name']
            })
        
        return chunks
    
    def group_bugs_by_chunk(self, bugs: List[Dict], chunks: List[Dict]) -> Dict[int, List[Dict]]:
        """Associe chaque bug à son chunk."""
        bugs_by_chunk = {}
        
        for bug in bugs:
            line = bug.get('line')
            if not line:
                continue
            
            # Trouver dans quel chunk se trouve ce bug
            for idx, chunk in enumerate(chunks):
                if chunk['start_line'] <= line <= chunk['end_line']:
                    if idx not in bugs_by_chunk:
                        bugs_by_chunk[idx] = []
                    bugs_by_chunk[idx].append(bug)
                    break
        
        return bugs_by_chunk
    
    def fix_chunk(self, chunk_code: str, bugs: List[Dict], chunk_name: str) -> str:
        """Corrige un chunk de code avec ses bugs associés."""
        
        if not bugs:
            # Pas de bugs, retourner tel quel
            return chunk_code
        
        # Créer un prompt simplifié pour ce chunk
        bugs_desc = '\n'.join(
            f"  - Line {b.get('line')}: {b.get('description')} "
            f"(Suggestion: {b.get('suggestion', 'N/A')})"
            for b in bugs
        )
        
        prompt = f"""Fix the following Python code section.

SECTION: {chunk_name}

BUGS TO FIX:
{bugs_desc}

CODE:
```python
{chunk_code}
```

REQUIREMENTS:
1. Fix ALL the bugs listed above
2. Keep the same structure and logic
3. Return ONLY the fixed code
4. NO markdown backticks
5. NO explanations

Return the fixed code:"""

        try:
            response = self.llm.invoke(prompt)
            fixed_code = response.content if hasattr(response, 'content') else str(response)
            
            # Nettoyer les backticks si présents
            if '```python' in fixed_code:
                fixed_code = fixed_code.split('```python')[1].split('```')[0].strip()
            elif '```' in fixed_code:
                parts = fixed_code.split('```')
                if len(parts) >= 3:
                    fixed_code = parts[1].strip()
            
            return fixed_code
            
        except Exception as e:
            print(f"     ⚠️ Erreur correction chunk: {e}")
            return chunk_code  # Retourner l'original en cas d'erreur
    
    def fix_file_chunked(self, file_path: str, code: str, audit_report: Dict) -> Dict:
        """Corrige un gros fichier en le découpant en chunks."""
        
        print(f"  📦 Fichier volumineux ({len(code)} chars, ~{self.estimate_tokens(code)} tokens)")
        print(f"  📦 Activation du mode chunking...")
        
        # Découper le code
        chunks = self.split_by_functions(code)
        print(f"  📦 Découpé en {len(chunks)} section(s)")
        
        # Grouper les bugs par chunk
        bugs = audit_report.get('bugs', [])
        bugs_by_chunk = self.group_bugs_by_chunk(bugs, chunks)
        
        total_bugs = sum(len(b) for b in bugs_by_chunk.values())
        print(f"  📦 {total_bugs} bug(s) répartis dans {len(bugs_by_chunk)} section(s)")
        
        # Corriger chunk par chunk
        fixed_chunks = []
        changes_made = []
        
        for i, chunk in enumerate(chunks):
            chunk_bugs = bugs_by_chunk.get(i, [])
            
            if chunk_bugs:
                print(f"  🔧 Section {i+1}/{len(chunks)} ({chunk['name']}): {len(chunk_bugs)} bug(s)")
                
                fixed_code = self.fix_chunk(chunk['code'], chunk_bugs, chunk['name'])
                fixed_chunks.append(fixed_code)
                
                changes_made.append(f"Fixed {len(chunk_bugs)} bug(s) in {chunk['name']}")
                
                # Pause entre chunks pour éviter rate limit
                if i < len(chunks) - 1:
                    time.sleep(1)
            else:
                # Pas de bugs, garder tel quel
                fixed_chunks.append(chunk['code'])
        
        # Reconstituer le fichier
        fixed_code = '\n\n'.join(fixed_chunks)
        
        print(f"  ✅ Fichier reconstitué: {len(fixed_code)} chars")
        
        return {
            'fixed_code': fixed_code,
            'changes_made': changes_made,
            'confidence': 0.85,  # Confiance légèrement réduite pour chunking
            'chunked': True
        }
    
    # ========================================
    # MÉTHODE NORMALE (petits fichiers)
    # ========================================
    
    def build_fix_prompt(
        self, 
        file_path: str, 
        code: str, 
        audit_report: Dict,
        iteration: int = 1,
        previous_error: Optional[str] = None
    ) -> str:
        """Construit le prompt pour corriger le code (méthode normale)."""
        
        bugs = audit_report.get("bugs", [])
        quality_issues = audit_report.get("quality_issues", [])
        style_issues = audit_report.get("style_issues", [])
        refactoring_plan = audit_report.get("refactoring_plan", [])
        
        prompt = f"""You are a senior Python developer specialized in code refactoring.

Your mission: Fix the following Python file based on the audit report.

FILE: {file_path}
ITERATION: {iteration}/{self.max_retries}

ORIGINAL CODE:
```python
{code}
```

AUDIT REPORT:
- Bugs found: {len(bugs)}
- Quality issues: {len(quality_issues)}
- Style issues: {len(style_issues)}

DETAILED ISSUES:
"""
        
        if bugs:
            prompt += "\n🐛 BUGS (HIGH PRIORITY):\n"
            for bug in bugs:
                prompt += f"  Line {bug.get('line', '?')}: {bug.get('description', 'N/A')}\n"
                prompt += f"  Suggestion: {bug.get('suggestion', 'N/A')}\n\n"
        
        if quality_issues:
            prompt += "\n⚠️ QUALITY ISSUES:\n"
            for issue in quality_issues[:5]:
                prompt += f"  Line {issue.get('line', '?')}: {issue.get('description', 'N/A')}\n"
        
        if refactoring_plan:
            prompt += "\n📋 REFACTORING PLAN:\n"
            for i, step in enumerate(refactoring_plan, 1):
                prompt += f"  {i}. {step}\n"
        
        if previous_error:
            prompt += f"\n\n❌ PREVIOUS ATTEMPT FAILED:\n{previous_error}\n"
            prompt += "Please fix this error in your new version.\n"
        
        prompt += """

REQUIREMENTS:

1. Return ONLY valid JSON with this structure:
{
  "fixed_code": "def example():\\n    return 42",
  "changes_made": ["Added zero check"],
  "confidence": 0.95
}

CRITICAL: Use \\n for newlines, \\t for tabs in the fixed_code string.

2. The fixed_code must be:
   - Syntactically valid Python
   - All bugs fixed
   - All critical issues resolved
   - Well-formatted (PEP8)
   - With proper docstrings

3. DO NOT include markdown backticks in the JSON response
4. DO NOT add explanations outside the JSON

Return ONLY the JSON object.
"""
        
        return prompt
    
    def validate_fixed_code(self, code: str, file_path: str) -> Dict:
        """Valide que le code corrigé est syntaxiquement correct."""
        return self.tools.check_syntax(code, file_path)
    
    # ========================================
    # MÉTHODE PRINCIPALE fix_file
    # ========================================
    
    def fix_file(
        self, 
        file_path: str, 
        audit_report: Dict,
        output_dir: str = None
    ) -> Dict:
        """Corrige un fichier (avec support chunking automatique)."""
        
        try:
            original_code = PyFileTool.read_file(file_path)
        except Exception as e:
            error_msg = f"Impossible de lire {file_path}: {e}"
            log_experiment(
                agent_name=self.name,
                model_used="N/A",
                action=ActionType.FIX,
                details={
                    "file_fixed": file_path,
                    "error": str(e)
                },
                status="FAILURE"
            )
            return {
                "file_path": file_path,
                "success": False,
                "error": error_msg,
                "original_code": "",
                "fixed_code": ""
            }
        
        # ✅ NOUVEAU: Vérifier si chunking nécessaire
        if self.should_use_chunking(original_code):
            try:
                llm_result = self.fix_file_chunked(file_path, original_code, audit_report)
                
                fixed_code = llm_result.get('fixed_code', '')
                changes_made = llm_result.get('changes_made', [])
                confidence = llm_result.get('confidence', 0.85)
                
                # Valider le code
                validation = self.validate_fixed_code(fixed_code, file_path)
                
                if not validation["valid"]:
                    print(f"  ⚠️ Code chunked invalide: {validation.get('error')}")
                    print(f"  🔄 Tentative avec méthode normale...")
                    # Fallback vers méthode normale (continuera ci-dessous)
                else:
                    # Succès avec chunking!
                    if output_dir:
                        output_path = self.tools.save_fixed_file(fixed_code, file_path, output_dir)
                    else:
                        output_path = file_path
                        with open(file_path, 'w', encoding='utf-8') as f:
                            f.write(fixed_code)
                    
                    log_experiment(
                        agent_name=self.name,
                        model_used="llama-3.3-70b-versatile",
                        action=ActionType.FIX,
                        details={
                            "file_fixed": file_path,
                            "changes_made": changes_made,
                            "confidence": confidence,
                            "chunked": True,
                            "output_path": output_path
                        },
                        status="SUCCESS"
                    )
                    
                    return {
                        "file_path": file_path,
                        "output_path": output_path,
                        "success": True,
                        "original_code": original_code,
                        "fixed_code": fixed_code,
                        "changes_made": changes_made,
                        "confidence": confidence,
                        "iterations": 1,
                        "chunked": True
                    }
                    
            except Exception as e:
                print(f"  ⚠️ Échec chunking: {e}")
                print(f"  🔄 Tentative avec méthode normale...")
        
        # Méthode normale (petits fichiers ou fallback)
        cache_key = hash(original_code + str(audit_report))
        previous_error = None
        
        for iteration in range(1, self.max_retries + 1):
            try:
                if cache_key in self.llm_cache and iteration == 1:
                    print(f"  ⚡ Cache hit pour {file_path}")
                    llm_result = self.llm_cache[cache_key]
                else:
                    prompt = self.build_fix_prompt(
                        file_path, 
                        original_code, 
                        audit_report,
                        iteration,
                        previous_error
                    )
                    
                    print(f"  🔧 Tentative {iteration}/{self.max_retries} pour {file_path}")
                    
                    response = self.llm.invoke(prompt)
                    raw_text = response.content if hasattr(response, 'content') else str(response)
                    
                    llm_result = safe_parse_json(raw_text)
                    
                    if iteration == 1:
                        self.llm_cache[cache_key] = llm_result
                
                fixed_code = llm_result.get("fixed_code", "")
                changes_made = llm_result.get("changes_made", [])
                confidence = llm_result.get("confidence", 0.0)
                
                if not fixed_code:
                    raise ValueError("Le LLM n'a pas retourné de code corrigé")
                
                validation = self.validate_fixed_code(fixed_code, file_path)
                
                if not validation["valid"]:
                    previous_error = f"Syntax Error at line {validation.get('line', '?')}: {validation.get('error', 'Unknown')}"
                    print(f"  ❌ {previous_error}")
                    
                    if iteration < self.max_retries:
                        time.sleep(2)
                        continue
                    else:
                        raise ValueError(f"Code invalide après {self.max_retries} tentatives: {previous_error}")
                
                # Code valide!
                if output_dir:
                    output_path = self.tools.save_fixed_file(fixed_code, file_path, output_dir)
                else:
                    output_path = file_path
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(fixed_code)
                
                log_experiment(
                    agent_name=self.name,
                    model_used="llama-3.3-70b-versatile",
                    action=ActionType.FIX,
                    details={
                        "file_fixed": file_path,
                        "input_prompt": prompt[:500] + "...",
                        "output_response": str(llm_result)[:500] + "...",
                        "changes_made": changes_made,
                        "confidence": confidence,
                        "iteration": iteration,
                        "output_path": output_path
                    },
                    status="SUCCESS"
                )
                
                return {
                    "file_path": file_path,
                    "output_path": output_path,
                    "success": True,
                    "original_code": original_code,
                    "fixed_code": fixed_code,
                    "changes_made": changes_made,
                    "confidence": confidence,
                    "iterations": iteration
                }
                
            except Exception as e:
                error_msg = f"Erreur à l'itération {iteration}: {e}"
                print(f"  ⚠️ {error_msg}")
                
                if iteration < self.max_retries:
                    previous_error = str(e)
                    time.sleep(2)
                    continue
                else:
                    log_experiment(
                        agent_name=self.name,
                        model_used="llama-3.3-70b-versatile",
                        action=ActionType.FIX,
                        details={
                            "file_fixed": file_path,
                            "error": str(e),
                            "iterations": iteration
                        },
                        status="FAILURE"
                    )
                    
                    return {
                        "file_path": file_path,
                        "success": False,
                        "error": error_msg,
                        "original_code": original_code,
                        "fixed_code": "",
                        "iterations": iteration
                    }
        
        return {
            "file_path": file_path,
            "success": False,
            "error": "Max retries exceeded",
            "original_code": original_code,
            "fixed_code": ""
        }
    
    def fix_directory(
        self, 
        audit_results: List[Dict],
        output_dir: str
    ) -> List[Dict]:
        """Corrige tous les fichiers d'un dossier."""
        
        os.makedirs(output_dir, exist_ok=True)
        
        results = []
        total_files = len(audit_results)
        
        print(f"\n🔧 Début de la correction de {total_files} fichier(s)...\n")
        
        for i, audit_report in enumerate(audit_results, 1):
            file_path = audit_report.get("file_path")
            
            if not file_path:
                print(f"⚠️ [{i}/{total_files}] Rapport sans file_path, ignoré")
                continue
            
            print(f"📝 [{i}/{total_files}] Correction de {file_path}")
            
            result = self.fix_file(file_path, audit_report, output_dir)
            results.append(result)
            
            if i < total_files:
                time.sleep(2)
        
        return results
    
    def generate_fix_report(self, fix_results: List[Dict]) -> Dict:
        """Génère un rapport de synthèse des corrections."""
        
        total_files = len(fix_results)
        successful = sum(1 for r in fix_results if r.get("success", False))
        failed = total_files - successful
        
        total_changes = sum(len(r.get("changes_made", [])) for r in fix_results)
        avg_confidence = sum(r.get("confidence", 0) for r in fix_results) / max(total_files, 1)
        
        chunked_files = sum(1 for r in fix_results if r.get("chunked", False))
        
        report = {
            "summary": {
                "total_files": total_files,
                "successful_fixes": successful,
                "failed_fixes": failed,
                "success_rate": f"{(successful/max(total_files, 1))*100:.1f}%",
                "total_changes": total_changes,
                "average_confidence": round(avg_confidence, 2),
                "chunked_files": chunked_files
            },
            "files": fix_results
        }
        
        return report
    