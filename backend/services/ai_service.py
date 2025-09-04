"""
Сервис для работы с ИИ (OpenAI)
"""

import os
import re
import json
from typing import Dict, Optional
from pathlib import Path

try:
    import openai
except ImportError:
    openai = None

class AiService:
    """Сервис для работы с OpenAI API"""
    
    def __init__(self, config):
        self.config = config
        self.api_key = config.get('OPENAI_API_KEY') or os.getenv('OPENAI_API_KEY')
        self.chat_sessions = {}
        
        if self.api_key and openai:
            openai.api_key = self.api_key
    
    def is_available(self) -> bool:
        """Проверка доступности ИИ сервиса"""
        return bool(self.api_key and openai)
    
    def chat(self, message: str, session_id: str, context: Optional[Dict] = None) -> str:
        """Чат с ИИ консультантом"""
        if not self.is_available():
            return "ИИ сервис недоступен. Проверьте настройку OPENAI_API_KEY."
        
        try:
            # Инициализация сессии
            if session_id not in self.chat_sessions:
                self.chat_sessions[session_id] = []
            
            # Добавляем контекст если есть
            context_info = ""
            if context:
                dimensions = context.get("geometry", {}).get("dimensions", {})
                if dimensions:
                    context_info = f"\nТекущая деталь: {dimensions.get('length', 0):.1f} x {dimensions.get('width', 0):.1f} x {dimensions.get('height', 0):.1f} мм"
            
            # Строим историю разговора
            messages = [
                {
                    "role": "system", 
                    "content": f"Вы эксперт по CNC обработке. Помогайте с техническими вопросами по программированию ЧПУ, инструментам и производству. Отвечайте на русском языке.{context_info}"
                }
            ]
            
            # Добавляем последние 10 сообщений из истории
            for msg in self.chat_sessions[session_id][-10:]:
                messages.append(msg)
            
            # Добавляем текущее сообщение
            messages.append({"role": "user", "content": message})
            
            # Запрос к OpenAI
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content
            
            # Сохраняем в историю сессии
            self.chat_sessions[session_id].append({"role": "user", "content": message})
            self.chat_sessions[session_id].append({"role": "assistant", "content": ai_response})
            
            # Ограничиваем историю последними 20 сообщениями
            if len(self.chat_sessions[session_id]) > 20:
                self.chat_sessions[session_id] = self.chat_sessions[session_id][-20:]
            
            return ai_response
            
        except Exception as e:
            return f"Извините, произошла ошибка: {str(e)}"
    
    def analyze_part(self, stl_path: Path, part_info: Dict) -> Dict:
        """ИИ анализ детали"""
        if not self.is_available():
            return {"error": "ИИ сервис недоступен"}
        
        try:
            dimensions = part_info.get("geometry", {}).get("dimensions", {})
            mesh_info = part_info.get("mesh_info", {})
            
            analysis_prompt = f"""
            Проанализируйте эту 3D деталь для CNC обработки:
            
            Размеры: {dimensions.get('length', 0):.1f} x {dimensions.get('width', 0):.1f} x {dimensions.get('height', 0):.1f} мм
            Сложность сетки: {mesh_info.get('vertices', 0)} вершин, {mesh_info.get('faces', 0)} граней
            
            Предоставьте рекомендации по:
            1. Стратегии обработки (черновая, чистовая и т.д.)
            2. Рекомендуемые размеры и типы инструментов
            3. Оптимальные параметры резания (подачи, скорости)
            4. Рекомендации по закреплению заготовки
            5. Потенциальные проблемы и их решения
            6. Примерное время обработки
            
            Ответьте в формате JSON со структурированными разделами.
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Вы эксперт-инженер по CNC обработке. Предоставьте детальный технический анализ."},
                    {"role": "user", "content": analysis_prompt}
                ],
                max_tokens=1500,
                temperature=0.3
            )
            
            ai_analysis = response.choices[0].message.content
            
            # Пытаемся распарсить как JSON, иначе возвращаем как текст
            try:
                return json.loads(ai_analysis)
            except:
                return {"analysis": ai_analysis}
                
        except Exception as e:
            return {"error": f"Ошибка ИИ анализа: {str(e)}"}
    
    def generate_gcode_params(self, stl_path: Path, part_info: Dict, requirements: str) -> Dict:
        """ИИ генерация параметров G-кода"""
        if not self.is_available():
            return {"error": "ИИ сервис недоступен"}
        
        try:
            dimensions = part_info.get("geometry", {}).get("dimensions", {})
            
            gcode_prompt = f"""
            Сгенерируйте оптимальные параметры CNC для этой детали:
            
            Размеры детали: {dimensions.get('length', 0):.1f} x {dimensions.get('width', 0):.1f} x {dimensions.get('height', 0):.1f} мм
            Требования: {requirements}
            
            Предоставьте JSON с параметрами:
            {{
                "tool_diameter": <мм>,
                "spindle_speed": <об/мин>,
                "feed_rate": <мм/мин>,
                "plunge_rate": <мм/мин>,
                "stepover": <0.1-0.8>,
                "stepdown": <мм>,
                "operation_type": "milling|roughing|finishing",
                "controller": "fanuc|siemens|heidenhain",
                "strategy": "описание стратегии обработки",
                "estimated_time": "примерное время"
            }}
            """
            
            response = openai.ChatCompletion.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "Вы эксперт по программированию ЧПУ. Генерируйте оптимальные параметры обработки."},
                    {"role": "user", "content": gcode_prompt}
                ],
                max_tokens=800,
                temperature=0.2
            )
            
            ai_params = response.choices[0].message.content
            
            # Пытаемся распарсить JSON
            try:
                return json.loads(ai_params)
            except:
                # Извлекаем параметры с помощью регулярных выражений
                params = {}
                patterns = {
                    "tool_diameter": r'"tool_diameter":\s*(\d+\.?\d*)',
                    "spindle_speed": r'"spindle_speed":\s*(\d+)',
                    "feed_rate": r'"feed_rate":\s*(\d+\.?\d*)',
                    "plunge_rate": r'"plunge_rate":\s*(\d+\.?\d*)',
                    "stepover": r'"stepover":\s*(\d+\.?\d*)',
                    "stepdown": r'"stepdown":\s*(\d+\.?\d*)',
                    "operation_type": r'"operation_type":\s*"([^"]*)"',
                    "controller": r'"controller":\s*"([^"]*)"'
                }
                
                for key, pattern in patterns.items():
                    match = re.search(pattern, ai_params)
                    if match:
                        try:
                            if key in ["tool_diameter", "feed_rate", "plunge_rate", "stepover", "stepdown"]:
                                params[key] = float(match.group(1))
                            elif key == "spindle_speed":
                                params[key] = int(match.group(1))
                            else:
                                params[key] = match.group(1)
                        except:
                            pass
                
                params["raw_response"] = ai_params
                return params
                
        except Exception as e:
            return {"error": f"Ошибка генерации параметров: {str(e)}"}
    
    def clear_session(self, session_id: str) -> bool:
        """Очистка истории сессии"""
        if session_id in self.chat_sessions:
            del self.chat_sessions[session_id]
            return True
        return False