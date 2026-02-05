import os
import shutil
import subprocess
from typing import Dict, Optional

class FixerTools:
    """
    Outils pour le Fixer Agent.
    
    Responsabilités:
    - Validation de code (syntaxe, sécurité)
    - Sauvegarde sécurisée de fichiers
    - Backup et restauration
    - Formatage de code (optionnel)
    """
    
    @staticmethod
    def check_syntax(code: str, file_path: str = "temp.py") -> Dict:
        """
        Vérifie si le code Python est syntaxiquement valide.
        
        Args:
            code: Le code Python à vérifier
            file_path: Nom du fichier (pour les messages d'erreur)
            
        Returns:
            Dict avec {valid: bool, error: str, line: int}
        """
        try:
            compile(code, file_path, "exec")
            return {
                "valid": True,
                "error": None,
                "line": None
            }
        except SyntaxError as e:
            return {
                "valid": False,
                "error": e.msg,
                "line": e.lineno,
                "offset": e.offset
            }
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "line": None
            }
    
    @staticmethod
    def validate_safe_path(file_path: str, allowed_dirs: list = None) -> bool:
        """
        Vérifie qu'un chemin de fichier est sûr (pas de path traversal).
        
        Args:
            file_path: Chemin à valider
            allowed_dirs: Liste des dossiers autorisés (défaut: sandbox)
            
        Returns:
            True si le chemin est sûr
        """
        if allowed_dirs is None:
            allowed_dirs = ["sandbox", "output", "logs"]
        
        # Normaliser le chemin
        normalized_path = os.path.normpath(file_path)
        
        # Vérifier qu'il ne contient pas de ".."
        if ".." in normalized_path:
            return False
        
        # Vérifier qu'il commence par un dossier autorisé
        for allowed_dir in allowed_dirs:
            if normalized_path.startswith(allowed_dir) or normalized_path.startswith(f"./{allowed_dir}"):
                return True
        
        return False
    
    @staticmethod
    def save_fixed_file(
        fixed_code: str, 
        original_path: str, 
        output_dir: str,
        create_backup: bool = False
    ) -> str:
        """
        Sauvegarde le code corrigé dans un fichier.
        
        Args:
            fixed_code: Le code corrigé
            original_path: Chemin du fichier original
            output_dir: Dossier de sortie
            create_backup: Si True, crée un backup du fichier original
            
        Returns:
            Chemin du fichier sauvegardé
        """
        
        # Créer le dossier de sortie s'il n'existe pas
        os.makedirs(output_dir, exist_ok=True)
        
        # Déterminer le nom du fichier de sortie
        file_name = os.path.basename(original_path)
        output_path = os.path.join(output_dir, file_name)
        
        # Créer un backup si demandé
        if create_backup and os.path.exists(original_path):
            backup_path = f"{original_path}.backup"
            shutil.copy2(original_path, backup_path)
        
        # Sauvegarder le code corrigé
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(fixed_code)
        
        return output_path
    
    @staticmethod
    def restore_backup(file_path: str) -> bool:
        """
        Restaure un fichier depuis son backup.
        
        Args:
            file_path: Chemin du fichier à restaurer
            
        Returns:
            True si la restauration a réussi
        """
        backup_path = f"{file_path}.backup"
        
        if not os.path.exists(backup_path):
            return False
        
        try:
            shutil.copy2(backup_path, file_path)
            return True
        except Exception:
            return False
    
    @staticmethod
    def format_code_with_black(code: str) -> Optional[str]:
        """
        Formate le code avec Black (si installé).
        
        Args:
            code: Code Python à formater
            
        Returns:
            Code formaté ou None si Black n'est pas disponible
        """
        try:
            # Créer un fichier temporaire
            temp_file = "/tmp/temp_code_to_format.py"
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(code)
            
            # Lancer Black
            result = subprocess.run(
                ["black", "--quiet", temp_file],
                capture_output=True,
                timeout=10
            )
            
            if result.returncode == 0:
                # Lire le code formaté
                with open(temp_file, 'r', encoding='utf-8') as f:
                    formatted_code = f.read()
                
                # Nettoyer
                os.remove(temp_file)
                return formatted_code
            else:
                return None
                
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Black n'est pas installé ou timeout
            return None
        except Exception:
            return None
    
    @staticmethod
    def run_pylint(file_path: str) -> Dict:
        """
        Execute Pylint sur un fichier et retourne le score.
        
        Args:
            file_path: Chemin du fichier à analyser
            
        Returns:
            Dict avec {score: float, messages: list, success: bool}
        """
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
                    messages = eval(result.stdout)  # Pylint retourne du JSON-like
                except Exception:
                    pass
            
            # Extraire le score
            score = 0.0
            text = (result.stderr or "") + "\n" + (result.stdout or "")
            for line in text.splitlines():
                if "rated at" in line.lower():
                    try:
                        score = float(line.split("rated at")[1].split("/")[0].strip())
                    except Exception:
                        pass
            
            return {
                "score": score,
                "messages": messages,
                "success": True
            }
            
        except Exception as e:
            return {
                "score": 0.0,
                "messages": [],
                "success": False,
                "error": str(e)
            }
    
    @staticmethod
    def compare_code_quality(original_path: str, fixed_path: str) -> Dict:
        """
        Compare la qualité du code avant/après correction.
        
        Args:
            original_path: Chemin du fichier original
            fixed_path: Chemin du fichier corrigé
            
        Returns:
            Dict avec les scores avant/après et l'amélioration
        """
        
        original_score = FixerTools.run_pylint(original_path)
        fixed_score = FixerTools.run_pylint(fixed_path)
        
        original_val = original_score.get("score", 0.0)
        fixed_val = fixed_score.get("score", 0.0)
        improvement = fixed_val - original_val
        
        return {
            "original_score": original_val,
            "fixed_score": fixed_val,
            "improvement": round(improvement, 2),
            "improvement_percent": round((improvement / max(original_val, 0.1)) * 100, 1) if original_val > 0 else 0,
            "success": fixed_val > original_val
        }
    
    @staticmethod
    def count_lines_of_code(code: str) -> Dict:
        """
        Compte les lignes de code (LOC metrics).
        
        Args:
            code: Le code Python
            
        Returns:
            Dict avec les métriques
        """
        lines = code.splitlines()
        
        total_lines = len(lines)
        code_lines = 0
        comment_lines = 0
        blank_lines = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                blank_lines += 1
            elif stripped.startswith("#"):
                comment_lines += 1
            else:
                code_lines += 1
        
        return {
            "total_lines": total_lines,
            "code_lines": code_lines,
            "comment_lines": comment_lines,
            "blank_lines": blank_lines,
            "comment_ratio": round(comment_lines / max(code_lines, 1), 2)
        }
    
    @staticmethod
    def detect_dangerous_patterns(code: str) -> list:
        """
        Détecte des patterns dangereux dans le code.
        
        Args:
            code: Le code Python à analyser
            
        Returns:
            Liste des patterns dangereux trouvés
        """
        dangerous_patterns = []
        
        dangerous_imports = ["os.system", "subprocess.call", "eval(", "exec(", "__import__"]
        
        for pattern in dangerous_imports:
            if pattern in code:
                dangerous_patterns.append({
                    "pattern": pattern,
                    "severity": "HIGH",
                    "description": f"Usage potentiellement dangereux: {pattern}"
                })
        
        # Vérifier les écritures de fichiers hors sandbox
        if "open(" in code and ("w" in code or "a" in code):
            if "sandbox" not in code.lower():
                dangerous_patterns.append({
                    "pattern": "file_write_outside_sandbox",
                    "severity": "MEDIUM",
                    "description": "Écriture de fichier potentiellement hors sandbox"
                })
        
        return dangerous_patterns