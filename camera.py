import cv2
import time
import threading
import numpy as np
import os
import math

class CameraThread(threading.Thread):
    def __init__(self, camera_id, width=640, height=480):
        super().__init__()
        self.camera_id = camera_id
        self.width = width
        self.height = height
        self.cap = None
        self.frame = None
        self.running = False
        self.lock = threading.Lock()
        self.is_mock = False
        
        # Mock engine variables
        self.angle_x = 0
        self.angle_y = 0
        self.angle_z = 0
        
    def run(self):
        self.running = True
        
        # Try to open the physical camera
        try:
            # Check if camera_id is an integer (for physical webcam) or path
            cid = int(self.camera_id) if str(self.camera_id).isdigit() else self.camera_id
            self.cap = cv2.VideoCapture(cid)
            if self.cap.isOpened():
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
                # Verify actual resolution
                self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            else:
                self.is_mock = True
        except Exception:
            self.is_mock = True
            
        if self.is_mock:
            print(f"[Camera {self.camera_id}] Web camera not found. Initializing stereo simulator.")
            
        last_time = time.time()
        while self.running:
            if not self.is_mock and self.cap and self.cap.isOpened():
                ret, frame = self.cap.read()
                if ret:
                    with self.lock:
                        self.frame = frame.copy()
                else:
                    time.sleep(0.01)
            else:
                # Mock Frame Generation (Simulated 3D Engine with Stereo Disparity)
                now = time.time()
                dt = now - last_time
                last_time = now
                
                # Update mock rotation angles
                self.angle_x += dt * 0.5
                self.angle_y += dt * 0.8
                self.angle_z += dt * 0.3
                
                frame = self.generate_mock_frame(self.camera_id)
                with self.lock:
                    self.frame = frame
                # Limit to ~30 FPS
                sleep_time = max(0.001, 0.033 - (time.time() - now))
                time.sleep(sleep_time)
                
        if self.cap and self.cap.isOpened():
            self.cap.release()

    def get_frame(self):
        with self.lock:
            if self.frame is not None:
                return self.frame.copy()
            return None

    def stop(self):
        self.running = False

    def generate_mock_frame(self, cam_type):
        """Generates a mock frame of a 3D rotating cube projected onto a stereo camera sensor."""
        # Create blank dark blue canvas
        canvas = np.zeros((self.height, self.width, 3), dtype=np.uint8)
        
        # Grid lines in background
        for y in range(0, self.height, 40):
            cv2.line(canvas, (0, y), (self.width, y), (15, 15, 25), 1)
        for x in range(0, self.width, 40):
            cv2.line(canvas, (x, 0), (x, self.height), (15, 15, 25), 1)

        # 3D Cube vertices (centered at X=0, Y=0, Z=400 mm)
        # Cube size = 120 mm
        size = 60
        vertices = [
            [-size, -size, -size],
            [size, -size, -size],
            [size, size, -size],
            [-size, size, -size],
            [-size, -size, size],
            [size, -size, size],
            [size, size, size],
            [-size, size, size]
        ]
        
        # Stereo geometry parameters
        # Baseline B (distance between cameras) = 60 mm
        # Focal length in pixels f = 500
        # Principal point (u0, v0) = (width/2, height/2)
        B = 60.0
        f = 500.0
        u0 = self.width / 2.0
        v0 = self.height / 2.0
        
        # Offset along X-axis depending on Left vs Right camera
        # If cam_type is 0 or 'left', it's Left Camera (offset +B/2 in world coordinates, meaning camera is at -B/2)
        # If cam_type is 1 or 'right', it's Right Camera (offset -B/2 in world coordinates, meaning camera is at +B/2)
        is_left = (str(cam_type).lower() in ['0', 'left'])
        x_offset = B / 2.0 if is_left else -B / 2.0
        
        # Rotate vertices
        rotated_vertices = []
        for x, y, z in vertices:
            # Rotate X
            xy = y * math.cos(self.angle_x) - z * math.sin(self.angle_x)
            xz = y * math.sin(self.angle_x) + z * math.cos(self.angle_x)
            
            # Rotate Y
            yx = x * math.cos(self.angle_y) + xz * math.sin(self.angle_y)
            yz = -x * math.sin(self.angle_y) + xz * math.cos(self.angle_y)
            
            # Rotate Z
            zx = yx * math.cos(self.angle_z) - xy * math.sin(self.angle_z)
            zy = yx * math.sin(self.angle_z) + xy * math.cos(self.angle_z)
            
            # Translate along Z (push away from camera to Z = 350mm)
            world_x = zx + x_offset
            world_y = zy
            world_z = yz + 350.0
            
            # Pin-hole Camera Projection
            u = int(u0 + f * (world_x / world_z))
            v = int(v0 + f * (world_y / world_z))
            rotated_vertices.append((u, v))
            
        # Draw cube edges
        edges = [
            (0, 1), (1, 2), (2, 3), (3, 0), # Front face
            (4, 5), (5, 6), (6, 7), (7, 4), # Back face
            (0, 4), (1, 5), (2, 6), (3, 7)  # Connecting edges
        ]
        
        # Use different colors for Left and Right mock cameras to distinguish them
        color = (255, 105, 180) if is_left else (0, 255, 255) # Hot Pink for Left, Cyan for Right
        
        for p1_idx, p2_idx in edges:
            p1 = rotated_vertices[p1_idx]
            p2 = rotated_vertices[p2_idx]
            # Clip drawing to canvas boundary to prevent OpenCV exceptions
            cv2.line(canvas, p1, p2, color, 2, cv2.LINE_AA)
            
        # Draw some features (high-contrast stickers/dots on the object)
        # We place 4 circular dots on the faces of the cube
        face_centers = [
            [0, 0, -size], # Front face center
            [0, 0, size],  # Back face center
            [-size, 0, 0], # Left face center
            [size, 0, 0]   # Right face center
        ]
        for idx, (x, y, z) in enumerate(face_centers):
            # Rotate center
            xy = y * math.cos(self.angle_x) - z * math.sin(self.angle_x)
            xz = y * math.sin(self.angle_x) + z * math.cos(self.angle_x)
            yx = x * math.cos(self.angle_y) + xz * math.sin(self.angle_y)
            yz = -x * math.sin(self.angle_y) + xz * math.cos(self.angle_y)
            zx = yx * math.cos(self.angle_z) - xy * math.sin(self.angle_z)
            zy = yx * math.sin(self.angle_z) + xy * math.cos(self.angle_z)
            
            world_x = zx + x_offset
            world_y = zy
            world_z = yz + 350.0
            
            u = int(u0 + f * (world_x / world_z))
            v = int(v0 + f * (world_y / world_z))
            
            # Draw fiducial marker sticker (green ring with yellow center)
            cv2.circle(canvas, (u, v), 8, (0, 255, 0), -1)
            cv2.circle(canvas, (u, v), 4, (0, 255, 255), -1)
            cv2.putText(canvas, f"ID{idx}", (u + 10, v - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

        # Print camera indicator label
        label = "LEFT CAMERA - MOCK" if is_left else "RIGHT CAMERA - MOCK"
        cv2.putText(canvas, label, (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
        cv2.putText(canvas, f"Resolution: {self.width}x{self.height}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        # Add a simulated calibration/baseline overlay text
        cv2.putText(canvas, f"Est. Baseline: {B}mm", (20, 100), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        
        return canvas


class StereoCameraManager:
    def __init__(self):
        self.left_id = 0
        self.right_id = 1
        self.width = 640
        self.height = 480
        self.left_thread = None
        self.right_thread = None
        self.is_running = False
        
        # Recording variables
        self.is_recording = False
        self.video_writer = None
        self.record_lock = threading.Lock()
        
    def start_streams(self, left_id=0, right_id=1, width=640, height=480):
        if self.is_running:
            self.stop_streams()
            
        self.left_id = left_id
        self.right_id = right_id
        self.width = width
        self.height = height
        
        self.left_thread = CameraThread(left_id, width, height)
        self.right_thread = CameraThread(right_id, width, height)
        
        self.left_thread.start()
        self.right_thread.start()
        self.is_running = True
        print(f"Stereo streams started. Left Cam: {left_id}, Right Cam: {right_id}")

    def stop_streams(self):
        self.stop_recording()
        if self.left_thread:
            self.left_thread.stop()
            self.left_thread.join()
        if self.right_thread:
            self.right_thread.stop()
            self.right_thread.join()
        self.left_thread = None
        self.right_thread = None
        self.is_running = False
        print("Stereo streams stopped.")

    def get_frames(self):
        if not self.is_running:
            return None, None
            
        left_frame = self.left_thread.get_frame() if self.left_thread else None
        right_frame = self.right_thread.get_frame() if self.right_thread else None
        
        return left_frame, right_frame

    def start_recording(self, filepath):
        with self.record_lock:
            if self.is_recording:
                return False
                
            # Direct stitching into Side-by-Side (SBS) format
            # SBS width will be 2x camera width, height remains same
            sbs_width = self.width * 2
            sbs_height = self.height
            
            # Ensure output folder exists
            os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
            
            # Define video encoder (mp4v is widely supported)
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            self.video_writer = cv2.VideoWriter(filepath, fourcc, 30.0, (sbs_width, sbs_height))
            self.is_recording = True
            
            # Start background thread to feed frames to video writer
            self.record_thread = threading.Thread(target=self._recording_loop)
            self.record_thread.start()
            print(f"Started stereoscopic recording to: {filepath}")
            return True

    def _recording_loop(self):
        while self.is_recording:
            left, right = self.get_frames()
            if left is not None and right is not None:
                # Resize if sizes are inconsistent
                if left.shape != (self.height, self.width, 3):
                    left = cv2.resize(left, (self.width, self.height))
                if right.shape != (self.height, self.width, 3):
                    right = cv2.resize(right, (self.width, self.height))
                    
                # Concatenate Side-by-Side
                sbs_frame = np.hstack((left, right))
                
                with self.record_lock:
                    if self.video_writer:
                        self.video_writer.write(sbs_frame)
            time.sleep(0.033) # Match ~30 FPS

    def stop_recording(self):
        with self.record_lock:
            if not self.is_recording:
                return
            self.is_recording = False
            
        if hasattr(self, 'record_thread'):
            self.record_thread.join()
            
        with self.record_lock:
            if self.video_writer:
                self.video_writer.release()
                self.video_writer = None
        print("Stopped stereoscopic recording.")

    def capture_still_pair(self, output_dir, file_prefix="capture"):
        left, right = self.get_frames()
        if left is None or right is None:
            return None
            
        os.makedirs(output_dir, exist_ok=True)
        timestamp = int(time.time() * 1000)
        
        left_path = os.path.join(output_dir, f"{file_prefix}_{timestamp}_L.png")
        right_path = os.path.join(output_dir, f"{file_prefix}_{timestamp}_R.png")
        
        cv2.imwrite(left_path, left)
        cv2.imwrite(right_path, right)
        
        return left_path, right_path
