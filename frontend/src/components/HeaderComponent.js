/**
 * Header Component
 * Application header with navigation and status
 */

import { BaseComponent } from './BaseComponent';

export class HeaderComponent extends BaseComponent {
    constructor() {
        super();
        this.state = {
            backendStatus: 'checking',
            aiStatus: 'unknown'
        };
    }
    
    async init(element) {
        await super.init(element);
        await this.checkBackendStatus();
    }
    
    getTemplate() {
        return `
            <div class="bg-gray-800 border-b border-gray-700 shadow-lg">
                <div class="container-responsive">
                    <div class="flex items-center justify-between py-4">
                        <!-- Logo and Title -->
                        <div class="flex items-center space-x-4">
                            <div class="flex items-center space-x-2">
                                <svg class="w-8 h-8 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"></path>
                                </svg>
                                <div>
                                    <h1 class="text-xl font-bold text-gradient">CNCera</h1>
                                    <p class="text-xs text-gray-400">AI-Powered CNC System</p>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Navigation -->
                        <nav class="hidden md:flex items-center space-x-6">
                            <a href="#upload" class="text-gray-300 hover:text-white transition">Загрузка</a>
                            <a href="#viewer" class="text-gray-300 hover:text-white transition">Просмотр</a>
                            <a href="#gcode" class="text-gray-300 hover:text-white transition">G-код</a>
                            <a href="#ai" class="text-gray-300 hover:text-white transition">ИИ</a>
                        </nav>
                        
                        <!-- Status Indicators -->
                        <div class="flex items-center space-x-4">
                            <!-- Backend Status -->
                            <div class="flex items-center space-x-2">
                                <div class="status-indicator ${this.getStatusColor('backend')}" title="Статус backend сервера"></div>
                                <span class="text-sm text-gray-400 hidden sm:inline">Backend</span>
                            </div>
                            
                            <!-- AI Status -->
                            <div class="flex items-center space-x-2">
                                <div class="status-indicator ${this.getStatusColor('ai')}" title="Статус ИИ сервиса"></div>
                                <span class="text-sm text-gray-400 hidden sm:inline">AI</span>
                            </div>
                            
                            <!-- Help Button -->
                            <button id="help-btn" class="text-gray-400 hover:text-white transition" title="Помощь">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path>
                                </svg>
                            </button>
                            
                            <!-- Settings Button -->
                            <button id="settings-btn" class="text-gray-400 hover:text-white transition" title="Настройки">
                                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"></path>
                                </svg>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
            
            <style>
                .status-indicator {
                    width: 8px;
                    height: 8px;
                    border-radius: 50%;
                    animation: pulse 2s infinite;
                }
                .status-online { background-color: #10b981; }
                .status-offline { background-color: #ef4444; }
                .status-checking { background-color: #f59e0b; }
                .status-unknown { background-color: #6b7280; }
            </style>
        `;
    }
    
    setupEventListeners() {
        this.addEventListener('#help-btn', 'click', this.showHelp.bind(this));
        this.addEventListener('#settings-btn', 'click', this.showSettings.bind(this));
        
        // Check backend status periodically
        setInterval(() => {
            this.checkBackendStatus();
        }, 30000); // Every 30 seconds
    }
    
    getStatusColor(service) {
        if (service === 'backend') {
            return `status-${this.state.backendStatus}`;
        } else if (service === 'ai') {
            return `status-${this.state.aiStatus}`;
        }
        return 'status-unknown';
    }
    
    async checkBackendStatus() {
        try {
            const api = window.CNCera.api;
            
            // Check backend health
            const health = await api.checkHealth();
            this.setState({ backendStatus: 'online' });
            
            // Check AI features
            const info = await api.getInfo();
            const aiAvailable = info.features?.ai_chat && info.features?.ai_analysis;
            this.setState({ aiStatus: aiAvailable ? 'online' : 'offline' });
            
        } catch (error) {
            console.warn('Backend status check failed:', error);
            this.setState({ 
                backendStatus: 'offline',
                aiStatus: 'unknown'
            });
        }
    }
    
    onStateChange() {
        // Re-render status indicators
        if (this.element) {
            const backendIndicator = this.$('.status-indicator:first-child');
            const aiIndicator = this.$('.status-indicator:last-child');
            
            if (backendIndicator) {
                backendIndicator.className = `status-indicator ${this.getStatusColor('backend')}`;
            }
            
            if (aiIndicator) {
                aiIndicator.className = `status-indicator ${this.getStatusColor('ai')}`;
            }
        }
    }
    
    showHelp() {
        // TODO: Implement help modal
        const helpContent = `
            <h3>Горячие клавиши:</h3>
            <ul>
                <li><kbd>Ctrl+O</kbd> - Открыть файл</li>
                <li><kbd>Ctrl+G</kbd> - Генерировать G-код</li>
                <li><kbd>F1</kbd> - Показать помощь</li>
            </ul>
            
            <h3>Поддерживаемые форматы:</h3>
            <ul>
                <li>STEP (.step, .stp)</li>
                <li>STL (.stl)</li>
            </ul>
            
            <h3>Контроллеры:</h3>
            <ul>
                <li>Fanuc</li>
                <li>Siemens</li>
                <li>Heidenhain</li>
                <li>GSK</li>
                <li>Mazak</li>
            </ul>
        `;
        
        alert('CNCera Помощь\\n\\n' + helpContent.replace(/<[^>]*>/g, ''));
    }
    
    showSettings() {
        // TODO: Implement settings modal
        alert('Настройки будут доступны в следующей версии');
    }
}