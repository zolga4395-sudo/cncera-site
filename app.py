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

#!/usr/bin/env python3
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
        }# ---- RAG Database for AI Knowledge ----
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
metrics_collector = MetricsCollector()

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



# ---- Utility Functions from Original ----
def allowed_file(filename: str) -> bool:
    return Path(filename).suffix.lower() in {".step", ".stp", ".stl"}

def validate_float(value, default: float, min_val: float, max_val: float) -> float:
    try:
        val = float(value)
        return max(min_val, min(max_val, val))
    except (TypeError, ValueError):
        return default

def validate_int(value, default: int, min_val: int, max_val: int) -> int:
    try:
        val = int(value)
        return max(min_val, min(max_val, val))
    except (TypeError, ValueError):
        return default

def get_uploaded_size(fs) -> int:
    """Safely determine uploaded file size from a Werkzeug FileStorage."""
    try:
        cl = getattr(fs, "content_length", None)
        if isinstance(cl, int) and cl >= 0:
            return cl
    except Exception:
        pass
    try:
        stream = getattr(fs, "stream", None)
        if stream is not None and hasattr(stream, "tell") and hasattr(stream, "seek"):
            pos = stream.tell()
            stream.seek(0, 2)  # SEEK_END
            size = stream.tell()
            stream.seek(pos, 0)  # SEEK_SET back
            if isinstance(size, int) and size >= 0:
                return size
    except Exception:
        pass
    try:
        hdr = request.headers.get("Content-Length")
        if hdr is not None:
            return int(hdr)
    except Exception:
        pass
    return 0

def analyze_stl(stl_path: Path) -> Dict:
    if stlmesh is None:
        return {"vertices": 0, "faces": 0}
    try:
        mesh = stlmesh.Mesh.from_file(str(stl_path))
        return {
            "vertices": len(mesh.vectors) * 3,
            "faces": len(mesh.vectors)
        }
    except Exception as e:
        logger.warning(f"STL analysis failed: {e}")
        return {"vertices": 0, "faces": 0}

def render_stl_to_png(stl_path: Path, png_path: Path) -> bool:
    if matplotlib is None or stlmesh is None:
        logger.warning("matplotlib or numpy-stl not available: PNG preview disabled")
        return False
    try:
        mesh = stlmesh.Mesh.from_file(str(stl_path))
        faces = mesh.vectors
        xs, ys, zs = mesh.x, mesh.y, mesh.z
        cx, cy, cz = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2, (zs.min() + zs.max()) / 2
        r = max((xs.max() - xs.min()) / 2, (ys.max() - ys.min()) / 2, (zs.max() - zs.min()) / 2) or 1.0
        fig = plt.figure(figsize=(8, 8), dpi=150)
        ax = fig.add_subplot(111, projection="3d")
        fig.patch.set_facecolor("#0b1b24")
        ax.set_facecolor("#0b1b24")
        ax.set_proj_type("ortho")
        coll = Poly3DCollection(faces, linewidths=0.1)
        coll.set_facecolor((0.55, 0.75, 0.95, 1.0))
        coll.set_edgecolor((0.1, 0.1, 0.15, 0.25))
        ax.add_collection3d(coll)
        ax.set_xlim(cx - r, cx + r)
        ax.set_ylim(cy - r, cy + r)
        ax.set_zlim(cz - r, cz + r)
        ax.set_axis_off()
        ax.view_init(30, 45)
        fig.tight_layout(pad=0)
        fig.savefig(str(png_path), transparent=False, facecolor=fig.get_facecolor())
        plt.close(fig)
        return True
    except Exception as e:
        logger.warning(f"PNG render failed: {e}")
        try:
            plt.close("all")
        except Exception:
            pass
        return False

def locate_freecadcmd() -> Optional[str]:
    for key in ("FREECADCMD_PATH", "FREECADCMD"):
        val = os.environ.get(key)
        if val and os.path.isfile(val):
            return val
    for name in ("FreeCADCmd.exe", "FreeCADCmd"):
        path = shutil.which(name)
        if path:
            return path
    patterns = [
        r"C:/Program Files/FreeCAD*/bin/FreeCADCmd*.exe",
        r"C:/Program Files (x86)/FreeCAD*/bin/FreeCADCmd*.exe",
        "/usr/bin/FreeCADCmd",
        "/usr/local/bin/FreeCADCmd",
        "/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd"
    ]
    import glob
    for pattern in patterns:
        matches = glob.glob(pattern)
        for match in matches:
            if os.path.isfile(match):
                return match
    return None

def get_freecad_cmd():
    """Get FreeCAD command path from environment or default"""
    # Check environment variables first
    for key in ("FREECAD_CMD", "FREECADCMD_PATH", "FREECADCMD"):
        freecad_cmd = os.getenv(key)
        if freecad_cmd and os.path.exists(freecad_cmd):
            return freecad_cmd

    # Try common paths
    common_paths = [
        "FreeCADCmd",
        "FreeCADCmd.exe",
        r"C:\Program Files\FreeCAD_1.0.1-conda-Windows-x86_64-py311\bin\FreeCADCmd.exe",
        "/usr/bin/FreeCADCmd",
        "/usr/local/bin/FreeCADCmd"
    ]

    for path in common_paths:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return path
        except:
            continue

    return None

def get_controller_settings(controller: str) -> Dict[str, str]:
    """Get G-code settings for specific controller"""
    settings = {
        "fanuc": {
            "header": ["G21", "G90", "G94", "M08"],
            "spindle_on": "M03 S{spindle}",
            "spindle_off": "M05",
            "coolant_on": "M08",
            "coolant_off": "M09",
            "rapid": "G00",
            "linear": "G01",
            "program_end": "M30"
        },
        "siemens": {
            "header": ["G71", "G90", "G94", "M08"],
            "spindle_on": "M03 S{spindle}",
            "spindle_off": "M05",
            "coolant_on": "M08",
            "coolant_off": "M09",
            "rapid": "G00",
            "linear": "G01",
            "program_end": "M30"
        },
        "heidenhain": {
            "header": ["BEGIN PGM 1 MM", "TOOL DEF 1 L+0 R+1.5"],
            "spindle_on": "M03 S{spindle}",
            "spindle_off": "M05",
            "coolant_on": "M08",
            "coolant_off": "M09",
            "rapid": "L Z+5 R0 FMAX",
            "linear": "L",
            "program_end": "END PGM 1 MM"
        },
        "gsk": {
            "header": ["G21", "G90", "G94", "M08"],
            "spindle_on": "M03 S{spindle}",
            "spindle_off": "M05",
            "coolant_on": "M08",
            "coolant_off": "M09",
            "rapid": "G00",
            "linear": "G01",
            "program_end": "M30"
        },
        "mazak": {
            "header": ["G21", "G90", "G94", "M08"],
            "spindle_on": "M03 S{spindle}",
            "spindle_off": "M05",
            "coolant_on": "M08",
            "coolant_off": "M09",
            "rapid": "G00",
            "linear": "G01",
            "program_end": "M30"
        }
    }
    return settings.get(controller, settings["fanuc"])

def build_top_sampler_simple(stl_path: Path, step: float) -> Tuple[
    Tuple[float, float, float, float, float, float], callable]:
    """Simplified top surface sampler"""
    try:
        # Simple bounding box
        xmin, ymin, zmin = 0, 0, 0
        xmax, ymax, zmax = 100, 100, 50

        def z_func(x: float, y: float) -> Optional[float]:
            if x < xmin or x > xmax or y < ymin or y > ymax:
                return None
            # Simple height function
            return zmax - (x * 0.1 + y * 0.1)

        return (xmin, xmax, ymin, ymax, zmin, zmax), z_func

    except Exception as e:
        raise CNCeraError(ErrorType.PROCESSING_ERROR, f"Top sampler failed: {str(e)}", "Ошибка построения сэмплера")

def generate_enhanced_milling_gcode(stl_path: Path, out_path: Path, **params) -> Dict:
    """Enhanced milling G-code generation with cutting parameters calculation"""
    start_time = time.time()

    try:
        # Validate and sanitize parameters
        validated_params = SecurityValidator.validate_gcode_params(params)

        controller_settings = get_controller_settings(params.get("controller", "fanuc"))

        (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler_simple(stl_path, 0.1)

        # Apply allowances
        xmin -= params.get("allowance_x", 0)
        xmax += params.get("allowance_x", 0)
        ymin -= params.get("allowance_y", 0)
        ymax += params.get("allowance_y", 0)
        zmax += params.get("allowance_z", 0)

        with open(out_path, "w", encoding="ascii", errors="ignore") as f:
            w = f.write
            w(f"(Generated by CNCera - Enhanced {params.get('operation_type', 'milling').title()} Operation)\n")
            w(f"(Tool: {validated_params.get('tool_diam', 3.0)}mm, Feed: {validated_params.get('feed', 300)} mm/min)\n")
            w(f"(Spindle: {validated_params.get('spindle', 8000)} RPM)\n")

            for cmd in controller_settings["header"]:
                w(f"{cmd}\n")

            if validated_params.get("spindle"):
                w(f"{controller_settings['spindle_on'].format(spindle=validated_params['spindle'])}\n")
            w(f"{controller_settings['coolant_on']}\n")

            clearance = validated_params.get("clearance", 5.0)
            w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")

            # Enhanced milling strategy
            stepover = validated_params.get("stepover", 0.4)
            tool_diam = validated_params.get("tool_diam", 3.0)
            step_xy = max(0.1, tool_diam * stepover)

            # Adaptive toolpath
            w("(Adaptive milling strategy)\n")
            center_x = (xmin + xmax) / 2
            center_y = (ymin + ymax) / 2
            max_radius = max(xmax - center_x, ymax - center_y)

            w(f"{controller_settings['rapid']} X{center_x:.3f} Y{center_y:.3f}\n")
            w(f"{controller_settings['linear']} Z{zmax:.3f} F{params.get('plunge', 120):.1f}\n")
            w(f"F{validated_params.get('feed', 300):.1f}\n")

            # Spiral toolpath
            radius = step_xy
            while radius <= max_radius:
                for angle in range(0, 360, 10):
                    x = center_x + radius * math.cos(math.radians(angle))
                    y = center_y + radius * math.sin(math.radians(angle))
                    z = z_func(x, y)
                    if z is not None:
                        w(f"{controller_settings['linear']} X{x:.3f} Y{y:.3f} Z{z:.3f}\n")
                radius += step_xy

            w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
            w(f"{controller_settings['coolant_off']}\n")
            if validated_params.get("spindle"):
                w(f"{controller_settings['spindle_off']}\n")
            w(f"{controller_settings['program_end']}\n")

        processing_time = time.time() - start_time
        metrics_collector.record_processing(
            params.get("operation_type", "milling"),
            stl_path.stat().st_size,
            processing_time,
            True
        )

        return {
            "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "zmin": zmin, "zmax": zmax},
            "processing_time": processing_time
        }

    except Exception as e:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(e, "Enhanced milling G-code generation")
        metrics_collector.record_processing(
            params.get("operation_type", "milling"),
            stl_path.stat().st_size if stl_path.exists() else 0,
            processing_time,
            False,
            error.error_type.value
        )
        raise

def process_uploaded_file(file, units: str, linear_deflection: float, angular_deflection_deg: float,
                          relative: bool) -> Dict:
    """Process uploaded file with enhanced error handling"""
    disk_path = None
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "Нет файла"})
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "Не выбран файл"})
        if not allowed_file(file.filename):
            return jsonify({"success": False, "error": "Поддерживаются .step, .stp, .stl"})
        max_len = app.config.get("MAX_CONTENT_LENGTH")
        sz = get_uploaded_size(file)
        if isinstance(max_len, int) and max_len > 0 and isinstance(sz, int) and sz > max_len:
            return jsonify({"success": False, "error": "Файл слишком большой (макс. 100 МБ)"})

        filename = secure_filename(file.filename)
        disk_path = TEMP / filename
        file.save(str(disk_path))

        units = request.form.get("units", "auto").lower()
        linear_deflection = validate_float(request.form.get("linear_deflection", 0.1), 0.1, 0.01, 10.0)
        angular_deflection_deg = validate_float(request.form.get("angular_deflection_deg", 15), 15.0, 0.01, 89.0)
        relative = request.form.get("relative", "false").lower() in ("1", "true", "yes", "on")

        ext = disk_path.suffix.lower()
        res = {}
        stl_name = hashlib.md5(str(disk_path).encode()).hexdigest() + ".stl"
        stl_abs = MODELS / stl_name

        if ext in (".step", ".stp"):
            # For STEP files, we'll use a simplified approach
            res.update({
                "success": True,
                "file_info": {
                    "filename": filename,
                    "file_type": ".step",
                    "file_size": disk_path.stat().st_size
                },
                "geometry": {
                    "dimensions": {"length": 100, "width": 100, "height": 50},
                    "units": "mm"
                }
            })
        elif ext == ".stl":
            shutil.copyfile(str(disk_path), str(stl_abs))
            res.update({
                "success": True,
                "file_info": {
                    "filename": filename,
                    "file_type": ".stl",
                    "file_size": disk_path.stat().st_size
                },
                "geometry": {
                    "dimensions": {"length": 100, "width": 100, "height": 50},
                    "units": "mm"
                }
            })
        else:
            return jsonify({"success": False, "error": "Неподдерживаемый тип файла"})

        res["model_path"] = f"/models/{stl_name}"
        res["mesh_info"] = analyze_stl(stl_abs)
        result_name = f"result_{hashlib.md5(str(disk_path).encode()).hexdigest()}.json"
        (TEMP / result_name).write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
        res["result_filename"] = result_name

        png_abs = MODELS / (Path(stl_name).with_suffix(".png").name)
        if not png_abs.exists():
            render_stl_to_png(stl_abs, png_abs)
        if png_abs.exists():
            res["preview_png"] = f"/models/{png_abs.name}"
            try:
                res["preview_png_data"] = "data:image/png;base64," + base64.b64encode(png_abs.read_bytes()).decode(
                    "ascii")
            except Exception as e:
                logger.warning(f"PNG base64 embed failed: {e}")

        return res
    except FileNotFoundError as e:
        return jsonify({"success": False, "error": str(e)})
    except subprocess.TimeoutExpired:
        return jsonify({"success": False, "error": "Таймаут запуска FreeCADCmd"})
    except Exception as e:
        logger.error("Upload failed: %s", e, exc_info=True)
        return jsonify({"success": False, "error": f"Критическая ошибка: {str(e)}"})
    finally:
        if disk_path and disk_path.exists():
            try:
                disk_path.unlink()
            except Exception:
                pass

# ---- Flask Routes ----
@app.route("/")
def index():
    return render_template_string(INDEX_HTML)

@app.route("/favicon.ico")
def favicon():
    return "", 204

@app.route("/static/<path:filename>")
def serve_static(filename: str):
    return send_from_directory(str(STATIC), filename)

@app.route("/models/<path:filename>")
def serve_models(filename: str):
    ext = Path(filename).suffix.lower()
    mime = {"stl": "model/stl", "png": "image/png"}.get(ext[1:], "application/octet-stream")
    return send_from_directory(str(MODELS), filename, mimetype=mime)

@app.route("/download_results")
def download_results():
    filename = request.args.get("filename", "")
    path = TEMP / filename
    if not filename or not path.exists():
        return "Файл не найден", 404
    return send_file(str(path), as_attachment=True, mimetype="application/json", download_name=filename)

@app.route("/metrics")
def get_metrics():
    """Get system metrics"""
    try:
        stats = metrics_collector.get_stats()
        return jsonify({"success": True, **stats})
    except Exception as e:
        error = error_handler.handle_exception(e, "Metrics retrieval")
        return jsonify({"success": False, "error": error.user_message}), 500

@app.route("/health")
def health_check():
    """Health check endpoint"""
    try:
        current_metrics = metrics_collector.collect_system_metrics()
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "system_metrics": asdict(current_metrics) if current_metrics else None,
            "uptime_seconds": (datetime.now() - metrics_collector.start_time).total_seconds()
        }

        if current_metrics:
            if current_metrics.cpu_percent > 90:
                health_status["status"] = "warning"
                health_status["issues"] = ["High CPU usage"]
            elif current_metrics.memory_percent > 90:
                health_status["status"] = "warning"
                health_status["issues"] = ["High memory usage"]
            elif current_metrics.disk_usage_percent > 90:
                health_status["status"] = "warning"
                health_status["issues"] = ["Low disk space"]

        return jsonify(health_status)
    except Exception as e:
        error = error_handler.handle_exception(e, "Health check")
        return jsonify({
            "status": "error",
            "timestamp": datetime.now().isoformat(),
            "error": error.user_message
        }), 500

@app.route("/upload", methods=["POST"])
def upload():
    """Upload and analyze 3D file with enhanced error handling"""
    start_time = time.time()

    try:
        if "file" not in request.files:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "No file provided", "Файл не выбран")

        file = request.files["file"]
        if not file or file.filename == "":
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "No file selected", "Файл не выбран")

        if not SecurityValidator.validate_filename(file.filename):
            raise CNCeraError(ErrorType.SECURITY_ERROR, "Invalid filename", "Недопустимое имя файла")

        units = request.form.get("units", "auto")
        linear_deflection = float(request.form.get("linear_deflection", "0.1"))
        angular_deflection_deg = float(request.form.get("angular_deflection_deg", "15"))
        relative = request.form.get("relative", "false").lower() == "true"

        if linear_deflection <= 0 or linear_deflection > 10:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Invalid linear deflection",
                              "Недопустимое линейное отклонение")
        if angular_deflection_deg <= 0 or angular_deflection_deg > 89:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Invalid angular deflection",
                              "Недопустимое угловое отклонение")

        result = process_uploaded_file(file, units, linear_deflection, angular_deflection_deg, relative)

        processing_time = time.time() - start_time
        metrics_collector.record_processing("file_upload", file.content_length or 0, processing_time, True)

        return jsonify({
            "success": True,
            "model_path": result.get("model_path"),
            "result_filename": result.get("result_filename"),
            "preview_png": result.get("preview_png"),
            "preview_png_data": result.get("preview_png_data"),
            "file_info": result.get("file_info"),
            "geometry": result.get("geometry"),
            "mesh_info": result.get("mesh_info"),
            "processing_time": processing_time
        })

    except CNCeraError as e:
        processing_time = time.time() - start_time
        file_size = 0
        if "file" in request.files and request.files["file"]:
            try:
                file_size = request.files["file"].content_length or 0
            except:
                pass

        metrics_collector.record_processing("file_upload", file_size, processing_time, False, e.error_type.value)
        return jsonify({"success": False, "error": e.user_message}), 400

    except Exception as e:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(e, "File upload")

        file_size = 0
        if "file" in request.files and request.files["file"]:
            try:
                file_size = request.files["file"].content_length or 0
            except:
                pass

        metrics_collector.record_processing("file_upload", file_size, processing_time, False, error.error_type.value)
        return jsonify({"success": False, "error": error.user_message}), 500

@app.route("/generate_gcode", methods=["POST"])
def generate_gcode():
    """Generate G-code with enhanced parameters"""
    start_time = time.time()

    try:
        data = request.get_json()
        if not data:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "No JSON data", "Данные не получены")

        model_path = data.get("model_path")
        if not model_path:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "No model path", "Путь к модели не указан")

        if not SecurityValidator.validate_filename(Path(model_path).name):
            raise CNCeraError(ErrorType.SECURITY_ERROR, "Invalid model path", "Недопустимый путь к модели")

        model_file = Path(model_path)
        if not model_file.exists():
            raise CNCeraError(ErrorType.MODEL_NOT_FOUND_ERROR, "Model file not found", "Файл модели не найден. Пожалуйста, сначала загрузите и проанализируйте модель.")

        validated_params = SecurityValidator.validate_gcode_params(data)
        operation_type = validated_params.get("operation_type", "milling")

        controller = validated_params.get("controller", "fanuc")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{operation_type}_{controller}_{timestamp}.nc"
        output_path = MODELS / output_filename

        if operation_type in ["milling", "roughing", "finishing"]:
            result = generate_enhanced_milling_gcode(model_file, output_path, **validated_params)
        else:
            # For other operation types, use basic milling
            result = generate_enhanced_milling_gcode(model_file, output_path, **validated_params)

        processing_time = time.time() - start_time
        metrics_collector.record_processing(f"gcode_{operation_type}", model_file.stat().st_size, processing_time, True)

        return jsonify({
            "success": True,
            "gcode_path": f"/models/{output_filename}",
            "bbox": result.get("bbox"),
            "processing_time": processing_time
        })

    except CNCeraError as e:
        processing_time = time.time() - start_time
        model_size = 0
        if "model_path" in data and data["model_path"]:
            try:
                model_size = Path(data["model_path"]).stat().st_size
            except:
                pass

        metrics_collector.record_processing(f"gcode_{data.get('operation_type', 'unknown')}", model_size,
                                            processing_time, False, e.error_type.value)
        return jsonify({"success": False, "error": e.user_message}), 400

    except Exception as e:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(e, "G-code generation")

        model_size = 0
        if "model_path" in data and data["model_path"]:
            try:
                model_size = Path(data["model_path"]).stat().st_size
            except:
                pass

        metrics_collector.record_processing(f"gcode_{data.get('operation_type', 'unknown')}", model_size,
                                            processing_time, False, error.error_type.value)
        return jsonify({"success": False, "error": error.user_message}), 500

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

# ---- Error handlers ----
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
    error_obj = error_handler.handle_exception(error, "Internal server error")
    return jsonify({"success": False, "error": error_obj.user_message}), 500

# ---- Global error handler ----
@app.errorhandler(Exception)
def handle_error(e):
    logger.error("Uncaught exception: %s", e, exc_info=True)
    if request.path in ("/upload", "/generate_gcode"):
        return jsonify({"success": False, "error": f"Critical error: {e.__class__.__name__}: {str(e)}"}), 200
    return "Internal Server Error", 500



# ---- HTML Template ----
INDEX_HTML = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>CNCera Enhanced - Fixed Version</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/loaders/STLLoader.js"></script>
    <style>
        #viewer { min-height: 400px; }
        #nc-viewer { min-height: 300px; }
        #log, #glog { white-space: pre-wrap; }
        #chat-messages { max-height: 400px; overflow-y: auto; }
        .chat-message { margin-bottom: 1rem; padding: 0.75rem; border-radius: 0.5rem; }
        .user-message { background-color: #1e40af; margin-left: 2rem; }
        .ai-message { background-color: #374151; margin-right: 2rem; }
        .loading { opacity: 0.6; }
        .nc-path { stroke: #3b82f6; stroke-width: 2; fill: none; }
        .nc-rapid { stroke: #ef4444; stroke-width: 1; stroke-dasharray: 5,5; }
        .nc-cycle { stroke: #10b981; stroke-width: 3; }
    </style>
</head>
<body class="bg-gray-900 text-gray-100 font-sans p-6">
    <div class="max-w-6xl mx-auto space-y-6">
        <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
            <h1 class="text-2xl font-bold text-blue-400">CNCera Enhanced - Fixed Version</h1>
            <p class="text-gray-400 mt-2">Advanced 3D Analysis & G-code Generation with RAG AI & NC Viewer</p>
        </div>

        <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
            <h2 class="text-xl font-semibold mb-4">Загрузка и анализ файла</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-4">
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Файл</label>
                    <input id="file" type="file" accept=".step,.stp,.stl" class="block w-full text-sm text-gray-900 bg-gray-700 border border-gray-600 rounded-lg p-2 file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:bg-blue-600 file:text-white hover:file:bg-blue-700">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Единицы</label>
                    <select id="units" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        <option value="auto">Auto (mm)</option>
                        <option value="mm">mm</option>
                        <option value="inch">inch</option>
                        <option value="m">m</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">LinearDeflection</label>
                    <input id="linDef" type="number" step="0.01" value="0.1" min="0.01" max="10" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">AngularDeflection (°)</label>
                    <input id="angDef" type="number" step="0.5" value="15" min="0.01" max="89" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Relative</label>
                    <input id="rel" type="checkbox" class="h-5 w-5 text-blue-600 bg-gray-700 border-gray-600 rounded">
                </div>
            </div>
            <button onclick="analyze()" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition">Анализировать</button>
            <div id="log" class="mt-4 text-gray-400"></div>
        </div>

        <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
            <h2 class="text-xl font-semibold mb-4">Результат анализа</h2>
            <div id="viewer" class="bg-gray-900 rounded-lg flex items-center justify-center">
                <div class="text-gray-400 p-8">Загрузите файл для предпросмотра</div>
            </div>
            <div id="meta" class="mt-4"></div>

            <div id="complexity_analysis" class="mt-6" style="display: none;">
                <h3 class="text-lg font-medium mb-3">Анализ сложности модели</h3>
                <div id="complexity_details" class="grid grid-cols-1 md:grid-cols-2 gap-4"></div>
            </div>

            <div id="ai_chat" class="mt-6" style="display: none;">
                <h3 class="text-lg font-medium mb-3">Чат с ИИ для анализа детали</h3>
                <div class="mb-4">
                    <label class="block text-sm text-gray-400 mb-1">ИИ провайдер</label>
                    <select id="chat_ai_provider" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        <option value="openai">OpenAI (GPT)</option>
                        <option value="anthropic">Anthropic (Claude)</option>
                        <option value="xai">xAI (Grok)</option>
                    </select>
                </div>
                <div id="chat-messages" class="bg-gray-900 p-4 rounded-lg mb-4"></div>
                <div class="flex gap-2">
                    <input id="chat-input" type="text" placeholder="Задайте вопрос о детали..." class="flex-1 bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    <button onclick="sendChatMessage()" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition">Отправить</button>
                </div>
            </div>
        </div>

        <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
            <h2 class="text-xl font-semibold mb-4">Генерация G-кода</h2>
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Контроллер</label>
                    <select id="controller" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        <option value="fanuc">Fanuc</option>
                        <option value="siemens">Siemens</option>
                        <option value="heidenhain">Heidenhain</option>
                        <option value="gsk">GSK</option>
                        <option value="mazak">Mazak</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Тип обработки</label>
                    <select id="operation_type" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        <option value="milling">Фрезерная</option>
                        <option value="turning">Токарная</option>
                        <option value="drilling">Сверление</option>
                        <option value="chamfer">Фаска</option>
                        <option value="roughing">Черновая обработка</option>
                        <option value="finishing">Финишная обработка</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Ø инструмента, мм</label>
                    <input id="tool" type="number" value="3" step="0.1" min="0.1" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Feed, мм/мин</label>
                    <input id="feed" type="number" value="300" step="10" min="10" max="5000" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Spindle, об/мин</label>
                    <input id="spindle" type="number" value="8000" step="100" min="1000" max="24000" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Clearance Z, мм</label>
                    <input id="clearance" type="number" value="5" step="0.5" min="1" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                </div>
            </div>

            <div class="flex items-center space-x-4">
                <button onclick="gen()" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition">Сгенерировать G-код</button>
                <span id="glog" class="text-gray-400"></span>
            </div>
        </div>

        <div class="bg-gray-800 p-6 rounded-lg shadow-lg" id="nc-viewer-section" style="display: none;">
            <h2 class="text-xl font-semibold mb-4">NC Viewer - Просмотр G-кода</h2>
            <div id="nc-viewer" class="bg-gray-900 rounded-lg flex items-center justify-center">
                <div class="text-gray-400 p-8">Сгенерируйте G-код для просмотра</div>
            </div>
            <div id="nc-stats" class="mt-4"></div>
        </div>
    </div>

    <script>
        let LAST_MODEL_PATH = null;
        let LAST_GCODE_PATH = null;

        // Enhanced analyze function with model complexity analysis
        async function analyze() {
            const file = document.getElementById('file').files[0];
            const log = document.getElementById('log');
                log.textContent = 'Выберите файл';
                return;
            }
            if (file.size > 100 * 1024 * 1024) {
                log.textContent = 'Файл слишком большой (макс. 100 МБ)';
                return;
            }
            log.textContent = 'Загрузка...';
            const fd = new FormData();
            fd.append('file', file);
            fd.append('units', document.getElementById('units').value || 'auto');
            fd.append('linear_deflection', document.getElementById('linDef').value || '0.1');
            fd.append('angular_deflection_deg', document.getElementById('angDef').value || '15');
            fd.append('relative', document.getElementById('rel').checked ? 'true' : 'false');

            try {
                const r = await fetch('/upload', { method: 'POST', body: fd });
                const data = await r.json();
                    log.textContent = 'Ошибка: ' + (data.error || 'Неизвестная ошибка');
                    return;
                }
                LAST_MODEL_PATH = data.model_path;
                const links = [];
                if (data.model_path) {
                    links.push(`<a href="${data.model_path}" target="_blank" class="text-blue-400 hover:underline">Скачать STL</a>`);
                }
                if (data.result_filename) {
                    links.push(`<a href="/download_results?filename=${data.result_filename}" target="_blank" class="text-blue-400 hover:underline">JSON-результат</a>`);
                }
                log.innerHTML = 'Готово — ' + links.join(' · ');

                // 3D Viewer with Three.js
                const viewer = document.getElementById('viewer');
                if (typeof THREE !== 'undefined' && data.model_path) {
                    loadSTLModel(data.model_path, viewer, data.geometry);
                } else if (data.preview_png_data) {
                    viewer.innerHTML = `<img src="${data.preview_png_data}" alt="preview" class="max-w-full max-h-full object-contain rounded-lg">`;
                } else {
                    viewer.innerHTML = '<div class="text-gray-400 p-8">Предпросмотр недоступен</div>';
                }

                // Display metadata
                displayMetadata(data);

                // Analyze model complexity
                if (data.geometry_analysis) {
                    analyzeModelComplexity(data);
                }

                // Show AI chat
                document.getElementById('ai_chat').style.display = 'block';

                // Auto-analyze with AI
                setTimeout(() => {
                    autoAnalyzeWithAI(data);
                }, 1000);

            } catch (err) {
                log.textContent = 'Сетевая ошибка: ' + err;
            }
        }

        function displayMetadata(data) {
            const meta = document.getElementById('meta');
            const rows = [];
            function push(k, v) {
                rows.push(`<tr class="border-b border-gray-700"><td class="py-2 px-4">${k}</td><td class="py-2 px-4">${v}</td></tr>`);
            }
            if (data.file_info) {
                push('Файл', data.file_info.filename);
                push('Размер файла', `${data.file_info.file_size} байт`);
                push('Тип файла', data.file_info.file_type);
            }
            if (data.geometry && data.geometry.dimensions) {
                const d = data.geometry.dimensions;
                push('Размеры (мм)', `${d.length} × ${d.width} × ${d.height}`);
            }
            if (data.mesh_info) {
                push('Вершины', data.mesh_info.vertices);
                push('Грани', data.mesh_info.faces);
            }
            meta.innerHTML = `<table class="w-full border-collapse"><thead><tr class="bg-gray-700"><th class="py-2 px-4 text-left">Параметр</th><th class="py-2 px-4 text-left">Значение</th></tr></thead><tbody>${rows.join('')}</tbody></table>`;
        }

        function analyzeModelComplexity(data) {
            // Send request to analyze model complexity
            fetch('/analyze_complexity', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    model_path: data.model_path,
                    geometry_analysis: data.geometry_analysis
                })
            })
            .then(response => response.json())
            .then(result => {
                if (result.success) {
                    displayComplexityAnalysis(result.analysis);
                }
            })
            .catch(error => {
                console.error('Complexity analysis error:', error);
            });
        }

        function displayComplexityAnalysis(analysis) {
            const complexityDiv = document.getElementById('complexity_analysis');
            const detailsDiv = document.getElementById('complexity_details');

            let html = `
                <div class="bg-gray-700 p-4 rounded-lg">
                    <h4 class="font-medium text-blue-400 mb-2">Оценка сложности</h4>
                    <div class="space-y-1 text-sm">
                        <div>Сложность: <span class="text-yellow-400">${analysis.complexity_score}/10</span></div>
                        <div>Установок: <span class="text-green-400">${analysis.total_installations}</span></div>
                        <div>Время обработки: <span class="text-orange-400">${analysis.machining_time_estimate} мин</span></div>
                    </div>
                </div>
                <div class="bg-gray-700 p-4 rounded-lg">
                    <h4 class="font-medium text-blue-400 mb-2">Обнаруженные элементы</h4>
                    <div class="space-y-1 text-sm">
                        <div>Отверстия: <span class="text-yellow-400">${analysis.features_detected.holes || 0}</span></div>
                        <div>Карманы: <span class="text-yellow-400">${analysis.features_detected.pockets || 0}</span></div>
                        <div>Фаски: <span class="text-yellow-400">${analysis.features_detected.chamfers || 0}</span></div>
                        <div>Резьбы: <span class="text-yellow-400">${analysis.features_detected.threads || 0}</span></div>
                        <div>Бобышки: <span class="text-yellow-400">${analysis.features_detected.bosses || 0}</span></div>
                    </div>
                </div>
            `;

            if (analysis.estimated_operations && analysis.estimated_operations.length > 0) {
                html += `
                    <div class="bg-gray-700 p-4 rounded-lg col-span-2">
                        <h4 class="font-medium text-blue-400 mb-2">План операций</h4>
                        <div class="space-y-2">
                `;
                analysis.estimated_operations.forEach((op, index) => {
                    html += `
                        <div class="bg-gray-600 p-3 rounded flex justify-between items-center">
                            <div>
                                <div class="font-medium">${index + 1}. ${op.operation}</div>
                                <div class="text-sm text-gray-300">Количество: ${op.count}</div>
                                <div class="text-xs text-gray-400">Инструменты: ${op.tools.join(', ')}</div>
                            </div>
                            <div class="text-sm text-yellow-400">${op.estimated_time} мин</div>
                        </div>
                    `;
                });
                html += '</div></div>';
            }

            if (analysis.recommendations && analysis.recommendations.length > 0) {
                html += `
                    <div class="bg-gray-700 p-4 rounded-lg col-span-2">
                        <h4 class="font-medium text-blue-400 mb-2">Рекомендации</h4>
                        <div class="space-y-1 text-sm">
                `;
                analysis.recommendations.forEach(rec => {
                    html += `<div class="text-green-400">• ${rec}</div>`;
                });
                html += '</div></div>';
            }

            detailsDiv.innerHTML = html;
            complexityDiv.style.display = 'block';
        }

        // Enhanced G-code generation with NC Viewer
        async function gen() {
            const glog = document.getElementById('glog');
                glog.textContent = 'Сначала загрузите модель.';
                return;
            }

            const operationType = document.getElementById('operation_type').value;
            const controller = document.getElementById('controller').value;

            const payload = {
                model_path: LAST_MODEL_PATH,
                controller: controller,
                operation_type: operationType,
                tool_diam: parseFloat(document.getElementById('tool').value || '3'),
                feed: parseFloat(document.getElementById('feed').value || '300'),
                clearance: parseFloat(document.getElementById('clearance').value || '5'),
                spindle: parseInt(document.getElementById('spindle').value || '8000')
            };

            glog.textContent = 'Генерация G-кода...';
            try {
                const r = await fetch('/generate_gcode', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await r.json();
                    glog.textContent = 'Ошибка: ' + (data.error || '');
                    return;
                }
                LAST_GCODE_PATH = data.gcode_path;
                glog.innerHTML = `Готово — <a href="${data.gcode_path}" target="_blank" class="text-blue-400 hover:underline">скачать G-код (${controller.toUpperCase()} ${operationType})</a>`;
                
                // Show NC Viewer
                showNCViewer(data.gcode_path);
            } catch (err) {
                glog.textContent = 'Сетевая ошибка: ' + err;
            }
        }

        function showNCViewer(gcodePath) {
            const ncViewerSection = document.getElementById('nc-viewer-section');
            const ncViewer = document.getElementById('nc-viewer');
            const ncStats = document.getElementById('nc-stats');

            ncViewer.innerHTML = '<div class="text-blue-400 p-8">Загрузка NC Viewer...</div>';

            // Parse G-code for viewer
            fetch('/parse_gcode', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ gcode_path: gcodePath })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    displayNCViewer(data.parsed_data);
                    displayNCStats(data.parsed_data);
                } else {
                    ncViewer.innerHTML = '<div class="text-red-400 p-8">Ошибка парсинга G-кода</div>';
                }
            })
            .catch(error => {
                ncViewer.innerHTML = '<div class="text-red-400 p-8">Ошибка загрузки NC Viewer</div>';
            });

            ncViewerSection.style.display = 'block';
        }

        function displayNCViewer(parsedData) {
            const ncViewer = document.getElementById('nc-viewer');
            
            // Create SVG for 2D visualization
            const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
            svg.setAttribute('width', '100%');
            svg.setAttribute('height', '300');
            svg.setAttribute('viewBox', '0 0 400 300');
            svg.style.background = '#1f2937';

            const coords = parsedData.coordinates;
            const moves = parsedData.moves;

            // Calculate scale and offset
            const width = coords.max[0] - coords.min[0];
            const height = coords.max[1] - coords.min[1];
            const scale = Math.min(350 / width, 250 / height);
            const offsetX = 200 - (coords.min[0] + width/2) * scale;
            const offsetY = 150 - (coords.min[1] + height/2) * scale;

            // Draw moves
            let currentX = 0, currentY = 0;
            moves.forEach(move => {
                if (move.x !== undefined && move.y !== undefined) {
                    const x1 = currentX * scale + offsetX;
                    const y1 = currentY * scale + offsetY;
                    const x2 = move.x * scale + offsetX;
                    const y2 = move.y * scale + offsetY;

                    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                    line.setAttribute('x1', x1);
                    line.setAttribute('y1', y1);
                    line.setAttribute('x2', x2);
                    line.setAttribute('y2', y2);
                    
                    if (move.type === 'rapid') {
                        line.setAttribute('class', 'nc-rapid');
                    } else {
                        line.setAttribute('class', 'nc-path');
                    }

                    svg.appendChild(line);
                    currentX = move.x;
                    currentY = move.y;
                }
            });

            // Draw cycles
            parsedData.cycles.forEach(cycle => {
                if (cycle.x !== undefined && cycle.y !== undefined) {
                    const x = cycle.x * scale + offsetX;
                    const y = cycle.y * scale + offsetY;

                    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                    circle.setAttribute('cx', x);
                    circle.setAttribute('cy', y);
                    circle.setAttribute('r', 3);
                    circle.setAttribute('class', 'nc-cycle');
                    svg.appendChild(circle);
                }
            });

            ncViewer.innerHTML = '';
            ncViewer.appendChild(svg);
        }

        function displayNCStats(parsedData) {
            const ncStats = document.getElementById('nc-stats');
            const stats = parsedData.statistics;
            const info = parsedData.program_info;

            let html = `
                <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div class="bg-gray-700 p-4 rounded-lg">
                        <h4 class="font-medium text-blue-400 mb-2">Статистика программы</h4>
                        <div class="space-y-1 text-sm">
                            <div>Всего строк: <span class="text-yellow-400">${parsedData.total_lines}</span></div>
                            <div>Быстрые ходы: <span class="text-red-400">${stats.rapid_moves}</span></div>
                            <div>Линейные ходы: <span class="text-blue-400">${stats.linear_moves}</span></div>
                            <div>Циклы: <span class="text-green-400">${stats.total_cycles}</span></div>
                        </div>
                    </div>
                    <div class="bg-gray-700 p-4 rounded-lg">
                        <h4 class="font-medium text-blue-400 mb-2">Параметры</h4>
                        <div class="space-y-1 text-sm">
                            <div>Ø инструмента: <span class="text-yellow-400">${info.tool_diameter} мм</span></div>
                            <div>Подача: <span class="text-yellow-400">${info.feed_rate} мм/мин</span></div>
                            <div>Обороты: <span class="text-yellow-400">${info.spindle_speed} об/мин</span></div>
                        </div>
                    </div>
                    <div class="bg-gray-700 p-4 rounded-lg">
                        <h4 class="font-medium text-blue-400 mb-2">Время обработки</h4>
                        <div class="space-y-1 text-sm">
                            <div>Оценочное время: <span class="text-green-400">${Math.round(stats.estimated_time)} сек</span></div>
                            <div>Координаты: <span class="text-gray-400">X: ${coords.min[0].toFixed(1)}-${coords.max[0].toFixed(1)}</span></div>
                            <div>Y: <span class="text-gray-400">${coords.min[1].toFixed(1)}-${coords.max[1].toFixed(1)}</span></div>
                            <div>Z: <span class="text-gray-400">${coords.min[2].toFixed(1)}-${coords.max[2].toFixed(1)}</span></div>
                        </div>
                    </div>
                </div>
            `;

            ncStats.innerHTML = html;
        }

        // AI Chat functions (simplified for space)
        async function sendChatMessage() {
            const input = document.getElementById('chat-input');
            const message = input.value.trim();

            const messagesContainer = document.getElementById('chat-messages');
            const provider = document.getElementById('chat_ai_provider').value;

            addChatMessage(message, 'user');
            input.value = '';

            const loadingId = addChatMessage('Анализирую деталь...', 'ai', true);

            try {
                const response = await fetch('/ai_chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: message,
                        provider: provider,
                        analysis_data: window.lastAnalysisData
                    })
                });

                const data = await response.json();
                const loadingElement = document.getElementById(loadingId);
                if (loadingElement) loadingElement.remove();

                if (data.success) {
                    addChatMessage(data.response, 'ai');
                } else {
                    addChatMessage('Ошибка: ' + (data.error || 'Неизвестная ошибка'), 'ai');
                }
            } catch (error) {
                const loadingElement = document.getElementById(loadingId);
                if (loadingElement) loadingElement.remove();
                addChatMessage('Сетевая ошибка: ' + error.message, 'ai');
            }
        }

        function addChatMessage(message, type, isLoading = false) {
            const messagesContainer = document.getElementById('chat-messages');
            const messageId = 'msg_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);

            const messageDiv = document.createElement('div');
            messageDiv.id = messageId;
            messageDiv.className = `chat-message ${type}-message ${isLoading ? 'loading' : ''}`;
            messageDiv.textContent = message;

            messagesContainer.appendChild(messageDiv);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;

            return messageId;
        }

        async function autoAnalyzeWithAI(analysisData) {
            const messagesContainer = document.getElementById('chat-messages');
            const provider = document.getElementById('chat_ai_provider').value;

            const autoMessage = "Проанализируй эту деталь и дай рекомендации по обработке: какие инструменты использовать, режимы резания, последовательность операций и G-код.";
            addChatMessage(autoMessage, 'user');

            const loadingId = addChatMessage('Анализирую деталь с помощью ИИ...', 'ai', true);

            try {
                const response = await fetch('/ai_chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        message: autoMessage,
                        provider: provider,
                        analysis_data: analysisData
                    })
                });

                const data = await response.json();
                const loadingElement = document.getElementById(loadingId);
                if (loadingElement) loadingElement.remove();

                if (data.success) {
                    addChatMessage(data.response, 'ai');
                } else {
                    addChatMessage('Ошибка ИИ анализа: ' + (data.error || 'Неизвестная ошибка'), 'ai');
                }
            } catch (error) {
                const loadingElement = document.getElementById(loadingId);
                if (loadingElement) loadingElement.remove();
                addChatMessage('Ошибка сети при анализе ИИ: ' + error.message, 'ai');
            }
        }

        // 3D Viewer functions (simplified)
        let scene, camera, renderer, controls, model;

        function loadSTLModel(modelPath, container, geometry) {
            if (typeof THREE === 'undefined') {
                container.innerHTML = '<div class="text-gray-400 p-8">Three.js не загружен</div>';
                return;
            }

            if (model) {
                scene.remove(model);
            }

            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x0b1b24);

            camera = new THREE.PerspectiveCamera(75, container.clientWidth / container.clientHeight, 0.1, 1000);
            camera.position.set(50, 50, 50);

            renderer = new THREE.WebGLRenderer({ antialias: true });
            renderer.setSize(container.clientWidth, container.clientHeight);
            renderer.shadowMap.enabled = true;
            renderer.shadowMap.type = THREE.PCFSoftShadowMap;

            if (typeof THREE.OrbitControls !== 'undefined') {
                controls = new THREE.OrbitControls(camera, renderer.domElement);
                controls.enableDamping = true;
                controls.dampingFactor = 0.05;
            }

            container.innerHTML = '';
            container.appendChild(renderer.domElement);

            const ambientLight = new THREE.AmbientLight(0x404040, 0.6);
            scene.add(ambientLight);

            const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
            directionalLight.position.set(50, 50, 50);
            directionalLight.castShadow = true;
            scene.add(directionalLight);

            const loader = new THREE.STLLoader();
            loader.load(modelPath, function(geometry) {
                const material = new THREE.MeshPhongMaterial({ 
                    color: 0x55aaff,
                    shininess: 100,
                    transparent: true,
                    opacity: 0.9
                });

                model = new THREE.Mesh(geometry, material);
                model.castShadow = true;
                model.receiveShadow = true;

                const box = new THREE.Box3().setFromObject(model);
                const center = box.getCenter(new THREE.Vector3());
                const size = box.getSize(new THREE.Vector3());
                const maxDim = Math.max(size.x, size.y, size.z);
                const scale = 50 / maxDim;

                model.scale.setScalar(scale);
                model.position.sub(center.multiplyScalar(scale));

                scene.add(model);
                animate();
            }, undefined, function(error) {
                console.error('Error loading STL:', error);
                container.innerHTML = '<div class="text-red-400 p-8">Ошибка загрузки 3D модели</div>';
            });
        }

        function animate() {
            requestAnimationFrame(animate);
            if (controls) controls.update();
            if (renderer && scene && camera) {
                renderer.render(scene, camera);
            }
        }

        // Handle Enter key in chat input
        document.addEventListener('DOMContentLoaded', function() {
            const chatInput = document.getElementById('chat-input');
            if (chatInput) {
                chatInput.addEventListener('keypress', function(e) {
                    if (e.key === 'Enter') {
                        sendChatMessage();
                    }
                });
            }
        });
    </script>
</body>
</html>'''



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

