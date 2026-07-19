import cv2
import numpy as np
import json
import os

class StereoCalibrator:
    def __init__(self, chessboard_size=(9, 6), square_size_mm=25.0):
        self.chessboard_size = chessboard_size
        self.square_size_mm = square_size_mm
        
        # 3D points in real world space (0,0,0), (1,0,0), ...
        self.objp = np.zeros((chessboard_size[0] * chessboard_size[1], 3), np.float32)
        self.objp[:, :2] = np.mgrid[0:chessboard_size[0], 0:chessboard_size[1]].T.reshape(-1, 2)
        self.objp *= self.square_size_mm
        
        # Arrays to store object points and image points from all images.
        self.objpoints = [] # 3d point in real world space
        self.imgpoints_l = [] # 2d points in image plane for left camera
        self.imgpoints_r = [] # 2d points in image plane for right camera
        
        self.calibration_file = "calibration_data.json"
        self.calibrated = False
        
        # Calibration results
        self.cameraMatrixL = None
        self.distCoeffsL = None
        self.cameraMatrixR = None
        self.distCoeffsR = None
        self.R = None
        self.T = None
        self.E = None
        self.F = None
        self.Q = None
        
        # Rectification maps
        self.map1_l = None
        self.map2_l = None
        self.map1_r = None
        self.map2_r = None
        
        # Load existing calibration if present
        self.load_calibration()

    def detect_chessboard(self, img):
        """Helper to find corners on a chessboard image."""
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        ret, corners = cv2.findChessboardCorners(gray, self.chessboard_size, 
                                                 cv2.CALIB_CB_ADAPTIVE_THRESH + 
                                                 cv2.CALIB_CB_NORMALIZE_IMAGE)
        if ret:
            # Refine corner locations
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
            corners2 = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
            return True, corners2
        return False, None

    def add_calibration_pair(self, left_img, right_img):
        """Attempts to find chessboard in both left and right frames.
        Returns (success, left_annotated, right_annotated).
        """
        ret_l, corners_l = self.detect_chessboard(left_img)
        ret_r, corners_r = self.detect_chessboard(right_img)
        
        annotated_l = left_img.copy()
        annotated_r = right_img.copy()
        
        if ret_l:
            cv2.drawChessboardCorners(annotated_l, self.chessboard_size, corners_l, ret_l)
        if ret_r:
            cv2.drawChessboardCorners(annotated_r, self.chessboard_size, corners_r, ret_r)
            
        if ret_l and ret_r:
            self.objpoints.append(self.objp)
            self.imgpoints_l.append(corners_l)
            self.imgpoints_r.append(corners_r)
            return True, annotated_l, annotated_r
            
        return False, annotated_l, annotated_r

    def calibrate(self, image_shape):
        """Runs the stereo calibration pipeline."""
        if len(self.objpoints) < 5:
            return False, f"Not enough calibration frames captured. Need at least 5 (currently have {len(self.objpoints)})."
            
        h, w = image_shape[:2]
        
        # 1. Calibrate each camera individually first to get better initial intrinsics
        ret_l, K_l, d_l, rvecs_l, tvecs_l = cv2.calibrateCamera(
            self.objpoints, self.imgpoints_l, (w, h), None, None
        )
        ret_r, K_r, d_r, rvecs_r, tvecs_r = cv2.calibrateCamera(
            self.objpoints, self.imgpoints_r, (w, h), None, None
        )
        
        if not ret_l or not ret_r:
            return False, "Individual camera calibration failed."
            
        # 2. Perform Stereo Calibration
        flags = cv2.CALIB_FIX_INTRINSIC
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 1e-5)
        
        retval, K_l, d_l, K_r, d_r, R, T, E, F = cv2.stereoCalibrate(
            self.objpoints,
            self.imgpoints_l,
            self.imgpoints_r,
            K_l, d_l,
            K_r, d_r,
            (w, h),
            R=None, T=None, E=None, F=None,
            flags=flags,
            criteria=criteria
        )
        
        self.cameraMatrixL = K_l
        self.distCoeffsL = d_l
        self.cameraMatrixR = K_r
        self.distCoeffsR = d_r
        self.R = R
        self.T = T
        self.E = E
        self.F = F
        self.calibrated = True
        
        # Compute rectification maps
        self.compute_rectification_maps((w, h))
        
        # Save to file
        self.save_calibration()
        
        return True, "Stereo calibration successful! Calibration parameters saved."

    def compute_rectification_maps(self, image_size):
        if not self.calibrated:
            return
            
        w, h = image_size
        
        # Rectification rotation and projection matrices
        R1, R2, P1, P2, Q, roi_left, roi_right = cv2.stereoRectify(
            self.cameraMatrixL, self.distCoeffsL,
            self.cameraMatrixR, self.distCoeffsR,
            image_size, self.R, self.T,
            flags=cv2.CALIB_ZERO_DISPARITY, alpha=0
        )
        self.Q = Q
        
        # Generate lookup maps for image remapping
        self.map1_l, self.map2_l = cv2.initUndistortRectifyMap(
            self.cameraMatrixL, self.distCoeffsL, R1, P1, image_size, cv2.CV_16SC2
        )
        self.map1_r, self.map2_r = cv2.initUndistortRectifyMap(
            self.cameraMatrixR, self.distCoeffsR, R2, P2, image_size, cv2.CV_16SC2
        )

    def rectify_pair(self, left_img, right_img):
        """Rectifies a pair of stereo images so that the optical axes are parallel."""
        if not self.calibrated or self.map1_l is None:
            # If not calibrated, return original images
            return left_img.copy(), right_img.copy()
            
        rectified_l = cv2.remap(left_img, self.map1_l, self.map2_l, cv2.INTER_LINEAR)
        rectified_r = cv2.remap(right_img, self.map1_r, self.map2_r, cv2.INTER_LINEAR)
        
        return rectified_l, rectified_r

    def save_calibration(self):
        if not self.calibrated:
            return
            
        data = {
            "calibrated": self.calibrated,
            "cameraMatrixL": self.cameraMatrixL.tolist(),
            "distCoeffsL": self.distCoeffsL.tolist(),
            "cameraMatrixR": self.cameraMatrixR.tolist(),
            "distCoeffsR": self.distCoeffsR.tolist(),
            "R": self.R.tolist(),
            "T": self.T.tolist(),
            "E": self.E.tolist(),
            "F": self.F.tolist(),
            "Q": self.Q.tolist() if self.Q is not None else None
        }
        
        with open(self.calibration_file, 'w') as f:
            json.dump(data, f, indent=4)
        print("Calibration parameters written to calibration_data.json")

    def load_calibration(self):
        if not os.path.exists(self.calibration_file):
            return False
            
        try:
            with open(self.calibration_file, 'r') as f:
                data = json.load(f)
                
            self.calibrated = data.get("calibrated", False)
            if self.calibrated:
                self.cameraMatrixL = np.array(data["cameraMatrixL"])
                self.distCoeffsL = np.array(data["distCoeffsL"])
                self.cameraMatrixR = np.array(data["cameraMatrixR"])
                self.distCoeffsR = np.array(data["distCoeffsR"])
                self.R = np.array(data["R"])
                self.T = np.array(data["T"])
                self.E = np.array(data["E"])
                self.F = np.array(data["F"])
                self.Q = np.array(data["Q"]) if data.get("Q") is not None else None
                
                # Assume standard 640x480 for default, maps will be recomputed if image size changes
                self.compute_rectification_maps((640, 480))
                print("Successfully loaded calibration parameters from calibration_data.json")
                return True
        except Exception as e:
            print(f"Error loading calibration data: {e}")
            self.calibrated = False
            
        return False
        
    def reset(self):
        """Resets the captured calibration points."""
        self.objpoints = []
        self.imgpoints_l = []
        self.imgpoints_r = []
        # Keep physical files intact unless explicitly deleted
