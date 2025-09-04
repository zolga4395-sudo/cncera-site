// Enhanced CNCera Frontend with AI Analysis and Tool Selection
let LAST_MODEL_PATH = null;
let LAST_GCODE = null;
let CURRENT_GEOMETRY = null;
let CURRENT_BBOX = null;

// Load tools on page load
document.addEventListener('DOMContentLoaded', function() {
    loadTools();
    toggleOperationSettings();
});

// Load tools from API
async function loadTools() {
    try {
        const response = await fetch('/tools');
        const data = await response.json();
        const toolSelect = document.getElementById('tool_select');
        
        // Clear existing options except first
        toolSelect.innerHTML = '<option value="">Выберите инструмент</option>';
        
        data.tools.forEach(tool => {
            const option = document.createElement('option');
            option.value = tool.id;
            option.textContent = `${tool.name} (${tool.diam_mm}mm)`;
            option.dataset.tool = JSON.stringify(tool);
            toolSelect.appendChild(option);
        });
    } catch (error) {
        console.warn('Failed to load tools:', error);
    }
}

// Load tool defaults when tool is selected
function loadToolDefaults() {
    const toolSelect = document.getElementById('tool_select');
    const selectedOption = toolSelect.options[toolSelect.selectedIndex];
    
    if (selectedOption && selectedOption.dataset.tool) {
        const tool = JSON.parse(selectedOption.dataset.tool);
        
        // Prefill tool parameters
        document.getElementById('tool').value = tool.diam_mm;
        document.getElementById('spindle').value = Math.min(tool.max_rpm, 8000);
        document.getElementById('feed').value = Math.min(tool.max_feed * 0.5, 3000);
        document.getElementById('plunge').value = Math.min(tool.max_feed * 0.3, 1200);
        
        // Update stepover based on tool diameter
        const stepover = Math.min(tool.diam_mm * 0.4, 0.95);
        document.getElementById('stepover').value = stepover;
    }
}

function toggleOperationSettings() {
    const operationType = document.getElementById('operation_type').value;
    const millingSettings = document.getElementById('milling_settings');
    const turningSettings = document.getElementById('turning_settings');
    const drillingSettings = document.getElementById('drilling_settings');

    // Hide all settings
    if (millingSettings) millingSettings.style.display = 'none';
    if (turningSettings) turningSettings.style.display = 'none';
    if (drillingSettings) drillingSettings.style.display = 'none';

    // Show relevant settings
    switch(operationType) {
        case 'milling':
        case 'roughing':
        case 'finishing':
        case 'chamfer':
            if (millingSettings) millingSettings.style.display = 'block';
            break;
        case 'turning':
            if (turningSettings) turningSettings.style.display = 'block';
            break;
        case 'drilling':
            if (drillingSettings) drillingSettings.style.display = 'block';
            break;
    }
}

// Enhanced 3D viewer with Three.js
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
    controls.minPolarAngle = 0;
    controls.maxPolarAngle = Math.PI;
    controls.minAzimuthAngle = -Infinity;
    controls.maxAzimuthAngle = Infinity;
    controls.enablePan = true;
    controls.enableZoom = true;
    controls.enableRotate = true;

    // Lighting
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
        const mat = new THREE.MeshPhongMaterial({ 
            color: 0x88aaff, 
            specular: 0x222222, 
            shininess: 30 
        });
        const mesh = new THREE.Mesh(geo, mat);
        geo.computeBoundingBox();
        const bb = geo.boundingBox;

        const size = bb.getSize(new THREE.Vector3());
        const center = bb.getCenter(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);

        mesh.position.set(-center.x, -center.y, -center.z);
        scene.add(mesh);

        // Add coordinate axes
        const axisLength = maxDim * 0.3;
        const axisOffset = size.z / 2 + axisLength * 0.1;

        // X axis (red)
        const xGeometry = new THREE.CylinderGeometry(axisLength * 0.01, axisLength * 0.01, axisLength, 8);
        const xMaterial = new THREE.MeshBasicMaterial({ color: 0xff0000 });
        const xAxis = new THREE.Mesh(xGeometry, xMaterial);
        xAxis.rotation.z = -Math.PI / 2;
        xAxis.position.set(axisLength / 2, 0, axisOffset);
        scene.add(xAxis);
        const xArrowGeometry = new THREE.ConeGeometry(axisLength * 0.03, axisLength * 0.1, 8);
        const xArrow = new THREE.Mesh(xArrowGeometry, xMaterial);
        xArrow.rotation.z = -Math.PI / 2;
        xArrow.position.set(axisLength, 0, axisOffset);
        scene.add(xArrow);

        // Y axis (green)
        const yGeometry = new THREE.CylinderGeometry(axisLength * 0.01, axisLength * 0.01, axisLength, 8);
        const yMaterial = new THREE.MeshBasicMaterial({ color: 0x00ff00 });
        const yAxis = new THREE.Mesh(yGeometry, yMaterial);
        yAxis.position.set(0, axisLength / 2, axisOffset);
        scene.add(yAxis);
        const yArrowGeometry = new THREE.ConeGeometry(axisLength * 0.03, axisLength * 0.1, 8);
        const yArrow = new THREE.Mesh(yArrowGeometry, yMaterial);
        yArrow.position.set(0, axisLength, axisOffset);
        scene.add(yArrow);

        // Z axis (blue)
        const zGeometry = new THREE.CylinderGeometry(axisLength * 0.01, axisLength * 0.01, axisLength, 8);
        const zMaterial = new THREE.MeshBasicMaterial({ color: 0x0000ff });
        const zAxis = new THREE.Mesh(zGeometry, zMaterial);
        zAxis.rotation.x = Math.PI / 2;
        zAxis.position.set(0, 0, axisOffset + axisLength / 2);
        scene.add(zAxis);
        const zArrowGeometry = new THREE.ConeGeometry(axisLength * 0.03, axisLength * 0.1, 8);
        const zArrow = new THREE.Mesh(zArrowGeometry, zMaterial);
        zArrow.rotation.x = Math.PI / 2;
        zArrow.position.set(0, 0, axisOffset + axisLength);
        scene.add(zArrow);

        // Origin point (yellow)
        const originGeometry = new THREE.SphereGeometry(axisLength * 0.04, 16, 16);
        const originMaterial = new THREE.MeshBasicMaterial({ color: 0xffff00 });
        const originPoint = new THREE.Mesh(originGeometry, originMaterial);
        originPoint.position.set(0, 0, axisOffset);
        scene.add(originPoint);

        const cameraDistance = maxDim * 2;
        cam.position.set(cameraDistance, cameraDistance * 0.8, cameraDistance * 0.8);
        cam.lookAt(0, 0, 0);
        controls.update();

        // Animation loop
        (function loop() {
            requestAnimationFrame(loop);
            controls.update();
            renderer.render(scene, cam);
        })();
    });
    return true;
}

function loadScript(path) {
    return new Promise(resolve => {
        const s = document.createElement('script');
        s.src = path;
        s.onload = () => resolve(true);
        s.onerror = () => resolve(false);
        document.head.appendChild(s);
    });
}

// Enhanced analyze function with AI analysis panel
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
        CURRENT_GEOMETRY = data.geometry;
        CURRENT_BBOX = data.bbox;
        
        const links = [];
        if (data.model_path) {
            links.push(`<a href="${data.model_path}" target="_blank" class="text-blue-400 hover:underline">Скачать STL</a>`);
        }
        if (data.result_filename) {
            links.push(`<a href="/download_results?filename=${data.result_filename}" target="_blank" class="text-blue-400 hover:underline">JSON-результат</a>`);
        }
        log.innerHTML = 'Готово — ' + links.join(' · ');

        // Show AI analysis panel
        const aiPanel = document.getElementById('ai-analysis');
        if (aiPanel) {
            aiPanel.style.display = 'block';
        }

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

        // Display analysis summary
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

// AI Model Inspection
async function aiInspectModel() {
    if (!CURRENT_GEOMETRY || !CURRENT_BBOX) {
        alert('Сначала загрузите модель');
        return;
    }
    
    const aiFindings = document.getElementById('ai-findings');
    aiFindings.innerHTML = '<div class="text-gray-600">Анализ модели...</div>';
    
    try {
        const response = await fetch('/ai/inspect_model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                geometry: CURRENT_GEOMETRY,
                bbox: CURRENT_BBOX,
                units: 'mm',
                controller: document.getElementById('controller').value,
                operation_type: document.getElementById('operation_type').value,
                tool: {
                    diameter: parseFloat(document.getElementById('tool').value),
                    type: 'endmill'
                }
            })
        });
        
        const data = await response.json();
        if (data.success) {
            let html = '<div class="space-y-3">';
            if (data.findings) {
                html += '<h4 class="font-medium text-gray-800">Находки:</h4>';
                if (data.findings.zmin !== undefined) html += `<p>Z min: ${data.findings.zmin} мм</p>`;
                if (data.findings.zmax !== undefined) html += `<p>Z max: ${data.findings.zmax} мм</p>`;
                if (data.findings.thickness !== undefined) html += `<p>Толщина: ${data.findings.thickness} мм</p>`;
                if (data.findings.flatness !== undefined) html += `<p>Плоскостность: ${data.findings.flatness}</p>`;
            }
            if (data.suggestions) {
                html += '<h4 class="font-medium text-gray-800 mt-4">Рекомендации:</h4>';
                if (data.suggestions.origin) html += `<p>Начало координат: ${data.suggestions.origin}</p>`;
                if (data.suggestions.stepover) html += `<p>Степовер: ${data.suggestions.stepover}</p>`;
                if (data.suggestions.stepdown) html += `<p>Шаг по Z: ${data.suggestions.stepdown} мм</p>`;
                if (data.suggestions.feeds_speeds) html += `<p>Подачи/скорости: ${data.suggestions.feeds_speeds}</p>`;
                if (data.suggestions.clamps) html += `<p>Крепление: ${data.suggestions.clamps}</p>`;
            }
            html += '</div>';
            aiFindings.innerHTML = html;
        } else {
            aiFindings.innerHTML = `<div class="text-red-600">Ошибка: ${data.error}</div>`;
        }
    } catch (error) {
        aiFindings.innerHTML = `<div class="text-red-600">Ошибка сети: ${error.message}</div>`;
    }
}

// AI G-code Analysis
async function aiAnalyzeGcode() {
    if (!LAST_GCODE) {
        alert('Сначала сгенерируйте G-код');
        return;
    }
    
    const aiFindings = document.getElementById('ai-findings');
    aiFindings.innerHTML = '<div class="text-gray-600">Анализ G-кода...</div>';
    
    try {
        const response = await fetch('/ai/analyze_gcode', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                gcode: LAST_GCODE,
                controller: document.getElementById('controller').value,
                material: 'aluminum_6061',
                tool: document.getElementById('tool_select').value
            })
        });
        
        const data = await response.json();
        if (data.success) {
            let html = '<div class="space-y-3">';
            if (data.summary) {
                html += `<h4 class="font-medium text-gray-800">Сводка:</h4><p>${data.summary}</p>`;
            }
            if (data.risks && data.risks.length > 0) {
                html += '<h4 class="font-medium text-gray-800 mt-4">Риски:</h4><ul class="list-disc list-inside">';
                data.risks.forEach(risk => html += `<li>${risk}</li>`);
                html += '</ul>';
            }
            if (data.suggestions && data.suggestions.length > 0) {
                html += '<h4 class="font-medium text-gray-800 mt-4">Предложения:</h4><ul class="list-disc list-inside">';
                data.suggestions.forEach(suggestion => html += `<li>${suggestion}</li>`);
                html += '</ul>';
            }
            if (data.linter) {
                html += '<h4 class="font-medium text-gray-800 mt-4">Линтер:</h4>';
                html += `<p>Ошибок: ${data.linter.errors_count}, Предупреждений: ${data.linter.warnings_count}</p>`;
            }
            html += '</div>';
            aiFindings.innerHTML = html;
        } else {
            aiFindings.innerHTML = `<div class="text-red-600">Ошибка: ${data.error}</div>`;
        }
    } catch (error) {
        aiFindings.innerHTML = `<div class="text-red-600">Ошибка сети: ${error.message}</div>`;
    }
}

// Enhanced G-code generation with preview
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
        tool: parseFloat(document.getElementById('tool').value || '3'),
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
        payload.waterline_dz = parseFloat(document.getElementById('waterline_dz').value || '0');
        payload.finish_stepover = parseFloat(document.getElementById('finish_stepover').value || '0.3');
    }

    glog.textContent = 'Генерация...';
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
        
        LAST_GCODE = data.gcode_content;
        glog.innerHTML = `Готово — <a href="${data.gcode_path}" target="_blank" class="text-blue-400 hover:underline">скачать G-код (${controller.toUpperCase()} ${operationType})</a>`;
        
        // Show G-code preview
        showGcodePreview(data.gcode_content, data.validation);
    } catch (err) {
        glog.textContent = 'Сетевая ошибка: ' + err;
    }
}

// Show G-code preview with NC Viewer
function showGcodePreview(gcode, validation) {
    const previewSection = document.getElementById('gcode-preview');
    const ncviewer = document.getElementById('ncviewer');
    const gcodeContent = document.getElementById('gcode-content');
    
    if (previewSection) {
        previewSection.style.display = 'block';
    }
    
    // Show G-code content
    if (gcodeContent) {
        let html = '<h3 class="text-lg font-medium mb-2">G-код:</h3>';
        html += '<pre class="bg-gray-900 text-gray-100 p-4 rounded overflow-auto max-h-64">';
        html += gcode;
        html += '</pre>';
        
        if (validation) {
            html += '<h3 class="text-lg font-medium mb-2 mt-4">Валидация:</h3>';
            html += `<p>Ошибок: ${validation.errors_count}, Предупреждений: ${validation.warnings_count}</p>`;
            if (validation.issues && validation.issues.length > 0) {
                html += '<ul class="list-disc list-inside mt-2">';
                validation.issues.slice(0, 10).forEach(issue => {
                    const color = issue.severity === 'error' ? 'text-red-400' : 'text-yellow-400';
                    html += `<li class="${color}">Строка ${issue.line}: ${issue.message}</li>`;
                });
                html += '</ul>';
            }
        }
        
        gcodeContent.innerHTML = html;
    }
    
    // Initialize NC Viewer if available
    if (window.renderGcode) {
        try {
            window.renderGcode(gcode);
        } catch (error) {
            console.warn('NC Viewer failed to load:', error);
        }
    } else if (window.NCViewer && ncviewer) {
        try {
            const viewer = new NCViewer(ncviewer);
            viewer.loadGcode(gcode);
        } catch (error) {
            console.warn('NC Viewer failed to load:', error);
        }
    }
}