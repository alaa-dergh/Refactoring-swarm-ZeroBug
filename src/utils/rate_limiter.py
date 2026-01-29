"""
🛡️ Rate Limiter pour OpenRouter Free Tier
Gère les limites de requêtes par minute (RPM) de manière centralisée

Author: ZeroBug System
Date: 2026-01-29
"""

import time
import threading
from queue import Queue, Empty
from dataclasses import dataclass, field
from typing import Optional, Callable, Any, Dict
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuration du rate limiter."""
    requests_per_minute: int = 20  # OpenRouter free tier limit
    requests_per_hour: int = 200   # Optional hourly limit
    retry_attempts: int = 3
    base_delay: float = 3.0        # Délai de base entre requêtes (secondes)
    max_delay: float = 60.0        # Délai maximum
    exponential_base: float = 2.0   # Base pour backoff exponentiel


@dataclass
class RequestRecord:
    """Enregistrement d'une requête."""
    timestamp: datetime
    agent_name: str
    success: bool = True
    retry_count: int = 0


class RateLimiter:
    """
    Gestionnaire centralisé de rate limiting pour tous les agents.
    
    Features:
    - Limite RPM (requests per minute)
    - Queue de requêtes avec priorité
    - Retry automatique avec exponential backoff
    - Statistiques en temps réel
    - Thread-safe
    """
    
    def __init__(self, config: Optional[RateLimitConfig] = None):
        self.config = config or RateLimitConfig()
        
        # Historique des requêtes
        self.request_history: list[RequestRecord] = []
        self.lock = threading.Lock()
        
        # Queue de requêtes en attente
        self.request_queue: Queue = Queue()
        
        # Statistiques
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "queued_requests": 0,
            "total_wait_time": 0.0,
        }
        
        logger.info(f"🛡️ Rate Limiter initialisé: {self.config.requests_per_minute} RPM")
    
    def _clean_old_records(self):
        """Nettoie les enregistrements de plus d'une minute."""
        now = datetime.now()
        cutoff = now - timedelta(minutes=1)
        
        with self.lock:
            self.request_history = [
                r for r in self.request_history 
                if r.timestamp > cutoff
            ]
    
    def _get_current_rpm(self) -> int:
        """Calcule le nombre de requêtes dans la dernière minute."""
        self._clean_old_records()
        return len(self.request_history)
    
    def _get_wait_time(self) -> float:
        """
        Calcule le temps d'attente nécessaire avant la prochaine requête.
        
        Returns:
            Temps d'attente en secondes (0 si pas d'attente nécessaire)
        """
        current_rpm = self._get_current_rpm()
        
        if current_rpm < self.config.requests_per_minute:
            return 0.0
        
        # Calculer le temps depuis la plus ancienne requête
        with self.lock:
            if not self.request_history:
                return 0.0
            
            oldest = min(self.request_history, key=lambda r: r.timestamp)
            time_since_oldest = (datetime.now() - oldest.timestamp).total_seconds()
            
            # Si < 60s, attendre le reste
            if time_since_oldest < 60:
                return 60 - time_since_oldest + 1  # +1 pour marge de sécurité
            
            return 0.0
    
    def _calculate_backoff_delay(self, retry_count: int) -> float:
        """
        Calcule le délai pour retry avec exponential backoff.
        
        Args:
            retry_count: Numéro de la tentative
            
        Returns:
            Délai en secondes
        """
        delay = self.config.base_delay * (self.config.exponential_base ** retry_count)
        return min(delay, self.config.max_delay)
    
    def wait_if_needed(self, agent_name: str = "Unknown") -> float:
        """
        Attend si nécessaire avant d'autoriser une requête.
        
        Args:
            agent_name: Nom de l'agent faisant la requête
            
        Returns:
            Temps d'attente effectif en secondes
        """
        wait_time = self._get_wait_time()
        
        if wait_time > 0:
            logger.warning(
                f"⏳ [{agent_name}] Rate limit atteint. "
                f"Attente de {wait_time:.1f}s... "
                f"({self._get_current_rpm()}/{self.config.requests_per_minute} RPM)"
            )
            
            with self.lock:
                self.stats["queued_requests"] += 1
                self.stats["total_wait_time"] += wait_time
            
            time.sleep(wait_time)
        
        return wait_time
    
    def record_request(self, agent_name: str, success: bool = True, retry_count: int = 0):
        """
        Enregistre une requête dans l'historique.
        
        Args:
            agent_name: Nom de l'agent
            success: Si la requête a réussi
            retry_count: Numéro de tentative
        """
        with self.lock:
            record = RequestRecord(
                timestamp=datetime.now(),
                agent_name=agent_name,
                success=success,
                retry_count=retry_count
            )
            self.request_history.append(record)
            
            self.stats["total_requests"] += 1
            if success:
                self.stats["successful_requests"] += 1
            else:
                self.stats["failed_requests"] += 1
    
    def execute_with_rate_limit(
        self,
        func: Callable,
        agent_name: str = "Unknown",
        *args,
        **kwargs
    ) -> Any:
        """
        Exécute une fonction avec gestion automatique du rate limiting et retry.
        
        Args:
            func: Fonction à exécuter
            agent_name: Nom de l'agent
            *args, **kwargs: Arguments pour la fonction
            
        Returns:
            Résultat de la fonction
            
        Raises:
            Exception: Si toutes les tentatives échouent
        """
        last_exception = None
        
        for attempt in range(self.config.retry_attempts):
            try:
                # Attendre si nécessaire
                self.wait_if_needed(agent_name)
                
                # Exécuter la fonction
                result = func(*args, **kwargs)
                
                # Enregistrer le succès
                self.record_request(agent_name, success=True, retry_count=attempt)
                
                if attempt > 0:
                    logger.info(f"✅ [{agent_name}] Succès après {attempt + 1} tentative(s)")
                
                return result
                
            except Exception as e:
                last_exception = e
                
                # Vérifier si c'est une erreur de rate limit
                is_rate_limit_error = any(
                    keyword in str(e).lower() 
                    for keyword in ['rate limit', '429', 'too many requests', 'quota']
                )
                
                if is_rate_limit_error:
                    # Enregistrer l'échec
                    self.record_request(agent_name, success=False, retry_count=attempt)
                    
                    if attempt < self.config.retry_attempts - 1:
                        backoff_delay = self._calculate_backoff_delay(attempt)
                        logger.warning(
                            f"⚠️ [{agent_name}] Rate limit error (tentative {attempt + 1}/{self.config.retry_attempts}). "
                            f"Retry dans {backoff_delay:.1f}s..."
                        )
                        time.sleep(backoff_delay)
                    else:
                        logger.error(
                            f"❌ [{agent_name}] Rate limit error après {self.config.retry_attempts} tentatives"
                        )
                else:
                    # Autre type d'erreur, ne pas retry
                    self.record_request(agent_name, success=False, retry_count=attempt)
                    raise e
        
        # Si on arrive ici, toutes les tentatives ont échoué
        raise last_exception
    
    def get_stats(self) -> Dict:
        """
        Retourne les statistiques du rate limiter.
        
        Returns:
            Dictionnaire avec les statistiques
        """
        current_rpm = self._get_current_rpm()
        wait_time = self._get_wait_time()
        
        with self.lock:
            stats = self.stats.copy()
        
        stats.update({
            "current_rpm": current_rpm,
            "rpm_limit": self.config.requests_per_minute,
            "rpm_usage_percent": (current_rpm / self.config.requests_per_minute) * 100,
            "estimated_wait_time": wait_time,
            "queue_size": self.request_queue.qsize(),
            "success_rate": (
                (stats["successful_requests"] / max(stats["total_requests"], 1)) * 100
            ),
        })
        
        return stats
    
    def print_stats(self):
        """Affiche les statistiques du rate limiter."""
        stats = self.get_stats()
        
        print("\n" + "="*60)
        print("📊 RATE LIMITER STATISTICS")
        print("="*60)
        print(f"📈 Current RPM: {stats['current_rpm']}/{stats['rpm_limit']} "
              f"({stats['rpm_usage_percent']:.1f}% usage)")
        print(f"✅ Successful requests: {stats['successful_requests']}")
        print(f"❌ Failed requests: {stats['failed_requests']}")
        print(f"⏳ Queued requests: {stats['queued_requests']}")
        print(f"⏱️  Total wait time: {stats['total_wait_time']:.1f}s")
        print(f"🎯 Success rate: {stats['success_rate']:.1f}%")
        print(f"⏰ Estimated wait: {stats['estimated_wait_time']:.1f}s")
        print("="*60 + "\n")


# =====================================
# USAGE EXAMPLE
# =====================================

def example_api_call(data: str):
    """Exemple de fonction qui appelle une API."""
    print(f"🔄 Calling API with data: {data}")
    time.sleep(0.5)  # Simuler latence réseau
    
    # Simuler aléatoirement des erreurs de rate limit
    import random
    if random.random() < 0.1:  # 10% de chance
        raise Exception("Rate limit exceeded")
    
    return f"Result for {data}"


if __name__ == "__main__":
    # Configuration
    config = RateLimitConfig(
        requests_per_minute=5,  # Test avec limite basse
        base_delay=2.0,
        retry_attempts=3
    )
    
    limiter = RateLimiter(config)
    
    # Test avec plusieurs requêtes
    print("🚀 Testing rate limiter with 10 requests...\n")
    
    for i in range(10):
        try:
            result = limiter.execute_with_rate_limit(
                example_api_call,
                agent_name=f"TestAgent{i % 3}",  # 3 agents différents
                data=f"request_{i}"
            )
            print(f"✅ Request {i}: {result}")
            
        except Exception as e:
            print(f"❌ Request {i} failed: {e}")
    
    # Afficher les statistiques
    limiter.print_stats()