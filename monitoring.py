# Система мониторинга и метрик для CNCera

import time
import psutil
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
import threading
from collections import defaultdict, deque

@dataclass
class SystemMetrics:
    """Системные метрики"""
    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    disk_usage_percent: float
    active_connections: int
    processing_tasks: int

@dataclass
class ProcessingMetrics:
    """Метрики обработки"""
    timestamp: datetime
    operation_type: str
    file_size: int
    processing_time: float
    success: bool
    error_type: Optional[str] = None

class MetricsCollector:
    """Сборщик метрик"""
    
    def __init__(self, max_history: int = 1000):
        self.max_history = max_history
        self.system_metrics = deque(maxlen=max_history)
        self.processing_metrics = deque(maxlen=max_history)
        self.request_counts = defaultdict(int)
        self.error_counts = defaultdict(int)
        self.start_time = datetime.now()
        self.lock = threading.Lock()
    
    def collect_system_metrics(self) -> SystemMetrics:
        """Сбор системных метрик"""
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            # Подсчет активных соединений (упрощенный)
            connections = len(psutil.net_connections())
            
            metrics = SystemMetrics(
                timestamp=datetime.now(),
                cpu_percent=cpu_percent,
                memory_percent=memory.percent,
                memory_used_mb=memory.used / (1024 * 1024),
                disk_usage_percent=disk.percent,
                active_connections=connections,
                processing_tasks=0  # Будет обновляться отдельно
            )
            
            with self.lock:
                self.system_metrics.append(metrics)
            
            return metrics
        except Exception as e:
            logging.error(f"Ошибка сбора системных метрик: {e}")
            return None
    
    def record_processing(self, operation_type: str, file_size: int, 
                         processing_time: float, success: bool, 
                         error_type: Optional[str] = None):
        """Запись метрик обработки"""
        metrics = ProcessingMetrics(
            timestamp=datetime.now(),
            operation_type=operation_type,
            file_size=file_size,
            processing_time=processing_time,
            success=success,
            error_type=error_type
        )
        
        with self.lock:
            self.processing_metrics.append(metrics)
            self.request_counts[operation_type] += 1
            if not success:
                self.error_counts[error_type or "unknown"] += 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики"""
        with self.lock:
            uptime = datetime.now() - self.start_time
            
            # Статистика обработки
            total_requests = sum(self.request_counts.values())
            total_errors = sum(self.error_counts.values())
            success_rate = ((total_requests - total_errors) / total_requests * 100) if total_requests > 0 else 0
            
            # Средние времена обработки
            processing_times = {}
            for op_type in set(m.operation_type for m in self.processing_metrics):
                times = [m.processing_time for m in self.processing_metrics if m.operation_type == op_type]
                if times:
                    processing_times[op_type] = {
                        "avg": sum(times) / len(times),
                        "min": min(times),
                        "max": max(times),
                        "count": len(times)
                    }
            
            # Последние системные метрики
            latest_system = self.system_metrics[-1] if self.system_metrics else None
            
            return {
                "uptime_seconds": uptime.total_seconds(),
                "total_requests": total_requests,
                "total_errors": total_errors,
                "success_rate": success_rate,
                "request_counts": dict(self.request_counts),
                "error_counts": dict(self.error_counts),
                "processing_times": processing_times,
                "system_metrics": asdict(latest_system) if latest_system else None
            }
    
    def get_health_status(self) -> Dict[str, Any]:
        """Проверка состояния системы"""
        latest = self.system_metrics[-1] if self.system_metrics else None
        if not latest:
            return {"status": "unknown", "message": "Нет данных о системе"}
        
        issues = []
        
        # Проверка CPU
        if latest.cpu_percent > 90:
            issues.append(f"Высокая загрузка CPU: {latest.cpu_percent:.1f}%")
        
        # Проверка памяти
        if latest.memory_percent > 90:
            issues.append(f"Высокое использование памяти: {latest.memory_percent:.1f}%")
        
        # Проверка диска
        if latest.disk_usage_percent > 90:
            issues.append(f"Мало места на диске: {latest.disk_usage_percent:.1f}%")
        
        # Проверка ошибок
        recent_errors = sum(1 for m in self.processing_metrics 
                          if not m.success and m.timestamp > datetime.now() - timedelta(minutes=5))
        if recent_errors > 10:
            issues.append(f"Много ошибок за последние 5 минут: {recent_errors}")
        
        if issues:
            return {
                "status": "warning",
                "message": "; ".join(issues),
                "issues": issues
            }
        else:
            return {
                "status": "healthy",
                "message": "Система работает нормально"
            }

class PerformanceMonitor:
    """Монитор производительности"""
    
    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self.monitoring_thread = None
        self.running = False
    
    def start_monitoring(self, interval: int = 30):
        """Запуск мониторинга"""
        if self.running:
            return
        
        self.running = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            args=(interval,),
            daemon=True
        )
        self.monitoring_thread.start()
        logging.info("Мониторинг производительности запущен")
    
    def stop_monitoring(self):
        """Остановка мониторинга"""
        self.running = False
        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)
        logging.info("Мониторинг производительности остановлен")
    
    def _monitoring_loop(self, interval: int):
        """Цикл мониторинга"""
        while self.running:
            try:
                self.metrics_collector.collect_system_metrics()
                time.sleep(interval)
            except Exception as e:
                logging.error(f"Ошибка в цикле мониторинга: {e}")
                time.sleep(interval)
    
    def record_operation(self, operation_type: str, file_size: int, 
                        processing_time: float, success: bool, 
                        error_type: Optional[str] = None):
        """Запись операции"""
        self.metrics_collector.record_processing(
            operation_type, file_size, processing_time, success, error_type
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Получение метрик"""
        return self.metrics_collector.get_stats()
    
    def get_health(self) -> Dict[str, Any]:
        """Проверка здоровья системы"""
        return self.metrics_collector.get_health_status()

# Глобальный экземпляр монитора
performance_monitor = PerformanceMonitor()