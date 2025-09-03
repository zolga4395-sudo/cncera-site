#!/usr/bin/env python3
"""
CNCera Enhanced - Advanced 3D Analysis & G-code Generation
Fixed version with all critical errors resolved
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
import psutil
import threading
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum
from collections import defaultdict
from datetime import datetime
from typing import Dict, Any, Optional, Tuple, List

import flask
from flask import Flask, request, jsonify, send_file, send_from_directory, render_template_string
import numpy as np
from stl import mesh
import matplotlib.pyplot as plt
from matplotlib.backends.backend_agg import FigureCanvasAgg
import io

# Import enhanced modules
from security_improvements import SecurityValidator
from error_handling import ErrorType, CNCeraError, ErrorHandler
from enhanced_gcode_generator import MaterialGroup, Material, Tool, CuttingParams, CuttingSpeedCalculator
from monitoring import SystemMetrics, ProcessingMetrics, MetricsCollector

# ---- Configuration ----
app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB

# Directories
MODELS = Path("models")
STATIC = Path("static")
TEMP = Path("temp")

# Create directories
for d in [MODELS, STATIC, TEMP]:
    d.mkdir(exist_ok=True)

# Initialize enhanced components
error_handler = ErrorHandler(logging.getLogger(__name__))
metrics_collector = MetricsCollector()

# ---- Utility Functions ----
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

def process_uploaded_file(file, units: str, linear_deflection: float, angular_deflection_deg: float, relative: bool) -> Dict:
    """Process uploaded file with enhanced error handling"""
    try:
        # Save uploaded file
        filename = file.filename
        if not SecurityValidator.validate_filename(filename):
            raise CNCeraError(ErrorType.SECURITY_ERROR, "Invalid filename", "Недопустимое имя файла")
        
        file_hash = hashlib.md5(filename.encode()).hexdigest()[:8]
        temp_path = TEMP / f"{file_hash}_{filename}"
        
        file.save(str(temp_path))
        
        # Convert STEP to STL if needed
        if filename.lower().endswith(('.step', '.stp')):
            stl_path = convert_step_to_stl(temp_path, linear_deflection, angular_deflection_deg)
        else:
            stl_path = temp_path
        
        # Analyze STL
        result = analyze_stl_file(stl_path, units, relative)
        
        # Generate preview
        preview_png = generate_preview_png(stl_path)
        preview_png_data = None
        if preview_png:
            with open(preview_png, 'rb') as f:
                preview_png_data = f"data:image/png;base64,{base64.b64encode(f.read()).decode()}"
        
        # Save results
        result_filename = f"analysis_{file_hash}.json"
        result_path = TEMP / result_filename
        with open(result_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        
        # Move STL to models directory
        model_filename = f"model_{file_hash}.stl"
        model_path = MODELS / model_filename
        shutil.move(str(stl_path), str(model_path))
        
        # Cleanup temp file
        if temp_path.exists() and temp_path != stl_path:
            temp_path.unlink()
        
        return {
            "model_path": f"/models/{model_filename}",
            "result_filename": result_filename,
            "preview_png": f"/models/{Path(preview_png).name}" if preview_png else None,
            "preview_png_data": preview_png_data,
            "file_info": {
                "filename": filename,
                "file_size": temp_path.stat().st_size if temp_path.exists() else 0,
                "file_type": "STEP" if filename.lower().endswith(('.step', '.stp')) else "STL"
            },
            "geometry": result.get("geometry"),
            "mesh_info": result.get("mesh_info")
        }
        
    except Exception as e:
        # Cleanup on error
        if 'temp_path' in locals() and temp_path.exists():
            temp_path.unlink()
        if 'stl_path' in locals() and stl_path.exists() and stl_path != temp_path:
            stl_path.unlink()
        raise

def convert_step_to_stl(step_path: Path, linear_deflection: float, angular_deflection_deg: float) -> Path:
    """Convert STEP file to STL using FreeCAD"""
    try:
        stl_path = step_path.with_suffix('.stl')
        
        # FreeCAD Python script for conversion
        script_content = f"""
import FreeCAD
import Part
import Mesh

# Load STEP file
doc = FreeCAD.newDocument()
Part.insert(unicode("{step_path}"), "part")

# Get the part
part = doc.Objects[0]

# Create mesh
mesh_obj = doc.addObject("Mesh::Feature", "mesh")
mesh_obj.Mesh = Mesh.Mesh(part.Shape, {linear_deflection}, {math.radians(angular_deflection_deg)})

# Export STL
mesh_obj.Mesh.write(unicode("{stl_path}"))

# Close document
FreeCAD.closeDocument(doc.Name)
"""
        
        script_path = TEMP / f"convert_{hashlib.md5(str(step_path).encode()).hexdigest()[:8]}.py"
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
        
        # Run FreeCAD
        result = subprocess.run([
            "FreeCADCmd", str(script_path)
        ], capture_output=True, text=True, timeout=300)
        
        # Cleanup script
        script_path.unlink()
        
        if result.returncode != 0:
            raise CNCeraError(ErrorType.PROCESSING_ERROR, "FreeCAD conversion failed", "Ошибка конвертации FreeCAD")
        
        if not stl_path.exists():
            raise CNCeraError(ErrorType.PROCESSING_ERROR, "STL file not created", "STL файл не создан")
        
        return stl_path
        
    except subprocess.TimeoutExpired:
        raise CNCeraError(ErrorType.PROCESSING_ERROR, "FreeCAD timeout", "Таймаут FreeCAD")
    except FileNotFoundError:
        raise CNCeraError(ErrorType.CONFIGURATION_ERROR, "FreeCAD not found", "FreeCAD не найден")
    except Exception as e:
        raise CNCeraError(ErrorType.PROCESSING_ERROR, f"Conversion error: {str(e)}", "Ошибка конвертации")

def analyze_stl_file(stl_path: Path, units: str, relative: bool) -> Dict:
    """Analyze STL file and return geometry information"""
    try:
        # Load STL
        stl_mesh = mesh.Mesh.from_file(str(stl_path))
        
        # Calculate bounding box
        min_coords = np.min(stl_mesh.vectors.reshape(-1, 3), axis=0)
        max_coords = np.max(stl_mesh.vectors.reshape(-1, 3), axis=0)
        
        # Calculate dimensions
        dimensions = max_coords - min_coords
        
        # Calculate volume and surface area
        volume = stl_mesh.get_mass_properties()[0]
        surface_area = np.sum([np.linalg.norm(np.cross(
            stl_mesh.vectors[i, 1] - stl_mesh.vectors[i, 0],
            stl_mesh.vectors[i, 2] - stl_mesh.vectors[i, 0]
        )) for i in range(len(stl_mesh.vectors))]) / 2
        
        # Convert units if needed
        if units == "inch":
            dimensions *= 25.4
            volume *= 25.4**3
            surface_area *= 25.4**2
        elif units == "m":
            dimensions *= 1000
            volume *= 1000**3
            surface_area *= 1000**2
        
        return {
            "geometry": {
                "dimensions": {
                    "length": float(dimensions[0]),
                    "width": float(dimensions[1]),
                    "height": float(dimensions[2])
                },
                "volume": float(volume),
                "surface_area": float(surface_area),
                "bounding_box": {
                    "min": [float(x) for x in min_coords],
                    "max": [float(x) for x in max_coords]
                }
            },
            "mesh_info": {
                "vertices": len(stl_mesh.vectors) * 3,
                "faces": len(stl_mesh.vectors)
            }
        }
        
    except Exception as e:
        raise CNCeraError(ErrorType.PROCESSING_ERROR, f"STL analysis failed: {str(e)}", "Ошибка анализа STL")

def generate_preview_png(stl_path: Path) -> Optional[Path]:
    """Generate PNG preview of STL file"""
    try:
        # Load STL
        stl_mesh = mesh.Mesh.from_file(str(stl_path))
        
        # Create figure
        fig = plt.figure(figsize=(10, 8))
        ax = fig.add_subplot(111, projection='3d')
        
        # Plot mesh
        for i in range(len(stl_mesh.vectors)):
            triangle = stl_mesh.vectors[i]
            ax.plot_trisurf(
                triangle[:, 0], triangle[:, 1], triangle[:, 2],
                color='lightblue', alpha=0.7, edgecolor='black', linewidth=0.1
            )
        
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Z')
        ax.set_title('3D Model Preview')
        
        # Save to PNG
        png_path = stl_path.with_suffix('.png')
        canvas = FigureCanvasAgg(fig)
        canvas.print_png(str(png_path))
        plt.close(fig)
        
        return png_path
        
    except Exception as e:
        logging.warning(f"Failed to generate preview: {e}")
        return None

def build_top_sampler(stl_path: Path, step: float) -> Tuple[Tuple[float, float, float, float, float, float], callable]:
    """Build top surface sampler for toolpath generation"""
    try:
        stl_mesh = mesh.Mesh.from_file(str(stl_path))
        
        # Get bounding box
        min_coords = np.min(stl_mesh.vectors.reshape(-1, 3), axis=0)
        max_coords = np.max(stl_mesh.vectors.reshape(-1, 3), axis=0)
        
        xmin, ymin, zmin = min_coords
        xmax, ymax, zmax = max_coords
        
        # Create grid
        x_coords = np.arange(xmin, xmax + step, step)
        y_coords = np.arange(ymin, ymax + step, step)
        
        # Sample top surface
        top_surface = np.full((len(y_coords), len(x_coords)), zmin)
        
        for i, y in enumerate(y_coords):
            for j, x in enumerate(x_coords):
                # Find highest Z for this (x,y)
                z_values = []
                for triangle in stl_mesh.vectors:
                    # Check if point is inside triangle
                    if point_in_triangle(x, y, triangle):
                        # Calculate Z at this point
                        z = calculate_z_at_point(x, y, triangle)
                        if z is not None:
                            z_values.append(z)
                
                if z_values:
                    top_surface[i, j] = max(z_values)
        
        def z_func(x: float, y: float) -> Optional[float]:
            if x < xmin or x > xmax or y < ymin or y > ymax:
                return None
            
            i = int((y - ymin) / step)
            j = int((x - xmin) / step)
            
            if 0 <= i < len(y_coords) and 0 <= j < len(x_coords):
                return float(top_surface[i, j])
            return None
        
        return (xmin, xmax, ymin, ymax, zmin, zmax), z_func
        
    except Exception as e:
        raise CNCeraError(ErrorType.PROCESSING_ERROR, f"Top sampler failed: {str(e)}", "Ошибка построения сэмплера")

def point_in_triangle(x: float, y: float, triangle: np.ndarray) -> bool:
    """Check if point is inside triangle"""
    p0, p1, p2 = triangle
    denom = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
    if abs(denom) < 1e-10:
        return False
    
    a = ((p1[1] - p2[1]) * (x - p2[0]) + (p2[0] - p1[0]) * (y - p2[1])) / denom
    b = ((p2[1] - p0[1]) * (x - p2[0]) + (p0[0] - p2[0]) * (y - p2[1])) / denom
    c = 1 - a - b
    
    return 0 <= a <= 1 and 0 <= b <= 1 and 0 <= c <= 1

def calculate_z_at_point(x: float, y: float, triangle: np.ndarray) -> Optional[float]:
    """Calculate Z coordinate at point (x,y) on triangle"""
    p0, p1, p2 = triangle
    
    # Calculate barycentric coordinates
    denom = (p1[1] - p2[1]) * (p0[0] - p2[0]) + (p2[0] - p1[0]) * (p0[1] - p2[1])
    if abs(denom) < 1e-10:
        return None
    
    a = ((p1[1] - p2[1]) * (x - p2[0]) + (p2[0] - p1[0]) * (y - p2[1])) / denom
    b = ((p2[1] - p0[1]) * (x - p2[0]) + (p0[0] - p2[0]) * (y - p2[1])) / denom
    c = 1 - a - b
    
    if 0 <= a <= 1 and 0 <= b <= 1 and 0 <= c <= 1:
        return a * p0[2] + b * p1[2] + c * p2[2]
    return None

def generate_ai_response(message: str, provider: str, api_key: str) -> str:
    """Generate AI response using specified provider"""
    try:
        if provider == "openai":
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-3.5-turbo",
                    "messages": [
                        {"role": "system", "content": "You are a CNC machining expert. Provide helpful, accurate information about CNC operations, G-code, and manufacturing processes."},
                        {"role": "user", "content": message}
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.7
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                raise CNCeraError(ErrorType.EXTERNAL_API_ERROR, f"OpenAI API error: {response.status_code}", "Ошибка API OpenAI")
        
        elif provider == "anthropic":
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                    "anthropic-version": "2023-06-01"
                },
                json={
                    "model": "claude-3-sonnet-20240229",
                    "max_tokens": 1000,
                    "messages": [
                        {"role": "user", "content": f"You are a CNC machining expert. {message}"}
                    ]
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()["content"][0]["text"]
            else:
                raise CNCeraError(ErrorType.EXTERNAL_API_ERROR, f"Anthropic API error: {response.status_code}", "Ошибка API Anthropic")
        
        elif provider == "xai":
            response = requests.post(
                "https://api.x.ai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "grok-beta",
                    "messages": [
                        {"role": "system", "content": "You are a CNC machining expert. Provide helpful, accurate information about CNC operations, G-code, and manufacturing processes."},
                        {"role": "user", "content": message}
                    ],
                    "max_tokens": 1000,
                    "temperature": 0.7
                },
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                raise CNCeraError(ErrorType.EXTERNAL_API_ERROR, f"xAI API error: {response.status_code}", "Ошибка API xAI")
        
        else:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Unknown provider", "Неизвестный провайдер")
            
    except requests.exceptions.Timeout:
        raise CNCeraError(ErrorType.EXTERNAL_API_ERROR, "API timeout", "Таймаут API")
    except requests.exceptions.RequestException as e:
        raise CNCeraError(ErrorType.EXTERNAL_API_ERROR, f"API request failed: {str(e)}", "Ошибка запроса API")
    except Exception as e:
        raise CNCeraError(ErrorType.EXTERNAL_API_ERROR, f"AI response generation failed: {str(e)}", "Ошибка генерации ответа ИИ")

def generate_enhanced_milling_gcode(stl_path: Path, out_path: Path, **params) -> Dict:
    """Enhanced milling G-code generation with cutting parameters calculation"""
    start_time = time.time()
    
    try:
        # Validate and sanitize parameters
        validated_params = SecurityValidator.validate_gcode_params(params)
        
        # Determine material and tool
        material_grade = params.get("material_grade", "42CrMo4")
        material_group = MaterialGroup.P  # Default to steel
        if "al" in material_grade.lower() or "6061" in material_grade:
            material_group = MaterialGroup.N
        elif "stainless" in material_grade.lower() or "316" in material_grade:
            material_group = MaterialGroup.M
        
        material = Material(group=material_group, grade=material_grade)
        tool = Tool(
            type="carbide_endmill",
            diameter=validated_params.get("tool_diam", 3.0),  # Fixed: use tool_diam instead of tool
            flutes=params.get("flutes", 2),
            corner_radius=params.get("corner_radius", 0.0)
        )
        
        # Calculate cutting parameters
        operation_type = params.get("operation_type", "milling")
        cutting_params = CuttingSpeedCalculator.calculate_milling_params(
            material, tool, "roughing" if "rough" in operation_type else "finishing"
        )
        
        controller_settings = get_controller_settings(params.get("controller", "fanuc"))
        
        (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler(stl_path, 0.1)
        
        # Apply allowances
        xmin -= params.get("allowance_x", 0)
        xmax += params.get("allowance_x", 0)
        ymin -= params.get("allowance_y", 0)
        ymax += params.get("allowance_y", 0)
        zmax += params.get("allowance_z", 0)
        
        with open(out_path, "w", encoding="ascii", errors="ignore") as f:
            w = f.write
            w(f"(Generated by CNCera - Enhanced {operation_type.title()} Operation)\n")
            w(f"(Material: {material.grade}, Tool: {tool.diameter}mm, {tool.flutes} flutes)\n")
            w(f"(Vc: {cutting_params.Vc:.1f} m/min, fz: {cutting_params.fz:.3f} mm/tooth)\n")
            w(f"(RPM: {cutting_params.rpm}, Feed: {cutting_params.feed:.1f} mm/min)\n")
            
            for cmd in controller_settings["header"]:
                w(f"{cmd}\n")
            
            if cutting_params.rpm:
                w(f"{controller_settings['spindle_on'].format(spindle=cutting_params.rpm)}\n")
            w(f"{controller_settings['coolant_on']}\n")
            
            clearance = validated_params.get("clearance", 5.0)
            w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
            
            # Enhanced milling strategy
            stepover = validated_params.get("stepover", 0.4)
            step_xy = max(0.1, tool.diameter * stepover)
            
            # Adaptive toolpath
            w("(Adaptive milling strategy)\n")
            center_x = (xmin + xmax) / 2
            center_y = (ymin + ymax) / 2
            max_radius = max(xmax - center_x, ymax - center_y)
            
            w(f"{controller_settings['rapid']} X{center_x:.3f} Y{center_y:.3f}\n")
            w(f"{controller_settings['linear']} Z{zmax:.3f} F{params.get('plunge', 120):.1f}\n")
            w(f"F{cutting_params.feed:.1f}\n")
            
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
            if cutting_params.rpm:
                w(f"{controller_settings['spindle_off']}\n")
            w(f"{controller_settings['program_end']}\n")
        
        processing_time = time.time() - start_time
        metrics_collector.record_processing(
            operation_type, 
            stl_path.stat().st_size, 
            processing_time, 
            True
        )
        
        return {
            "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "zmin": zmin, "zmax": zmax},
            "cutting_params": asdict(cutting_params),
            "material": asdict(material),
            "tool": asdict(tool),
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

def generate_chamfer_gcode(stl_path: Path, out_path: Path, **params) -> Dict:
    """Generate G-code for chamfering operations"""
    controller_settings = get_controller_settings(params.get("controller", "fanuc"))

    (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler(stl_path, 0.1)

    xmin -= params.get("allowance_x", 0)
    xmax += params.get("allowance_x", 0)
    ymin -= params.get("allowance_y", 0)
    ymax += params.get("allowance_y", 0)
    zmax += params.get("allowance_z", 0)

    with open(out_path, "w", encoding="ascii", errors="ignore") as f:
        w = f.write
        w("(Generated by CNCera - Chamfer Operation)\n")
        for cmd in controller_settings["header"]:
            w(f"{cmd}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_on'].format(spindle=params['spindle'])}\n")
        w(f"{controller_settings['coolant_on']}\n")

        clearance = params.get("clearance", 5.0)
        tool_diam = params.get("tool_diam", 3.0)

        w(f"(Chamfer around perimeter)\n")
        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")

        w(f"{controller_settings['rapid']} X{xmin:.3f} Y{ymin:.3f}\n")
        w(f"{controller_settings['linear']} Z{zmax:.3f} F{params.get('plunge', 120):.1f}\n")

        chamfer_points = [
            (xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax), (xmin, ymin)
        ]
        w(f"F{params.get('feed', 300):.1f}\n")
        for x, y in chamfer_points:
            w(f"{controller_settings['linear']} X{x:.3f} Y{y:.3f}\n")

        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
        w(f"{controller_settings['coolant_off']}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_off']}\n")
        w(f"{controller_settings['program_end']}\n")

    return {
        "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "zmin": zmin, "zmax": zmax},
        "grid": {"nx": 4, "ny": 4, "step_xy": (xmax - xmin) / 4},
        "origin": {"ox": xmin, "oy": ymin, "oz": zmin}
    }

def generate_turning_gcode(stl_path: Path, out_path: Path, **params) -> Dict:
    """Generate G-code for turning operations"""
    controller_settings = get_controller_settings(params.get("controller", "fanuc"))

    with open(out_path, "w", encoding="ascii", errors="ignore") as f:
        w = f.write
        w("(Generated by CNCera - Turning Operation)\n")
        for cmd in controller_settings["header"]:
            w(f"{cmd}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_on'].format(spindle=params['spindle'])}\n")
        w(f"{controller_settings['coolant_on']}\n")

        workpiece_dia = params.get("workpiece_diameter", 50.0)
        cut_depth = params.get("cut_depth", 1.0)
        feed_per_rev = params.get("feed_per_rev", 0.2)
        turning_type = params.get("turning_type", "roughing")
        clearance = params.get("clearance", 5.0)

        if turning_type == "facing":
            w("(Face operation)\n")
            w(f"{controller_settings['rapid']} X{workpiece_dia + clearance:.3f} Z{clearance:.3f}\n")
            w(f"{controller_settings['rapid']} Z0.5\n")
            w(f"{controller_settings['linear']} X{workpiece_dia:.3f} F{feed_per_rev:.3f}\n")
            w(f"{controller_settings['linear']} X0 Z0\n")
        else:
            w(f"(Turning - {turning_type})\n")
            current_dia = workpiece_dia
            target_dia = workpiece_dia - (cut_depth * 2)
            while current_dia > target_dia:
                w(f"{controller_settings['rapid']} X{current_dia + clearance:.3f} Z{clearance:.3f}\n")
                w(f"{controller_settings['rapid']} Z0.5\n")
                w(f"{controller_settings['linear']} X{current_dia:.3f} F{feed_per_rev:.3f}\n")
                w(f"{controller_settings['linear']} Z-50\n")
                current_dia -= cut_depth * 2

        w(f"{controller_settings['rapid']} X{workpiece_dia + clearance:.3f} Z{clearance:.3f}\n")
        w(f"{controller_settings['coolant_off']}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_off']}\n")
        w(f"{controller_settings['program_end']}\n")

    return {
        "bbox": {"xmin": 0, "xmax": workpiece_dia, "ymin": 0, "ymax": workpiece_dia, "zmin": -50, "zmax": 0},
        "grid": {"nx": 10, "ny": 10, "step_xy": workpiece_dia / 10},
        "origin": {"ox": 0, "oy": 0, "oz": 0}
    }

def generate_drilling_gcode(stl_path: Path, out_path: Path, **params) -> Dict:
    """Generate G-code for drilling operations"""
    controller_settings = get_controller_settings(params.get("controller", "fanuc"))

    (xmin, xmax, ymin, ymax, zmin, zmax), z_func = build_top_sampler(stl_path, 0.5)

    with open(out_path, "w", encoding="ascii", errors="ignore") as f:
        w = f.write
        w("(Generated by CNCera - Drilling Operation)\n")
        for cmd in controller_settings["header"]:
            w(f"{cmd}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_on'].format(spindle=params['spindle'])}\n")
        w(f"{controller_settings['coolant_on']}\n")

        drill_cycle = params.get("drill_cycle", "G81")
        drill_depth = params.get("drill_depth", 10.0)
        clearance = params.get("clearance", 5.0)
        peck_depth = params.get("peck_depth", 2.0)
        feed = params.get("feed", 300.0)

        center_x = (xmin + xmax) / 2
        center_y = (ymin + ymax) / 2

        w(f"(Drilling cycle: {drill_cycle})\n")
        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
        w(f"{controller_settings['rapid']} X{center_x:.3f} Y{center_y:.3f}\n")

        if drill_cycle == "G83":
            w(f"G83 X{center_x:.3f} Y{center_y:.3f} Z{-drill_depth:.3f} R{clearance:.3f} Q{peck_depth:.3f} F{feed:.1f}\n")
        elif drill_cycle == "G82":
            w(f"G82 X{center_x:.3f} Y{center_y:.3f} Z{-drill_depth:.3f} R{clearance:.3f} P1000 F{feed:.1f}\n")
        else:
            w(f"G81 X{center_x:.3f} Y{center_y:.3f} Z{-drill_depth:.3f} R{clearance:.3f} F{feed:.1f}\n")

        w("G80\n")
        w(f"{controller_settings['rapid']} Z{clearance:.3f}\n")
        w(f"{controller_settings['coolant_off']}\n")
        if params.get("spindle"):
            w(f"{controller_settings['spindle_off']}\n")
        w(f"{controller_settings['program_end']}\n")

    return {
        "bbox": {"xmin": xmin, "xmax": xmax, "ymin": ymin, "ymax": ymax, "zmin": zmin - drill_depth, "zmax": zmax},
        "grid": {"nx": 1, "ny": 1, "step_xy": 1},
        "origin": {"ox": center_x, "oy": center_y, "oz": zmax}
    }

# ---- HTML Template with Tailwind CSS ----
INDEX_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>CNCera — Enhanced 3D Analysis & G-code Generation</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        #viewer { min-height: 400px; }
        #log, #glog { white-space: pre-wrap; }
        .tooltip { position: relative; }
        .tooltip:hover::after {
            content: attr(data-tooltip);
            position: absolute; z-index: 10; bottom: 100%; left: 50%; transform: translateX(-50%);
            background: #1f2937; color: #e5e7eb; padding: 4px 8px; border-radius: 4px;
            font-size: 0.875rem; white-space: nowrap;
        }
    </style>
</head>
<body class="bg-gray-900 text-gray-100 font-sans p-6">
    <div class="max-w-6xl mx-auto space-y-6">
        <!-- Header with System Status -->
        <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
            <div class="flex justify-between items-center">
                <h1 class="text-2xl font-bold text-blue-400">CNCera Enhanced</h1>
                <div id="system_status" class="text-sm">
                    <span class="px-2 py-1 bg-green-600 rounded">System Healthy</span>
                </div>
            </div>
            <p class="text-gray-400 mt-2">Advanced 3D Analysis & G-code Generation with Enhanced Security & Monitoring</p>
        </div>

        <!-- File Upload Section -->
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
                    <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Линейное отклонение для сетки (мм)">LinearDeflection</label>
                    <input id="linDef" type="number" step="0.01" value="0.1" min="0.01" max="10" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Угловое отклонение (градусы)">AngularDeflection (°)</label>
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

        <!-- Analysis Results Section -->
        <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
            <h2 class="text-xl font-semibold mb-4">Результат анализа</h2>
            <div id="viewer" class="bg-gray-900 rounded-lg flex items-center justify-center"></div>
            <div id="meta" class="mt-4"></div>
            <p class="text-sm text-gray-500 mt-2">Офлайн-вьювер использует three.min.js, OrbitControls.js, STLLoader.js. Если они недоступны, отображается PNG.</p>
        </div>

        <!-- Enhanced G-code Generation Section -->
        <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
            <h2 class="text-xl font-semibold mb-4">Генерация G-кода (Enhanced)</h2>

            <!-- Controller and Operation Type Selection -->
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
                    <select id="operation_type" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100" onchange="toggleOperationSettings()">
                        <option value="milling">Фрезерная</option>
                        <option value="turning">Токарная</option>
                        <option value="drilling">Сверление</option>
                        <option value="chamfer">Фаска</option>
                        <option value="roughing">Черновая обработка</option>
                        <option value="finishing">Финишная обработка</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">G54 (начало координат)</label>
                    <select id="origin" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                        <option value="bbox_min">Нижний угол</option>
                        <option value="bbox_center">Центр низа</option>
                        <option value="bbox_top_center">Центр верха</option>
                    </select>
                </div>
            </div>

            <!-- Enhanced Material Selection -->
            <div class="mb-6">
                <h3 class="text-lg font-medium mb-3">Материал и инструмент</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Марка материала</label>
                        <select id="material_grade" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                            <option value="42CrMo4">42CrMo4 (Сталь)</option>
                            <option value="Al6061">Al6061 (Алюминий)</option>
                            <option value="316L">316L (Нержавеющая)</option>
                            <option value="GG25">GG25 (Чугун)</option>
                            <option value="Ti6Al4V">Ti6Al4V (Титан)</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Диаметр инструмента (мм)">Ø инструмента, мм</label>
                        <input id="tool" type="number" value="3" step="0.1" min="0.1" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Число зубьев</label>
                        <input id="flutes" type="number" value="2" step="1" min="1" max="8" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Радиус угла, мм</label>
                        <input id="corner_radius" type="number" value="0" step="0.1" min="0" max="5" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                </div>
            </div>

            <!-- Tool Parameters -->
            <div class="mb-6">
                <h3 class="text-lg font-medium mb-3">Параметры инструмента</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <div>
                        <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Скорость шпинделя (об/мин)">Spindle, об/мин</label>
                        <input id="spindle" type="number" value="8000" step="100" min="1000" max="24000" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Общая подача (мм/мин)">Feed, мм/мин</label>
                        <input id="feed" type="number" value="300" step="10" min="10" max="5000" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Скорость погружения (мм/мин)">Plunge, мм/мин</label>
                        <input id="plunge" type="number" value="120" step="10" min="10" max="2000" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Безопасная высота по Z (мм)">Clearance Z, мм</label>
                        <input id="clearance" type="number" value="5" step="0.5" min="1" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                </div>
            </div>

            <!-- Milling Specific Settings -->
            <div id="milling_settings" class="mb-6">
                <h3 class="text-lg font-medium mb-3">Настройки фрезерования</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <div>
                        <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Доля диаметра инструмента (0.05—0.95)">Степовер</label>
                        <input id="stepover" type="number" value="0.4" step="0.05" min="0.05" max="0.95" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Шаг по Z для черновой обработки">Stepdown Z, мм</label>
                        <input id="stepdown" type="number" value="0" step="0.5" min="0" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Ось проходов</label>
                        <select id="dir" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                            <option>X</option>
                            <option>Y</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1">Waterline</label>
                        <input id="waterline" type="checkbox" class="h-5 w-5 text-blue-600 bg-gray-700 border-gray-600 rounded">
                    </div>
                </div>
            </div>

            <!-- Allowance Settings -->
            <div class="mb-6">
                <h3 class="text-lg font-medium mb-3">Ручные припуски</h3>
                <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div>
                        <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Припуск по оси X">Припуск X, мм</label>
                        <input id="allowance_x" type="number" value="0" step="0.1" min="-10" max="10" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Припуск по оси Y">Припуск Y, мм</label>
                        <input id="allowance_y" type="number" value="0" step="0.1" min="-10" max="10" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                    <div>
                        <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Припуск по оси Z">Припуск Z, мм</label>
                        <input id="allowance_z" type="number" value="0" step="0.1" min="-10" max="10" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                    </div>
                </div>
            </div>

            <div class="flex items-center space-x-4">
                <button onclick="gen()" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition">Сгенерировать Enhanced G-код</button>
                <span id="glog" class="text-gray-400"></span>
            </div>
        </div>

        <!-- System Monitoring -->
        <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
            <h2 class="text-xl font-semibold mb-4">Мониторинг системы</h2>
            <div id="system_metrics" class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div class="bg-gray-700 p-4 rounded-lg">
                    <h3 class="text-sm text-gray-400">Всего запросов</h3>
                    <p id="total_requests" class="text-2xl font-bold text-blue-400">0</p>
                </div>
                <div class="bg-gray-700 p-4 rounded-lg">
                    <h3 class="text-sm text-gray-400">Успешность</h3>
                    <p id="success_rate" class="text-2xl font-bold text-green-400">100%</p>
                </div>
                <div class="bg-gray-700 p-4 rounded-lg">
                    <h3 class="text-sm text-gray-400">Время работы</h3>
                    <p id="uptime" class="text-2xl font-bold text-yellow-400">0s</p>
                </div>
            </div>
        </div>
    </div>

    <script>
        let LAST_MODEL_PATH = null;

        function loadScript(path) {
            return new Promise(resolve => {
                const s = document.createElement('script');
                s.src = path;
                s.onload = () => resolve(true);
                s.onerror = () => resolve(false);
                document.head.appendChild(s);
            });
        }

        function toggleOperationSettings() {
            const operationType = document.getElementById('operation_type').value;
            const millingSettings = document.getElementById('milling_settings');
            millingSettings.style.display = (operationType === 'milling' || operationType === 'roughing' || operationType === 'finishing' || operationType === 'chamfer') ? 'block' : 'none';
        }

        async function tryViewer(stlUrl) {
            const threeOk = await loadScript('https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js');
            if (!threeOk || !window.THREE) return false;

            const orbitOk = await loadScript('https://cdn.jsdelivr.net/gh/mrdoob/three.js@r128/examples/js/controls/OrbitControls.js');
            const stlOk = await loadScript('https://cdn.jsdelivr.net/gh/mrdoob/three.js@r128/examples/js/loaders/STLLoader.js');
            if (!window.THREE || !THREE.STLLoader || !THREE.OrbitControls) {
                return false;
            }

            const viewer = document.getElementById('viewer');
            viewer.innerHTML = '';
            const canvas = document.createElement('div');
            canvas.className = 'w-full h-[400px]';
            viewer.appendChild(canvas);

            const scene = new THREE.Scene();
            scene.background = new THREE.Color(0x0b1b24);
            const w = canvas.clientWidth, h = canvas.clientHeight;
            const aspect = w / h;
            const cam = new THREE.PerspectiveCamera(75, aspect, 0.1, 10000);
            cam.position.set(150, 120, 140);
            cam.lookAt(0, 0, 0);

            const renderer = new THREE.WebGLRenderer({ antialias: true });
            renderer.setSize(w, h);
            canvas.appendChild(renderer.domElement);

            const controls = new THREE.OrbitControls(cam, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.1;

            const light1 = new THREE.DirectionalLight(0xffffff, 0.8);
            light1.position.set(1, 1, 1);
            scene.add(light1);
            const light2 = new THREE.DirectionalLight(0xffffff, 0.5);
            light2.position.set(-1, -1, -1);
            scene.add(light2);
            const amb = new THREE.AmbientLight(0x88aacc, 0.3);
            scene.add(amb);

            const loader = new THREE.STLLoader();
            loader.load(stlUrl, geo => {
                const mat = new THREE.MeshPhongMaterial({ color: 0x88aaff, specular: 0x222222, shininess: 30 });
                const mesh = new THREE.Mesh(geo, mat);
                geo.computeBoundingBox();
                const bb = geo.boundingBox;

                const size = bb.getSize(new THREE.Vector3());
                const center = bb.getCenter(new THREE.Vector3());
                const maxDim = Math.max(size.x, size.y, size.z);

                mesh.position.set(-center.x, -center.y, -center.z);
                scene.add(mesh);

                const cameraDistance = maxDim * 2;
                cam.position.set(cameraDistance, cameraDistance * 0.8, cameraDistance * 0.8);
                cam.lookAt(0, 0, 0);
                controls.update();

                (function loop() {
                    requestAnimationFrame(loop);
                    controls.update();
                    renderer.render(scene, cam);
                })();
            });
            return true;
        }

        async function analyze() {
            const file = document.getElementById('file').files[0];
            const log = document.getElementById('log');
            if (!file) {
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
                if (!data.success) {
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

                const viewer = document.getElementById('viewer');
                let viewerOK = false;
                if (data.model_path) {
                    viewerOK = await tryViewer(data.model_path);
                }
                if (!viewerOK) {
                    viewer.innerHTML = data.preview_png_data
                        ? `<img src="${data.preview_png_data}" alt="preview" class="max-w-full max-h-full object-contain rounded-lg">`
                        : data.preview_png
                        ? `<img src="${data.preview_png}" alt="preview" class="max-w-full max-h-full object-contain rounded-lg">`
                        : '<div class="text-gray-400 p-8">PNG предпросмотр недоступен</div>';
                }

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
            } catch (err) {
                log.textContent = 'Сетевая ошибка: ' + err;
            }
        }

        async function gen() {
            const glog = document.getElementById('glog');
            if (!LAST_MODEL_PATH) {
                glog.textContent = 'Сначала загрузите модель.';
                return;
            }

            const operationType = document.getElementById('operation_type').value;
            const controller = document.getElementById('controller').value;

            const payload = {
                model_path: LAST_MODEL_PATH,
                controller: controller,
                operation_type: operationType,
                material_grade: document.getElementById('material_grade').value,
                tool_diam: parseFloat(document.getElementById('tool').value || '3'),  // Fixed: use tool_diam
                flutes: parseInt(document.getElementById('flutes').value || '2'),
                corner_radius: parseFloat(document.getElementById('corner_radius').value || '0'),
                feed: parseFloat(document.getElementById('feed').value || '300'),
                plunge: parseFloat(document.getElementById('plunge').value || '120'),
                clearance: parseFloat(document.getElementById('clearance').value || '5'),
                spindle: parseInt(document.getElementById('spindle').value || '8000'),
                origin: document.getElementById('origin').value || 'bbox_min',
                allowance_x: parseFloat(document.getElementById('allowance_x').value || '0'),
                allowance_y: parseFloat(document.getElementById('allowance_y').value || '0'),
                allowance_z: parseFloat(document.getElementById('allowance_z').value || '0')
            };

            if (operationType === 'milling' || operationType === 'roughing' || operationType === 'finishing' || operationType === 'chamfer') {
                payload.stepover = parseFloat(document.getElementById('stepover').value || '0.4');
                payload.stepdown = parseFloat(document.getElementById('stepdown').value || '0');
                payload.dir = document.getElementById('dir').value || 'X';
                payload.waterline = document.getElementById('waterline').checked;
            }

            glog.textContent = 'Генерация Enhanced G-кода...';
            try {
                const r = await fetch('/generate_gcode', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await r.json();
                if (!data.success) {
                    glog.textContent = 'Ошибка: ' + (data.error || '');
                    return;
                }
                glog.innerHTML = `Готово — <a href="${data.gcode_path}" target="_blank" class="text-blue-400 hover:underline">скачать Enhanced G-код (${controller.toUpperCase()} ${operationType})</a>`;
            } catch (err) {
                glog.textContent = 'Сетевая ошибка: ' + err;
            }
        }

        // Update system metrics
        async function updateMetrics() {
            try {
                const r = await fetch('/metrics');
                const data = await r.json();
                if (data.success) {
                    document.getElementById('total_requests').textContent = data.total_requests || 0;
                    document.getElementById('success_rate').textContent = (data.success_rate || 100).toFixed(1) + '%';
                    document.getElementById('uptime').textContent = Math.floor((data.uptime_seconds || 0) / 60) + 'm';
                }
            } catch (e) {
                console.log('Metrics update failed:', e);
            }
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', function() {
            toggleOperationSettings();
            updateMetrics();
            setInterval(updateMetrics, 30000); // Update every 30 seconds
        });
    </script>
</body>
</html>
"""

# ---- Routes ----
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
        # Collect current system metrics
        current_metrics = metrics_collector.collect_system_metrics()
        
        # Check system health
        health_status = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "system_metrics": asdict(current_metrics) if current_metrics else None,
            "uptime_seconds": (datetime.now() - metrics_collector.start_time).total_seconds()
        }
        
        # Check for issues
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
        
        # Validate filename
        if not SecurityValidator.validate_filename(file.filename):
            raise CNCeraError(ErrorType.SECURITY_ERROR, "Invalid filename", "Недопустимое имя файла")
        
        # Get parameters with validation
        units = request.form.get("units", "auto")
        linear_deflection = float(request.form.get("linear_deflection", "0.1"))
        angular_deflection_deg = float(request.form.get("angular_deflection_deg", "15"))
        relative = request.form.get("relative", "false").lower() == "true"
        
        # Validate parameters
        if linear_deflection <= 0 or linear_deflection > 10:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Invalid linear deflection", "Недопустимое линейное отклонение")
        if angular_deflection_deg <= 0 or angular_deflection_deg > 89:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Invalid angular deflection", "Недопустимое угловое отклонение")
        
        # Check file size
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning
        
        if file_size > 100 * 1024 * 1024:  # 100MB limit
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "File too large", "Файл слишком большой (макс. 100 МБ)")
        
        # Process file
        result = process_uploaded_file(
            file, units, linear_deflection, angular_deflection_deg, relative
        )
        
        processing_time = time.time() - start_time
        metrics_collector.record_processing(
            "file_upload", 
            file_size, 
            processing_time, 
            True
        )
        
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
                request.files["file"].seek(0, 2)
                file_size = request.files["file"].tell()
                request.files["file"].seek(0)
            except:
                pass
        
        metrics_collector.record_processing(
            "file_upload", 
            file_size, 
            processing_time, 
            False,
            e.error_type.value
        )
        
        return jsonify({"success": False, "error": e.user_message}), 400
        
    except Exception as e:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(e, "File upload")
        
        file_size = 0
        if "file" in request.files and request.files["file"]:
            try:
                request.files["file"].seek(0, 2)
                file_size = request.files["file"].tell()
                request.files["file"].seek(0)
            except:
                pass
        
        metrics_collector.record_processing(
            "file_upload", 
            file_size, 
            processing_time, 
            False,
            error.error_type.value
        )
        
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
        
        # Validate model path
        if not SecurityValidator.validate_filename(Path(model_path).name):
            raise CNCeraError(ErrorType.SECURITY_ERROR, "Invalid model path", "Недопустимый путь к модели")
        
        model_file = Path(model_path)
        if not model_file.exists():
            raise CNCeraError(ErrorType.FILE_ERROR, "Model file not found", "Файл модели не найден")
        
        # Validate and sanitize parameters
        validated_params = SecurityValidator.validate_gcode_params(data)
        
        # Generate G-code based on operation type
        operation_type = validated_params.get("operation_type", "milling")
        
        # Create output filename
        controller = validated_params.get("controller", "fanuc")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_filename = f"{operation_type}_{controller}_{timestamp}.nc"
        output_path = MODELS / output_filename
        
        # Generate G-code
        if operation_type in ["milling", "roughing", "finishing"]:
            result = generate_enhanced_milling_gcode(model_file, output_path, **validated_params)
        elif operation_type == "turning":
            result = generate_turning_gcode(model_file, output_path, **validated_params)
        elif operation_type == "drilling":
            result = generate_drilling_gcode(model_file, output_path, **validated_params)
        elif operation_type == "chamfer":
            result = generate_chamfer_gcode(model_file, output_path, **validated_params)
        else:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Unknown operation type", "Неизвестный тип операции")
        
        processing_time = time.time() - start_time
        metrics_collector.record_processing(
            f"gcode_{operation_type}", 
            model_file.stat().st_size, 
            processing_time, 
            True
        )
        
        return jsonify({
            "success": True,
            "gcode_path": f"/models/{output_filename}",
            "bbox": result.get("bbox"),
            "cutting_params": result.get("cutting_params"),
            "material": result.get("material"),
            "tool": result.get("tool"),
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
        
        metrics_collector.record_processing(
            f"gcode_{data.get('operation_type', 'unknown')}", 
            model_size, 
            processing_time, 
            False,
            e.error_type.value
        )
        
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
        
        metrics_collector.record_processing(
            f"gcode_{data.get('operation_type', 'unknown')}", 
            model_size, 
            processing_time, 
            False,
            error.error_type.value
        )
        
        return jsonify({"success": False, "error": error.user_message}), 500

@app.route("/download_gcode")
def download_gcode():
    """Download generated G-code file"""
    filename = request.args.get("filename", "")
    if not filename:
        return "Filename required", 400
    
    # Validate filename
    if not SecurityValidator.validate_filename(filename):
        return "Invalid filename", 400
    
    file_path = MODELS / filename
    if not file_path.exists():
        return "File not found", 404
    
    return send_file(
        str(file_path), 
        as_attachment=True, 
        mimetype="text/plain",
        download_name=filename
    )

@app.route("/gcode_preview")
def gcode_preview():
    """Preview G-code content - JSON API version"""
    name = request.args.get("name", "")
    if not name:
        return jsonify({"success": False, "error": "Name parameter required"}), 400
    
    # Validate filename
    if not SecurityValidator.validate_filename(name):
        return jsonify({"success": False, "error": "Invalid filename"}), 400
    
    file_path = MODELS / name
    if not file_path.exists():
        return jsonify({"success": False, "error": "File not found"}), 404
    
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        
        # Get first 40 lines
        lines = content.split('\n')
        preview_lines = lines[:40]
        
        return jsonify({
            "success": True,
            "lines": preview_lines,
            "total_lines": len(lines),
            "showing": len(preview_lines)
        })
        
    except Exception as e:
        error = error_handler.handle_exception(e, "G-code preview")
        return jsonify({"success": False, "error": error.user_message}), 500

@app.route("/chat", methods=["POST"])
def chat():
    """AI chat endpoint with enhanced error handling"""
    start_time = time.time()
    
    try:
        data = request.get_json()
        if not data:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "No JSON data", "Данные не получены")
        
        message = data.get("message", "").strip()
        if not message:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Empty message", "Сообщение пустое")
        
        # Validate message length
        if len(message) > 10000:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Message too long", "Сообщение слишком длинное")
        
        # Validate message content (basic security check)
        if not re.match(r'^[a-zA-Z0-9\s\.,!?\-_()\[\]{}:;"\'@#$%^&*+=<>/\\|`~а-яА-ЯёЁ]+$', message):
            raise CNCeraError(ErrorType.SECURITY_ERROR, "Invalid characters in message", "Недопустимые символы в сообщении")
        
        provider = data.get("provider", "openai").lower()
        if provider not in ["openai", "anthropic", "xai"]:
            raise CNCeraError(ErrorType.VALIDATION_ERROR, "Invalid provider", "Недопустимый провайдер")
        
        # Get API key from environment
        api_key = None
        if provider == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
        elif provider == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
        elif provider == "xai":
            api_key = os.getenv("XAI_API_KEY")
        
        if not api_key:
            raise CNCeraError(ErrorType.CONFIGURATION_ERROR, "API key not configured", "API ключ не настроен")
        
        # Generate response
        response = generate_ai_response(message, provider, api_key)
        
        processing_time = time.time() - start_time
        metrics_collector.record_processing(
            f"chat_{provider}", 
            len(message), 
            processing_time, 
            True
        )
        
        return jsonify({
            "success": True,
            "response": response,
            "provider": provider,
            "processing_time": processing_time
        })
        
    except CNCeraError as e:
        processing_time = time.time() - start_time
        message_length = len(data.get("message", "")) if data else 0
        
        metrics_collector.record_processing(
            f"chat_{data.get('provider', 'unknown')}", 
            message_length, 
            processing_time, 
            False,
            e.error_type.value
        )
        
        return jsonify({"success": False, "error": e.user_message}), 400
        
    except Exception as e:
        processing_time = time.time() - start_time
        error = error_handler.handle_exception(e, "AI chat")
        
        message_length = len(data.get("message", "")) if data else 0
        
        metrics_collector.record_processing(
            f"chat_{data.get('provider', 'unknown')}", 
            message_length, 
            processing_time, 
            False,
            error.error_type.value
        )
        
        return jsonify({"success": False, "error": error.user_message}), 500

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

# ---- Main execution ----
if __name__ == "__main__":
    # Initialize logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('cncera.log'),
            logging.StreamHandler()
        ]
    )
    
    logger = logging.getLogger(__name__)
    logger.info("Starting CNCera Enhanced Application")
    
    # Log system information
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Flask version: {flask.__version__}")
    logger.info(f"Working directory: {os.getcwd()}")
    logger.info(f"Models directory: {MODELS}")
    logger.info(f"Static directory: {STATIC}")
    logger.info(f"Temp directory: {TEMP}")
    
    # Check FreeCAD availability
    try:
        result = subprocess.run(["FreeCADCmd", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            logger.info("FreeCAD is available")
        else:
            logger.warning("FreeCAD may not be properly installed")
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.warning("FreeCAD not found - STEP file conversion will not work")
    
    # Start metrics collection in background
    def collect_metrics_background():
        while True:
            try:
                metrics_collector.collect_system_metrics()
                time.sleep(30)  # Collect every 30 seconds
            except Exception as e:
                logger.error(f"Error collecting metrics: {e}")
                time.sleep(60)  # Wait longer on error
    
    metrics_thread = threading.Thread(target=collect_metrics_background, daemon=True)
    metrics_thread.start()
    
    # Start the application
    try:
        app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
    except KeyboardInterrupt:
        logger.info("Application stopped by user")
    except Exception as e:
        error = error_handler.handle_exception(e, "Application startup")
        logger.error(f"Failed to start application: {error.user_message}")
        sys.exit(1)