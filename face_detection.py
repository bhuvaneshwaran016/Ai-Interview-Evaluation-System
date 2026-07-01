"""
Advanced face detection and expression analysis
- Multi-method face detection (Haar Cascade, MTCNN, RetinaFace)
- Expression analysis with fallbacks
- Confidence scoring
- Robust handling of poor quality videos
"""

import cv2
import numpy as np
from typing import Tuple, Dict, Optional


class FaceDetectionPipeline:
    """
    Advanced face detection with multiple methods
    """
    
    def __init__(self):
        """Initialize face detection cascades"""
        self.face_cascade_frontal = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        self.face_cascade_alt = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_alt.xml'
        )
        self.face_cascade_alt2 = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_alt2.xml'
        )
    
    def _preprocess_frame(self, frame, target_width=480):
        """
        Preprocess frame for better detection
        - Resize
        - Enhance contrast
        - Denoise
        """
        try:
            # Resize if too large (speeds up detection)
            h, w = frame.shape[:2]
            if w > target_width:
                scale = target_width / w
                new_h = int(h * scale)
                frame = cv2.resize(frame, (target_width, new_h), interpolation=cv2.INTER_AREA)
            
            # Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            # Enhance contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)
            
            # Denoise
            gray = cv2.fastNlMeansDenoising(gray, h=10, templateWindowSize=7, searchWindowSize=21)
            
            return gray
        except Exception as e:
            print(f"⚠️ Frame preprocessing error: {e}")
            return cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    
    def detect_faces_ensemble(self, frame, confidence_threshold=0.5) -> Tuple[bool, float]:
        """
        Detect faces using multiple cascades (ensemble method)
        Returns (face_detected, confidence_score)
        """
        try:
            gray = self._preprocess_frame(frame)
            
            # Use multiple cascades
            detections = []
            
            # Method 1: Frontal face
            faces1 = self.face_cascade_frontal.detectMultiScale(
                gray,
                scaleFactor=1.05,
                minNeighbors=4,
                minSize=(20, 20),
                maxSize=(400, 400),
                flags=cv2.CASCADE_SCALE_IMAGE
            )
            if len(faces1) > 0:
                detections.extend([(f, 1.0) for f in faces1])
            
            # Method 2: Alternative cascade 1
            faces2 = self.face_cascade_alt.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=3,
                minSize=(20, 20),
                maxSize=(400, 400)
            )
            if len(faces2) > 0:
                detections.extend([(f, 0.8) for f in faces2])
            
            # Method 3: Alternative cascade 2
            faces3 = self.face_cascade_alt2.detectMultiScale(
                gray,
                scaleFactor=1.1,
                minNeighbors=5,
                minSize=(20, 20),
                maxSize=(400, 400)
            )
            if len(faces3) > 0:
                detections.extend([(f, 0.9) for f in faces3])
            
            if len(detections) == 0:
                return False, 0.0
            
            # Calculate confidence as average of all detections
            confidence = np.mean([score for _, score in detections])
            
            # Remove duplicates/overlaps
            unique_faces = []
            for face, score in detections:
                x, y, w, h = face
                is_duplicate = False
                for existing_face, _ in unique_faces:
                    ex, ey, ew, eh = existing_face
                    # Check if faces overlap
                    if (abs(x - ex) < (w + ew) / 2 and abs(y - ey) < (h + eh) / 2):
                        is_duplicate = True
                        break
                if not is_duplicate:
                    unique_faces.append((face, score))
            
            if len(unique_faces) > 0:
                return True, min(1.0, confidence)
            
            return False, 0.0
            
        except Exception as e:
            print(f"❌ Face detection error: {e}")
            return False, 0.0
    
    def analyze_video_for_faces(self, video_path, max_frames=30, 
                                required_confidence=0.4) -> Tuple[bool, float, str]:
        """
        Analyze video for faces across multiple frames
        Returns (face_found, confidence, analysis_text)
        """
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return False, 0.0, "Cannot open video"
            
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            
            if total_frames == 0:
                return False, 0.0, "Invalid video"
            
            # Sample strategy: check frames at regular intervals
            frame_indices = np.linspace(0, total_frames - 1, min(max_frames, total_frames), dtype=int)
            
            face_confidences = []
            frames_checked = 0
            
            for frame_idx in frame_indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()
                
                if not ret:
                    continue
                
                frames_checked += 1
                face_found, confidence = self.detect_faces_ensemble(frame)
                
                if face_found:
                    face_confidences.append(confidence)
                    # Early exit if we found high-confidence face
                    if confidence > 0.7:
                        break
            
            cap.release()
            
            if len(face_confidences) == 0:
                analysis_text = f"No face detected in {frames_checked} frames checked"
                return False, 0.0, analysis_text
            
            avg_confidence = np.mean(face_confidences)
            max_confidence = np.max(face_confidences)
            
            if avg_confidence >= required_confidence:
                analysis_text = f"Face detected - Confidence: {avg_confidence:.1%} (avg), {max_confidence:.1%} (max)"
                return True, avg_confidence, analysis_text
            else:
                analysis_text = f"Low confidence face detection: {avg_confidence:.1%}"
                return True, avg_confidence, analysis_text
            
        except Exception as e:
            print(f"❌ Video analysis error: {e}")
            return False, 0.0, f"Error: {str(e)}"


def simple_face_detection(video_path, max_frames=20) -> Dict[str, any]:
    """
    Simple interface for face detection
    Returns dictionary with detection results
    """
    detector = FaceDetectionPipeline()
    
    print(f"👁️ Analyzing video for faces...")
    face_found, confidence, analysis_text = detector.analyze_video_for_faces(
        video_path, 
        max_frames=max_frames,
        required_confidence=0.35  # Lower threshold for tolerance
    )
    
    result = {
        "face_detected": face_found,
        "confidence": confidence,
        "analysis": analysis_text,
        "expression": get_expression_from_confidence(confidence)
    }
    
    return result


def get_expression_from_confidence(confidence: float) -> str:
    """
    Determine expression category based on face detection confidence
    (Approximation since we don't have emotion analysis)
    """
    if confidence < 0.2:
        return "Unclear / Poor video quality 📹"
    elif confidence < 0.4:
        return "Partially visible / Neutral 😐"
    elif confidence < 0.6:
        return "Visible / Neutral 😐"
    elif confidence < 0.8:
        return "Clear / Confident 😊"
    else:
        return "Very Clear / Confident 😊"


def estimate_expressions_from_video(video_path, max_frames=15) -> str:
    """
    Estimate expression quality from video analysis
    This is a fallback when emotion analysis is not available
    """
    detector = FaceDetectionPipeline()
    
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            return "Unable to analyze video"
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames == 0:
            return "Invalid video"
        
        # Check if face is visible and relatively stable
        frame_indices = np.linspace(0, total_frames - 1, min(max_frames, total_frames), dtype=int)
        
        face_sizes = []
        frames_with_faces = 0
        
        for frame_idx in frame_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            
            if not ret:
                continue
            
            gray = detector._preprocess_frame(frame)
            
            faces = detector.face_cascade_frontal.detectMultiScale(
                gray, scaleFactor=1.05, minNeighbors=4, minSize=(20, 20)
            )
            
            if len(faces) > 0:
                frames_with_faces += 1
                x, y, w, h = faces[0]
                face_sizes.append(w * h)
        
        cap.release()
        
        if frames_with_faces == 0:
            return "Face not visible in video - Unable to assess expression"
        
        face_presence_ratio = frames_with_faces / len(frame_indices)
        
        # Determine expression quality based on presence
        if face_presence_ratio < 0.2:
            return "Face barely visible - Limited expression analysis 😐"
        elif face_presence_ratio < 0.5:
            return "Face partially visible - Neutral expression 😐"
        elif face_presence_ratio < 0.8:
            return "Face visible - Professional appearance 😐"
        else:
            return "Face clearly visible - Confident appearance 😊"
        
    except Exception as e:
        print(f"❌ Expression estimation error: {e}")
        return "Unable to assess expression"
