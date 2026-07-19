import uvicorn
from fastapi import FastAPI, Response, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import time
import glob
import numpy as np
import cv2
import subprocess
import asyncio

# Import local modules
from camera import StereoCameraManager
from calibration import StereoCalibrator
from neopixel_controller import NeoPixelController

# Constants
WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(WORKSPACE_DIR, "static")
DATASETS_DIR = os.path.join(WORKSPACE_DIR, "datasets")
CALIBRATION_DIR = os.path.join(DATASETS_DIR, "calibration_captures")
SCANS_DIR = os.path.join(DATASETS_DIR, "scans")
RECORDINGS_DIR = os.path.join(DATASETS_DIR, "recordings")

# Ensure directories exist
for directory in [STATIC_DIR, DATASETS_DIR, CALIBRATION_DIR, SCANS_DIR, RECORDINGS_DIR]:
    os.makedirs(directory, exist_ok=True)

# Initialize application
app = FastAPI(title="Pro3Dscan Software Backend")

# State management
camera_manager = StereoCameraManager()
calibrator = StereoCalibrator()
neopixel = NeoPixelController()

# Stereo Depth Matcher setup
stereo_matcher = cv2.StereoSGBM_create(
    minDisparity=0,
    numDisparities=16 * 6, # Must be divisible by 16
    blockSize=11,
    P1=8 * 3 * 11 ** 2,
    P2=32 * 3 * 11 ** 2,
    disp12MaxDiff=1,
    uniquenessRatio=10,
    speckleWindowSize=100,
    speckleRange=32,
    mode=cv2.STEREO_SGBM_MODE_SGBM_3WAY
)

# Set default settings
current_left_id = 0
current_right_id = 1
current_width = 640
current_height = 480

@app.get("/api/devices/scan_cameras")
async def scan_cameras():
    # Attempt to use macOS system_profiler to get real camera names
    try:
        result = subprocess.run(['system_profiler', 'SPCameraDataType'], capture_output=True, text=True)
        if result.returncode == 0:
            cameras = []
            lines = result.stdout.split('\n')
            for line in lines:
                if not line.strip(): continue
                if line.startswith('    ') and not line.startswith('      '): 
                    name = line.strip().rstrip(':')
                    if name:
                        cameras.append(name)
            
            if cameras:
                mapped = [{"id": i, "name": f"{name} (ID: {i})"} for i, name in enumerate(cameras)]
                return {"status": "success", "cameras": mapped}
    except Exception:
        pass
        
    # Fallback if not on Mac or if system_profiler fails
    # Just probe indices 0-4
    mapped = []
    for i in range(5):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            mapped.append({"id": i, "name": f"Camera Device {i}"})
            cap.release()
    return {"status": "success", "cameras": mapped}

# Pydantic models for API validation
class ConnectPortRequest(BaseModel):
    port: str
    baudrate: int = 115200

class ColorRequest(BaseModel):
    r: int
    g: int
    b: int

class PixelRequest(BaseModel):
    index: int
    r: int
    g: int
    b: int

class BrightnessRequest(BaseModel):
    val: int

class PresetRequest(BaseModel):
    preset_id: int

class DeviceSettings(BaseModel):
    left_id: int
    right_id: int
    width: int = 640
    height: int = 480

class SequenceRequest(BaseModel):
    colors: list[list[int]] # list of [R,G,B]

class ScanCaptureRequest(BaseModel):
    project_name: str = "MyProject"

class Scan360Request(BaseModel):
    count: int = 36
    project_name: str = "MyProject"

class ReconstructRequest(BaseModel):
    format: str = "usdz"
    engine: str = "local"
    files: list = []
    project_name: str = "MyProject"

class VideoRecordRequest(BaseModel):
    project_name: str = "MyProject"

class DownloadZipRequest(BaseModel):
    project_name: str = "MyProject"
    files: list[dict] # [{"type": "scan", "name": "file.png"}]

# Lifetime events
@app.on_event("startup")
async def startup_event():
    # Start default mock/real camera feeds
    camera_manager.start_streams(current_left_id, current_right_id, current_width, current_height)
    print("FastAPI server started, camera streams running.")

@app.on_event("shutdown")
async def shutdown_event():
    camera_manager.stop_streams()
    neopixel.disconnect()
    print("Server shutting down, released camera and serial resources.")

# Camera Video Streaming Generators (MJPEG)
def video_frame_generator(eye: str, rect: bool = False):
    while True:
        left, right = camera_manager.get_frames()
        frame = None
        
        if eye == "left" and left is not None:
            frame = left
        elif eye == "right" and right is not None:
            frame = right
        elif eye == "sbs" and left is not None and right is not None:
            # Handle resolution mismatch if any
            if left.shape != right.shape:
                right = cv2.resize(right, (left.shape[1], left.shape[0]))
                
            if rect and calibrator.calibrated:
                l_rect, r_rect = calibrator.rectify_pair(left, right)
                frame = np.hstack((l_rect, r_rect))
            else:
                frame = np.hstack((left, right))
                
        if frame is not None:
            # If rectified mode is active, draw alignment scanlines to help visual check
            if rect and eye == "sbs":
                # Draw horizontal lines every 30px
                for y in range(30, frame.shape[0], 30):
                    cv2.line(frame, (0, y), (frame.shape[1], y), (0, 255, 0), 1)

            ret, encoded_img = cv2.imencode('.jpg', frame)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + encoded_img.tobytes() + b'\r\n')
                       
        # Sleep to keep frame rate near 30 FPS
        time.sleep(0.033)

@app.get("/stream/left")
async def stream_left():
    return StreamingResponse(
        video_frame_generator("left"),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/stream/right")
async def stream_right():
    return StreamingResponse(
        video_frame_generator("right"),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.get("/stream/sbs")
async def stream_sbs(rectified: bool = False):
    return StreamingResponse(
        video_frame_generator("sbs", rect=rectified),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

def depth_frame_generator():
    while True:
        left, right = camera_manager.get_frames()
        if left is not None and right is not None and calibrator.calibrated:
            l_rect, r_rect = calibrator.rectify_pair(left, right)
            
            # Convert to grayscale for stereo matching
            gray_left = cv2.cvtColor(l_rect, cv2.COLOR_BGR2GRAY)
            gray_right = cv2.cvtColor(r_rect, cv2.COLOR_BGR2GRAY)
            
            # Reduce resolution for performance
            scale = 0.5
            small_left = cv2.resize(gray_left, (0, 0), fx=scale, fy=scale)
            small_right = cv2.resize(gray_right, (0, 0), fx=scale, fy=scale)
            
            # Compute disparity
            disparity = stereo_matcher.compute(small_left, small_right)
            
            # Normalize for visualization
            norm_disp = cv2.normalize(disparity, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            
            # Apply color map
            colored_depth = cv2.applyColorMap(norm_disp, cv2.COLORMAP_JET)
            
            # Resize back up if needed, but keeping it small is fine for web stream
            ret, encoded_img = cv2.imencode('.jpg', colored_depth)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + encoded_img.tobytes() + b'\r\n')
        else:
            # Fallback if not calibrated or frames missing
            placeholder = np.zeros((240, 320, 3), dtype=np.uint8)
            cv2.putText(placeholder, "Calibrate cameras first", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            ret, encoded_img = cv2.imencode('.jpg', placeholder)
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + encoded_img.tobytes() + b'\r\n')
                       
        time.sleep(0.05) # Cap at ~20 fps

@app.get("/stream/depth")
async def stream_depth():
    return StreamingResponse(
        depth_frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame"
    )

@app.websocket("/ws/pointcloud")
async def ws_pointcloud(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            left, right = camera_manager.get_frames()
            if left is not None and right is not None and calibrator.calibrated and calibrator.Q is not None:
                l_rect, r_rect = calibrator.rectify_pair(left, right)
                
                # Convert to grayscale for stereo matching
                gray_left = cv2.cvtColor(l_rect, cv2.COLOR_BGR2GRAY)
                gray_right = cv2.cvtColor(r_rect, cv2.COLOR_BGR2GRAY)
                
                # Downsample for faster stereo matching
                scale = 0.5
                small_left = cv2.resize(gray_left, (0, 0), fx=scale, fy=scale)
                small_right = cv2.resize(gray_right, (0, 0), fx=scale, fy=scale)
                
                # Compute disparity
                disparity_small = stereo_matcher.compute(small_left, small_right).astype(np.float32) / 16.0
                
                # Scale disparity back up to match Q matrix
                disparity = cv2.resize(disparity_small, (l_rect.shape[1], l_rect.shape[0]), interpolation=cv2.INTER_NEAREST) / scale
                
                # Compute 3D points
                points_3d = cv2.reprojectImageTo3D(disparity, calibrator.Q)
                
                # Downsample by striding to reduce point count sent over network (e.g. send every 4th pixel)
                stride = 4
                disp_strided = disparity[::stride, ::stride]
                color_strided = l_rect[::stride, ::stride]
                points_strided = points_3d[::stride, ::stride]
                
                # Mask out invalid points (e.g. disparity <= 0 or Z > max distance)
                mask = (disp_strided > 0) & (points_strided[:,:,2] < 2000) & (points_strided[:,:,2] > 0)
                
                valid_points = points_strided[mask]
                valid_colors = color_strided[mask]
                
                num_points = len(valid_points)
                if num_points > 0:
                    pos_bytes = valid_points.astype(np.float32).tobytes()
                    rgb = cv2.cvtColor(valid_colors.reshape(-1, 1, 3), cv2.COLOR_BGR2RGB).reshape(-1, 3)
                    col_bytes = rgb.astype(np.uint8).tobytes()
                    
                    # Header: 1 int32 for number of points
                    header = np.array([num_points], dtype=np.int32).tobytes()
                    
                    payload = header + pos_bytes + col_bytes
                    await websocket.send_bytes(payload)
                
            await asyncio.sleep(0.05) # ~20 FPS limit
    except WebSocketDisconnect:
        print("PointCloud WebSocket disconnected")

# API: Device Settings
@app.get("/api/devices")
async def get_devices():
    ports = neopixel.get_available_ports()
    return {
        "left_id": current_left_id,
        "right_id": current_right_id,
        "width": current_width,
        "height": current_height,
        "neopixel_connected": neopixel.is_connected,
        "neopixel_port": neopixel.port,
        "available_ports": ports,
        "calibration": {
            "calibrated": calibrator.calibrated,
            "captured_frames": len(calibrator.objpoints)
        }
    }

@app.post("/api/devices/update")
async def update_devices(settings: DeviceSettings):
    global current_left_id, current_right_id, current_width, current_height
    current_left_id = settings.left_id
    current_right_id = settings.right_id
    current_width = settings.width
    current_height = settings.height
    
    # Restart feeds with new settings
    camera_manager.start_streams(current_left_id, current_right_id, current_width, current_height)
    return {"status": "success", "message": "Camera configurations updated."}

# API: NeoPixel Control
@app.post("/api/neopixel/connect")
async def connect_neopixel(req: ConnectPortRequest):
    success = neopixel.connect(req.port, req.baudrate)
    if success:
        return {"status": "success", "message": f"Connected to {req.port}"}
    else:
        raise HTTPException(status_code=400, detail="Failed to connect to specified serial port.")

@app.post("/api/neopixel/disconnect")
async def disconnect_neopixel():
    neopixel.disconnect()
    return {"status": "success", "message": "Serial connection closed."}

@app.post("/api/neopixel/color")
async def set_neopixel_color(req: ColorRequest):
    neopixel.set_all(req.r, req.g, req.b)
    return {"status": "success"}

@app.post("/api/neopixel/pixel")
async def set_neopixel_pixel(req: PixelRequest):
    neopixel.set_pixel(req.index, req.r, req.g, req.b)
    return {"status": "success"}

@app.post("/api/neopixel/brightness")
async def set_neopixel_brightness(req: BrightnessRequest):
    neopixel.set_brightness(req.val)
    return {"status": "success"}

@app.post("/api/neopixel/preset")
async def trigger_preset(req: PresetRequest):
    neopixel.trigger_preset(req.preset_id)
    return {"status": "success"}

# API: Stereo Calibration
@app.post("/api/calibration/capture")
async def capture_calibration():
    left, right = camera_manager.get_frames()
    if left is None or right is None:
        raise HTTPException(status_code=400, detail="Failed to read camera frames.")
        
    success, annotated_l, annotated_r = calibrator.add_calibration_pair(left, right)
    
    if success:
        idx = len(calibrator.objpoints)
        # Save raw calibration frames for user verification
        cv2.imwrite(os.path.join(CALIBRATION_DIR, f"calib_{idx}_L.png"), left)
        cv2.imwrite(os.path.join(CALIBRATION_DIR, f"calib_{idx}_R.png"), right)
        return {
            "status": "success", 
            "message": f"Chessboard found! Added calibration frame #{idx}.",
            "count": idx
        }
    else:
        return {
            "status": "failed", 
            "message": "Chessboard pattern not found in one or both camera views. Adjust position or lighting."
        }

@app.post("/api/calibration/calibrate")
async def run_calibration():
    left, _ = camera_manager.get_frames()
    if left is None:
        raise HTTPException(status_code=400, detail="No active camera feed to determine resolution.")
        
    success, message = calibrator.calibrate(left.shape)
    if success:
        return {"status": "success", "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)

@app.post("/api/calibration/reset")
async def reset_calibration():
    calibrator.reset()
    # Clean up captured calibration files in filesystem
    files = glob.glob(os.path.join(CALIBRATION_DIR, "calib_*"))
    for f in files:
        try:
            os.remove(f)
        except Exception:
            pass
    return {"status": "success", "message": "Calibration points reset."}

# API: Image Capture (Photogrammetry Export / Scan)
@app.post("/api/scan/capture")
async def capture_scan_pair(req: ScanCaptureRequest):
    project_dir = os.path.join(SCANS_DIR, req.project_name)
    os.makedirs(project_dir, exist_ok=True)
    paths = camera_manager.capture_still_pair(project_dir, file_prefix="scan")
    if paths:
        return {
            "status": "success", 
            "message": "Stereo scan pair captured.",
            "left": os.path.basename(paths[0]),
            "right": os.path.basename(paths[1])
        }
    else:
        raise HTTPException(status_code=400, detail="Failed to capture frames. Verify cameras.")

# Automated flash & capture sequence
@app.post("/api/scan/sequence")
async def run_scan_sequence(req: SequenceRequest, background_tasks: BackgroundTasks):
    def sequence_task():
        for i, color in enumerate(req.colors):
            # 1. Set Light Color
            neopixel.set_all(color[0], color[1], color[2])
            # Wait for LEDs and auto-exposure to stabilize
            time.sleep(0.8)
            # 2. Capture Frame Pair
            prefix = f"sequence_{i}_color_{color[0]}_{color[1]}_{color[2]}"
            camera_manager.capture_still_pair(SCANS_DIR, file_prefix=prefix)
        # Turn off LEDs when done
        neopixel.set_all(0, 0, 0)
        
    background_tasks.add_task(sequence_task)
    return {"status": "success", "message": "Automated scan sequence started in background."}

scan_360_active = False

@app.post("/api/scan/360/start")
async def start_360_scan(req: Scan360Request, background_tasks: BackgroundTasks):
    global scan_360_active
    if scan_360_active:
        return {"status": "error", "message": "A 360 scan is already running."}
        
    scan_360_active = True
    
    project_dir = os.path.join(SCANS_DIR, req.project_name)
    os.makedirs(project_dir, exist_ok=True)

    def scan_task():
        global scan_360_active
        for i in range(req.count):
            if not scan_360_active:
                break
            # Trigger table turn (mocked delay for now)
            time.sleep(1)
            # Capture photo
            camera_manager.capture_still_pair(project_dir, file_prefix="scan")
            time.sleep(2.0) # 2 seconds delay for user/turntable to rotate object
            
        scan_360_active = False
            
    background_tasks.add_task(scan_task)
    return {"status": "success", "message": f"Started 360 scan for {req.count} angles in background."}

@app.post("/api/scan/360/stop")
async def stop_360_scan():
    global scan_360_active
    scan_360_active = False
    return {"status": "success", "message": "360 scan stopped."}

@app.post("/api/scan/reconstruct")
async def run_reconstruct(req: ReconstructRequest):
    # Call the local python extension script for 3D conversion
    extension_script = os.path.join(WORKSPACE_DIR, "extension_3d_converter.py")
    if not os.path.exists(extension_script):
        raise HTTPException(status_code=500, detail="Converter extension script not found.")
        
    try:
        import shutil
        project_dir = os.path.join(SCANS_DIR, req.project_name)
        target_dir = project_dir
        temp_dir = None
        
        # If specific files are selected, copy them to a temporary directory
        if req.files and len(req.files) > 0:
            temp_dir = os.path.join(DATASETS_DIR, f"temp_scans_{int(time.time())}")
            os.makedirs(temp_dir, exist_ok=True)
            for f in req.files:
                src = os.path.join(project_dir, f)
                if os.path.exists(src):
                    shutil.copy(src, temp_dir)
            target_dir = temp_dir
            
        # Run subprocess and wait for it to complete
        result = subprocess.run(["python3", extension_script, target_dir, req.format, req.engine], capture_output=True, text=True)
        
        output_file = f"reconstructed_model.{req.format}"
        
        if result.returncode == 0:
            # If we used a temp dir, copy the output file back to project_dir
            if temp_dir and os.path.exists(os.path.join(temp_dir, output_file)):
                shutil.copy(os.path.join(temp_dir, output_file), os.path.join(project_dir, output_file))
                shutil.rmtree(temp_dir)
                
            if os.path.exists(os.path.join(project_dir, output_file)):
                return {"status": "success", "message": "3D reconstruction complete.", "file": output_file}
            else:
                raise HTTPException(status_code=500, detail="Reconstruction succeeded but output file not found.")
        else:
            if temp_dir:
                shutil.rmtree(temp_dir)
            raise HTTPException(status_code=500, detail=f"Reconstruction failed: {result.stderr or result.stdout}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# API: VR Stereoscopic Video Recording
@app.post("/api/record/start")
async def start_recording(req: VideoRecordRequest):
    project_dir = os.path.join(RECORDINGS_DIR, req.project_name)
    os.makedirs(project_dir, exist_ok=True)
    if camera_manager.start_video_recording(project_dir, file_prefix="sbs_video"):
        return {"status": "success", "message": "Recording started."}
    else:
        raise HTTPException(status_code=400, detail="Recording already in progress.")

@app.post("/api/record/stop")
async def stop_recording():
    camera_manager.stop_recording()
    return {"status": "success", "message": "Recording saved."}

# API: File manager & list items
@app.get("/api/files")
async def list_files(project_name: str = "MyProject"):
    project_scans_dir = os.path.join(SCANS_DIR, project_name)
    project_recs_dir = os.path.join(RECORDINGS_DIR, project_name)
    
    scans = glob.glob(os.path.join(project_scans_dir, "*.png"))
    recordings = glob.glob(os.path.join(project_recs_dir, "*.mp4"))
    
    models = glob.glob(os.path.join(project_scans_dir, "*.3mf"))
    models.extend(glob.glob(os.path.join(project_scans_dir, "*.obj")))
    models.extend(glob.glob(os.path.join(project_scans_dir, "*.stl")))
    models.extend(glob.glob(os.path.join(project_scans_dir, "*.usdz")))
    
    return {
        "scans": [os.path.basename(s) for s in sorted(scans)],
        "recordings": [os.path.basename(r) for r in sorted(recordings)],
        "models": [os.path.basename(m) for m in sorted(models)]
    }

@app.get("/api/files/download/{file_type}/{filename}")
async def download_file(file_type: str, filename: str, project_name: str = "MyProject"):
    if file_type == "scan" or file_type == "model":
        path = os.path.join(SCANS_DIR, project_name, filename)
    elif file_type == "recording":
        path = os.path.join(RECORDINGS_DIR, project_name, filename)
    else:
        raise HTTPException(status_code=400, detail="Invalid file type.")
        
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found.")
        
    return FileResponse(path, filename=filename)

@app.delete("/api/files/{file_type}/{filename}")
async def delete_file(file_type: str, filename: str, project_name: str = "MyProject"):
    if file_type == "scan" or file_type == "model":
        path = os.path.join(SCANS_DIR, project_name, filename)
    elif file_type == "recording":
        path = os.path.join(RECORDINGS_DIR, project_name, filename)
    else:
        raise HTTPException(status_code=400, detail="Invalid file type.")
        
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found.")
        
    try:
        os.remove(path)
        return {"status": "success", "message": f"Deleted {filename}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete file: {str(e)}")

@app.post("/api/files/download_zip")
async def download_zip(req: DownloadZipRequest, background_tasks: BackgroundTasks):
    import zipfile
    import tempfile
    
    if not req.files:
        raise HTTPException(status_code=400, detail="No files selected.")
        
    temp_fd, temp_path = tempfile.mkstemp(suffix=".zip", prefix="pro3dscan_")
    os.close(temp_fd)
    
    try:
        with zipfile.ZipFile(temp_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for f in req.files:
                file_type = f.get("type")
                filename = f.get("name")
                if not file_type or not filename:
                    continue
                    
                if file_type == "scan" or file_type == "model":
                    path = os.path.join(SCANS_DIR, req.project_name, filename)
                elif file_type == "recording":
                    path = os.path.join(RECORDINGS_DIR, req.project_name, filename)
                else:
                    continue
                    
                if os.path.exists(path):
                    zipf.write(path, arcname=filename)
                    
        # Clean up temp file after response is sent
        background_tasks.add_task(os.remove, temp_path)
        return FileResponse(temp_path, media_type="application/zip", filename=f"{req.project_name}_files.zip")
    except Exception as e:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise HTTPException(status_code=500, detail=f"Failed to create ZIP: {str(e)}")

# Mount the static files directory at the root
# Note: Root index.html must be served properly
@app.get("/")
async def get_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
