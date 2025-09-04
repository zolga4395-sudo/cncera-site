let LAST_MODEL_PATH = null;

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
    const turningSettings = document.getElementById('turning_settings');
    const drillingSettings = document.getElementById('drilling_settings');

    millingSettings.style.display = 'none';
    turningSettings.style.display = 'none';
    drillingSettings.style.display = 'none';

    switch(operationType) {
        case 'milling':
        case 'roughing':
        case 'finishing':
        case 'chamfer':
            millingSettings.style.display = 'block';
            break;
        case 'turning':
            turningSettings.style.display = 'block';
            break;
        case 'drilling':
            drillingSettings.style.display = 'block';
            break;
    }
}

async function tryViewer(stlUrl) {
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
    controls.minPolarAngle = 0;
    controls.maxPolarAngle = Math.PI;
    controls.minAzimuthAngle = -Infinity;
    controls.maxAzimuthAngle = Infinity;
    controls.enablePan = true;
    controls.enableZoom = true;
    controls.enableRotate = true;

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

        const axisLength = maxDim * 0.3;
        const axisOffset = size.z / 2 + axisLength * 0.1;

        const xGeometry = new THREE.CylinderGeometry(axisLength * 0.01, axisLength * 0.01, axisLength, 8);
        const xMaterial = new THREE.MeshBasicMaterial({ color: 0xff0000 });
        const xAxis = new THREE.Mesh(xGeometry, xMaterial);
        xAxis.rotation.z = -Math.PI / 2;
        xAxis.position.set(axisLength / 2, 0, axisOffset);
        scene.add(xAxis);
        const xArrowGeometry = new THREE.ConeGeometry(axisLength * 0.03, axisLength * 0.1, 8);
        const xArrow = new THREE.Mesh(xArrowGeometry, xMaterial);
        xArrow.rotation.z = -Math.PI / 2;
        xArrow.position.set(axisLength, 0, axisOffset);
        scene.add(xArrow);

        const yGeometry = new THREE.CylinderGeometry(axisLength * 0.01, axisLength * 0.01, axisLength, 8);
        const yMaterial = new THREE.MeshBasicMaterial({ color: 0x00ff00 });
        const yAxis = new THREE.Mesh(yGeometry, yMaterial);
        yAxis.position.set(0, axisLength / 2, axisOffset);
        scene.add(yAxis);
        const yArrowGeometry = new THREE.ConeGeometry(axisLength * 0.03, axisLength * 0.1, 8);
        const yArrow = new THREE.Mesh(yArrowGeometry, yMaterial);
        yArrow.position.set(0, axisLength, axisOffset);
        scene.add(yArrow);

        const zGeometry = new THREE.CylinderGeometry(axisLength * 0.01, axisLength * 0.01, axisLength, 8);
        const zMaterial = new THREE.MeshBasicMaterial({ color: 0x0000ff });
        const zAxis = new THREE.Mesh(zGeometry, zMaterial);
        zAxis.rotation.x = Math.PI / 2;
        zAxis.position.set(0, 0, axisOffset + axisLength / 2);
        scene.add(zAxis);
        const zArrowGeometry = new THREE.ConeGeometry(axisLength * 0.03, axisLength * 0.1, 8);
        const zArrow = new THREE.Mesh(zArrowGeometry, zMaterial);
        zArrow.rotation.x = Math.PI / 2;
        zArrow.position.set(0, 0, axisOffset + axisLength);
        scene.add(zArrow);

        const originGeometry = new THREE.SphereGeometry(axisLength * 0.04, 16, 16);
        const originMaterial = new THREE.MeshBasicMaterial({ color: 0xffff00 });
        const originPoint = new THREE.Mesh(originGeometry, originMaterial);
        originPoint.position.set(0, 0, axisOffset);
        scene.add(originPoint);

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
        allowance_z: parseFloat(document.getElementById('allowance_z').value || '0')
    };

    if (operationType === 'milling' || operationType === 'roughing' || operationType === 'finishing' || operationType === 'chamfer') {
        payload.stepover = parseFloat(document.getElementById('stepover').value || '0.4');
        payload.stepdown = parseFloat(document.getElementById('stepdown').value || '0');
        payload.dir = document.getElementById('dir').value || 'X';
        payload.waterline = document.getElementById('waterline').checked;
        payload.waterline_dz = parseFloat(document.getElementById('waterline_dz').value || '0');
        payload.finish_stepover = parseFloat(document.getElementById('finish_stepover').value || '0.3');
    }

    if (operationType === 'turning') {
        payload.workpiece_diameter = parseFloat(document.getElementById('workpiece_diameter').value || '50');
        payload.cut_depth = parseFloat(document.getElementById('cut_depth').value || '1');
        payload.feed_per_rev = parseFloat(document.getElementById('feed_per_rev').value || '0.2');
        payload.turning_type = document.getElementById('turning_type').value || 'roughing';
    }

    if (operationType === 'drilling') {
        payload.drill_diameter = parseFloat(document.getElementById('drill_diameter').value || '6');
        payload.drill_depth = parseFloat(document.getElementById('drill_depth').value || '10');
        payload.drill_cycle = document.getElementById('drill_cycle').value || 'G81';
        payload.peck_depth = parseFloat(document.getElementById('peck_depth').value || '2');
    }

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

// Инициализация видимости блоков на загрузке
document.addEventListener('DOMContentLoaded', toggleOperationSettings);