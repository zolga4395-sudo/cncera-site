/**
 * Main App Component
 * Manages the overall application state and layout
 */

import { HeaderComponent } from './components/HeaderComponent';
import { FileUploadComponent } from './components/FileUploadComponent';
import { ViewerComponent } from './components/ViewerComponent';
import { GcodeGeneratorComponent } from './components/GcodeGeneratorComponent';
import { AiChatComponent } from './components/AiChatComponent';
import { StatusComponent } from './components/StatusComponent';

export default class App {
    constructor() {
        this.state = {
            currentModel: null,
            analysisResult: null,
            aiAnalysis: null,
            isLoading: false,
            error: null
        };
        
        this.components = {};
        this.eventListeners = new Map();
    }
    
    async init() {
        try {
            await this.render();
            await this.initComponents();
            this.setupEventListeners();
            
            console.log('✅ App initialized successfully');
        } catch (error) {
            console.error('❌ App initialization failed:', error);
            this.handleError('Ошибка инициализации приложения', error);
        }
    }
    
    async render() {
        const appContainer = document.getElementById('app');
        
        appContainer.innerHTML = `
            <div class="min-h-screen bg-gray-900">
                <!-- Header -->
                <header id="app-header"></header>
                
                <!-- Main Content -->
                <main class="container-responsive py-6">
                    <!-- Status Bar -->
                    <div id="app-status" class="mb-6"></div>
                    
                    <!-- Main Grid Layout -->
                    <div class="grid grid-cols-1 lg:grid-cols-4 gap-6">
                        
                        <!-- Left Column: Upload & Analysis -->
                        <div class="lg:col-span-3 space-y-6">
                            
                            <!-- File Upload Section -->
                            <div id="file-upload-section" class="card">
                                <div class="card-header">
                                    <svg class="w-6 h-6 mr-2 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path>
                                    </svg>
                                    Загрузка и анализ файла
                                </div>
                                <div id="file-upload-component"></div>
                            </div>
                            
                            <!-- 3D Viewer Section -->
                            <div id="viewer-section" class="card">
                                <div class="card-header">
                                    <svg class="w-6 h-6 mr-2 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"></path>
                                    </svg>
                                    3D Просмотрщик
                                </div>
                                <div id="viewer-component"></div>
                            </div>
                            
                            <!-- G-code Generator Section -->
                            <div id="gcode-section" class="card">
                                <div class="card-header">
                                    <svg class="w-6 h-6 mr-2 text-orange-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                                    </svg>
                                    Генерация G-кода
                                </div>
                                <div id="gcode-component"></div>
                            </div>
                        </div>
                        
                        <!-- Right Column: AI Chat -->
                        <div class="lg:col-span-1 space-y-6">
                            <div id="ai-chat-section" class="card">
                                <div class="card-header">
                                    <svg class="w-6 h-6 mr-2 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path>
                                    </svg>
                                    ИИ Консультант
                                </div>
                                <div id="ai-chat-component"></div>
                            </div>
                        </div>
                    </div>
                </main>
                
                <!-- Footer -->
                <footer class="bg-gray-800 border-t border-gray-700 py-6 mt-12">
                    <div class="container-responsive">
                        <div class="flex flex-col md:flex-row justify-between items-center">
                            <div class="text-sm text-gray-400">
                                © 2024 CNCera. AI-Powered CNC System.
                            </div>
                            <div class="flex space-x-4 mt-2 md:mt-0">
                                <a href="#" class="text-sm text-gray-400 hover:text-gray-300 transition">Документация</a>
                                <a href="#" class="text-sm text-gray-400 hover:text-gray-300 transition">GitHub</a>
                                <a href="#" class="text-sm text-gray-400 hover:text-gray-300 transition">Поддержка</a>
                            </div>
                        </div>
                    </div>
                </footer>
            </div>
        `;
    }
    
    async initComponents() {
        // Initialize all components
        this.components.header = new HeaderComponent();
        this.components.status = new StatusComponent();
        this.components.fileUpload = new FileUploadComponent();
        this.components.viewer = new ViewerComponent();
        this.components.gcodeGenerator = new GcodeGeneratorComponent();
        this.components.aiChat = new AiChatComponent();
        
        // Initialize each component
        await this.components.header.init(document.getElementById('app-header'));
        await this.components.status.init(document.getElementById('app-status'));
        await this.components.fileUpload.init(document.getElementById('file-upload-component'));
        await this.components.viewer.init(document.getElementById('viewer-component'));
        await this.components.gcodeGenerator.init(document.getElementById('gcode-component'));
        await this.components.aiChat.init(document.getElementById('ai-chat-component'));
    }
    
    setupEventListeners() {
        // File upload events
        this.addEventListener('file-uploaded', this.handleFileUploaded.bind(this));
        this.addEventListener('file-analyzed', this.handleFileAnalyzed.bind(this));
        
        // AI events
        this.addEventListener('ai-analysis-complete', this.handleAiAnalysisComplete.bind(this));
        this.addEventListener('ai-params-generated', this.handleAiParamsGenerated.bind(this));
        
        // G-code events
        this.addEventListener('gcode-generated', this.handleGcodeGenerated.bind(this));
        
        // Error events
        this.addEventListener('error', this.handleError.bind(this));
        
        // Global keyboard shortcuts
        document.addEventListener('keydown', this.handleKeyboardShortcuts.bind(this));
    }
    
    // Event handling methods
    handleFileUploaded(event) {
        const { data } = event.detail;
        this.setState({ currentModel: data });
        this.components.viewer.loadModel(data.model_path);
        this.components.status.showSuccess('Файл загружен успешно');
    }
    
    handleFileAnalyzed(event) {
        const { data } = event.detail;
        this.setState({ analysisResult: data });
        this.components.aiChat.setContext(data);
    }
    
    handleAiAnalysisComplete(event) {
        const { analysis } = event.detail;
        this.setState({ aiAnalysis: analysis });
        this.components.status.showSuccess('ИИ анализ завершен');
    }
    
    handleAiParamsGenerated(event) {
        const { params } = event.detail;
        this.components.gcodeGenerator.applyAiParams(params);
        this.components.status.showSuccess('ИИ параметры применены');
    }
    
    handleGcodeGenerated(event) {
        const { result } = event.detail;
        this.components.status.showSuccess('G-код сгенерирован успешно');
    }
    
    handleError(event) {
        const { title, message } = event.detail;
        console.error(`${title}: ${message}`);
        this.components.status.showError(title, message);
    }
    
    handleKeyboardShortcuts(event) {
        // Ctrl/Cmd + O: Open file
        if ((event.ctrlKey || event.metaKey) && event.key === 'o') {
            event.preventDefault();
            this.components.fileUpload.openFileDialog();
        }
        
        // Ctrl/Cmd + G: Generate G-code
        if ((event.ctrlKey || event.metaKey) && event.key === 'g') {
            event.preventDefault();
            if (this.state.currentModel) {
                this.components.gcodeGenerator.generate();
            }
        }
        
        // F1: Help
        if (event.key === 'F1') {
            event.preventDefault();
            this.showHelp();
        }
    }
    
    // Utility methods
    setState(newState) {
        this.state = { ...this.state, ...newState };
        this.notifyStateChange();
    }
    
    notifyStateChange() {
        this.dispatchEvent('state-changed', { state: this.state });
    }
    
    addEventListener(eventName, handler) {
        if (!this.eventListeners.has(eventName)) {
            this.eventListeners.set(eventName, []);
        }
        this.eventListeners.get(eventName).push(handler);
        document.addEventListener(eventName, handler);
    }
    
    dispatchEvent(eventName, detail) {
        const event = new CustomEvent(eventName, { detail });
        document.dispatchEvent(event);
    }
    
    showHelp() {
        // TODO: Implement help modal
        alert('Горячие клавиши:\nCtrl+O - Открыть файл\nCtrl+G - Генерировать G-код\nF1 - Помощь');
    }
    
    destroy() {
        // Cleanup event listeners
        this.eventListeners.forEach((handlers, eventName) => {
            handlers.forEach(handler => {
                document.removeEventListener(eventName, handler);
            });
        });
        this.eventListeners.clear();
        
        // Destroy components
        Object.values(this.components).forEach(component => {
            if (component.destroy) {
                component.destroy();
            }
        });
    }
}