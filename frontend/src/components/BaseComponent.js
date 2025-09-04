/**
 * Base Component Class
 * Provides common functionality for all UI components
 */

export class BaseComponent {
    constructor() {
        this.element = null;
        this.state = {};
        this.eventListeners = new Map();
    }
    
    async init(element) {
        this.element = element;
        await this.render();
        this.setupEventListeners();
    }
    
    async render() {
        // Override in subclasses
        if (this.element) {
            this.element.innerHTML = this.getTemplate();
        }
    }
    
    getTemplate() {
        // Override in subclasses
        return '<div>Base Component</div>';
    }
    
    setupEventListeners() {
        // Override in subclasses
    }
    
    setState(newState) {
        this.state = { ...this.state, ...newState };
        this.onStateChange();
    }
    
    onStateChange() {
        // Override in subclasses
    }
    
    addEventListener(selector, event, handler) {
        if (!this.element) return;
        
        const element = selector ? this.element.querySelector(selector) : this.element;
        if (element) {
            element.addEventListener(event, handler);
            
            // Store for cleanup
            const key = `${selector || 'root'}_${event}`;
            if (!this.eventListeners.has(key)) {
                this.eventListeners.set(key, []);
            }
            this.eventListeners.get(key).push({ element, handler });
        }
    }
    
    dispatchEvent(eventName, detail) {
        const event = new CustomEvent(eventName, { detail });
        document.dispatchEvent(event);
    }
    
    showLoading(message = 'Загрузка...') {
        this.setState({ isLoading: true, loadingMessage: message });
    }
    
    hideLoading() {
        this.setState({ isLoading: false, loadingMessage: null });
    }
    
    showError(message) {
        this.setState({ error: message });
        setTimeout(() => this.setState({ error: null }), 5000);
    }
    
    showSuccess(message) {
        this.setState({ success: message });
        setTimeout(() => this.setState({ success: null }), 3000);
    }
    
    $(selector) {
        return this.element ? this.element.querySelector(selector) : null;
    }
    
    $$(selector) {
        return this.element ? this.element.querySelectorAll(selector) : [];
    }
    
    destroy() {
        // Cleanup event listeners
        this.eventListeners.forEach((listeners) => {
            listeners.forEach(({ element, handler }) => {
                element.removeEventListener(element, handler);
            });
        });
        this.eventListeners.clear();
        
        // Clear element
        if (this.element) {
            this.element.innerHTML = '';
        }
    }
    
    // Utility methods
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    formatTime(seconds) {
        if (seconds < 60) return `${seconds}с`;
        if (seconds < 3600) return `${Math.floor(seconds / 60)}м ${seconds % 60}с`;
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        return `${hours}ч ${minutes}м`;
    }
    
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
    
    throttle(func, limit) {
        let inThrottle;
        return function(...args) {
            if (!inThrottle) {
                func.apply(this, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        };
    }
}