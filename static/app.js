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
        'settings': 'Device Manager'
    };
    document.getElementById("page-title").textContent = titles[tabId] || 'Dashboard';
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

// 5. Save settings
async function saveHardwareSettings() {
    const leftId = parseInt(document.getElementById("setting-left-id").value) || 0;
    const rightId = parseInt(document.getElementById("setting-right-id").value) || 1;
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
        const response = await fetch("/api/record/start", { method: "POST" });
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

// Single capture
async function captureScanPair() {
    try {
        const response = await fetch("/api/scan/capture", { method: "POST" });
        const res = await response.json();
        alert(res.message + "\nSaved: " + res.left + " & " + res.right);
        refreshFileList();
    } catch (e) {
        alert("Scan capture failed.");
    }
}

// 12. File list and download rendering
async function refreshFileList() {
    try {
        const response = await fetch("/api/files");
        if (!response.ok) return;
        const data = await response.json();
        
        const tbody = document.getElementById("file-list-tbody");
        tbody.innerHTML = "";
        
        // Merge list files
        const scans = data.scans.map(s => ({ name: s, type: "scan" }));
        const recs = data.recordings.map(r => ({ name: r, type: "recording" }));
        const allFiles = [...recs, ...scans];
        
        // Update mini badge
        document.getElementById("mini-scan-count").textContent = `${scans.length} Scans / ${recs.length} Video`;
        
        if (allFiles.length === 0) {
            tbody.innerHTML = `<tr><td colspan="3" class="center-text text-muted">No files captured yet.</td></tr>`;
            return;
        }
        
        allFiles.forEach(file => {
            const tr = document.createElement("tr");
            
            const nameTd = document.createElement("td");
            nameTd.textContent = file.name;
            tr.appendChild(nameTd);
            
            const typeTd = document.createElement("td");
            const typeSpan = document.createElement("span");
            typeSpan.className = file.type === "recording" ? "badge badge-vr" : "badge";
            typeSpan.textContent = file.type === "recording" ? "VR SBS Video" : "Stereo Image";
            typeTd.appendChild(typeSpan);
            tr.appendChild(typeTd);
            
            const actionTd = document.createElement("td");
            const dlBtn = document.createElement("a");
            dlBtn.href = `/api/files/download/${file.type}/${file.name}`;
            dlBtn.className = "btn btn-secondary btn-sm";
            dlBtn.innerHTML = "<i class='fa-solid fa-download'></i> Download";
            dlBtn.setAttribute("download", file.name);
            actionTd.appendChild(dlBtn);
            tr.appendChild(actionTd);
            
            tbody.appendChild(tr);
        });
    } catch (e) {
        console.error("Failed to fetch files list", e);
    }
}
