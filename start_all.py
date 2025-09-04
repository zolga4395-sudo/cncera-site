#!/usr/bin/env python3
"""
CNCera Full Stack Startup Script
Запуск backend и frontend одновременно
"""

import os
import sys
import time
import signal
import subprocess
import threading
from pathlib import Path

class CNCeraLauncher:
    def __init__(self):
        self.backend_process = None
        self.frontend_process = None
        self.running = True
        
    def signal_handler(self, signum, frame):
        """Обработчик сигналов для корректного завершения"""
        print("\n🛑 Получен сигнал завершения...")
        self.running = False
        self.stop_all()
        
    def start_backend(self):
        """Запуск backend в отдельном процессе"""
        backend_dir = Path(__file__).parent / 'backend'
        run_script = backend_dir / 'run.py'
        
        if not run_script.exists():
            print("❌ Backend скрипт не найден")
            return False
            
        try:
            print("🐍 Запуск Backend...")
            self.backend_process = subprocess.Popen([
                sys.executable, str(run_script)
            ], cwd=backend_dir)
            
            # Ждем запуска backend
            time.sleep(3)
            
            if self.backend_process.poll() is None:
                print("✅ Backend запущен (PID: {})".format(self.backend_process.pid))
                return True
            else:
                print("❌ Backend не смог запуститься")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка запуска Backend: {e}")
            return False
    
    def start_frontend(self):
        """Запуск frontend в отдельном процессе"""
        frontend_dir = Path(__file__).parent / 'frontend'
        
        if not (frontend_dir / 'package.json').exists():
            print("❌ Frontend package.json не найден")
            return False
            
        try:
            print("🌐 Запуск Frontend...")
            self.frontend_process = subprocess.Popen([
                'npm', 'start'
            ], cwd=frontend_dir)
            
            # Ждем запуска frontend
            time.sleep(5)
            
            if self.frontend_process.poll() is None:
                print("✅ Frontend запущен (PID: {})".format(self.frontend_process.pid))
                return True
            else:
                print("❌ Frontend не смог запуститься")
                return False
                
        except Exception as e:
            print(f"❌ Ошибка запуска Frontend: {e}")
            return False
    
    def check_backend_health(self):
        """Проверка здоровья backend"""
        try:
            import requests
            response = requests.get('http://127.0.0.1:5000/api/health', timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def monitor_processes(self):
        """Мониторинг процессов"""
        while self.running:
            time.sleep(10)  # Проверка каждые 10 секунд
            
            # Проверка backend
            if self.backend_process and self.backend_process.poll() is not None:
                print("⚠️ Backend процесс завершился")
                self.running = False
                break
                
            # Проверка frontend
            if self.frontend_process and self.frontend_process.poll() is not None:
                print("⚠️ Frontend процесс завершился")
                self.running = False
                break
    
    def stop_all(self):
        """Остановка всех процессов"""
        print("🛑 Остановка сервисов...")
        
        if self.frontend_process:
            try:
                self.frontend_process.terminate()
                self.frontend_process.wait(timeout=5)
                print("✅ Frontend остановлен")
            except:
                try:
                    self.frontend_process.kill()
                    print("🔪 Frontend принудительно остановлен")
                except:
                    pass
        
        if self.backend_process:
            try:
                self.backend_process.terminate()
                self.backend_process.wait(timeout=5)
                print("✅ Backend остановлен")
            except:
                try:
                    self.backend_process.kill()
                    print("🔪 Backend принудительно остановлен")
                except:
                    pass
    
    def run(self):
        """Главный метод запуска"""
        print("🚀 CNCera Full Stack Launcher")
        print("=" * 50)
        
        # Установка обработчика сигналов
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
        
        # Запуск backend
        if not self.start_backend():
            print("❌ Не удалось запустить Backend")
            return False
        
        # Ждем готовности backend
        print("⏳ Ожидание готовности Backend...")
        for i in range(30):  # 30 секунд максимум
            if self.check_backend_health():
                print("✅ Backend готов к работе")
                break
            time.sleep(1)
        else:
            print("❌ Backend не готов к работе")
            self.stop_all()
            return False
        
        # Запуск frontend
        if not self.start_frontend():
            print("❌ Не удалось запустить Frontend")
            self.stop_all()
            return False
        
        # Информация о запуске
        print("=" * 50)
        print("🎉 CNCera успешно запущен!")
        print()
        print("🌐 Frontend: http://127.0.0.1:3000")
        print("🐍 Backend API: http://127.0.0.1:5000/api")
        print("📋 API Info: http://127.0.0.1:5000/api/info")
        print("❤️ Health: http://127.0.0.1:5000/api/health")
        print()
        print("Для остановки нажмите Ctrl+C")
        print("=" * 50)
        
        # Запуск мониторинга в отдельном потоке
        monitor_thread = threading.Thread(target=self.monitor_processes)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        # Ожидание завершения
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
        
        self.stop_all()
        print("👋 CNCera остановлен")
        return True

def main():
    launcher = CNCeraLauncher()
    success = launcher.run()
    sys.exit(0 if success else 1)

if __name__ == '__main__':
    main()