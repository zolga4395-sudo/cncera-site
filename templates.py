# ---- Enhanced HTML Template with AI Chat ----
INDEX_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>CNCera — 3D Analysis & AI-Powered G-code Generation</title>
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
        .chat-container {
            max-height: 400px;
            overflow-y: auto;
        }
        .chat-message {
            margin-bottom: 12px;
            padding: 8px 12px;
            border-radius: 8px;
        }
        .chat-message.user {
            background-color: #2563eb;
            color: white;
            margin-left: 20%;
        }
        .chat-message.assistant {
            background-color: #374151;
            color: #e5e7eb;
            margin-right: 20%;
        }
        .loading-dots {
            display: inline-block;
        }
        .loading-dots:after {
            content: '...';
            animation: dots 1.5s steps(4, end) infinite;
        }
        @keyframes dots {
            0%, 20% { color: rgba(0,0,0,0); text-shadow: .25em 0 0 rgba(0,0,0,0), .5em 0 0 rgba(0,0,0,0); }
            40% { color: white; text-shadow: .25em 0 0 rgba(0,0,0,0), .5em 0 0 rgba(0,0,0,0); }
            60% { text-shadow: .25em 0 0 white, .5em 0 0 rgba(0,0,0,0); }
            80%, 100% { text-shadow: .25em 0 0 white, .5em 0 0 white; }
        }
    </style>
</head>
<body class="bg-gray-900 text-gray-100 font-sans p-6">
    <div class="max-w-7xl mx-auto space-y-6">
        <!-- Header -->
        <div class="text-center mb-8">
            <h1 class="text-3xl font-bold text-blue-400 mb-2">CNCera</h1>
            <p class="text-gray-400">3D Analysis & AI-Powered G-code Generation</p>
        </div>

        <!-- Main Content Grid -->
        <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            <!-- Left Column: File Upload & Analysis -->
            <div class="lg:col-span-2 space-y-6">
                
                <!-- File Upload Section -->
                <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
                    <h2 class="text-xl font-semibold mb-4 flex items-center">
                        <svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M5.5 13a3.5 3.5 0 01-.369-6.98 4 4 0 117.753-1.977A4.5 4.5 0 1113.5 13H11V9.413l1.293 1.293a1 1 0 001.414-1.414l-3-3a1 1 0 00-1.414 0l-3 3a1 1 0 001.414 1.414L9 9.414V13H5.5z"/>
                        </svg>
                        Загрузка и анализ файла
                    </h2>
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
                    <div class="flex space-x-3">
                        <button onclick="analyze()" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition">
                            Анализировать
                        </button>
                        <button onclick="aiAnalyze()" class="bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 transition" disabled id="aiAnalyzeBtn">
                            <svg class="w-4 h-4 inline mr-2" fill="currentColor" viewBox="0 0 20 20">
                                <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/>
                            </svg>
                            ИИ Анализ
                        </button>
                    </div>
                    <div id="log" class="mt-4 text-gray-400"></div>
                </div>

                <!-- Analysis Results Section -->
                <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
                    <h2 class="text-xl font-semibold mb-4">Результат анализа</h2>
                    <div id="viewer" class="bg-gray-900 rounded-lg flex items-center justify-center"></div>
                    <div id="meta" class="mt-4"></div>
                    <div id="aiAnalysisResult" class="mt-4 hidden">
                        <h3 class="text-lg font-medium mb-2 text-purple-400">ИИ Анализ детали</h3>
                        <div id="aiAnalysisContent" class="bg-gray-700 p-4 rounded-lg text-sm"></div>
                    </div>
                    <p class="text-sm text-gray-500 mt-2">Офлайн-вьювер использует three.min.js, OrbitControls.js, STLLoader.js. Если они недоступны, отображается PNG.</p>
                </div>

                <!-- G-code Generation Section -->
                <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
                    <h2 class="text-xl font-semibold mb-4 flex items-center">
                        <svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M4 4a2 2 0 00-2 2v8a2 2 0 002 2h12a2 2 0 002-2V6a2 2 0 00-2-2H4zm2 6a2 2 0 114 0 2 2 0 01-4 0zm8 0a2 2 0 114 0 2 2 0 01-4 0z"/>
                        </svg>
                        Генерация G-кода
                    </h2>

                    <!-- AI G-code Generation -->
                    <div class="mb-6 p-4 bg-purple-900/20 border border-purple-600/30 rounded-lg">
                        <h3 class="text-lg font-medium mb-3 text-purple-400">ИИ Генерация параметров</h3>
                        <div class="flex flex-col sm:flex-row gap-3">
                            <input id="aiRequirements" type="text" placeholder="Опишите требования к обработке..." class="flex-1 bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                            <button onclick="aiGenerateParams()" class="bg-purple-600 text-white px-4 py-2 rounded-lg hover:bg-purple-700 transition whitespace-nowrap" disabled id="aiGenerateBtn">
                                Генерировать ИИ параметры
                            </button>
                        </div>
                        <div id="aiParamsResult" class="mt-3 hidden">
                            <div class="bg-gray-700 p-3 rounded text-sm">
                                <div id="aiParamsContent"></div>
                                <button onclick="applyAiParams()" class="mt-2 bg-green-600 text-white px-3 py-1 rounded text-sm hover:bg-green-700 transition">
                                    Применить параметры
                                </button>
                            </div>
                        </div>
                    </div>

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

                    <!-- Tool Parameters -->
                    <div class="mb-6">
                        <h3 class="text-lg font-medium mb-3">Параметры инструмента</h3>
                        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                            <div>
                                <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Диаметр инструмента (мм)">Ø инструмента, мм</label>
                                <input id="tool" type="number" value="3" step="0.1" min="0.1" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                            </div>
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
                                <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Безопасная высота по Z (мм)">Clearance Z, мм</label>
                                <input id="clearance" type="number" value="5" step="0.5" min="1" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                            </div>
                        </div>

                        <!-- Advanced Milling Options -->
                        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">
                            <div>
                                <label class="block text-sm text-gray-400 mb-1">Waterline</label>
                                <input id="waterline" type="checkbox" class="h-5 w-5 text-blue-600 bg-gray-700 border-gray-600 rounded">
                            </div>
                            <div>
                                <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Шаг по Z для waterline">Шаг Waterline dZ, мм</label>
                                <input id="waterline_dz" type="number" value="0.5" step="0.1" min="0" max="50" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
                            </div>
                            <div>
                                <label class="block text-sm text-gray-400 mb-1 tooltip" data-tooltip="Степовер для финишной обработки">Finish stepover</label>
                                <input id="finish_stepover" type="number" value="0.3" step="0.05" min="0.05" max="0.95" class="w-full bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100">
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
                        <button onclick="gen()" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition">Сгенерировать G-код</button>
                        <span id="glog" class="text-gray-400"></span>
                    </div>
                </div>
            </div>

            <!-- Right Column: AI Chat -->
            <div class="space-y-6">
                <div class="bg-gray-800 p-6 rounded-lg shadow-lg">
                    <h2 class="text-xl font-semibold mb-4 flex items-center">
                        <svg class="w-5 h-5 mr-2" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M2 5a2 2 0 012-2h7a2 2 0 012 2v4a2 2 0 01-2 2H9l-3 3v-3H4a2 2 0 01-2-2V5z"/>
                            <path d="M15 7v2a4 4 0 01-4 4H9.828l-1.766 1.767c.28.149.599.233.938.233h2l3 3v-3h2a2 2 0 002-2V9a2 2 0 00-2-2h-1z"/>
                        </svg>
                        ИИ Консультант
                    </h2>
                    
                    <div class="chat-container bg-gray-900 p-4 rounded-lg mb-4" id="chatContainer">
                        <div class="chat-message assistant">
                            <div class="text-sm text-gray-400 mb-1">ИИ Ассистент</div>
                            <div>Привет! Я ваш ИИ консультант по CNC обработке. Могу помочь с выбором инструментов, параметрами резания, стратегиями обработки и технологическими вопросами. Задавайте любые вопросы!</div>
                        </div>
                    </div>
                    
                    <div class="flex space-x-2">
                        <input type="text" id="chatInput" placeholder="Задайте вопрос о CNC обработке..." class="flex-1 bg-gray-700 border border-gray-600 rounded-lg p-2 text-gray-100" onkeypress="handleChatKeyPress(event)">
                        <button onclick="sendChatMessage()" class="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 transition">
                            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                                <path d="M10.894 2.553a1 1 0 00-1.788 0l-7 14a1 1 0 001.169 1.409l5-1.429A1 1 0 009 15.571V11a1 1 0 112 0v4.571a1 1 0 00.725.962l5 1.428a1 1 0 001.17-1.408l-7-14z"/>
                            </svg>
                        </button>
                    </div>
                    
                    <div class="mt-4 text-xs text-gray-500">
                        <p>💡 <strong>Примеры вопросов:</strong></p>
                        <ul class="list-disc list-inside mt-1 space-y-1">
                            <li>"Какие параметры для фрезерования алюминия?"</li>
                            <li>"Как выбрать скорость шпинделя для стали?"</li>
                            <li>"Объясни стратегию waterline обработки"</li>
                            <li>"Какой инструмент лучше для чистовой обработки?"</li>
                        </ul>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        let LAST_MODEL_PATH = null;
        let LAST_PART_INFO = null;
        let AI_GENERATED_PARAMS = null;
        const CHAT_SESSION_ID = 'session_' + Date.now();

        // Chat functionality
        function handleChatKeyPress(event) {
            if (event.key === 'Enter') {
                sendChatMessage();
            }
        }

        async function sendChatMessage() {
            const input = document.getElementById('chatInput');
            const message = input.value.trim();
            if (!message) return;

            const chatContainer = document.getElementById('chatContainer');
            
            // Add user message
            const userMessage = document.createElement('div');
            userMessage.className = 'chat-message user';
            userMessage.innerHTML = `
                <div class="text-sm text-gray-300 mb-1">Вы</div>
                <div>${message}</div>
            `;
            chatContainer.appendChild(userMessage);
            
            // Clear input
            input.value = '';
            
            // Add loading message
            const loadingMessage = document.createElement('div');
            loadingMessage.className = 'chat-message assistant';
            loadingMessage.innerHTML = `
                <div class="text-sm text-gray-400 mb-1">ИИ Ассистент</div>
                <div class="loading-dots">Думаю</div>
            `;
            chatContainer.appendChild(loadingMessage);
            chatContainer.scrollTop = chatContainer.scrollHeight;

            try {
                const response = await fetch('/ai_chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        message: message,
                        session_id: CHAT_SESSION_ID,
                        context: LAST_PART_INFO
                    })
                });
                
                const data = await response.json();
                
                // Remove loading message
                chatContainer.removeChild(loadingMessage);
                
                if (data.success) {
                    // Add AI response
                    const aiMessage = document.createElement('div');
                    aiMessage.className = 'chat-message assistant';
                    aiMessage.innerHTML = `
                        <div class="text-sm text-gray-400 mb-1">ИИ Ассистент</div>
                        <div>${data.response.replace(/\\n/g, '<br>')}</div>
                    `;
                    chatContainer.appendChild(aiMessage);
                } else {
                    // Add error message
                    const errorMessage = document.createElement('div');
                    errorMessage.className = 'chat-message assistant';
                    errorMessage.innerHTML = `
                        <div class="text-sm text-gray-400 mb-1">Ошибка</div>
                        <div class="text-red-400">${data.error}</div>
                    `;
                    chatContainer.appendChild(errorMessage);
                }
            } catch (error) {
                // Remove loading message
                chatContainer.removeChild(loadingMessage);
                
                const errorMessage = document.createElement('div');
                errorMessage.className = 'chat-message assistant';
                errorMessage.innerHTML = `
                    <div class="text-sm text-gray-400 mb-1">Ошибка</div>
                    <div class="text-red-400">Ошибка сети: ${error.message}</div>
                `;
                chatContainer.appendChild(errorMessage);
            }
            
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }

        // AI Analysis
        async function aiAnalyze() {
            if (!LAST_MODEL_PATH) {
                alert('Сначала загрузите и проанализируйте модель');
                return;
            }

            const btn = document.getElementById('aiAnalyzeBtn');
            btn.disabled = true;
            btn.innerHTML = '<div class="loading-dots inline-block">Анализирую</div>';

            try {
                const response = await fetch('/ai_analyze', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        model_path: LAST_MODEL_PATH
                    })
                });

                const data = await response.json();
                
                if (data.success) {
                    const resultDiv = document.getElementById('aiAnalysisResult');
                    const contentDiv = document.getElementById('aiAnalysisContent');
                    
                    let analysisHtml = '';
                    if (typeof data.analysis === 'object') {
                        // Format structured analysis
                        for (const [key, value] of Object.entries(data.analysis)) {
                            if (key !== 'error') {
                                analysisHtml += `<div class="mb-2"><strong class="text-purple-300">${key}:</strong> ${JSON.stringify(value, null, 2).replace(/\\n/g, '<br>')}</div>`;
                            }
                        }
                    } else {
                        analysisHtml = data.analysis.replace(/\\n/g, '<br>');
                    }
                    
                    contentDiv.innerHTML = analysisHtml;
                    resultDiv.classList.remove('hidden');
                } else {
                    alert('Ошибка ИИ анализа: ' + data.error);
                }
            } catch (error) {
                alert('Ошибка: ' + error.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = '<svg class="w-4 h-4 inline mr-2" fill="currentColor" viewBox="0 0 20 20"><path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>ИИ Анализ';
            }
        }

        // AI Parameter Generation
        async function aiGenerateParams() {
            if (!LAST_MODEL_PATH) {
                alert('Сначала загрузите модель');
                return;
            }

            const requirements = document.getElementById('aiRequirements').value;
            const btn = document.getElementById('aiGenerateBtn');
            
            btn.disabled = true;
            btn.innerHTML = '<div class="loading-dots inline-block">Генерирую</div>';

            try {
                const response = await fetch('/ai_generate_gcode', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({
                        model_path: LAST_MODEL_PATH,
                        requirements: requirements
                    })
                });

                const data = await response.json();
                
                if (data.success) {
                    AI_GENERATED_PARAMS = data.parameters;
                    const resultDiv = document.getElementById('aiParamsResult');
                    const contentDiv = document.getElementById('aiParamsContent');
                    
                    let paramsHtml = '<div class="text-green-400 font-medium mb-2">Рекомендуемые параметры:</div>';
                    for (const [key, value] of Object.entries(data.parameters)) {
                        if (key !== 'error' && key !== 'raw_response') {
                            paramsHtml += `<div><strong>${key}:</strong> ${value}</div>`;
                        }
                    }
                    
                    contentDiv.innerHTML = paramsHtml;
                    resultDiv.classList.remove('hidden');
                } else {
                    alert('Ошибка генерации параметров: ' + data.error);
                }
            } catch (error) {
                alert('Ошибка: ' + error.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = 'Генерировать ИИ параметры';
            }
        }

        function applyAiParams() {
            if (!AI_GENERATED_PARAMS) return;
            
            // Apply the generated parameters to form fields
            if (AI_GENERATED_PARAMS.tool_diameter) {
                document.getElementById('tool').value = AI_GENERATED_PARAMS.tool_diameter;
            }
            if (AI_GENERATED_PARAMS.spindle_speed) {
                document.getElementById('spindle').value = AI_GENERATED_PARAMS.spindle_speed;
            }
            if (AI_GENERATED_PARAMS.feed_rate) {
                document.getElementById('feed').value = AI_GENERATED_PARAMS.feed_rate;
            }
            if (AI_GENERATED_PARAMS.plunge_rate) {
                document.getElementById('plunge').value = AI_GENERATED_PARAMS.plunge_rate;
            }
            if (AI_GENERATED_PARAMS.stepover) {
                document.getElementById('stepover').value = AI_GENERATED_PARAMS.stepover;
            }
            if (AI_GENERATED_PARAMS.stepdown) {
                document.getElementById('stepdown').value = AI_GENERATED_PARAMS.stepdown;
            }
            if (AI_GENERATED_PARAMS.operation_type) {
                document.getElementById('operation_type').value = AI_GENERATED_PARAMS.operation_type;
                toggleOperationSettings();
            }
            if (AI_GENERATED_PARAMS.controller) {
                document.getElementById('controller').value = AI_GENERATED_PARAMS.controller;
            }
            
            alert('Параметры применены!');
        }

        // Rest of the existing JavaScript functions...
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

            millingSettings.style.display = 'block'; // Show milling settings for all types in this simplified version
        }

        async function tryViewer(stlUrl) {
            // Existing 3D viewer code...
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
                LAST_PART_INFO = data;
                
                // Enable AI buttons
                document.getElementById('aiAnalyzeBtn').disabled = false;
                document.getElementById('aiGenerateBtn').disabled = false;
                
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
                tool: parseFloat(document.getElementById('tool').value || '3'),
                feed: parseFloat(document.getElementById('feed').value || '300'),
                plunge: parseFloat(document.getElementById('plunge').value || '120'),
                clearance: parseFloat(document.getElementById('clearance').value || '5'),
                spindle: parseInt(document.getElementById('spindle').value || '8000'),
                origin: document.getElementById('origin').value || 'bbox_min',
                allowance_x: parseFloat(document.getElementById('allowance_x').value || '0'),
                allowance_y: parseFloat(document.getElementById('allowance_y').value || '0'),
                allowance_z: parseFloat(document.getElementById('allowance_z').value || '0'),
                stepover: parseFloat(document.getElementById('stepover').value || '0.4'),
                stepdown: parseFloat(document.getElementById('stepdown').value || '0'),
                dir: document.getElementById('dir').value || 'X',
                waterline: document.getElementById('waterline').checked,
                waterline_dz: parseFloat(document.getElementById('waterline_dz').value || '0'),
                finish_stepover: parseFloat(document.getElementById('finish_stepover').value || '0.3')
            };

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
                glog.innerHTML = `Готово — <a href="${data.gcode_path}" target="_blank" class="text-blue-400 hover:underline">скачать G-код (${controller.toUpperCase()} ${operationType})</a>`;
            } catch (err) {
                glog.textContent = 'Сетевая ошибка: ' + err;
            }
        }

        // Initialize
        document.addEventListener('DOMContentLoaded', toggleOperationSettings);
    </script>
</body>
</html>
"""