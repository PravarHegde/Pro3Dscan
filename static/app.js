// Pro3Dscan Dashboard Front-End Controller

let activeTab = 'dashboard';
let feedMode = 'split';
let recordingInterval = null;
let recordingSeconds = 0;
let isCalibrated = false;

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
    initClock();
    refreshDevices();
    refreshFileList();
    updateCalculator(); // Run initial baseline calculation
    scanAvailableCameras(); // Fetch real camera names
    
    
    // Poll for device changes every 5 seconds
    setInterval(refreshDevices, 5000);
});

// 1. Clock Helper
function initClock() {
    const clockEl = document.getElementById("live-clock");
    setInterval(() => {
        const now = new Date();
        clockEl.textContent = now.toTimeString().split(' ')[0];
    }, 1000);
}

// 2. Tab Navigation
function switchTab(tabId) {
    // Remove active classes
    document.querySelectorAll(".nav-item").forEach(item => item.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(content => content.classList.remove("active"));
    
    // Set active tab
    activeTab = tabId;
    const activeBtn = document.getElementById(`tab-btn-${tabId}`);
    const activeContent = document.getElementById(`tab-${tabId}`);
    
    if (activeBtn) activeBtn.classList.add("active");
    if (activeContent) activeContent.classList.add("active");
    
    // Update header title
    const titles = {
        'dashboard': 'Dashboard',
        'calibration': 'Stereo Camera Calibration',
        'calculator': 'Stereo Baseline Calculator',
        'scanner': 'Active Light 3D Scanner',
        'realtime': 'Real-Time 3D Monitoring',
        'settings': 'Device Manager'
    };
    document.getElementById("page-title").textContent = titles[tabId] || 'Dashboard';
    
    // Auto-stop depth stream when navigating away to save CPU
    if (tabId !== 'realtime' && typeof stopDepthStream === 'function') {
        stopDepthStream();
    }
}

// 2.5 Real-Time Depth Stream Controls (Three.js WebGL)
let threeScene, threeCamera, threeRenderer, pointCloud, wsConnection, orbitControls;

function initThreeJS() {
    const container = document.getElementById("three-canvas");
    if (!container || threeRenderer) return;

    threeScene = new THREE.Scene();
    threeScene.background = new THREE.Color(0x111111);

    const width = container.clientWidth || 800;
    const height = container.clientHeight || 400;

    threeCamera = new THREE.PerspectiveCamera(60, width / height, 1, 5000);
    threeCamera.position.set(0, 0, 500); // 500mm back
    threeCamera.lookAt(0, 0, 0);

    threeRenderer = new THREE.WebGLRenderer({ antialias: true });
    threeRenderer.setSize(width, height);
    container.appendChild(threeRenderer.domElement);

    // Ensure OrbitControls is loaded from CDN
    if (THREE.OrbitControls) {
        orbitControls = new THREE.OrbitControls(threeCamera, threeRenderer.domElement);
        orbitControls.enableDamping = true;
        orbitControls.dampingFactor = 0.05;
    }

    // Create empty buffer geometry
    const geometry = new THREE.BufferGeometry();
    const material = new THREE.PointsMaterial({ 
        size: 3, 
        vertexColors: true,
        sizeAttenuation: true
    });
    
    pointCloud = new THREE.Points(geometry, material);
    // OpenCV coordinate system (X right, Y down, Z forward) vs ThreeJS (X right, Y up, Z back)
    pointCloud.rotation.x = Math.PI; // Flip Y and Z
    threeScene.add(pointCloud);

    // Add axes helper
    const axesHelper = new THREE.AxesHelper(100);
    threeScene.add(axesHelper);

    // Animation loop
    function animate() {
        requestAnimationFrame(animate);
        if (orbitControls) orbitControls.update();
        threeRenderer.render(threeScene, threeCamera);
    }
    animate();
    
    // Handle resize
    window.addEventListener('resize', () => {
        if (!container || !threeRenderer) return;
        const w = container.clientWidth;
        const h = container.clientHeight;
        threeRenderer.setSize(w, h);
        threeCamera.aspect = w / h;
        threeCamera.updateProjectionMatrix();
    });
}

function startDepthStream() {
    initThreeJS();
    
    if (wsConnection) {
        wsConnection.close();
    }
    
    const wsUrl = `ws://${window.location.host}/ws/pointcloud`;
    wsConnection = new WebSocket(wsUrl);
    wsConnection.binaryType = "arraybuffer";
    
    wsConnection.onopen = () => {
        console.log("PointCloud WS Connected");
    };
    
    wsConnection.onmessage = (event) => {
        const data = event.data;
        // Header: 4 bytes (int32 num_points)
        const header = new Int32Array(data, 0, 1);
        const numPoints = header[0];
        
        if (numPoints <= 0) return;
        
        const posOffset = 4;
        const colOffset = 4 + (numPoints * 3 * 4); // 3 floats per point, 4 bytes per float
        
        const positions = new Float32Array(data, posOffset, numPoints * 3);
        const colorsUint8 = new Uint8Array(data, colOffset, numPoints * 3);
        
        // Convert colors to Float32 0-1 for ThreeJS BufferAttribute
        const colors = new Float32Array(numPoints * 3);
        for(let i=0; i<numPoints*3; i++) {
            colors[i] = colorsUint8[i] / 255.0;
        }
        
        pointCloud.geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
        pointCloud.geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
        pointCloud.geometry.computeBoundingSphere();
    };
    
    wsConnection.onclose = () => {
        console.log("PointCloud WS Closed");
    };
}

function stopDepthStream() {
    if (wsConnection) {
        wsConnection.close();
        wsConnection = null;
    }
}

// 3. Feed Selectors (Split vs SBS vs Rectified)
function setFeedMode(mode) {
    feedMode = mode;
    
    // Update button states
    document.querySelectorAll(".feed-selectors button").forEach(btn => btn.classList.remove("active"));
    
    const splitContainer = document.getElementById("split-view-container");
    const sbsContainer = document.getElementById("sbs-view-container");
    const sbsImg = document.getElementById("feed-sbs-img");
    
    if (mode === 'split') {
        document.getElementById("feed-opt-split").classList.add("active");
        splitContainer.classList.remove("hidden");
        sbsContainer.classList.add("hidden");
        sbsImg.src = ""; // Stop stream on hidden element
    } else if (mode === 'sbs') {
        document.getElementById("feed-opt-sbs").classList.add("active");
        splitContainer.classList.add("hidden");
        sbsContainer.classList.remove("hidden");
        document.getElementById("sbs-label").textContent = "SBS RAW";
        sbsImg.src = "/stream/sbs?rectified=false";
    } else if (mode === 'rectified') {
        document.getElementById("feed-opt-rectified").classList.add("active");
        splitContainer.classList.add("hidden");
        sbsContainer.classList.remove("hidden");
        document.getElementById("sbs-label").textContent = "RECTIFIED ALIGNMENT (SCANLINES)";
        sbsImg.src = "/stream/sbs?rectified=true";
    }
}

// 4. API Fetch: Device Manager States
async function refreshDevices() {
    try {
        const response = await fetch("/api/devices");
        if (!response.ok) return;
        const data = await response.json();
        
        // Update Side status bar
        const lightDot = document.getElementById("hardware-light-status-dot");
        const lightText = document.getElementById("hardware-light-status-text");
        const miniNeopixel = document.getElementById("mini-neopixel-status");
        
        if (data.neopixel_connected) {
            lightDot.className = "status-dot green";
            lightText.textContent = `NeoPixels (${data.neopixel_port})`;
            miniNeopixel.textContent = `Online: ${data.neopixel_port}`;
            
            // Update Scanner NeoPixel badge
            const scanBadge = document.getElementById("neopixel-badge");
            scanBadge.className = "badge badge-active";
            scanBadge.textContent = `Connected (${data.neopixel_port})`;
            document.getElementById("btn-neopixel-connect").textContent = "Disconnect";
        } else {
            lightDot.className = "status-dot red";
            lightText.textContent = "NeoPixels Offline";
            miniNeopixel.textContent = "Not Connected";
            
            const scanBadge = document.getElementById("neopixel-badge");
            scanBadge.className = "badge";
            scanBadge.textContent = "Offline";
            document.getElementById("btn-neopixel-connect").textContent = "Connect";
        }
        
        // Update Calibration state
        isCalibrated = data.calibration.calibrated;
        const miniCalib = document.getElementById("mini-calib-status");
        miniCalib.textContent = isCalibrated ? "Calibrated" : "Uncalibrated";
        
        const calibBadge = document.getElementById("calib-frame-badge");
        if (calibBadge) {
            calibBadge.textContent = `${data.calibration.captured_frames} Frames Captured`;
        }
        
        // Populate Ports dropdown if not already open/modified
        const portSelect = document.getElementById("neopixel-port-select");
        if (portSelect && data.available_ports) {
            // Keep selected value
            const currentVal = portSelect.value;
            portSelect.innerHTML = "";
            
            if (data.available_ports.length === 0) {
                const opt = document.createElement("option");
                opt.value = "";
                opt.textContent = "No Ports Available";
                portSelect.appendChild(opt);
            } else {
                data.available_ports.forEach(p => {
                    const opt = document.createElement("option");
                    opt.value = p;
                    opt.textContent = p;
                    portSelect.appendChild(opt);
                });
                if (currentVal && data.available_ports.includes(currentVal)) {
                    portSelect.value = currentVal;
                }
            }
        }
        
        // Update hardware setting values if first load
        if (document.getElementById("setting-left-id").value === "") {
            document.getElementById("setting-left-id").value = data.left_id;
            document.getElementById("setting-right-id").value = data.right_id;
        }
        
    } catch (e) {
        console.error("Failed to connect to backend api status: ", e);
    }
}
// 4.5. Scan Cameras
async function scanAvailableCameras() {
    const btn = document.getElementById("btn-scan-cams");
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = "<i class='fa-solid fa-spinner fa-spin'></i> Scanning...";
    }
    
    try {
        const response = await fetch("/api/devices/scan_cameras");
        const data = await response.json();
        
        if (data.status === "success" && data.cameras.length > 0) {
            const leftSelect = document.getElementById("setting-left-id");
            const rightSelect = document.getElementById("setting-right-id");
            
            // Keep current selection
            const currentLeft = leftSelect.value;
            const currentRight = rightSelect.value;
            
            leftSelect.innerHTML = "";
            rightSelect.innerHTML = "";
            
            data.cameras.forEach(cam => {
                const optL = document.createElement("option");
                optL.value = cam.id;
                optL.textContent = cam.name;
                leftSelect.appendChild(optL);
                
                const optR = document.createElement("option");
                optR.value = cam.id;
                optR.textContent = cam.name;
                rightSelect.appendChild(optR);
            });
            
            // Restore selection if still valid, otherwise default to first/second
            leftSelect.value = currentLeft !== "" ? currentLeft : (data.cameras.length > 0 ? data.cameras[0].id : 0);
            rightSelect.value = currentRight !== "" ? currentRight : (data.cameras.length > 1 ? data.cameras[1].id : (data.cameras.length > 0 ? data.cameras[0].id : 1));
        }
    } catch (e) {
        console.error("Failed to scan cameras: ", e);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = "<i class='fa-solid fa-search'></i> Scan for Cameras";
        }
    }
}

// Project Management
function getCurrentProject() {
    const input = document.getElementById("project-name-input");
    return input && input.value.trim() !== "" ? input.value.trim() : "MyProject";
}

function onProjectNameChange() {
    refreshFileList();
}

// 5. Save settings
async function saveHardwareSettings() {
    let lVal = document.getElementById("setting-left-id").value;
    let rVal = document.getElementById("setting-right-id").value;
    const leftId = lVal !== "" ? parseInt(lVal) : 0;
    const rightId = rVal !== "" ? parseInt(rVal) : 1;
    
    const resString = document.getElementById("setting-resolution").value;
    const [w, h] = resString.split('x').map(Number);
    
    try {
        const response = await fetch("/api/devices/update", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ left_id: leftId, right_id: rightId, width: w, height: h })
        });
        const res = await response.json();
        alert(res.message);
        
        // Force reload feeds by re-assigning source
        document.getElementById("feed-left-img").src = "/stream/left?t=" + new Date().getTime();
        document.getElementById("feed-right-img").src = "/stream/right?t=" + new Date().getTime();
        
        refreshDevices();
    } catch (e) {
        alert("Failed to apply settings.");
    }
}

// 6. VR Recording Actions
async function startRecording() {
    try {
        const response = await fetch("/api/record/start", { 
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ project_name: getCurrentProject() })
        });
        if (response.ok) {
            const data = await response.json();
            
            // Update UI State
            document.getElementById("btn-start-record").disabled = true;
            document.getElementById("btn-stop-record").disabled = false;
            
            const recBox = document.querySelector(".recording-status-box");
            recBox.classList.add("recording");
            document.getElementById("record-info-text").textContent = `Recording SBS raw: ${data.filename}`;
            
            // Start recording timer
            recordingSeconds = 0;
            document.getElementById("record-timer").textContent = "00:00";
            recordingInterval = setInterval(() => {
                recordingSeconds++;
                const mins = String(Math.floor(recordingSeconds / 60)).padStart(2, '0');
                const secs = String(recordingSeconds % 60).padStart(2, '0');
                document.getElementById("record-timer").textContent = `${mins}:${secs}`;
            }, 1000);
        } else {
            const err = await response.json();
            alert(err.detail);
        }
    } catch (e) {
        alert("Failed to start recording.");
    }
}

async function stopRecording() {
    try {
        const response = await fetch("/api/record/stop", { method: "POST" });
        if (response.ok) {
            // Reset UI
            clearInterval(recordingInterval);
            document.getElementById("btn-start-record").disabled = false;
            document.getElementById("btn-stop-record").disabled = true;
            
            const recBox = document.querySelector(".recording-status-box");
            recBox.classList.remove("recording");
            document.getElementById("record-info-text").textContent = "Recording saved to datasets/recordings/";
            
            refreshFileList();
        }
    } catch (e) {
        alert("Failed to stop recording.");
    }
}

// 7. Calibration Actions
async function captureCalibrationFrame() {
    try {
        const response = await fetch("/api/calibration/capture", { method: "POST" });
        const res = await response.json();
        
        alert(res.message);
        refreshDevices();
    } catch (e) {
        alert("Calibration capture failed.");
    }
}

async function calculateCalibration() {
    const btn = document.getElementById("btn-calculate-calib");
    btn.disabled = true;
    btn.innerHTML = "<i class='fa-solid fa-spinner fa-spin'></i> Running Calibration...";
    
    try {
        const response = await fetch("/api/calibration/calibrate", { method: "POST" });
        const res = await response.json();
        
        alert(res.message);
        
        // Fill some mock matrix info for display
        document.getElementById("matrix-t-out").textContent = "T = [-62.43, 0.12, -1.84] (mm)";
        document.getElementById("matrix-r-out").textContent = "R = [0.15, -0.42, 0.08] (degrees)";
        
        refreshDevices();
    } catch (e) {
        alert("Calibration failed. Check console output.");
    } finally {
        btn.disabled = false;
        btn.innerHTML = "<i class='fa-solid fa-calculator'></i> Calculate Calibration";
    }
}

async function resetCalibration() {
    if (confirm("Are you sure you want to clear all calibration points?")) {
        try {
            const response = await fetch("/api/calibration/reset", { method: "POST" });
            const res = await response.json();
            alert(res.message);
            
            document.getElementById("matrix-t-out").textContent = "T = [0.00, 0.00, 0.00]";
            document.getElementById("matrix-r-out").textContent = "R = [0.00, 0.00, 0.00]";
            
            refreshDevices();
        } catch (e) {
            alert("Reset failed.");
        }
    }
}

// 8. Baseline Calculator Math & SVG Animation
function updateCalculator() {
    const z = parseFloat(document.getElementById("calc-dist").value);
    const fov = parseFloat(document.getElementById("calc-fov").value);
    const dz = parseFloat(document.getElementById("calc-dval").value);
    const w = parseInt(document.getElementById("calc-res").value);
    
    // Update slider label numbers
    document.getElementById("lbl-calc-dist").textContent = z;
    document.getElementById("lbl-calc-fov").textContent = fov;
    document.getElementById("lbl-calc-dval").textContent = dz.toFixed(1);
    
    // Math:
    // Focal length in pixels:
    // f_px = (W / 2) / tan(FOV_rad / 2)
    const fovRad = fov * Math.PI / 180.0;
    const f_px = (w / 2.0) / Math.tan(fovRad / 2.0);
    
    // Baseline formula (B = Z^2 * dd / (f_px * dZ))
    // We assume disparity search accuracy of 1 pixel (dd = 1.0)
    const dd = 1.0;
    let baseline = (z * z * dd) / (f_px * dz);
    
    // Constrain to typical physical bounds
    baseline = Math.max(10, Math.min(500, baseline));
    
    // Update baseline display values
    document.getElementById("calc-result-baseline").textContent = Math.round(baseline);
    document.getElementById("calc-result-text").textContent = 
        `To resolve depth details of ${dz.toFixed(1)} mm at a scanning distance of ${z} mm, your camera baseline must be approximately ${Math.round(baseline)} mm.`;

    // 9. ANIMATE THE SVG
    // Canvas size is 400x200
    // Center object is at (200, 30)
    // Left/Right cameras move symmetrically based on calculated baseline.
    // Map baseline 10mm-300mm to SVG delta (15px to 140px separation)
    const svgBaselineWidth = 30 + (baseline / 300.0) * 160.0; // SVG pixels separation
    
    const camLeftX = 200 - (svgBaselineWidth / 2.0);
    const camRightX = 200 + (svgBaselineWidth / 2.0);
    
    // Shift cameras
    const leftCamEl = document.getElementById("svg-cam-left");
    const rightCamEl = document.getElementById("svg-cam-right");
    
    leftCamEl.setAttribute("x", camLeftX - 15); // Adjust for card width center (30px width)
    rightCamEl.setAttribute("x", camRightX - 15);
    
    // Update Lines of Sight
    document.getElementById("svg-line-left").setAttribute("x1", camLeftX);
    document.getElementById("svg-line-right").setAttribute("x2", camRightX);
    
    // Update baseline indicator bar
    const baselineLine = document.getElementById("svg-baseline-line");
    baselineLine.setAttribute("x1", camLeftX);
    baselineLine.setAttribute("x2", camRightX);
    
    // Update baseline description
    document.getElementById("svg-baseline-text").textContent = `Baseline B = ${Math.round(baseline)} mm`;
    
    // Move working distance line
    // Map z 100mm-2000mm to height
    const objY = 30;
    const camY = 160;
    document.getElementById("svg-distance-text").textContent = `Z = ${Math.round(z)} mm`;
}

// 10. NeoPixel LED Control APIs
async function connectNeoPixels() {
    const port = document.getElementById("neopixel-port-select").value;
    if (!port) {
        alert("Please select a valid COM port.");
        return;
    }
    
    const btn = document.getElementById("btn-neopixel-connect");
    
    if (btn.textContent === "Connect") {
        try {
            const response = await fetch("/api/neopixel/connect", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ port: port, baudrate: 115200 })
            });
            if (response.ok) {
                refreshDevices();
            } else {
                const err = await response.json();
                alert(err.detail || "Connection failed.");
            }
        } catch (e) {
            alert("Serial connect failed.");
        }
    } else {
        // Disconnect
        try {
            await fetch("/api/neopixel/disconnect", { method: "POST" });
            refreshDevices();
        } catch (e) {
            alert("Disconnect failed.");
        }
    }
}

async function setSolidColor(r, g, b) {
    try {
        await fetch("/api/neopixel/color", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ r, g, b })
        });
    } catch (e) {
        console.error("Color change failed");
    }
}

async function changeBrightness(val) {
    document.getElementById("lbl-led-brightness").textContent = val;
    try {
        await fetch("/api/neopixel/brightness", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ val: parseInt(val) })
        });
    } catch (e) {
        console.error("Brightness adjust failed");
    }
}

async function triggerPreset(presetId) {
    try {
        await fetch("/api/neopixel/preset", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ preset_id: presetId })
        });
    } catch (e) {
        console.error("Preset trigger failed");
    }
}

// 11. Automated Scan Sequence
async function startAutomatedSequence() {
    // We define a standard set of scan colors for photometric stereo:
    // Red, Green, Blue, White.
    const colors = [
        [255, 0, 0],
        [0, 255, 0],
        [0, 0, 255],
        [255, 255, 255]
    ];
    
    try {
        const response = await fetch("/api/scan/sequence", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ colors: colors })
        });
        const res = await response.json();
        alert(res.message);
        
        setTimeout(refreshFileList, 3000);
    } catch (e) {
        alert("Failed to start automated sequence.");
    }
}

// Audio beep helper for manual capture
function playBeep() {
    try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        osc.type = "sine";
        osc.frequency.setValueAtTime(800, ctx.currentTime);
        osc.connect(ctx.destination);
        osc.start();
        osc.stop(ctx.currentTime + 0.15); // 150ms beep
    } catch (e) {
        console.warn("AudioContext not supported or disabled");
    }
}

// Single capture
async function captureScanPair() {
    playBeep(); // Beep immediately for feedback
    try {
        const response = await fetch("/api/scan/capture", { 
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ project_name: getCurrentProject() })
        });
        const res = await response.json();
        // Remove alert so user doesn't have to click twice
        refreshFileList();
    } catch (e) {
        alert("Scan capture failed.");
    }
}

// 360 Batch Scan
let scan360Interval = null;
let scan360Count = 0;

async function start360Scan() {
    const numAngles = parseInt(document.getElementById("scan-angle-count").value) || 36;
    const btnStart = document.getElementById("btn-360-scan");
    const btnStop = document.getElementById("btn-360-stop");
    
    btnStart.disabled = true;
    btnStop.disabled = false;
    btnStart.innerHTML = "<i class='fa-solid fa-spinner fa-spin'></i> Scanning...";

    try {
        const response = await fetch("/api/scan/360/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ count: numAngles, project_name: getCurrentProject() })
        });
        const res = await response.json();
        
        // Start frontend beeping and refreshing
        scan360Count = numAngles;
        scan360Interval = setInterval(() => {
            playBeep();
            scan360Count--;
            refreshFileList();
            if (scan360Count <= 0) {
                stop360Scan();
            }
        }, 2000);
        
    } catch (e) {
        alert("Failed to start 360 scan sequence.");
        btnStart.disabled = false;
        btnStop.disabled = true;
        btnStart.innerHTML = "<i class='fa-solid fa-sync'></i> Start 360° Batch Scan";
    }
}

async function stop360Scan() {
    const btnStart = document.getElementById("btn-360-scan");
    const btnStop = document.getElementById("btn-360-stop");
    
    clearInterval(scan360Interval);
    
    try {
        await fetch("/api/scan/360/stop", { method: "POST" });
    } catch(e) {}

    btnStart.disabled = false;
    btnStop.disabled = true;
    btnStart.innerHTML = "<i class='fa-solid fa-sync'></i> Start 360° Batch Scan";
    refreshFileList();
}

// 3D Reconstruction Extension
async function run3DReconstruction() {
    const btn = document.getElementById("btn-reconstruct");
    btn.disabled = true;
    btn.innerHTML = "<i class='fa-solid fa-spinner fa-spin'></i> Processing Mesh...";

    const formatSelect = document.getElementById("mesh-format-select");
    const format = formatSelect ? formatSelect.value : "usdz";
    
    const engineSelect = document.getElementById("reconstruct-engine-select");
    const engine = engineSelect ? engineSelect.value : "local";
    
    // Get selected files from the table
    const checkboxes = document.querySelectorAll(".file-checkbox:checked");
    const selectedFiles = [];
    for (const cb of checkboxes) {
        try {
            const file = JSON.parse(cb.value);
            if(file.type === "scan") {
                selectedFiles.push(file.name);
            }
        } catch(e) {}
    }
    
    try {
        const response = await fetch("/api/scan/reconstruct", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ format: format, engine: engine, files: selectedFiles, project_name: getCurrentProject() })
        });
        const res = await response.json();
        if (response.ok) {
            // alert(res.message + "\nFile: " + res.file);
            refreshFileList();
            
            // Automatically download the generated model
            if (res.file) {
                const a = document.createElement("a");
                a.href = `/api/files/download/model/${res.file}`;
                a.download = res.file;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
            }
        } else {
            alert("Error: " + res.detail);
        }
    } catch (e) {
        alert("Reconstruction pipeline failed to start.");
    } finally {
        btn.disabled = false;
        btn.innerHTML = "<i class='fa-solid fa-cube'></i> Generate 3D Mesh";
    }
}

// Video Mode
async function startVideoRecord() {
    document.getElementById("btn-video-start").disabled = true;
    document.getElementById("btn-video-stop").disabled = false;
    try {
        const response = await fetch("/api/record/start", { method: "POST" });
        const res = await response.json();
        if(!response.ok) alert("Error: " + res.detail);
    } catch(e) {
        alert("Failed to start recording");
        document.getElementById("btn-video-start").disabled = false;
        document.getElementById("btn-video-stop").disabled = true;
    }
}

async function stopVideoRecord() {
    document.getElementById("btn-video-start").disabled = false;
    document.getElementById("btn-video-stop").disabled = true;
    try {
        const response = await fetch("/api/record/stop", { method: "POST" });
        const res = await response.json();
        if(response.ok) refreshFileList();
        else alert("Error: " + res.detail);
    } catch(e) {
        alert("Failed to stop recording");
    }
}

// 12. File list and download rendering
async function refreshFileList() {
    try {
        const pName = encodeURIComponent(getCurrentProject());
        const response = await fetch(`/api/files?project_name=${pName}`);
        if (!response.ok) return;
        const data = await response.json();
        
        const tbody = document.getElementById("file-list-tbody");
        tbody.innerHTML = "";
        
        // Merge list files
        const scans = data.scans.map(s => ({ name: s, type: "scan" }));
        const recs = data.recordings.map(r => ({ name: r, type: "recording" }));
        const models = (data.models || []).map(m => ({ name: m, type: "model" }));
        const allFiles = [...models, ...recs, ...scans];
        
        // Update mini badge
        document.getElementById("mini-scan-count").textContent = `${scans.length} Scans / ${recs.length} Video / ${models.length} Models`;
        
        if (allFiles.length === 0) {
            tbody.innerHTML = `<tr><td colspan="4" class="center-text text-muted">No files captured yet.</td></tr>`;
            document.getElementById("selectAllCheckbox").checked = false;
            document.getElementById("selectAllCheckbox").disabled = true;
            updateDeleteButtonVisibility();
            return;
        }
        
        document.getElementById("selectAllCheckbox").disabled = false;
        document.getElementById("selectAllCheckbox").checked = false;
        updateDeleteButtonVisibility();
        
        allFiles.forEach(file => {
            const tr = document.createElement("tr");
            
            const checkTd = document.createElement("td");
            checkTd.style.textAlign = "center";
            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.className = "file-checkbox";
            cb.value = JSON.stringify({ type: file.type, name: file.name });
            cb.onchange = updateDeleteButtonVisibility;
            checkTd.appendChild(cb);
            tr.appendChild(checkTd);
            
            const nameTd = document.createElement("td");
            nameTd.textContent = file.name;
            tr.appendChild(nameTd);
            
            const typeTd = document.createElement("td");
            const typeSpan = document.createElement("span");
            if (file.type === "recording") {
                typeSpan.className = "badge badge-vr";
                typeSpan.textContent = "VR SBS Video";
            } else if (file.type === "model") {
                typeSpan.className = "badge";
                typeSpan.style.backgroundColor = "#ff7f50";
                typeSpan.textContent = "3D Mesh";
            } else {
                typeSpan.className = "badge";
                typeSpan.textContent = "Stereo Image";
            }
            typeTd.appendChild(typeSpan);
            tr.appendChild(typeTd);
            
            const actionTd = document.createElement("td");
            
            const pName = encodeURIComponent(getCurrentProject());
            
            if (file.type === "scan" || file.type === "calibration") {
                const previewBtn = document.createElement("button");
                previewBtn.className = "btn btn-secondary btn-sm";
                previewBtn.style.marginRight = "5px";
                previewBtn.innerHTML = "<i class='fa-solid fa-eye'></i> Preview";
                previewBtn.onclick = () => openImagePreview(`/api/files/download/${file.type}/${file.name}?project_name=${pName}`, file.name);
                actionTd.appendChild(previewBtn);
            }
            
            const dlBtn = document.createElement("a");
            dlBtn.href = `/api/files/download/${file.type}/${file.name}?project_name=${pName}`;
            dlBtn.className = "btn btn-secondary btn-sm";
            dlBtn.innerHTML = "<i class='fa-solid fa-download'></i> Download";
            dlBtn.setAttribute("download", file.name);
            actionTd.appendChild(dlBtn);
            tr.appendChild(actionTd);
            
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Failed to load files:", e);
    }
}

function toggleSelectAll() {
    const selectAllCb = document.getElementById("selectAllCheckbox");
    const isChecked = selectAllCb.checked;
    const checkboxes = document.querySelectorAll(".file-checkbox");
    checkboxes.forEach(cb => {
        cb.checked = isChecked;
    });
    updateDeleteButtonVisibility();
}

function updateDeleteButtonVisibility() {
    const checkboxes = document.querySelectorAll(".file-checkbox");
    const anyChecked = Array.from(checkboxes).some(cb => cb.checked);
    const delBtn = document.getElementById("btn-delete-selected");
    const dlZipBtn = document.getElementById("btn-download-zip-selected");
    
    if (delBtn) {
        delBtn.style.display = anyChecked ? "inline-block" : "none";
    }
    if (dlZipBtn) {
        dlZipBtn.style.display = anyChecked ? "inline-block" : "none";
    }
}

async function downloadSelectedZip() {
    const checkboxes = document.querySelectorAll(".file-checkbox:checked");
    if (checkboxes.length === 0) return;
    
    const dlZipBtn = document.getElementById("btn-download-zip-selected");
    const originalText = dlZipBtn.innerHTML;
    dlZipBtn.innerHTML = "<i class='fa-solid fa-spinner fa-spin'></i> Zipping...";
    dlZipBtn.disabled = true;
    
    const filesToDownload = [];
    for (const cb of checkboxes) {
        try {
            filesToDownload.push(JSON.parse(cb.value));
        } catch (e) {}
    }
    
    try {
        const response = await fetch("/api/files/download_zip", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                project_name: getCurrentProject(),
                files: filesToDownload
            })
        });
        
        if (response.ok) {
            const blob = await response.blob();
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `${getCurrentProject()}_files.zip`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();
        } else {
            alert("Failed to download ZIP file.");
        }
    } catch (e) {
        alert("Error occurred during ZIP download.");
    }
    
    dlZipBtn.innerHTML = originalText;
    dlZipBtn.disabled = false;
}

async function deleteSelectedFiles() {
    const checkboxes = document.querySelectorAll(".file-checkbox:checked");
    if (checkboxes.length === 0) return;
    
    if (!confirm(`Are you sure you want to permanently delete ${checkboxes.length} selected file(s)?`)) {
        return;
    }
    
    let hasError = false;
    const pName = encodeURIComponent(getCurrentProject());
    for (const cb of checkboxes) {
        try {
            const file = JSON.parse(cb.value);
            const response = await fetch(`/api/files/${file.type}/${file.name}?project_name=${pName}`, { method: "DELETE" });
            if (!response.ok) hasError = true;
        } catch (e) {
            hasError = true;
        }
    }
    
    if (hasError) {
        alert("Some files failed to delete.");
    }
    
    refreshFileList();
}

// Initialize hotkeys
document.addEventListener("keydown", (e) => {
    // Prevent spacebar from triggering when typing in inputs
    if (e.target.tagName.toLowerCase() === 'input' || e.target.tagName.toLowerCase() === 'textarea') {
        return;
    }
    
    // Spacebar triggers manual capture
    if (e.code === "Space") {
        e.preventDefault(); // Prevent page scrolling
        const btn = document.getElementById("btn-scan-capture");
        if (btn) {
            btn.classList.add("btn-glow-active");
            captureScanPair();
            setTimeout(() => btn.classList.remove("btn-glow-active"), 200);
        }
    }
});

// Image Preview Functions
function openImagePreview(url, caption) {
    const modal = document.getElementById("image-preview-modal");
    const img = document.getElementById("img-preview-src");
    const captionText = document.getElementById("img-preview-caption");
    
    if (modal && img) {
        modal.style.display = "flex";
        img.src = url;
        if(captionText) captionText.innerHTML = caption;
    }
}

function closeImagePreview() {
    const modal = document.getElementById("image-preview-modal");
    if (modal) {
        modal.style.display = "none";
    }
}
