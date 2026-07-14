# Pro3Dscan 🚀

![Pro3Dscan Dashboard](docs/dashboard.png) *(Note: Please add a screenshot of your dashboard here at `docs/dashboard.png`)*

**Pro3Dscan** is a powerful, open-source, and modular 3D scanning dashboard. It bridges the gap between high-end professional active-light 3D scanners and affordable DIY photogrammetry setups. By combining stereoscopic camera control, automated photometric stereo lighting (via NeoPixels), and batch capturing, Pro3Dscan provides a seamless pipeline from physical object to 3D mesh.

Whether you're scanning for game assets, 3D printing, VR environments, or digital archiving, Pro3Dscan is designed to be your central control hub.

---

## ✨ Features

* 📷 **Dual Camera Stereoscopic Support:** Manage and stream synchronized Left and Right camera feeds.
* 🎯 **Camera Calibration Suite:** Built-in tools for capturing chessboard patterns and calculating camera intrinsics/extrinsics to correct lens distortion.
* 📐 **Stereo Baseline Calculator:** Interactive visual tool to calculate the exact distance needed between your cameras based on working distance and desired depth accuracy.
* 💡 **NeoPixel Lighting Control:** Connect an Arduino/ESP32 via USB serial to control NeoPixel rings/strips. Enables **Photometric Stereo** scanning (taking photos under Red, Green, Blue, and White lights automatically).
* 🔄 **360° Batch Scanning:** Easily capture 25-100 angle shots sequentially. Ideal for turntable setups.
* 🧊 **3D Reconstruction Pipeline:** Built-in hooks for extending the software with mesh generators (like Meshroom, Polycam APIs, or Probharath software). Converts your datasets into `.stl` or `.3mf` files.
* 🥽 **VR Video Recording:** Record raw Side-By-Side (SBS) video directly to mp4 for stereoscopic viewing.

---

## 🛠️ Hardware Requirements

* 2x USB Webcams (e.g., Zebronics, Logitech) mounted securely on a rigid bar.
* *(Optional but Recommended)* Turntable for 360° scanning.
* *(Optional)* Arduino or microcontroller driving WS2812B NeoPixels connected via USB for active lighting control.

---

## 🚀 Installation & Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/PravarHegde/Pro3Dscan.git
   cd Pro3Dscan
   ```

2. **Create a virtual environment (Recommended):**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application:**
   ```bash
   python3 main.py
   ```

5. **Open the Dashboard:**
   Navigate to `http://localhost:8000` in your web browser.

---

## 📖 How to Use

### 1. Setup Your Cameras
Go to the **Device Manager** tab (Gear icon) to assign your Left and Right camera indices (e.g., `1` and `2`) and set your target resolution.

### 2. Calibrate
Go to the **Calibration** tab. Hold a standard OpenCV chessboard pattern in front of both cameras and click "Capture Calibration Frame". Capture at least 15-20 frames from different angles, then click "Calculate Calibration".

### 3. Scan & Reconstruct
Go to the **Active Light 3D Scanner** tab:
- Use **Capture Stereo Scan Pair** for a single shot.
- Use **360° Multi-Angle Batch Scan** for a full sequence (e.g., 36 photos). You'll be given 2 seconds between shots to rotate your turntable.
- Once done, click **Generate 3D Mesh (.3mf)** to run the reconstruction extension pipeline.

### 4. Download Your Files
All raw scans, calibration frames, and generated 3D meshes are securely saved in the `datasets/` folder. You can download them directly from the table at the bottom of the dashboard.

---

## 🔌 Hardware Extension (NeoPixels)
If you are using NeoPixels, flash your microcontroller with a script that listens to the Serial port for RGB commands. Connect it to your PC, go to the Pro3Dscan dashboard, select the COM Port, and connect. The scanner will automatically use the lights during "Automated Scan Sequences".

## 🗺️ Roadmap
- [ ] Add advanced active structured light features (laser mesh/line scanning) as an add-on.
- [ ] Direct integration with Probharath 3D software pipeline.
- [ ] Real-time disparity map preview in the dashboard.

---

*Built for makers, researchers, and 3D enthusiasts.* 🚀
