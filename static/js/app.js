/**
 * CNCera App - Main UI Logic
 */

(function() {
    'use strict';
    
    const state = {
        lastModelPath: null,
        lastGcode: null,
        lastAnalysis: null,
        isAnalyzing: false,
        isGenerating: false
    };
    
    let elements = {};
    
    function init() {
        try {
            cacheElements();
            setupEventListeners();
            loadToolDefaults();
            console.log('CNCera App initialized');
        } catch (error) {
            console.error('App initialization failed:', error);
        }
    }
    
    function cacheElements() {
        elements = {
            fileInput: document.getElementById('file'),
            unitsSelect: document.getElementById('units'),
            linDefInput: document.getElementById('linDef'),
            angDefInput: document.getElementById('angDef'),
            relCheckbox: document.getElementById('rel'),
            analyzeBtn: document.getElementById('analyzeBtn'),
            logArea: document.getElementById('log'),
            viewer: document.getElementById('viewer'),
            meta: document.getElementById('meta'),
            controllerSelect: document.getElementById('controller'),
            operationTypeSelect: document.getElementById('operation_type'),
            originSelect: document.getElementById('origin'),
            toolInput: document.getElementById('tool'),
            spindleInput: document.getElementById('spindle'),
            feedInput: document.getElementById('feed'),
            plungeInput: document.getElementById('plunge'),
            clearanceInput: document.getElementById('clearance'),
            stepoverInput: document.getElementById('stepover'),
            stepdownInput: document.getElementById('stepdown'),
            dirSelect: document.getElementById('dir'),
            waterlineCheckbox: document.getElementById('waterline'),
            waterlineDzInput: document.getElementById('waterline_dz'),
            finishStepoverInput: document.getElementById('finish_stepover'),
            allowanceXInput: document.getElementById('allowance_x'),
            allowanceYInput: document.getElementById('allowance_y'),
            allowanceZInput: document.getElementById('allowance_z'),
            generateBtn: document.getElementById('generateBtn'),
            glogArea: document.getElementById('glog'),
            toolSelect: document.getElementById('toolSelect'),
            aiInspectBtn: document.getElementById('aiInspectBtn'),
            aiAnalyzeBtn: document.getElementById('aiAnalyzeBtn'),
            aiResults: document.getElementById('aiResults'),
            gcodePreview: document.getElementById('gcode-preview'),
            gcodeContent: document.getElementById('gcode-content'),
            previewBtn: document.getElementById('previewBtn'),
            millingSettings: document.getElementById('milling_settings'),
            turningSettings: document.getElementById('turning_settings'),
            drillingSettings: document.getElementById('drilling_settings')
        };
    }
    
    function setupEventListeners() {
        if (elements.analyzeBtn) {
            elements.analyzeBtn.addEventListener('click', handleAnalyze);
        }
        if (elements.generateBtn) {
            elements.generateBtn.addEventListener('click', handleGenerate);
        }
        if (elements.toolSelect) {
            elements.toolSelect.addEventListener('change', handleToolSelect);
        }
        if (elements.operationTypeSelect) {
            elements.operationTypeSelect.addEventListener('change', handleOperationTypeChange);
        }
        if (elements.aiInspectBtn) {
            elements.aiInspectBtn.addEventListener('click', handleAIInspect);
        }
        if (elements.aiAnalyzeBtn) {
            elements.aiAnalyzeBtn.addEventListener('click', handleAIAnalyze);
        }
        if (elements.previewBtn) {
            elements.previewBtn.addEventListener('click', handlePreview);
        }
        if (elements.fileInput) {
            elements.fileInput.addEventListener('change', handleFileSelect);
        }
    }
    
    async function handleAnalyze() {
        if (state.isAnalyzing) return;
        
        const file = elements.fileInput?.files[0];
        if (!file) {
            showLog('Выберите файл для анализа');
            return;
        }
        
        if (file.size > 100 * 1024 * 1024) {
            showLog('Файл слишком большой (макс. 100 МБ)');
            return;
        }
        
        state.isAnalyzing = true;
        updateAnalyzeButton(true);
        showLog('Анализ файла...');
        
        try {
            const formData = new FormData();
            formData.append('file', file);
            formData.append('units', elements.unitsSelect?.value || 'auto');
            formData.append('linear_deflection', elements.linDefInput?.value || '0.1');
            formData.append('angular_deflection_deg', elements.angDefInput?.value || '15');
            formData.append('relative', elements.relCheckbox?.checked ? 'true' : 'false');
            
            const response = await fetch('/upload', {
                method: 'POST',
                body: formData
            });
            
            const data = await response.json();
            
            if (!data.success) {
                showLog('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
                return;
            }
            
            state.lastModelPath = data.model_path;
            state.lastAnalysis = data;
            
            renderAnalysis(data);
            
            const links = [];
            if (data.model_path) {
                links.push(`<a href="${data.model_path}" target="_blank" class="link">Скачать STL</a>`);
            }
            if (data.result_filename) {
                links.push(`<a href="/download_results?filename=${data.result_filename}" target="_blank" class="link">JSON-результат</a>`);
            }
            
            showLog('Анализ завершен — ' + links.join(' · '));
            
        } catch (error) {
            console.error('Analysis failed:', error);
            showLog('Ошибка анализа: ' + error.message);
        } finally {
            state.isAnalyzing = false;
            updateAnalyzeButton(false);
        }
    }
    
    async function handleGenerate() {
        if (state.isGenerating) return;
        
        if (!state.lastModelPath) {
            showGlog('Сначала загрузите модель');
            return;
        }
        
        state.isGenerating = true;
        updateGenerateButton(true);
        showGlog('Генерация G-кода...');
        
        try {
            const payload = buildGenerationPayload();
            
            const response = await fetch('/generate_gcode', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            const data = await response.json();
            
            if (!data.success) {
                showGlog('Ошибка: ' + (data.error || 'Неизвестная ошибка'));
                return;
            }
            
            state.lastGcode = data.gcode_content;
            
            renderGcodeContent(data.gcode_content);
            
            showGlog(`Готово — <a href="${data.gcode_path}" target="_blank" class="link">скачать G-код</a>`);
            
            if (elements.gcodePreview) {
                elements.gcodePreview.style.display = 'block';
            }
            
        } catch (error) {
            console.error('Generation failed:', error);
            showGlog('Ошибка генерации: ' + error.message);
        } finally {
            state.isGenerating = false;
            updateGenerateButton(false);
        }
    }
    
    function handleToolSelect() {
        const toolId = elements.toolSelect?.value;
        if (!toolId) return;
        loadToolDefaults(toolId);
    }
    
    function handleOperationTypeChange() {
        const operationType = elements.operationTypeSelect?.value;
        
        if (elements.millingSettings) elements.millingSettings.style.display = 'none';
        if (elements.turningSettings) elements.turningSettings.style.display = 'none';
        if (elements.drillingSettings) elements.drillingSettings.style.display = 'none';
        
        switch (operationType) {
            case 'milling':
            case 'roughing':
            case 'finishing':
            case 'chamfer':
                if (elements.millingSettings) elements.millingSettings.style.display = 'block';
                break;
            case 'turning':
                if (elements.turningSettings) elements.turningSettings.style.display = 'block';
                break;
            case 'drilling':
                if (elements.drillingSettings) elements.drillingSettings.style.display = 'block';
                break;
        }
    }
    
    async function handleAIInspect() {
        if (!state.lastAnalysis) {
            showAIResults('Сначала загрузите и проанализируйте модель');
            return;
        }
        
        try {
            const payload = {
                geometry: state.lastAnalysis.geometry,
                bbox: state.lastAnalysis.geometry?.dimensions,
                units: state.lastAnalysis.geometry?.units || 'mm',
                controller: elements.controllerSelect?.value || 'fanuc_metric',
                operation_type: elements.operationTypeSelect?.value || 'milling',
                tool: elements.toolSelect?.value || null
            };
            
            const response = await fetch('/ai/inspect_model', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            const data = await response.json();
            renderAIResults(data, 'AI Анализ модели');
            
        } catch (error) {
            console.error('AI inspect failed:', error);
            showAIResults('Ошибка AI анализа: ' + error.message);
        }
    }
    
    async function handleAIAnalyze() {
        if (!state.lastGcode) {
            showAIResults('Сначала сгенерируйте G-код');
            return;
        }
        
        try {
            const payload = {
                gcode: state.lastGcode,
                controller: elements.controllerSelect?.value || 'fanuc_metric',
                material: null,
                tool: elements.toolSelect?.value || null
            };
            
            const response = await fetch('/ai/analyze_gcode', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(payload)
            });
            
            const data = await response.json();
            renderAIResults(data, 'AI Анализ G-кода');
            
        } catch (error) {
            console.error('AI analyze failed:', error);
            showAIResults('Ошибка AI анализа: ' + error.message);
        }
    }
    
    function handlePreview() {
        if (!state.lastGcode) {
            showGlog('Сначала сгенерируйте G-код');
            return;
        }
        
        if (window.NCV && window.NCV.renderGcode) {
            const success = window.NCV.renderGcode(state.lastGcode);
            if (!success) {
                showGlog('Предпросмотр недоступен (WebGL не поддерживается)');
            }
        } else {
            showGlog('NC Viewer не загружен');
        }
    }
    
    function handleFileSelect() {
        const file = elements.fileInput?.files[0];
        if (file) {
            showLog(`Выбран файл: ${file.name} (${formatFileSize(file.size)})`);
        }
    }
    
    function buildGenerationPayload() {
        const operationType = elements.operationTypeSelect?.value || 'milling';
        
        const payload = {
            model_path: state.lastModelPath,
            controller: elements.controllerSelect?.value || 'fanuc_metric',
            operation_type: operationType,
            tool: parseFloat(elements.toolInput?.value || '3'),
            feed: parseFloat(elements.feedInput?.value || '300'),
            plunge: parseFloat(elements.plungeInput?.value || '120'),
            clearance: parseFloat(elements.clearanceInput?.value || '5'),
            spindle: parseInt(elements.spindleInput?.value || '8000'),
            origin: elements.originSelect?.value || 'bbox_min',
            allowance_x: parseFloat(elements.allowanceXInput?.value || '0'),
            allowance_y: parseFloat(elements.allowanceYInput?.value || '0'),
            allowance_z: parseFloat(elements.allowanceZInput?.value || '0')
        };
        
        if (operationType === 'milling' || operationType === 'roughing' || 
            operationType === 'finishing' || operationType === 'chamfer') {
            payload.stepover = parseFloat(elements.stepoverInput?.value || '0.4');
            payload.stepdown = parseFloat(elements.stepdownInput?.value || '0');
            payload.dir = elements.dirSelect?.value || 'X';
            payload.waterline = elements.waterlineCheckbox?.checked || false;
            payload.waterline_dz = parseFloat(elements.waterlineDzInput?.value || '0');
            payload.finish_stepover = parseFloat(elements.finishStepoverInput?.value || '0.3');
        }
        
        if (operationType === 'turning') {
            payload.workpiece_diameter = parseFloat(document.getElementById('workpiece_diameter')?.value || '50');
            payload.cut_depth = parseFloat(document.getElementById('cut_depth')?.value || '1');
            payload.feed_per_rev = parseFloat(document.getElementById('feed_per_rev')?.value || '0.2');
            payload.turning_type = document.getElementById('turning_type')?.value || 'roughing';
        }
        
        if (operationType === 'drilling') {
            payload.drill_diameter = parseFloat(document.getElementById('drill_diameter')?.value || '6');
            payload.drill_depth = parseFloat(document.getElementById('drill_depth')?.value || '10');
            payload.drill_cycle = document.getElementById('drill_cycle')?.value || 'G81';
            payload.peck_depth = parseFloat(document.getElementById('peck_depth')?.value || '2');
        }
        
        return payload;
    }
    
    async function loadToolDefaults(toolId = null) {
        try {
            const response = await fetch('/tools');
            const data = await response.json();
            
            if (data.success && data.tools) {
                if (elements.toolSelect) {
                    elements.toolSelect.innerHTML = '<option value="">Выберите инструмент</option>';
                    data.tools.forEach(tool => {
                        const option = document.createElement('option');
                        option.value = tool.id;
                        option.textContent = tool.name;
                        elements.toolSelect.appendChild(option);
                    });
                }
                
                if (toolId) {
                    const tool = data.tools.find(t => t.id === toolId);
                    if (tool) {
                        if (elements.toolInput) elements.toolInput.value = tool.diam_mm;
                        if (elements.spindleInput) elements.spindleInput.value = Math.min(tool.max_rpm, 8000);
                        if (elements.feedInput) elements.feedInput.value = Math.min(tool.max_feed, 300);
                    }
                }
            }
        } catch (error) {
            console.warn('Failed to load tools:', error);
        }
    }
    
    function renderAnalysis(data) {
        if (elements.viewer) {
            if (data.preview_png_data) {
                elements.viewer.innerHTML = `<img src="${data.preview_png_data}" alt="preview" class="max-w-full max-h-full object-contain rounded-lg">`;
            } else if (data.preview_png) {
                elements.viewer.innerHTML = `<img src="${data.preview_png}" alt="preview" class="max-w-full max-h-full object-contain rounded-lg">`;
            } else {
                elements.viewer.innerHTML = '<div class="text-gray-400 p-8">Предпросмотр недоступен</div>';
            }
        }
        
        if (elements.meta) {
            const rows = [];
            
            function addRow(key, value) {
                rows.push(`<tr class="border-b border-gray-700"><td class="py-2 px-4">${key}</td><td class="py-2 px-4">${value}</td></tr>`);
            }
            
            if (data.file_info) {
                addRow('Файл', data.file_info.filename);
                addRow('Размер файла', formatFileSize(data.file_info.file_size));
                addRow('Тип файла', data.file_info.file_type);
            }
            
            if (data.geometry && data.geometry.dimensions) {
                const d = data.geometry.dimensions;
                addRow('Размеры (мм)', `${d.length} × ${d.width} × ${d.height}`);
            }
            
            if (data.mesh_info) {
                addRow('Вершины', data.mesh_info.vertices.toLocaleString());
                addRow('Грани', data.mesh_info.faces.toLocaleString());
            }
            
            elements.meta.innerHTML = `
                <table class="w-full border-collapse">
                    <thead>
                        <tr class="bg-gray-700">
                            <th class="py-2 px-4 text-left">Параметр</th>
                            <th class="py-2 px-4 text-left">Значение</th>
                        </tr>
                    </thead>
                    <tbody>${rows.join('')}</tbody>
                </table>
            `;
        }
    }
    
    function renderGcodeContent(gcode) {
        if (!elements.gcodeContent) return;
        
        const lines = gcode.split('\n');
        const html = lines.map(line => {
            if (line.trim().startsWith('(') || line.trim().startsWith(';')) {
                return `<div class="text-gray-500">${escapeHtml(line)}</div>`;
            } else if (line.trim().startsWith('G0')) {
                return `<div class="text-yellow-400">${escapeHtml(line)}</div>`;
            } else if (line.trim().startsWith('G1')) {
                return `<div class="text-blue-400">${escapeHtml(line)}</div>`;
            } else {
                return `<div class="text-gray-300">${escapeHtml(line)}</div>`;
            }
        }).join('');
        
        elements.gcodeContent.innerHTML = html;
    }
    
    function renderAIResults(data, title) {
        if (!elements.aiResults) return;
        
        let content = `<h3 class="text-lg font-semibold mb-3">${title}</h3>`;
        
        if (data.success) {
            if (data.findings) {
                content += '<div class="mb-4"><h4 class="font-medium mb-2">Результаты анализа:</h4>';
                content += `<pre class="bg-gray-100 text-gray-800 p-3 rounded">${JSON.stringify(data.findings, null, 2)}</pre></div>`;
            }
            
            if (data.suggestions) {
                content += '<div class="mb-4"><h4 class="font-medium mb-2">Рекомендации:</h4>';
                content += `<pre class="bg-gray-100 text-gray-800 p-3 rounded">${JSON.stringify(data.suggestions, null, 2)}</pre></div>`;
            }
            
            if (data.summary) {
                content += `<div class="mb-4"><h4 class="font-medium mb-2">Краткое описание:</h4><p>${data.summary}</p></div>`;
            }
            
            if (data.risks && data.risks.length > 0) {
                content += '<div class="mb-4"><h4 class="font-medium mb-2">Риски:</h4><ul class="list-disc list-inside">';
                data.risks.forEach(risk => {
                    content += `<li class="text-red-400">${risk}</li>`;
                });
                content += '</ul></div>';
            }
        } else {
            content += `<div class="text-red-400">Ошибка: ${data.error || 'Неизвестная ошибка'}</div>`;
        }
        
        elements.aiResults.innerHTML = content;
    }
    
    function showLog(message) {
        if (elements.logArea) {
            elements.logArea.textContent = message;
        }
    }
    
    function showGlog(message) {
        if (elements.glogArea) {
            elements.glogArea.innerHTML = message;
        }
    }
    
    function showAIResults(message) {
        if (elements.aiResults) {
            elements.aiResults.innerHTML = `<div class="text-gray-400">${message}</div>`;
        }
    }
    
    function updateAnalyzeButton(loading) {
        if (elements.analyzeBtn) {
            elements.analyzeBtn.disabled = loading;
            elements.analyzeBtn.textContent = loading ? 'Анализ...' : 'Анализировать';
        }
    }
    
    function updateGenerateButton(loading) {
        if (elements.generateBtn) {
            elements.generateBtn.disabled = loading;
            elements.generateBtn.textContent = loading ? 'Генерация...' : 'Сгенерировать G-код';
        }
    }
    
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    function escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
    
})();