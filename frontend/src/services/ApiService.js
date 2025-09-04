/**
 * API Service for CNCera Backend Communication
 * Handles all HTTP requests to the backend API
 */

export class ApiService {
    constructor() {
        this.baseURL = this.getBaseURL();
        this.timeout = 30000; // 30 seconds
        this.retryAttempts = 3;
        this.retryDelay = 1000; // 1 second
    }
    
    getBaseURL() {
        // Development: use webpack proxy
        // Production: use environment variable or same origin
        if (process.env.NODE_ENV === 'development') {
            return 'http://127.0.0.1:5000/api';
        }
        return window.location.origin + '/api';
    }
    
    /**
     * Generic HTTP request method
     */
    async request(method, endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const config = {
            method: method.toUpperCase(),
            headers: {
                'Content-Type': 'application/json',
                ...options.headers
            },
            ...options
        };
        
        // Add timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), this.timeout);
        config.signal = controller.signal;
        
        try {
            const response = await this.fetchWithRetry(url, config);
            clearTimeout(timeoutId);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                return await response.json();
            }
            
            return response;
            
        } catch (error) {
            clearTimeout(timeoutId);
            
            if (error.name === 'AbortError') {
                throw new Error('Запрос превысил время ожидания');
            }
            
            throw error;
        }
    }
    
    /**
     * Fetch with retry logic
     */
    async fetchWithRetry(url, config, attempt = 1) {
        try {
            return await fetch(url, config);
        } catch (error) {
            if (attempt < this.retryAttempts && this.isRetryableError(error)) {
                console.warn(`Request failed (attempt ${attempt}), retrying...`, error);
                await this.delay(this.retryDelay * attempt);
                return this.fetchWithRetry(url, config, attempt + 1);
            }
            throw error;
        }
    }
    
    isRetryableError(error) {
        return (
            error.name === 'TypeError' || // Network error
            error.name === 'NetworkError' ||
            (error.message && error.message.includes('fetch'))
        );
    }
    
    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
    
    // HTTP Methods
    async get(endpoint, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const url = queryString ? `${endpoint}?${queryString}` : endpoint;
        return this.request('GET', url);
    }
    
    async post(endpoint, data = {}) {
        return this.request('POST', endpoint, {
            body: JSON.stringify(data)
        });
    }
    
    async put(endpoint, data = {}) {
        return this.request('PUT', endpoint, {
            body: JSON.stringify(data)
        });
    }
    
    async delete(endpoint) {
        return this.request('DELETE', endpoint);
    }
    
    /**
     * Upload file with progress tracking
     */
    async uploadFile(file, progressCallback = null) {
        const formData = new FormData();
        formData.append('file', file);
        
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            
            // Progress tracking
            if (progressCallback) {
                xhr.upload.addEventListener('progress', (event) => {
                    if (event.lengthComputable) {
                        const progress = Math.round((event.loaded * 100) / event.total);
                        progressCallback(progress);
                    }
                });
            }
            
            // Response handling
            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        resolve(response);
                    } catch (error) {
                        reject(new Error('Ошибка парсинга ответа сервера'));
                    }
                } else {
                    reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
                }
            });
            
            xhr.addEventListener('error', () => {
                reject(new Error('Ошибка сети при загрузке файла'));
            });
            
            xhr.addEventListener('timeout', () => {
                reject(new Error('Превышено время ожидания загрузки'));
            });
            
            // Configure and send
            xhr.timeout = this.timeout;
            xhr.open('POST', `${this.baseURL}/upload`);
            xhr.send(formData);
        });
    }
    
    /**
     * Download file
     */
    async downloadFile(url, filename = null) {
        try {
            const response = await fetch(`${this.baseURL}${url}`);
            
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }
            
            const blob = await response.blob();
            
            // Create download link
            const downloadUrl = window.URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = downloadUrl;
            link.download = filename || this.getFilenameFromUrl(url);
            
            // Trigger download
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            
            // Cleanup
            window.URL.revokeObjectURL(downloadUrl);
            
            return true;
            
        } catch (error) {
            console.error('Download failed:', error);
            throw error;
        }
    }
    
    getFilenameFromUrl(url) {
        return url.split('/').pop() || 'download';
    }
    
    // API Endpoints
    
    /**
     * Health check
     */
    async checkHealth() {
        return this.get('/health');
    }
    
    /**
     * Get API info
     */
    async getInfo() {
        return this.get('/info');
    }
    
    /**
     * Upload and analyze file
     */
    async uploadAndAnalyze(file, options = {}, progressCallback = null) {
        const formData = new FormData();
        formData.append('file', file);
        
        // Add options to form data
        Object.entries(options).forEach(([key, value]) => {
            formData.append(key, value);
        });
        
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            
            if (progressCallback) {
                xhr.upload.addEventListener('progress', (event) => {
                    if (event.lengthComputable) {
                        const progress = Math.round((event.loaded * 100) / event.total);
                        progressCallback(progress);
                    }
                });
            }
            
            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        resolve(response);
                    } catch (error) {
                        reject(new Error('Ошибка парсинга ответа'));
                    }
                } else {
                    reject(new Error(`HTTP ${xhr.status}: ${xhr.statusText}`));
                }
            });
            
            xhr.addEventListener('error', () => {
                reject(new Error('Ошибка сети'));
            });
            
            xhr.open('POST', `${this.baseURL}/upload`);
            xhr.send(formData);
        });
    }
    
    /**
     * AI Chat
     */
    async aiChat(message, sessionId, context = null) {
        return this.post('/ai/chat', {
            message,
            session_id: sessionId,
            context
        });
    }
    
    /**
     * AI Analysis
     */
    async aiAnalyze(modelPath) {
        return this.post('/ai/analyze', {
            model_path: modelPath
        });
    }
    
    /**
     * AI Generate Parameters
     */
    async aiGenerateParams(modelPath, requirements) {
        return this.post('/ai/generate-params', {
            model_path: modelPath,
            requirements
        });
    }
    
    /**
     * Generate G-code
     */
    async generateGcode(params) {
        return this.post('/gcode/generate', params);
    }
    
    /**
     * Preview G-code
     */
    async previewGcode(gcodeFilename) {
        return this.post('/gcode/preview', {
            gcode_filename: gcodeFilename
        });
    }
    
    /**
     * Validate G-code parameters
     */
    async validateGcodeParams(params) {
        return this.post('/gcode/validate', params);
    }
    
    /**
     * List files
     */
    async listFiles() {
        return this.get('/files/list');
    }
    
    /**
     * Download G-code
     */
    async downloadGcode(filename) {
        return this.downloadFile(`/files/gcode/${filename}`, filename);
    }
    
    /**
     * Download result
     */
    async downloadResult(filename) {
        return this.downloadFile(`/files/results/${filename}`, filename);
    }
    
    /**
     * Cleanup files
     */
    async cleanupFiles(type = 'temp') {
        return this.post('/files/cleanup', { type });
    }
}