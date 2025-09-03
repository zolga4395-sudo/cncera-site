#!/usr/bin/env python3
"""
CNCera Enhanced - Advanced 3D Analysis & G-code Generation
Fixed version with improved error handling, RAG database, and NC Viewer
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
        
        if material:
            cursor.execute(
                "SELECT * FROM tooling_knowledge WHERE applications LIKE ?",
                (f"%{operation_type}%",)
            )
        else:
            cursor.execute("SELECT * FROM tooling_knowledge")
        
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

# Continue with the rest of the code...#!/usr/bin/env python3
"""
CNCera Enhanced - Fixed Components
This file contains the fixed components for the main application
"""

import os
import sys
import json
import sqlite3
import re
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

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

# ---- Enhanced Model Detection and Analysis ----
class ModelAnalyzer:
    def __init__(self):
        self.analysis_cache = {}
    
    def analyze_model_complexity(self, model_path: Path, geometry_data: Dict = None) -> Dict:
        """Analyze model complexity and estimate machining operations"""
        try:
            if not model_path.exists():
                raise Exception("Model file not found")
            
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
            raise Exception(f"Model analysis failed: {str(e)}")
    
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
            raise Exception(f"API ключ для {provider} не настроен. Установите переменную окружения {provider.upper()}_API_KEY")
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
                raise Exception("Неизвестный провайдер ИИ")
                
        except Exception as e:
            raise Exception(f"AI service error: {str(e)}")
    
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
        import requests
        
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
            raise Exception(f"OpenAI API error: {response.status_code}")
    
    def _call_anthropic(self, prompt: str, api_key: str) -> str:
        """Call Anthropic API"""
        import requests
        
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
            raise Exception(f"Anthropic API error: {response.status_code}")
    
    def _call_xai(self, prompt: str, api_key: str) -> str:
        """Call xAI API"""
        import requests
        
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
            raise Exception(f"xAI API error: {response.status_code}")

# ---- NC Viewer Component ----
class NCViewer:
    def __init__(self):
        self.viewer_data = {}
    
    def parse_gcode(self, gcode_path: Path) -> Dict:
        """Parse G-code file and extract viewer data"""
        try:
            if not gcode_path.exists():
                raise Exception("G-code file not found")
            
            with open(gcode_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            
            # Parse G-code
            parsed_data = {
                "total_lines": len(lines),
                "tool_changes": [],
                "moves": [],
                "cycles": [],
                "coordinates": {"min": [0, 0, 0], "max": [0, 0, 0]},
                "program_info": {
                    "title": "",
                    "description": "",
                    "tool_diameter": 0,
                    "feed_rate": 0,
                    "spindle_speed": 0
                }
            }
            
            current_tool = None
            current_feed = 0
            current_spindle = 0
            
            for i, line in enumerate(lines):
                line = line.strip()
                if not line or line.startswith('('):
                    # Extract program info from comments
                    if line.startswith('(') and 'Tool:' in line:
                        match = re.search(r'Tool:\s*([0-9.]+)mm', line)
                        if match:
                            parsed_data["program_info"]["tool_diameter"] = float(match.group(1))
                    elif line.startswith('(') and 'Feed:' in line:
                        match = re.search(r'Feed:\s*([0-9.]+)', line)
                        if match:
                            parsed_data["program_info"]["feed_rate"] = float(match.group(1))
                    elif line.startswith('(') and 'Spindle:' in line:
                        match = re.search(r'Spindle:\s*([0-9.]+)', line)
                        if match:
                            parsed_data["program_info"]["spindle_speed"] = float(match.group(1))
                    continue
                
                # Parse tool changes
                if 'T' in line and 'M06' in line:
                    tool_match = re.search(r'T(\d+)', line)
                    if tool_match:
                        current_tool = int(tool_match.group(1))
                        parsed_data["tool_changes"].append({
                            "line": i + 1,
                            "tool": current_tool,
                            "command": line
                        })
                
                # Parse spindle commands
                if 'M03' in line or 'M04' in line:
                    spindle_match = re.search(r'S(\d+)', line)
                    if spindle_match:
                        current_spindle = int(spindle_match.group(1))
                
                # Parse feed rate
                if 'F' in line:
                    feed_match = re.search(r'F(\d+\.?\d*)', line)
                    if feed_match:
                        current_feed = float(feed_match.group(1))
                
                # Parse moves
                if 'G00' in line or 'G01' in line or 'G02' in line or 'G03' in line:
                    move_data = self._parse_move_line(line, i + 1)
                    if move_data:
                        parsed_data["moves"].append(move_data)
                        
                        # Update coordinate bounds
                        if move_data.get("x") is not None:
                            parsed_data["coordinates"]["min"][0] = min(parsed_data["coordinates"]["min"][0], move_data["x"])
                            parsed_data["coordinates"]["max"][0] = max(parsed_data["coordinates"]["max"][0], move_data["x"])
                        if move_data.get("y") is not None:
                            parsed_data["coordinates"]["min"][1] = min(parsed_data["coordinates"]["min"][1], move_data["y"])
                            parsed_data["coordinates"]["max"][1] = max(parsed_data["coordinates"]["max"][1], move_data["y"])
                        if move_data.get("z") is not None:
                            parsed_data["coordinates"]["min"][2] = min(parsed_data["coordinates"]["min"][2], move_data["z"])
                            parsed_data["coordinates"]["max"][2] = max(parsed_data["coordinates"]["max"][2], move_data["z"])
                
                # Parse cycles
                if any(cycle in line for cycle in ['G81', 'G82', 'G83', 'G84']):
                    cycle_data = self._parse_cycle_line(line, i + 1)
                    if cycle_data:
                        parsed_data["cycles"].append(cycle_data)
            
            # Calculate program statistics
            parsed_data["statistics"] = {
                "rapid_moves": len([m for m in parsed_data["moves"] if m.get("type") == "rapid"]),
                "linear_moves": len([m for m in parsed_data["moves"] if m.get("type") == "linear"]),
                "circular_moves": len([m for m in parsed_data["moves"] if m.get("type") == "circular"]),
                "total_cycles": len(parsed_data["cycles"]),
                "estimated_time": self._estimate_machining_time(parsed_data)
            }
            
            return parsed_data
            
        except Exception as e:
            raise Exception(f"G-code parsing failed: {str(e)}")
    
    def _parse_move_line(self, line: str, line_number: int) -> Optional[Dict]:
        """Parse individual move line"""
        try:
            move_data = {"line": line_number, "command": line}
            
            # Determine move type
            if 'G00' in line:
                move_data["type"] = "rapid"
            elif 'G01' in line:
                move_data["type"] = "linear"
            elif 'G02' in line or 'G03' in line:
                move_data["type"] = "circular"
                move_data["direction"] = "cw" if 'G02' in line else "ccw"
            
            # Extract coordinates
            x_match = re.search(r'X(-?\d+\.?\d*)', line)
            if x_match:
                move_data["x"] = float(x_match.group(1))
            
            y_match = re.search(r'Y(-?\d+\.?\d*)', line)
            if y_match:
                move_data["y"] = float(y_match.group(1))
            
            z_match = re.search(r'Z(-?\d+\.?\d*)', line)
            if z_match:
                move_data["z"] = float(z_match.group(1))
            
            # Extract feed rate
            f_match = re.search(r'F(\d+\.?\d*)', line)
            if f_match:
                move_data["feed"] = float(f_match.group(1))
            
            return move_data
            
        except Exception:
            return None
    
    def _parse_cycle_line(self, line: str, line_number: int) -> Optional[Dict]:
        """Parse cycle line"""
        try:
            cycle_data = {"line": line_number, "command": line}
            
            if 'G81' in line:
                cycle_data["type"] = "drill"
            elif 'G82' in line:
                cycle_data["type"] = "drill_with_dwell"
            elif 'G83' in line:
                cycle_data["type"] = "peck_drill"
            elif 'G84' in line:
                cycle_data["type"] = "tap"
            
            # Extract cycle parameters
            x_match = re.search(r'X(-?\d+\.?\d*)', line)
            if x_match:
                cycle_data["x"] = float(x_match.group(1))
            
            y_match = re.search(r'Y(-?\d+\.?\d*)', line)
            if y_match:
                cycle_data["y"] = float(y_match.group(1))
            
            z_match = re.search(r'Z(-?\d+\.?\d*)', line)
            if z_match:
                cycle_data["z"] = float(z_match.group(1))
            
            r_match = re.search(r'R(-?\d+\.?\d*)', line)
            if r_match:
                cycle_data["r"] = float(r_match.group(1))
            
            return cycle_data
            
        except Exception:
            return None
    
    def _estimate_machining_time(self, parsed_data: Dict) -> float:
        """Estimate machining time based on moves and cycles"""
        total_time = 0
        
        # Estimate time for moves
        for move in parsed_data["moves"]:
            if move.get("type") == "rapid":
                total_time += 0.1  # 0.1 seconds per rapid move
            elif move.get("type") == "linear":
                # Estimate based on distance and feed rate
                feed = move.get("feed", 1000)  # Default feed rate
                distance = 1.0  # Simplified distance estimation
                total_time += distance / feed * 60  # Convert to seconds
        
        # Estimate time for cycles
        for cycle in parsed_data["cycles"]:
            if cycle.get("type") in ["drill", "drill_with_dwell", "peck_drill"]:
                total_time += 30  # 30 seconds per drilling cycle
            elif cycle.get("type") == "tap":
                total_time += 60  # 60 seconds per tapping cycle
        
        return total_time
    
    def generate_viewer_data(self, parsed_data: Dict) -> Dict:
        """Generate data for NC viewer visualization"""
        return {
            "coordinates": parsed_data["coordinates"],
            "moves": parsed_data["moves"][:100],  # Limit for performance
            "cycles": parsed_data["cycles"],
            "statistics": parsed_data["statistics"],
            "program_info": parsed_data["program_info"],
            "tool_changes": parsed_data["tool_changes"]
        }#!/usr/bin/env python3
"""
Flask Routes - Fixed Version
Enhanced routes with improved error handling, model detection, and NC Viewer
"""

from flask import Flask, request, jsonify, send_file, send_from_directory, render_template_string
from pathlib import Path
import json
import time
import logging
from datetime import datetime

# Import fixed components
from cncera_fixes import RAGDatabase, ModelAnalyzer, EnhancedAIService, NCViewer

# Initialize components
rag_db = RAGDatabase()
model_analyzer = ModelAnalyzer()
ai_service = EnhancedAIService(rag_db)
nc_viewer = NCViewer()

# ---- Enhanced Routes ----

@app.route("/analyze_complexity", methods=["POST"])
def analyze_complexity():
    """Analyze model complexity and estimate machining operations"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON data"}), 400
        
        model_path = data.get("model_path")
        if not model_path:
            return jsonify({"success": False, "error": "No model path provided"}), 400
        
        # Validate model path
        model_file = Path(model_path)
        if not model_file.exists():
            return jsonify({"success": False, "error": "Model file not found"}), 404
        
        geometry_analysis = data.get("geometry_analysis", {})
        
        # Analyze model complexity
        analysis_result = model_analyzer.analyze_model_complexity(model_file, geometry_analysis)
        
        processing_time = time.time() - start_time
        
        return jsonify({
            "success": True,
            "analysis": analysis_result,
            "processing_time": processing_time
        })
        
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"Complexity analysis error: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"Complexity analysis failed: {str(e)}",
            "processing_time": processing_time
        }), 500

@app.route("/ai_chat", methods=["POST"])
def ai_chat_enhanced():
    """Enhanced AI chat with RAG knowledge integration"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON data"}), 400
        
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"success": False, "error": "Empty message"}), 400
        
        provider = data.get("provider", "openai").lower()
        if provider not in ["openai", "anthropic", "xai"]:
            return jsonify({"success": False, "error": "Invalid provider"}), 400
        
        analysis_data = data.get("analysis_data", {})
        
        # Generate enhanced AI response with RAG
        ai_response = ai_service.generate_enhanced_response(message, provider, analysis_data)
        
        processing_time = time.time() - start_time
        
        return jsonify({
            "success": True,
            "response": ai_response,
            "provider": provider,
            "processing_time": processing_time
        })
        
    except Exception as e:
        processing_time = time.time() - start_time
        error_message = str(e)
        
        # Handle specific API key errors
        if "API ключ" in error_message or "API key" in error_message:
            return jsonify({
                "success": False,
                "error": error_message,
                "processing_time": processing_time
            }), 400
        
        logger.error(f"AI chat error: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"AI chat failed: {str(e)}",
            "processing_time": processing_time
        }), 500

@app.route("/parse_gcode", methods=["POST"])
def parse_gcode():
    """Parse G-code file for NC Viewer"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON data"}), 400
        
        gcode_path = data.get("gcode_path")
        if not gcode_path:
            return jsonify({"success": False, "error": "No G-code path provided"}), 400
        
        # Validate G-code path
        gcode_file = Path(gcode_path)
        if not gcode_file.exists():
            return jsonify({"success": False, "error": "G-code file not found"}), 404
        
        # Parse G-code
        parsed_data = nc_viewer.parse_gcode(gcode_file)
        
        # Generate viewer data
        viewer_data = nc_viewer.generate_viewer_data(parsed_data)
        
        processing_time = time.time() - start_time
        
        return jsonify({
            "success": True,
            "parsed_data": parsed_data,
            "viewer_data": viewer_data,
            "processing_time": processing_time
        })
        
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"G-code parsing error: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"G-code parsing failed: {str(e)}",
            "processing_time": processing_time
        }), 500

@app.route("/generate_gcode", methods=["POST"])
def generate_gcode_enhanced():
    """Enhanced G-code generation with model validation"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON data"}), 400
        
        model_path = data.get("model_path")
        if not model_path:
            return jsonify({"success": False, "error": "No model path provided"}), 400
        
        # Validate model file exists
        model_file = Path(model_path)
        if not model_file.exists():
            return jsonify({"success": False, "error": "Model file not found. Please upload and analyze a model first."}), 404
        
        # Validate parameters
        validated_params = SecurityValidator.validate_gcode_params(data)
        operation_type = validated_params.get("operation_type", "milling")
        controller = validated_params.get("controller", "fanuc")
        
        # Generate output filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{operation_type}_{controller}_{timestamp}.nc"
        output_path = MODELS / output_filename
        
        # Generate G-code based on operation type
        if operation_type in ["milling", "roughing", "finishing"]:
            result = generate_enhanced_milling_gcode(model_file, output_path, **validated_params)
        elif operation_type == "turning":
            result = generate_turning_gcode(model_file, output_path, **validated_params)
        elif operation_type == "drilling":
            result = generate_drilling_gcode(model_file, output_path, **validated_params)
        elif operation_type == "chamfer":
            result = generate_chamfer_gcode(model_file, output_path, **validated_params)
        else:
            return jsonify({"success": False, "error": "Unknown operation type"}), 400
        
        processing_time = time.time() - start_time
        
        return jsonify({
            "success": True,
            "gcode_path": f"/models/{output_filename}",
            "bbox": result.get("bbox"),
            "processing_time": processing_time
        })
        
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"G-code generation error: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"G-code generation failed: {str(e)}",
            "processing_time": processing_time
        }), 500

@app.route("/upload", methods=["POST"])
def upload_enhanced():
    """Enhanced file upload with geometry analysis"""
    start_time = time.time()
    
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file provided"}), 400
        
        file = request.files["file"]
        if not file or file.filename == "":
            return jsonify({"success": False, "error": "No file selected"}), 400
        
        # Validate filename
        if not SecurityValidator.validate_filename(file.filename):
            return jsonify({"success": False, "error": "Invalid filename"}), 400
        
        # Get parameters
        units = request.form.get("units", "auto")
        linear_deflection = float(request.form.get("linear_deflection", "0.1"))
        angular_deflection_deg = float(request.form.get("angular_deflection_deg", "15"))
        relative = request.form.get("relative", "false").lower() == "true"
        
        # Validate parameters
        if linear_deflection <= 0 or linear_deflection > 10:
            return jsonify({"success": False, "error": "Invalid linear deflection"}), 400
        if angular_deflection_deg <= 0 or angular_deflection_deg > 89:
            return jsonify({"success": False, "error": "Invalid angular deflection"}), 400
        
        # Process file
        result = process_uploaded_file(file, units, linear_deflection, angular_deflection_deg, relative)
        
        # Add geometry analysis if available
        if result.get("success") and result.get("geometry_analysis"):
            # Store analysis data for later use
            result["geometry_analysis"] = result["geometry_analysis"]
        
        processing_time = time.time() - start_time
        result["processing_time"] = processing_time
        
        return jsonify(result)
        
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"File upload error: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"File upload failed: {str(e)}",
            "processing_time": processing_time
        }), 500

@app.route("/cam_analysis", methods=["POST"])
def cam_analysis_enhanced():
    """Enhanced CAM analysis with RAG knowledge"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        if not data:
            return jsonify({"success": False, "error": "No JSON data"}), 400
        
        geometry_analysis = data.get("geometry_analysis")
        if not geometry_analysis:
            return jsonify({"success": False, "error": "No geometry analysis data provided"}), 400
        
        provider = data.get("provider", "openai").lower()
        if provider not in ["openai", "anthropic", "xai"]:
            return jsonify({"success": False, "error": "Invalid provider"}), 400
        
        # Generate CAM recommendations using RAG knowledge
        cam_recommendations = generate_cam_recommendations_enhanced(geometry_analysis, provider)
        
        processing_time = time.time() - start_time
        
        return jsonify({
            "success": True,
            "cam_recommendations": cam_recommendations,
            "processing_time": processing_time
        })
        
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(f"CAM analysis error: {str(e)}", exc_info=True)
        return jsonify({
            "success": False,
            "error": f"CAM analysis failed: {str(e)}",
            "processing_time": processing_time
        }), 500

def generate_cam_recommendations_enhanced(geometry_analysis: dict, provider: str = "openai") -> dict:
    """Generate enhanced CAM recommendations using RAG knowledge"""
    try:
        # Get material properties from RAG database
        material = geometry_analysis.get("summary", {}).get("primary_material", "")
        material_props = None
        if material:
            material_props = rag_db.get_material_properties(material)
        
        # Get tooling recommendations from RAG database
        operation_types = ["milling", "drilling", "chamfering"]
        tooling_recs = []
        for op_type in operation_types:
            tools = rag_db.get_tooling_recommendations(op_type, material)
            tooling_recs.extend(tools)
        
        # Prepare enhanced prompt with RAG knowledge
        prompt = f"""
Проанализируй следующую 3D-модель и предоставь рекомендации для CAM-обработки:

ГЕОМЕТРИЯ:
- Материал: {material}
- Размеры: {geometry_analysis.get('elements', [{}])[0].get('dimensions', {})}
- Отверстия: {geometry_analysis.get('summary', {}).get('total_holes', 0)}
- Карманы: {geometry_analysis.get('summary', {}).get('total_pockets', 0)}
- Фаски: {geometry_analysis.get('summary', {}).get('total_chamfers', 0)}

ЗНАНИЯ ИЗ БАЗЫ:
{f"- Материал: {material_props['material_name']} - {material_props['notes']}" if material_props else ""}
{f"- Скорость резания: {material_props['cutting_speed_min']}-{material_props['cutting_speed_max']} м/мин" if material_props else ""}
{f"- Рекомендуемые инструменты: {material_props['recommended_tools']}" if material_props else ""}

ТРЕБУЕТСЯ:
1. Подобрать инструменты и патроны
2. Рассчитать режимы резания
3. Составить план операций
4. Предложить G-код
5. Указать количество установок

Ответ в JSON формате с конкретными рекомендациями.
"""
        
        # Generate AI response
        ai_response = ai_service.generate_enhanced_response(prompt, provider, {"geometry_analysis": geometry_analysis})
        
        # Try to parse JSON from AI response
        try:
            import re
            json_match = re.search(r'\{.*\}', ai_response, re.DOTALL)
            if json_match:
                cam_data = json.loads(json_match.group())
                return {
                    "success": True,
                    "ai_provider": provider,
                    "recommendations": cam_data,
                    "raw_response": ai_response,
                    "rag_knowledge_used": True
                }
        except json.JSONDecodeError:
            pass
        
        # Fallback to basic recommendations
        return generate_basic_cam_recommendations(geometry_analysis)
        
    except Exception as e:
        logger.error(f"Enhanced CAM recommendations error: {str(e)}")
        return generate_basic_cam_recommendations(geometry_analysis)

def generate_basic_cam_recommendations(geometry_analysis: dict) -> dict:
    """Generate basic CAM recommendations without AI"""
    try:
        summary = geometry_analysis.get("summary", {})
        elements = geometry_analysis.get("elements", [{}])
        
        material = summary.get("primary_material", "Steel (42CrMo4)")
        holes = summary.get("total_holes", 0)
        pockets = summary.get("total_pockets", 0)
        chamfers = summary.get("total_chamfers", 0)
        
        # Basic tooling recommendations
        tools = [
            {
                "type": "end_mill",
                "diameter": 6,
                "flutes": 2,
                "material": "HSS",
                "holder": "BT40",
                "description": "Фреза концевая для черновой обработки"
            },
            {
                "type": "end_mill",
                "diameter": 3,
                "flutes": 4,
                "material": "Carbide",
                "holder": "BT40",
                "description": "Фреза концевая для чистовой обработки"
            }
        ]
        
        if holes > 0:
            tools.append({
                "type": "drill",
                "diameter": 3,
                "material": "HSS",
                "holder": "BT40",
                "description": "Сверло для отверстий"
            })
        
        # Basic cutting parameters
        cutting_parameters = {
            "roughing": {
                "Vc": 120,
                "n": 6366,
                "fz": 0.1,
                "F": 1273,
                "ap": 2,
                "ae": 1.2
            },
            "finishing": {
                "Vc": 150,
                "n": 7958,
                "fz": 0.05,
                "F": 796,
                "ap": 0.5,
                "ae": 0.3
            }
        }
        
        # Basic operations plan
        operations = [
            {
                "step": 1,
                "type": "roughing",
                "tool": "end_mill_6mm",
                "description": "Черновая обработка контура",
                "estimated_time": "15 мин"
            }
        ]
        
        if holes > 0:
            operations.append({
                "step": 2,
                "type": "drilling",
                "tool": "drill_3mm",
                "description": "Сверление отверстий",
                "estimated_time": "5 мин"
            })
        
        if pockets > 0:
            operations.append({
                "step": len(operations) + 1,
                "type": "pocket_milling",
                "tool": "end_mill_6mm",
                "description": "Обработка карманов",
                "estimated_time": "10 мин"
            })
        
        operations.append({
            "step": len(operations) + 1,
            "type": "finishing",
            "tool": "end_mill_3mm",
            "description": "Чистовая обработка",
            "estimated_time": "10 мин"
        })
        
        # Calculate total installations
        total_installations = len(operations)
        
        return {
            "success": True,
            "ai_provider": "basic",
            "recommendations": {
                "tools": tools,
                "cutting_parameters": cutting_parameters,
                "operations": operations,
                "total_installations": total_installations,
                "estimated_total_time": sum([int(op["estimated_time"].split()[0]) for op in operations])
            },
            "raw_response": "Базовые рекомендации без ИИ"
        }
        
    except Exception as e:
        logger.error(f"Basic CAM recommendations error: {str(e)}")
        return {
            "success": False,
            "error": f"Failed to generate recommendations: {str(e)}"
        }

# ---- Error Handlers ----
@app.errorhandler(404)
def not_found(error):
    return jsonify({"success": False, "error": "Endpoint not found"}), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({"success": False, "error": "Method not allowed"}), 405

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"success": False, "error": "File too large"}), 413

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {str(error)}", exc_info=True)
    return jsonify({"success": False, "error": "Internal server error"}), 500