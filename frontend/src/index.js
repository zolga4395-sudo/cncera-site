/**
 * CNCera Frontend Application Entry Point
 * AI-Powered CNC Analysis & G-code Generation
 */

import './styles/main.css';
import App from './App';
import { ApiService } from './services/ApiService';
import { ThreeViewerService } from './services/ThreeViewerService';

// Global app state
window.CNCera = {
    version: '1.0.0',
    api: null,
    viewer: null,
    currentModel: null,
    chatSession: `session_${Date.now()}`,
    
    // App lifecycle
    async init() {
        console.log('🚀 CNCera Frontend v' + this.version);
        
        try {
            // Initialize services
            this.api = new ApiService();
            this.viewer = new ThreeViewerService();
            
            // Check backend connection
            await this.checkBackendHealth();
            
            // Initialize main app
            const app = new App();
            await app.init();
            
            console.log('✅ CNCera initialized successfully');
            
        } catch (error) {
            console.error('❌ CNCera initialization failed:', error);
            this.showError('Ошибка инициализации приложения', error.message);
        }
    },
    
    async checkBackendHealth() {
        try {
            const health = await this.api.get('/health');
            console.log('🔗 Backend connection:', health);
            
            const info = await this.api.get('/info');
            console.log('📋 Backend features:', info.features);
            
            return true;
        } catch (error) {
            console.warn('⚠️ Backend connection failed:', error);
            this.showWarning('Соединение с сервером', 'Проверьте, что backend сервер запущен на порту 5000');
            return false;
        }
    },
    
    showError(title, message) {
        const errorEl = document.getElementById('error-boundary');
        const messageEl = document.getElementById('error-message');
        
        if (errorEl && messageEl) {
            messageEl.textContent = `${title}: ${message}`;
            errorEl.classList.remove('hidden');
        } else {
            alert(`${title}: ${message}`);
        }
    },
    
    showWarning(title, message) {
        console.warn(`${title}: ${message}`);
        // TODO: Implement toast notifications
    },
    
    showSuccess(title, message) {
        console.log(`${title}: ${message}`);
        // TODO: Implement toast notifications
    }
};

// Initialize app when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.CNCera.init();
});

// Handle page visibility changes
document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
        // Page became visible, check backend health
        window.CNCera.checkBackendHealth();
    }
});

// Export for debugging
if (process.env.NODE_ENV === 'development') {
    window.CNCera.debug = true;
    console.log('🔧 Development mode enabled');
}