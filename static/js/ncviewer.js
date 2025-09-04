// Simple NC Viewer for G-code visualization
class NCViewer {
    constructor(container) {
        this.container = container;
        this.scene = null;
        this.camera = null;
        this.renderer = null;
        this.controls = null;
        this.toolpath = null;
        this.animationId = null;
        
        this.init();
    }
    
    init() {
        if (!window.THREE) {
            this.container.innerHTML = '<div class="text-gray-400 p-8">Three.js не загружен</div>';
            return;
        }
        
        // Create scene
        this.scene = new THREE.Scene();
        this.scene.background = new THREE.Color(0x0a0a0a);
        
        // Create camera
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;
        this.camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000);
        this.camera.position.set(50, 50, 50);
        
        // Create renderer
        this.renderer = new THREE.WebGLRenderer({ antialias: true });
        this.renderer.setSize(width, height);
        this.renderer.shadowMap.enabled = true;
        this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
        this.container.appendChild(this.renderer.domElement);
        
        // Add lighting
        const ambientLight = new THREE.AmbientLight(0x404040, 0.6);
        this.scene.add(ambientLight);
        
        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
        directionalLight.position.set(50, 50, 50);
        directionalLight.castShadow = true;
        directionalLight.shadow.mapSize.width = 2048;
        directionalLight.shadow.mapSize.height = 2048;
        this.scene.add(directionalLight);
        
        // Add controls if available
        if (window.THREE.OrbitControls) {
            this.controls = new THREE.OrbitControls(this.camera, this.renderer.domElement);
            this.controls.enableDamping = true;
            this.controls.dampingFactor = 0.1;
        }
        
        // Add coordinate axes
        this.addAxes();
        
        // Start animation loop
        this.animate();
        
        // Handle window resize
        window.addEventListener('resize', () => this.onWindowResize());
    }
    
    addAxes() {
        const axesHelper = new THREE.AxesHelper(20);
        this.scene.add(axesHelper);
        
        // Add axis labels
        const loader = new THREE.FontLoader();
        // For now, just add simple geometry as labels
        const xLabel = new THREE.Mesh(
            new THREE.PlaneGeometry(2, 2),
            new THREE.MeshBasicMaterial({ color: 0xff0000, transparent: true, opacity: 0.8 })
        );
        xLabel.position.set(22, 0, 0);
        this.scene.add(xLabel);
        
        const yLabel = new THREE.Mesh(
            new THREE.PlaneGeometry(2, 2),
            new THREE.MeshBasicMaterial({ color: 0x00ff00, transparent: true, opacity: 0.8 })
        );
        yLabel.position.set(0, 22, 0);
        this.scene.add(yLabel);
        
        const zLabel = new THREE.Mesh(
            new THREE.PlaneGeometry(2, 2),
            new THREE.MeshBasicMaterial({ color: 0x0000ff, transparent: true, opacity: 0.8 })
        );
        zLabel.position.set(0, 0, 22);
        this.scene.add(zLabel);
    }
    
    loadGcode(gcode) {
        // Clear existing toolpath
        if (this.toolpath) {
            this.scene.remove(this.toolpath);
        }
        
        // Parse G-code and create toolpath
        const toolpath = this.parseGcode(gcode);
        if (toolpath) {
            this.scene.add(toolpath);
            this.toolpath = toolpath;
            
            // Fit camera to toolpath
            this.fitCameraToToolpath(toolpath);
        }
    }
    
    parseGcode(gcode) {
        const lines = gcode.split('\n');
        const points = [];
        let currentX = 0, currentY = 0, currentZ = 0;
        let isRapid = false;
        
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed || trimmed.startsWith('(') || trimmed.startsWith(';')) continue;
            
            // Parse G0 (rapid) and G1 (linear) moves
            if (trimmed.includes('G0')) {
                isRapid = true;
            } else if (trimmed.includes('G1')) {
                isRapid = false;
            }
            
            // Extract coordinates
            const xMatch = trimmed.match(/X(-?\d*\.?\d*)/);
            const yMatch = trimmed.match(/Y(-?\d*\.?\d*)/);
            const zMatch = trimmed.match(/Z(-?\d*\.?\d*)/);
            
            if (xMatch) currentX = parseFloat(xMatch[1]) || currentX;
            if (yMatch) currentY = parseFloat(yMatch[1]) || currentY;
            if (zMatch) currentZ = parseFloat(zMatch[1]) || currentZ;
            
            // Add point if we have coordinates
            if (xMatch || yMatch || zMatch) {
                points.push({
                    x: currentX,
                    y: currentY,
                    z: currentZ,
                    isRapid: isRapid
                });
            }
        }
        
        if (points.length < 2) return null;
        
        // Create toolpath geometry
        const geometry = new THREE.BufferGeometry();
        const positions = [];
        const colors = [];
        
        for (let i = 0; i < points.length; i++) {
            const point = points[i];
            positions.push(point.x, point.y, point.z);
            
            // Color: red for rapid moves, green for cutting moves
            if (point.isRapid) {
                colors.push(1, 0, 0); // Red
            } else {
                colors.push(0, 1, 0); // Green
            }
        }
        
        geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
        geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
        
        // Create line segments
        const indices = [];
        for (let i = 0; i < points.length - 1; i++) {
            indices.push(i, i + 1);
        }
        geometry.setIndex(indices);
        
        const material = new THREE.LineBasicMaterial({
            vertexColors: true,
            linewidth: 2
        });
        
        return new THREE.LineSegments(geometry, material);
    }
    
    fitCameraToToolpath(toolpath) {
        if (!toolpath) return;
        
        const box = new THREE.Box3().setFromObject(toolpath);
        const center = box.getCenter(new THREE.Vector3());
        const size = box.getSize(new THREE.Vector3());
        const maxDim = Math.max(size.x, size.y, size.z);
        
        // Position camera
        this.camera.position.set(
            center.x + maxDim * 1.5,
            center.y + maxDim * 1.5,
            center.z + maxDim * 1.5
        );
        this.camera.lookAt(center);
        
        if (this.controls) {
            this.controls.target.copy(center);
            this.controls.update();
        }
    }
    
    animate() {
        this.animationId = requestAnimationFrame(() => this.animate());
        
        if (this.controls) {
            this.controls.update();
        }
        
        this.renderer.render(this.scene, this.camera);
    }
    
    onWindowResize() {
        const width = this.container.clientWidth;
        const height = this.container.clientHeight;
        
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }
    
    dispose() {
        if (this.animationId) {
            cancelAnimationFrame(this.animationId);
        }
        
        if (this.renderer) {
            this.renderer.dispose();
        }
        
        if (this.container && this.renderer) {
            this.container.removeChild(this.renderer.domElement);
        }
    }
}

// Export for global use
window.NCViewer = NCViewer;