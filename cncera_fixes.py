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
        }