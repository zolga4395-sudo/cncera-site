/**
 * NC Viewer - 3D G-code and STL visualization
 * Uses three.js with fallback to PNG preview
 */

window.NCV = (function() {
    'use strict';
    
    let scene, camera, renderer, controls;
    let container, isInitialized = false;
    let currentGcode = null;
    let currentSTL = null;
    let gcodeGroup, stlGroup;
    let originMarker, gridHelper, axesHelper;
    
    // Configuration
    const config = {
        cameraDistance: 200,
        backgroundColor: 0x0a0a0a,
        gridSize: 100,
        gridDivisions: 20,
        axisLength: 50,
        originMarkerSize: 2
    };
    
    /**
     * Initialize the NC Viewer
     * @param {string} containerSelector - CSS selector for container
     * @returns {boolean} - Success status
     */
    function init(containerSelector) {
        try {
            container = document.querySelector(containerSelector);
            if (!container) {
                console.warn('NC Viewer: Container not found:', containerSelector);
                return false;
            }
            
            // Check for three.js availability
            if (typeof THREE === 'undefined') {
                showFallback('Three.js not available');
                return false;
            }
            
            // Check for required three.js components
            if (!THREE.OrbitControls || !THREE.STLLoader) {
                showFallback('Three.js components not available');
                return false;
            }
            
            // Check for WebGL support
            if (!isWebGLSupported()) {
                showFallback('WebGL not supported');
                return false;
            }
            
            setupScene();
            setupCamera();
            setupRenderer();
            setupControls();
            setupLighting();
            setupHelpers();
            setupEventListeners();
            
            isInitialized = true;
            console.log('NC Viewer initialized successfully');
            return true;
            
        } catch (error) {
            console.warn('NC Viewer initialization failed:', error);
            showFallback('Initialization failed: ' + error.message);
            return false;
        }
    }
    
    /**
     * Setup the three.js scene
     */
    function setupScene() {
        scene = new THREE.Scene();
        scene.background = new THREE.Color(config.backgroundColor);
        
        // Create groups for organization
        gcodeGroup = new THREE.Group();
        stlGroup = new THREE.Group();
        scene.add(gcodeGroup);
        scene.add(stlGroup);
    }
    
    /**
     * Setup the camera
     */
    function setupCamera() {
        const aspect = container.clientWidth / container.clientHeight;
        camera = new THREE.PerspectiveCamera(75, aspect, 0.1, 10000);
        camera.position.set(config.cameraDistance, config.cameraDistance * 0.8, config.cameraDistance * 0.8);
        camera.lookAt(0, 0, 0);
    }
    
    /**
     * Setup the renderer
     */
    function setupRenderer() {
        renderer = new THREE.WebGLRenderer({ 
            antialias: true,
            alpha: false
        });
        renderer.setSize(container.clientWidth, container.clientHeight);
        renderer.setPixelRatio(window.devicePixelRatio);
        renderer.shadowMap.enabled = true;
        renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        
        container.appendChild(renderer.domElement);
    }
    
    /**
     * Setup orbit controls
     */
    function setupControls() {
        controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.1;
        controls.minPolarAngle = 0;
        controls.maxPolarAngle = Math.PI;
        controls.minAzimuthAngle = -Infinity;
        controls.maxAzimuthAngle = Infinity;
        controls.enablePan = true;
        controls.enableZoom = true;
        controls.enableRotate = true;
        controls.maxDistance = 1000;
        controls.minDistance = 10;
    }
    
    /**
     * Setup lighting
     */
    function setupLighting() {
        // Ambient light
        const ambientLight = new THREE.AmbientLight(0x404040, 0.3);
        scene.add(ambientLight);
        
        // Directional light 1
        const directionalLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
        directionalLight1.position.set(1, 1, 1);
        directionalLight1.castShadow = true;
        directionalLight1.shadow.mapSize.width = 2048;
        directionalLight1.shadow.mapSize.height = 2048;
        scene.add(directionalLight1);
        
        // Directional light 2
        const directionalLight2 = new THREE.DirectionalLight(0xffffff, 0.5);
        directionalLight2.position.set(-1, -1, -1);
        scene.add(directionalLight2);
    }
    
    /**
     * Setup helper objects
     */
    function setupHelpers() {
        // Grid helper
        gridHelper = new THREE.GridHelper(config.gridSize, config.gridDivisions, 0x444444, 0x444444);
        gridHelper.position.y = -0.01; // Slightly below origin
        scene.add(gridHelper);
        
        // Axes helper
        axesHelper = new THREE.AxesHelper(config.axisLength);
        scene.add(axesHelper);
        
        // Origin marker
        const originGeometry = new THREE.SphereGeometry(config.originMarkerSize, 16, 16);
        const originMaterial = new THREE.MeshBasicMaterial({ color: 0xffff00 });
        originMarker = new THREE.Mesh(originGeometry, originMaterial);
        originMarker.position.set(0, 0, 0);
        scene.add(originMarker);
    }
    
    /**
     * Setup event listeners
     */
    function setupEventListeners() {
        // Window resize
        window.addEventListener('resize', onWindowResize, false);
        
        // Animation loop
        animate();
    }
    
    /**
     * Animation loop
     */
    function animate() {
        requestAnimationFrame(animate);
        
        if (controls) {
            controls.update();
        }
        
        if (renderer && scene && camera) {
            renderer.render(scene, camera);
        }
    }
    
    /**
     * Handle window resize
     */
    function onWindowResize() {
        if (!camera || !renderer || !container) return;
        
        const width = container.clientWidth;
        const height = container.clientHeight;
        
        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height);
    }
    
    /**
     * Render G-code toolpath
     * @param {string} gcodeText - G-code content
     */
    function renderGcode(gcodeText) {
        if (!isInitialized) {
            console.warn('NC Viewer not initialized');
            return false;
        }
        
        try {
            currentGcode = gcodeText;
            clearGcode();
            
            if (!gcodeText || gcodeText.trim() === '') {
                console.warn('Empty G-code provided');
                return false;
            }
            
            const toolpath = parseGcode(gcodeText);
            if (toolpath.length === 0) {
                console.warn('No valid toolpath found in G-code');
                return false;
            }
            
            createToolpathVisualization(toolpath);
            fitToView();
            
            console.log('G-code rendered successfully');
            return true;
            
        } catch (error) {
            console.warn('G-code rendering failed:', error);
            return false;
        }
    }
    
    /**
     * Render STL model
     * @param {string|Blob} urlOrBlob - STL file URL or Blob
     */
    function renderSTL(urlOrBlob) {
        if (!isInitialized) {
            console.warn('NC Viewer not initialized');
            return false;
        }
        
        try {
            clearSTL();
            
            const loader = new THREE.STLLoader();
            loader.load(
                urlOrBlob,
                function(geometry) {
                    const material = new THREE.MeshPhongMaterial({ 
                        color: 0x88aaff,
                        specular: 0x222222,
                        shininess: 30
                    });
                    
                    const mesh = new THREE.Mesh(geometry, material);
                    mesh.castShadow = true;
                    mesh.receiveShadow = true;
                    
                    // Center the model
                    geometry.computeBoundingBox();
                    const boundingBox = geometry.boundingBox;
                    const center = boundingBox.getCenter(new THREE.Vector3());
                    mesh.position.sub(center);
                    
                    stlGroup.add(mesh);
                    currentSTL = mesh;
                    
                    fitToView();
                    console.log('STL model loaded successfully');
                },
                function(progress) {
                    console.log('STL loading progress:', (progress.loaded / progress.total * 100) + '%');
                },
                function(error) {
                    console.warn('STL loading failed:', error);
                }
            );
            
            return true;
            
        } catch (error) {
            console.warn('STL rendering failed:', error);
            return false;
        }
    }
    
    /**
     * Parse G-code and extract toolpath
     * @param {string} gcodeText - G-code content
     * @returns {Array} - Array of toolpath points
     */
    function parseGcode(gcodeText) {
        const lines = gcodeText.split('\n');
        const toolpath = [];
        let currentPos = { x: 0, y: 0, z: 0 };
        let isRapid = false;
        
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith('(') || trimmed.startsWith(';')) continue;
            
            // Parse G0 (rapid) and G1 (linear) moves
            if (trimmed.startsWith('G0') || trimmed.startsWith('G1')) {
                isRapid = trimmed.startsWith('G0');
                
                const xMatch = trimmed.match(/X([+-]?\d*\.?\d+)/);
                const yMatch = trimmed.match(/Y([+-]?\d*\.?\d+)/);
                const zMatch = trimmed.match(/Z([+-]?\d*\.?\d+)/);
                
                if (xMatch) currentPos.x = parseFloat(xMatch[1]);
                if (yMatch) currentPos.y = parseFloat(yMatch[1]);
                if (zMatch) currentPos.z = parseFloat(zMatch[1]);
                
                toolpath.push({
                    x: currentPos.x,
                    y: currentPos.y,
                    z: currentPos.z,
                    isRapid: isRapid
                });
            }
        }
        
        return toolpath;
    }
    
    /**
     * Create toolpath visualization
     * @param {Array} toolpath - Array of toolpath points
     */
    function createToolpathVisualization(toolpath) {
        if (toolpath.length < 2) return;
        
        const geometry = new THREE.BufferGeometry();
        const positions = [];
        const colors = [];
        const indices = [];
        
        // Create line segments
        for (let i = 0; i < toolpath.length - 1; i++) {
            const current = toolpath[i];
            const next = toolpath[i + 1];
            
            // Add vertices
            positions.push(current.x, current.y, current.z);
            positions.push(next.x, next.y, next.z);
            
            // Add colors (orange for rapid, blue for feed)
            const color = current.isRapid ? new THREE.Color(0xf59e0b) : new THREE.Color(0x3b82f6);
            colors.push(color.r, color.g, color.b);
            colors.push(color.r, color.g, color.b);
            
            // Add line indices
            indices.push(i * 2, i * 2 + 1);
        }
        
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
        geometry.setIndex(indices);
        
        const material = new THREE.LineBasicMaterial({ 
            vertexColors: true,
            linewidth: 2
        });
        
        const toolpathMesh = new THREE.LineSegments(geometry, material);
        gcodeGroup.add(toolpathMesh);
    }
    
    /**
     * Clear G-code visualization
     */
    function clearGcode() {
        if (gcodeGroup) {
            gcodeGroup.clear();
        }
    }
    
    /**
     * Clear STL model
     */
    function clearSTL() {
        if (stlGroup) {
            stlGroup.clear();
        }
        currentSTL = null;
    }
    
    /**
     * Clear all content
     */
    function clear() {
        clearGcode();
        clearSTL();
    }
    
    /**
     * Fit view to content
     */
    function fitToView() {
        if (!camera || !controls) return;
        
        const box = new THREE.Box3();
        
        // Include G-code toolpath
        gcodeGroup.traverse(function(child) {
            if (child.geometry) {
                box.expandByObject(child);
            }
        });
        
        // Include STL model
        stlGroup.traverse(function(child) {
            if (child.geometry) {
                box.expandByObject(child);
            }
        });
        
        if (box.isEmpty()) return;
        
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        const distance = maxDim * 2;
        
        camera.position.set(
            center.x + distance,
            center.y + distance * 0.8,
            center.z + distance * 0.8
        );
        camera.lookAt(center);
        controls.target.copy(center);
        controls.update();
    }
    
    /**
     * Show fallback content
     * @param {string} message - Fallback message
     */
    function showFallback(message) {
        if (!container) return;
        
        container.innerHTML = `
            <div class="ncviewer-placeholder">
                <h3>NC Viewer Unavailable</h3>
                <p>${message}</p>
                <p>Falling back to PNG preview...</p>
            </div>
        `;
    }
    
    /**
     * Check WebGL support
     * @returns {boolean} - WebGL support status
     */
    function isWebGLSupported() {
        try {
            const canvas = document.createElement('canvas');
            return !!(window.WebGLRenderingContext && 
                     (canvas.getContext('webgl') || canvas.getContext('experimental-webgl')));
        } catch (e) {
            return false;
        }
    }
    
    /**
     * Get viewer info
     * @returns {Object} - Viewer information
     */
    function getInfo() {
        return {
            initialized: isInitialized,
            hasGcode: currentGcode !== null,
            hasSTL: currentSTL !== null,
            webglSupported: isWebGLSupported(),
            threejsAvailable: typeof THREE !== 'undefined'
        };
    }
    
    // Public API
    return {
        init: init,
        renderGcode: renderGcode,
        renderSTL: renderSTL,
        clear: clear,
        getInfo: getInfo
    };
})();

// Global function for backward compatibility
window.renderGcode = function(gcodeText) {
    return window.NCV.renderGcode(gcodeText);
};