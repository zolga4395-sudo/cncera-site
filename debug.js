// Debug script for CNCera
console.log('CNCera Debug Script Loaded');

// Check for common issues
function checkCommonIssues() {
    console.log('Checking for common issues...');
    
    // Check if Three.js is loaded
    if (typeof THREE === 'undefined') {
        console.error('❌ Three.js is not loaded');
        return false;
    } else {
        console.log('✅ Three.js loaded successfully');
    }
    
    // Check if required Three.js components are available
    if (typeof THREE.STLLoader === 'undefined') {
        console.warn('⚠️ STLLoader not found, trying alternative...');
    }
    
    if (typeof THREE.OrbitControls === 'undefined') {
        console.warn('⚠️ OrbitControls not found, trying alternative...');
    }
    
    // Check if required DOM elements exist
    const requiredElements = [
        'uploadForm',
        'gcodeForm', 
        'previewCanvas',
        'uploadBtn',
        'gcodeBtn'
    ];
    
    requiredElements.forEach(id => {
        const element = document.getElementById(id);
        if (!element) {
            console.error(`❌ Required element #${id} not found`);
        } else {
            console.log(`✅ Element #${id} found`);
        }
    });
    
    return true;
}

// Test API connectivity
async function testAPIConnectivity() {
    console.log('Testing API connectivity...');
    
    const endpoints = [
        { url: '/upload', method: 'POST' },
        { url: '/generate_gcode', method: 'POST' },
        { url: '/models/test.stl', method: 'GET' },
        { url: '/download_gcode', method: 'GET' },
        { url: '/download_results', method: 'GET' }
    ];
    
    for (const endpoint of endpoints) {
        try {
            const response = await fetch(endpoint.url, {
                method: endpoint.method,
                headers: {
                    'Content-Type': 'application/json'
                }
            });
            
            console.log(`✅ ${endpoint.method} ${endpoint.url}: ${response.status} ${response.statusText}`);
        } catch (error) {
            console.error(`❌ ${endpoint.method} ${endpoint.url}: ${error.message}`);
        }
    }
}

// Enhanced error handling
function setupErrorHandling() {
    window.addEventListener('error', (event) => {
        console.error('Global error:', event.error);
        console.error('Error details:', {
            message: event.message,
            filename: event.filename,
            lineno: event.lineno,
            colno: event.colno
        });
    });
    
    window.addEventListener('unhandledrejection', (event) => {
        console.error('Unhandled promise rejection:', event.reason);
    });
}

// Initialize debug
document.addEventListener('DOMContentLoaded', () => {
    console.log('DOM loaded, starting debug checks...');
    setupErrorHandling();
    checkCommonIssues();
    testAPIConnectivity();
});

// Export for manual testing
window.debugCNCera = {
    checkCommonIssues,
    testAPIConnectivity
};