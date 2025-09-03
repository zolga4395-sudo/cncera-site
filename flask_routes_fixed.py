#!/usr/bin/env python3
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