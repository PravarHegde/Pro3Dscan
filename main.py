import uvicorn
from fastapi import FastAPI, Response, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import os
import time
import glob
import numpy as np
import cv2

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

# Set default settings
current_left_id = 0
current_right_id = 1
current_width = 640
current_height = 480

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
async def capture_scan_pair():
    paths = camera_manager.capture_still_pair(SCANS_DIR, file_prefix="scan")
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

# API: VR Stereoscopic Video Recording
@app.post("/api/record/start")
async def start_recording():
    timestamp = int(time.time())
    filepath = os.path.join(RECORDINGS_DIR, f"sbs_video_{timestamp}.mp4")
    success = camera_manager.start_recording(filepath)
    if success:
        return {"status": "success", "message": "Recording started.", "filename": os.path.basename(filepath)}
    else:
        raise HTTPException(status_code=400, detail="Recording already in progress.")

@app.post("/api/record/stop")
async def stop_recording():
    camera_manager.stop_recording()
    return {"status": "success", "message": "Recording saved."}

# API: File manager & list items
@app.get("/api/files")
async def list_files():
    scans = glob.glob(os.path.join(SCANS_DIR, "*.png"))
    recordings = glob.glob(os.path.join(RECORDINGS_DIR, "*.mp4"))
    
    return {
        "scans": [os.path.basename(s) for s in sorted(scans)],
        "recordings": [os.path.basename(r) for r in sorted(recordings)]
    }

@app.get("/api/files/download/{file_type}/{filename}")
async def download_file(file_type: str, filename: str):
    if file_type == "scan":
        path = os.path.join(SCANS_DIR, filename)
    elif file_type == "recording":
        path = os.path.join(RECORDINGS_DIR, filename)
    else:
        raise HTTPException(status_code=400, detail="Invalid file type.")
        
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found.")
        
    return FileResponse(path, filename=filename)

# Mount the static files directory at the root
# Note: Root index.html must be served properly
@app.get("/")
async def get_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
