#!/usr/bin/env python3
"""
CNCera Enhanced - Final Fixed Version
Advanced 3D Analysis & G-code Generation with RAG AI, NC Viewer, and Enhanced Error Handling
"""

import os
import sys
import json
import hashlib
import logging
import subprocess
import base64
import shutil
import tempfile
import math
import time
import requests
import re
import threading
import traceback
import glob
import sqlite3
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List
from string import Template

import flask
from flask import Flask, request, jsonify, send_file, send_from_directory, render_template_string
from werkzeug.utils import secure_filename

# ---- Server-side PNG rendering (fallback) ----
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    try:
        from stl import mesh as stlmesh
    except Exception:
        stlmesh = None
except Exception:
    matplotlib = None
    stlmesh = None
    plt = None

# ---- RAG Database for AI Knowledge ----
class RAGDatabase:
    def __init__(self, db_path: str = "rag_knowledge.db"):
        self.db_path = db_path
        self.init_database()
        self.populate_initial_data()
    
    def init_database(self):
        """Initialize RAG database with G-code knowledge"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create knowledge table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS gcode_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create material properties table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS material_properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_name TEXT NOT NULL,
                material_type TEXT NOT NULL,
                cutting_speed_min REAL,
                cutting_speed_max REAL,
                feed_rate_factor REAL,
                hardness_hb REAL,
                machinability_rating INTEGER,
                recommended_tools TEXT,
                notes TEXT
            )
        ''')
        
        # Create tooling knowledge table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tooling_knowledge (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_type TEXT NOT NULL,
                diameter REAL,
                material TEXT,
                flutes INTEGER,
                cutting_speed REAL,
                feed_per_tooth REAL,
                applications TEXT,
                notes TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def populate_initial_data(self):
        """Populate database with initial G-code and machining knowledge"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Check if data already exists
        cursor.execute("SELECT COUNT(*) FROM gcode_knowledge")
        if cursor.fetchone()[0] > 0:
            conn.close()
            return
        
        # G-code knowledge
        gcode_data = [
            ("G-code Basics", "G-code Fundamentals", 
             "G-code is a programming language for CNC machines. Basic commands: G00 (rapid move), G01 (linear interpolation), G02/G03 (circular interpolation), M03 (spindle on), M05 (spindle off), M08 (coolant on), M09 (coolant off).", 
             "gcode,basics,cnc"),
            ("Milling Operations", "Milling G-code Patterns",
             "For milling operations: Use G17 for XY plane, G21 for metric units, G90 for absolute positioning. Roughing: high feed rates, large stepover. Finishing: low feed rates, small stepover for surface quality.",
             "milling,roughing,finishing"),
            ("Drilling Cycles", "Drilling G-code Cycles",
             "Drilling cycles: G81 (simple drill), G82 (drill with dwell), G83 (peck drilling), G84 (tapping). Use G80 to cancel cycle. R plane is clearance height above part.",
             "drilling,cycles,peck"),
            ("Tool Compensation", "Tool Length and Radius Compensation",
             "G43 H01 (tool length compensation), G41/G42 (cutter radius compensation left/right), G40 (cancel compensation). Always use compensation for accurate machining.",
             "compensation,tool,radius"),
            ("Safety Commands", "Safety and Setup Commands",
             "Always start with: G21 (metric), G90 (absolute), G94 (feed per minute), G17 (XY plane). End with: M05 (spindle off), M09 (coolant off), M30 (program end).",
             "safety,setup,programming")
        ]
        
        cursor.executemany(
            "INSERT INTO gcode_knowledge (category, title, content, tags) VALUES (?, ?, ?, ?)",
            gcode_data
        )
        
        # Material properties
        material_data = [
            ("42CrMo4", "Steel", 80, 120, 1.0, 280, 3, "HSS, Carbide", "High strength steel, requires coolant"),
            ("Al6061-T6", "Aluminum", 300, 500, 2.5, 95, 5, "HSS, Carbide", "Excellent machinability, high feed rates possible"),
            ("316L", "Stainless Steel", 60, 100, 0.7, 200, 2, "Carbide", "Corrosion resistant, work hardening tendency"),
            ("GG25", "Cast Iron", 100, 150, 1.2, 200, 4, "HSS, Carbide", "Good machinability, produces chips"),
            ("Ti6Al4V", "Titanium", 30, 60, 0.5, 350, 1, "Carbide", "Difficult to machine, low thermal conductivity")
        ]
        
        cursor.executemany(
            "INSERT INTO material_properties (material_name, material_type, cutting_speed_min, cutting_speed_max, feed_rate_factor, hardness_hb, machinability_rating, recommended_tools, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            material_data
        )
        
        # Tooling knowledge
        tooling_data = [
            ("End Mill", 6.0, "HSS", 2, 120, 0.1, "General milling, roughing", "2-flute for aluminum, 4-flute for steel"),
            ("End Mill", 3.0, "Carbide", 4, 150, 0.05, "Finishing, detail work", "High precision, good surface finish"),
            ("Drill", 3.0, "HSS", 1, 100, 0.05, "Hole drilling", "Use peck drilling for deep holes"),
            ("Drill", 8.0, "Carbide", 1, 80, 0.08, "Large hole drilling", "Requires pilot hole for large diameters"),
            ("Chamfer Mill", 45.0, "HSS", 2, 100, 0.1, "Chamfering edges", "45-degree angle for standard chamfers")
        ]
        
        cursor.executemany(
            "INSERT INTO tooling_knowledge (tool_type, diameter, material, flutes, cutting_speed, feed_per_tooth, applications, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            tooling_data
        )
        
        conn.commit()
        conn.close()
    
    def search_knowledge(self, query: str, category: str = None) -> List[Dict]:
        """Search knowledge base for relevant information"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if category:
            cursor.execute(
                "SELECT * FROM gcode_knowledge WHERE category = ? AND (title LIKE ? OR content LIKE ? OR tags LIKE ?)",
                (category, f"%{query}%", f"%{query}%", f"%{query}%")
            )
        else:
            cursor.execute(
                "SELECT * FROM gcode_knowledge WHERE title LIKE ? OR content LIKE ? OR tags LIKE ?",
                (f"%{query}%", f"%{query}%", f"%{query}%")
            )
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "id": row[0],
                "category": row[1],
                "title": row[2],
                "content": row[3],
                "tags": row[4]
            })
        
        conn.close()
        return results
    
    def get_material_properties(self, material_name: str) -> Optional[Dict]:
        """Get material properties for machining recommendations"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM material_properties WHERE material_name LIKE ?", (f"%{material_name}%",))
        row = cursor.fetchone()
        
        if row:
            result = {
                "material_name": row[1],
                "material_type": row[2],
                "cutting_speed_min": row[3],
                "cutting_speed_max": row[4],
                "feed_rate_factor": row[5],
                "hardness_hb": row[6],
                "machinability_rating": row[7],
                "recommended_tools": row[8],
                "notes": row[9]
            }
        else:
            result = None
        
        conn.close()
        return result
    
    def get_tooling_recommendations(self, operation_type: str, material: str = None) -> List[Dict]:
        """Get tooling recommendations based on operation and material"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT * FROM tooling_knowledge WHERE applications LIKE ?",
            (f"%{operation_type}%",)
        )
        
        results = []
        for row in cursor.fetchall():
            results.append({
                "tool_type": row[1],
                "diameter": row[2],
                "material": row[3],
                "flutes": row[4],
                "cutting_speed": row[5],
                "feed_per_tooth": row[6],
                "applications": row[7],
                "notes": row[8]
            })
        
        conn.close()
        return results

# Initialize RAG database
rag_db = RAGDatabase()

# ---- Enhanced Error Handling ----
class ErrorType(Enum):
    VALIDATION_ERROR = "validation_error"
    SECURITY_ERROR = "security_error"
    FILE_ERROR = "file_error"
    PROCESSING_ERROR = "processing_error"
    CONFIGURATION_ERROR = "configuration_error"
    EXTERNAL_API_ERROR = "external_api_error"
    MODEL_NOT_FOUND_ERROR = "model_not_found_error"
    API_KEY_ERROR = "api_key_error"
    UNKNOWN_ERROR = "unknown_error"

@dataclass
class CNCeraError(Exception):
    error_type: ErrorType
    technical_message: str
    user_message: str
    retry_suggested: bool = False

    def __str__(self):
        return f"{self.error_type.value}: {self.user_message}"

class ErrorHandler:
    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def handle_exception(self, exc: Exception, context: str = "") -> CNCeraError:
        if isinstance(exc, CNCeraError):
            return exc

        # Enhanced exception classification
        if isinstance(exc, (ValueError, TypeError)):
            error_type = ErrorType.VALIDATION_ERROR
            user_message = "Некорректные данные"
        elif isinstance(exc, (FileNotFoundError, PermissionError)):
            error_type = ErrorType.FILE_ERROR
            user_message = "Ошибка работы с файлом"
        elif isinstance(exc, (requests.RequestException, ConnectionError)):
            error_type = ErrorType.EXTERNAL_API_ERROR
            user_message = "Ошибка внешнего сервиса"
        elif "404" in str(exc):
            error_type = ErrorType.EXTERNAL_API_ERROR
            user_message = "Сервис недоступен (404)"
        elif "API key" in str(exc) or "authentication" in str(exc).lower():
            error_type = ErrorType.API_KEY_ERROR
            user_message = "Ошибка API ключа"
        else:
            error_type = ErrorType.UNKNOWN_ERROR
            user_message = "Неизвестная ошибка"

        self.logger.error(f"Error in {context}: {str(exc)}", exc_info=True)
        return CNCeraError(
            error_type=error_type,
            technical_message=str(exc),
            user_message=user_message,
            retry_suggested=error_type in [ErrorType.EXTERNAL_API_ERROR, ErrorType.PROCESSING_ERROR]
        )

# ---- Enhanced Model Detection and Analysis ----
class ModelAnalyzer:
    def __init__(self):
        self.analysis_cache = {}
    
    def analyze_model_complexity(self, model_path: Path, geometry_data: Dict = None) -> Dict:
        """Analyze model complexity and estimate machining operations"""
        try:
            if not model_path.exists():
                raise CNCeraError(ErrorType.MODEL_NOT_FOUND_ERROR, "Model file not found", "Файл модели не найден")
            
            # Get file size
            file_size = model_path.stat().st_size
            
            # Analyze geometry if available
            complexity_score = 0
            estimated_operations = []
            machining_time_estimate = 0
            
            if geometry_data and geometry_data.get("geometry_analysis"):
                geometry = geometry_data["geometry_analysis"]
                elements = geometry.get("elements", [{}])
                summary = geometry.get("summary", {})
                
                if elements:
                    first_element = elements[0]
                    dimensions = first_element.get("dimensions", {})
                    
                    # Calculate complexity based on features
                    holes = summary.get("total_holes", 0)
                    pockets = summary.get("total_pockets", 0)
                    chamfers = summary.get("total_chamfers", 0)
                    threads = summary.get("total_threads", 0)
                    bosses = summary.get("total_bosses", 0)
                    
                    # Complexity scoring
                    complexity_score = (
                        holes * 2 +           # Holes are moderately complex
                        pockets * 3 +         # Pockets are more complex
                        chamfers * 1 +        # Chamfers are simple
                        threads * 4 +         # Threads are very complex
                        bosses * 2            # Bosses are moderately complex
                    )
                    
                    # Estimate operations based on features
                    if holes > 0:
                        estimated_operations.append({
                            "operation": "drilling",
                            "count": holes,
                            "estimated_time": holes * 2,  # 2 minutes per hole
                            "tools": ["drill"]
                        })
                        machining_time_estimate += holes * 2
                    
                    if pockets > 0:
                        estimated_operations.append({
                            "operation": "pocket_milling",
                            "count": pockets,
                            "estimated_time": pockets * 15,  # 15 minutes per pocket
                            "tools": ["end_mill"]
                        })
                        machining_time_estimate += pockets * 15
                    
                    if chamfers > 0:
                        estimated_operations.append({
                            "operation": "chamfering",
                            "count": chamfers,
                            "estimated_time": chamfers * 5,  # 5 minutes per chamfer
                            "tools": ["chamfer_mill"]
                        })
                        machining_time_estimate += chamfers * 5
                    
                    # Always add roughing and finishing
                    estimated_operations.append({
                        "operation": "roughing",
                        "count": 1,
                        "estimated_time": 30,  # 30 minutes roughing
                        "tools": ["end_mill"]
                    })
                    
                    estimated_operations.append({
                        "operation": "finishing",
                        "count": 1,
                        "estimated_time": 20,  # 20 minutes finishing
                        "tools": ["end_mill"]
                    })
                    
                    machining_time_estimate += 50  # Base roughing + finishing
                    
                    # Calculate total installations needed
                    total_installations = len(estimated_operations)
                    
                    return {
                        "complexity_score": complexity_score,
                        "estimated_operations": estimated_operations,
                        "machining_time_estimate": machining_time_estimate,
                        "total_installations": total_installations,
                        "file_size": file_size,
                        "features_detected": {
                            "holes": holes,
                            "pockets": pockets,
                            "chamfers": chamfers,
                            "threads": threads,
                            "bosses": bosses
                        },
                        "recommendations": self._generate_machining_recommendations(complexity_score, estimated_operations)
                    }
            
            # Fallback analysis if no geometry data
            return {
                "complexity_score": 1,
                "estimated_operations": [
                    {"operation": "roughing", "count": 1, "estimated_time": 30, "tools": ["end_mill"]},
                    {"operation": "finishing", "count": 1, "estimated_time": 20, "tools": ["end_mill"]}
                ],
                "machining_time_estimate": 50,
                "total_installations": 2,
                "file_size": file_size,
                "features_detected": {},
                "recommendations": ["Базовая обработка: черновая + чистовая"]
            }
            
        except Exception as e:
            raise CNCeraError(ErrorType.PROCESSING_ERROR, f"Model analysis failed: {str(e)}", "Ошибка анализа модели")
    
    def _generate_machining_recommendations(self, complexity_score: int, operations: List[Dict]) -> List[str]:
        """Generate machining recommendations based on complexity"""
        recommendations = []
        
        if complexity_score <= 2:
            recommendations.append("Простая деталь - можно обработать за 1-2 установки")
        elif complexity_score <= 5:
            recommendations.append("Средняя сложность - потребуется 2-3 установки")
        else:
            recommendations.append("Сложная деталь - потребуется 3+ установок")
        
        # Add specific recommendations based on operations
        operation_types = [op["operation"] for op in operations]
        
        if "drilling" in operation_types:
            recommendations.append("Используйте сверлильные циклы G81/G83 для отверстий")
        
        if "pocket_milling" in operation_types:
            recommendations.append("Применяйте спиральную стратегию для карманов")
        
        if "chamfering" in operation_types:
            recommendations.append("Фаски обрабатывайте в последнюю очередь")
        
        return recommendations

# Initialize model analyzer
model_analyzer = ModelAnalyzer()

# ---- Enhanced AI Integration with RAG ----
class EnhancedAIService:
    def __init__(self, rag_db: RAGDatabase):
        self.rag_db = rag_db
        self.api_keys = {
            "openai": os.getenv("OPENAI_API_KEY"),
            "anthropic": os.getenv("ANTHROPIC_API_KEY"),
            "xai": os.getenv("XAI_API_KEY")
        }
    
    def get_api_key(self, provider: str) -> str:
        """Get API key for provider with proper error handling"""
        key = self.api_keys.get(provider.lower())
        if not key:
            raise CNCeraError(
                ErrorType.API_KEY_ERROR,
                f"API key not found for {provider}",
                f"API ключ для {provider} не настроен. Установите переменную окружения {provider.upper()}_API_KEY"
            )
        return key
    
    def generate_enhanced_response(self, message: str, provider: str, analysis_data: Dict = None) -> str:
        """Generate AI response with RAG knowledge integration"""
        try:
            # Get relevant knowledge from RAG database
            rag_context = self._get_rag_context(message, analysis_data)
            
            # Prepare enhanced prompt with RAG knowledge
            enhanced_prompt = self._build_enhanced_prompt(message, rag_context, analysis_data)
            
            # Get API key
            api_key = self.get_api_key(provider)
            
            # Generate response
            if provider.lower() == "openai":
                return self._call_openai(enhanced_prompt, api_key)
            elif provider.lower() == "anthropic":
                return self._call_anthropic(enhanced_prompt, api_key)
            elif provider.lower() == "xai":
                return self._call_xai(enhanced_prompt, api_key)
            else:
                raise CNCeraError(ErrorType.VALIDATION_ERROR, "Unknown provider", "Неизвестный провайдер ИИ")
                
        except CNCeraError:
            raise
        except Exception as e:
            raise CNCeraError(ErrorType.EXTERNAL_API_ERROR, f"AI service error: {str(e)}", "Ошибка сервиса ИИ")
    
    def _get_rag_context(self, message: str, analysis_data: Dict = None) -> str:
        """Get relevant context from RAG database"""
        context_parts = []
        
        # Search for G-code related knowledge
        gcode_knowledge = self.rag_db.search_knowledge("gcode", "G-code Basics")
        if gcode_knowledge:
            context_parts.append("G-CODE KNOWLEDGE:")
            for item in gcode_knowledge[:3]:  # Limit to 3 most relevant
                context_parts.append(f"- {item['title']}: {item['content']}")
        
        # Search for milling knowledge
        milling_knowledge = self.rag_db.search_knowledge("milling")
        if milling_knowledge:
            context_parts.append("\nMILLING KNOWLEDGE:")
            for item in milling_knowledge[:2]:
                context_parts.append(f"- {item['title']}: {item['content']}")
        
        # Get material properties if available
        if analysis_data and analysis_data.get("geometry_analysis"):
            material = analysis_data["geometry_analysis"].get("summary", {}).get("primary_material", "")
            if material:
                material_props = self.rag_db.get_material_properties(material)
                if material_props:
                    context_parts.append(f"\nMATERIAL PROPERTIES ({material}):")
                    context_parts.append(f"- Cutting speed: {material_props['cutting_speed_min']}-{material_props['cutting_speed_max']} m/min")
                    context_parts.append(f"- Machinability: {material_props['machinability_rating']}/5")
                    context_parts.append(f"- Recommended tools: {material_props['recommended_tools']}")
        
        return "\n".join(context_parts)
    
    def _build_enhanced_prompt(self, message: str, rag_context: str, analysis_data: Dict = None) -> str:
        """Build enhanced prompt with RAG context and analysis data"""
        prompt_parts = [
            "Ты эксперт по CNC-обработке и анализу 3D-моделей. Используй следующие знания для ответа:",
            "",
            rag_context,
            ""
        ]
        
        # Add analysis data context
        if analysis_data and analysis_data.get("geometry_analysis"):
            geometry = analysis_data["geometry_analysis"]
            elements = geometry.get("elements", [{}])
            summary = geometry.get("summary", {})
            
            if elements:
                first_element = elements[0]
                dimensions = first_element.get("dimensions", {})
                
                prompt_parts.extend([
                    "ДАННЫЕ АНАЛИЗА ДЕТАЛИ:",
                    f"- Размеры: {dimensions.get('length', 0)} x {dimensions.get('width', 0)} x {dimensions.get('height', 0)} мм",
                    f"- Материал: {summary.get('primary_material', 'Не определен')}",
                    f"- Отверстия: {summary.get('total_holes', 0)}",
                    f"- Карманы: {summary.get('total_pockets', 0)}",
                    f"- Фаски: {summary.get('total_chamfers', 0)}",
                    f"- Резьбы: {summary.get('total_threads', 0)}",
                    f"- Бобышки: {summary.get('total_bosses', 0)}",
                    ""
                ])
        
        prompt_parts.extend([
            "Отвечай на русском языке, давай конкретные рекомендации по:",
            "1. Инструментам и режимам резания",
            "2. Последовательности операций",
            "3. G-коду для разных контроллеров",
            "4. Количеству установок для обработки",
            "",
            f"Вопрос пользователя: {message}"
        ])
        
        return "\n".join(prompt_parts)
    
    def _call_openai(self, prompt: str, api_key: str) -> str:
        """Call OpenAI API"""
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4",
                "messages": [
                    {"role": "system", "content": "You are a CNC machining expert with access to comprehensive G-code knowledge."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 2000,
                "temperature": 0.7
            },
            timeout=60
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            raise CNCeraError(
                ErrorType.EXTERNAL_API_ERROR,
                f"OpenAI API error: {response.status_code} - {response.text}",
                f"Ошибка OpenAI API: {response.status_code}"
            )
    
    def _call_anthropic(self, prompt: str, api_key: str) -> str:
        """Call Anthropic API"""
        response = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "Content-Type": "application/json",
                "anthropic-version": "2023-06-01"
            },
            json={
                "model": "claude-3-sonnet-20240229",
                "max_tokens": 2000,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            },
            timeout=60
        )
        
        if response.status_code == 200:
            return response.json()["content"][0]["text"]
        else:
            raise CNCeraError(
                ErrorType.EXTERNAL_API_ERROR,
                f"Anthropic API error: {response.status_code} - {response.text}",
                f"Ошибка Anthropic API: {response.status_code}"
            )
    
    def _call_xai(self, prompt: str, api_key: str) -> str:
        """Call xAI API"""
        response = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "grok-beta",
                "messages": [
                    {"role": "system", "content": "You are a CNC machining expert with access to comprehensive G-code knowledge."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": 2000,
                "temperature": 0.7
            },
            timeout=60
        )
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            raise CNCeraError(
                ErrorType.EXTERNAL_API_ERROR,
                f"xAI API error: {response.status_code} - {response.text}",
                f"Ошибка xAI API: {response.status_code}"
            )

# Initialize enhanced AI service
ai_service = EnhancedAIService(rag_db)

# Continue with the rest of the application...
# [The rest of the original code would continue here with the enhanced components integrated]

# ---- Logging setup ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("CNCera")

# ---- Directory setup ----
BASE = Path(__file__).parent.resolve()
TEMP = BASE / "temp"
TEMP.mkdir(exist_ok=True)
MODELS = BASE / "models"
MODELS.mkdir(exist_ok=True)
STATIC = BASE / "static"
STATIC.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".step", ".stp", ".stl"}
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100MB limit

# Initialize components
error_handler = ErrorHandler(logging.getLogger(__name__))

# Load the enhanced HTML template
with open("index_template_fixed.html", "r", encoding="utf-8") as f:
    INDEX_HTML = f.read()

# ---- Main execution ----
if __name__ == "__main__":
    logger.info("Starting CNCera Enhanced Application - Fixed Version")
    logger.info(f"RAG Database initialized: {rag_db.db_path}")
    logger.info(f"Model Analyzer initialized")
    logger.info(f"Enhanced AI Service initialized")
    
    # Check API keys
    for provider in ["openai", "anthropic", "xai"]:
        key = os.getenv(f"{provider.upper()}_API_KEY")
        if key:
            logger.info(f"{provider.upper()} API key configured")
        else:
            logger.warning(f"{provider.upper()} API key not configured")
    
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        error = error_handler.handle_exception(e, "Application startup")
        logger.error(f"Failed to start application: {error.user_message}")
        sys.exit(1)