from ultralytics import YOLO
import cv2
from datetime import datetime
import os
import sys
import time
from audio_capture import AudioRecorder
from video_processing_queue import VideoProcessingQueue

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Blue_dream_agents.timezone_utils import now_local
from Blue_dream_agents.Tools.dementia_email import GmailAgent

# Fall detection class IDs from your custom YOLO model
FALLEN_CLASS_ID = 0
NOT_FALLEN_CLASS_ID = 1

# Class names for display
CLASS_NAMES = {FALLEN_CLASS_ID: "Fallen", NOT_FALLEN_CLASS_ID: "Standing"}

# Colors (BGR format)
FALLEN_COLOR = (0, 0, 255)  # Red for fallen
STANDING_COLOR = (0, 255, 0)  # Green for standing

CAMERA_ROOM_MAPPING = {
    1: 0,  # Camera index 1 → Room 0 (Bedroom)
    2: 1,  # Camera index 2 → Room 1 (Living Room) # Uncomment this when we have attached the second camera
}

ROOMS = {
    0: "Bedroom",
    1: "Living Room",  # Uncomment this when we have attached the second camera
}


def send_fall_alert(
    gmail_agent, camera_idx, timestamp, frame=None, screenshot_dir=None
):
    """Send alert when a fall is detected, optionally with a screenshot."""
    print(f"⚠️ FALL DETECTED! Camera {camera_idx} at {timestamp}")
    print("🚨 ALERT: Person has fallen down! Immediate attention required!")

    # Resolve room name
    room_name = ROOMS.get(
        CAMERA_ROOM_MAPPING.get(camera_idx, -1), f"Camera {camera_idx}"
    )

    # Save screenshot of the fall if frame is provided
    screenshot_path = None
    if frame is not None and screenshot_dir is not None:
        try:
            os.makedirs(screenshot_dir, exist_ok=True)
            screenshot_filename = f"fall_alert_{camera_idx}_{now_local().strftime('%Y-%m-%d_%H-%M-%S')}.jpg"
            screenshot_path = os.path.join(screenshot_dir, screenshot_filename)
            cv2.imwrite(screenshot_path, frame)
            print(f"📸 Fall screenshot saved: {screenshot_path}")
        except Exception as e:
            print(f"Error saving fall screenshot: {e}")
            screenshot_path = None

    if gmail_agent:
        try:
            print(f"Sending email alert for {room_name}...")
            gmail_agent.send_alert_email(
                to="amogh@outlook.com",  # REPLACE WITH ACTUAL EMAIL
                subject=f"URGENT: Fall Detected in {room_name}",
                alert_type="FALL DETECTED",
                location=room_name,
                timestamp=timestamp,
                image_path=screenshot_path,
            )
        except Exception as e:
            print(f"Error sending email alert: {e}")


def save_last_frame_screenshot(video_path, screenshot_dir):
    """Extract and save the last frame from a video file as a screenshot."""
    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            print(f"Error: Could not open video file for screenshot: {video_path}")
            return None

        # Get total frame count and go to last frame
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames - 1)

        ret, frame = cap.read()
        cap.release()

        if ret and frame is not None:
            # Generate screenshot filename based on video filename
            video_basename = os.path.splitext(os.path.basename(video_path))[0]
            screenshot_filename = os.path.join(screenshot_dir, f"{video_basename}.jpg")
            cv2.imwrite(screenshot_filename, frame)
            print(f"Saved screenshot: {screenshot_filename}")
            return screenshot_filename
        else:
            print(f"Error: Could not read last frame from video: {video_path}")
            return None
    except Exception as e:
        print(f"Error saving screenshot: {e}")
        return None


def camera_feed():
    # Get the project root directory (parent of Capture folder)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)

    # Load YOLO11 model
    model = YOLO(r"Capture\trained-weights\best.pt")

    # Initialize Gmail Agent
    try:
        print("Initializing Gmail Agent...")
        gmail_agent = GmailAgent()
    except Exception as e:
        print(
            f"Warning: Could not initialize Gmail Agent. Email alerts will be disabled. Error: {e}"
        )
        gmail_agent = None

    # Detect all available cameras
    # camera_indices = [1]
    camera_indices = [1, 2]  # Uncomment this when we have attached the second camera
    cameras = []
    video_writers = {}  # Track video writers for each camera
    audio_recorders = {}  # Track audio recorders for each camera
    recording_active = {}  # Track recording state for each camera
    video_output_dirs = {}  # Track video output directories per camera
    audio_output_dirs = {}  # Track audio output directories per camera
    screenshot_output_dirs = {}  # Track screenshot output directories per camera

    # Buffer tracking for detection grace period
    last_person_detected_time = {}  # Track when person was last detected per camera
    current_video_filename = {}  # Track current video filename for screenshot
    fall_alert_sent = {}  # Track if fall alert has been sent for current recording session
    DETECTION_BUFFER_SECONDS = 2  # 3-second buffer before stopping recording

    # Track fall start time for stability check
    fall_start_time = {}

    # Producer-Consumer queue for video processing
    recording_start_timestamp = {}  # Track when recording started per camera
    current_audio_filename = {}  # Track current audio filename per camera
    processing_queue = VideoProcessingQueue()
    processing_queue.start()

    for idx in camera_indices:
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)  # Try higher resolution
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
        if cap.isOpened():
            cameras.append((idx, cap))
            video_writers[idx] = None
            audio_recorders[idx] = AudioRecorder()
            recording_active[idx] = False
            last_person_detected_time[idx] = None
            current_video_filename[idx] = None
            fall_alert_sent[idx] = False  # Reset fall alert state
            fall_start_time[idx] = None
            # Create camera-specific output directories
            video_output_dirs[idx] = os.path.join(
                project_root, "Storage", "video_recordings", f"camera_{idx}"
            )
            audio_output_dirs[idx] = os.path.join(
                project_root, "Storage", "audio_recordings", f"camera_{idx}"
            )
            screenshot_output_dirs[idx] = os.path.join(
                project_root, "Storage", "screenshots", f"camera_{idx}"
            )
            os.makedirs(video_output_dirs[idx], exist_ok=True)
            os.makedirs(audio_output_dirs[idx], exist_ok=True)
            os.makedirs(screenshot_output_dirs[idx], exist_ok=True)
            print(f"Camera {idx} opened successfully!")
        else:
            print(f"Camera {idx} not available")

    if not cameras:
        print("Error: No cameras available")
        return

    print("Press 'q' to quit")
    # print("Fall Detection Model: Class 0 = Fallen, Class 1 = Standing")

    frame_width = int(cameras[0][1].get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(cameras[0][1].get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = 20

    while True:
        # Process each camera
        for idx, cap in cameras:
            ret, frame = (
                cap.read()
            )  # here ret stands for return value and frame stands for the frame read from the camera

            if not ret:
                print(f"Error: Could not read frame from camera {idx}")
                continue

            # Run YOLO11 inference on the frame
            results = model(frame, verbose=False)

            # Process detections - detect any person (fallen or standing)
            person_detected = False
            fall_detected = False

            # Temporary lists to hold valid boxes for drawing
            valid_boxes = []

            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        class_id = int(box.cls[0])
                        confidence = float(box.conf[0])

                        # Apply confidence threshold
                        if confidence > 0.50:
                            # Your model: 0 = fallen, 1 = not fallen (standing)
                            if class_id in (FALLEN_CLASS_ID, NOT_FALLEN_CLASS_ID):
                                person_detected = True
                                valid_boxes.append(box)
                                if class_id == FALLEN_CLASS_ID:
                                    fall_detected = True

                current_time = time.time()

                # Update last detection time if person is detected
                if person_detected:
                    last_person_detected_time[idx] = current_time

                # Fall Detection Logic with 5-second Buffer
                if fall_detected:
                    if fall_start_time[idx] is None:
                        fall_start_time[idx] = current_time
                    else:
                        fall_duration = current_time - fall_start_time[idx]
                        if fall_duration >= 3.5:
                            # Confirmed fall for 3.5 seconds - send alert with screenshot
                            if recording_active[idx] and not fall_alert_sent[idx]:
                                timestamp_str = now_local().strftime(
                                    "%Y-%m-%d %H:%M:%S"
                                )
                                send_fall_alert(
                                    gmail_agent,
                                    idx,
                                    timestamp_str,
                                    frame=frame,
                                    screenshot_dir=screenshot_output_dirs[idx],
                                )
                                fall_alert_sent[idx] = True
                else:
                    # Reset fall timer if no fall detected
                    fall_start_time[idx] = None

                if person_detected and not recording_active[idx]:
                    # Start new recording
                    recording_start_timestamp[idx] = (
                        now_local()
                    )  # Capture timestamp at start
                    timestamp = now_local().strftime("%Y-%m-%d_%H-%M-%S")
                    video_filename = os.path.join(
                        video_output_dirs[idx], f"camera_{idx}_{timestamp}.mp4"
                    )
                    audio_filename = os.path.join(
                        audio_output_dirs[idx], f"camera_{idx}_{timestamp}.mp3"
                    )
                    current_video_filename[idx] = video_filename
                    current_audio_filename[idx] = audio_filename  # Store for queue
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    video_writers[idx] = cv2.VideoWriter(
                        video_filename, fourcc, fps, (frame_width, frame_height)
                    )
                    # Start audio recording
                    audio_recorders[idx].start_recording(audio_filename)
                    recording_active[idx] = True
                    fall_alert_sent[idx] = False  # Reset fall alert for new recording
                    print(f"Started recording: {video_filename}")
                elif not person_detected and recording_active[idx]:
                    # Check if buffer time has elapsed since last detection
                    time_since_last_detection = (
                        current_time - last_person_detected_time[idx]
                    )

                    if time_since_last_detection >= DETECTION_BUFFER_SECONDS:
                        # Buffer expired, stop recording
                        video_writers[idx].release()
                        video_writers[idx] = None
                        # Stop audio recording
                        audio_recorders[idx].stop_recording()
                        recording_active[idx] = False
                        fall_alert_sent[idx] = False  # Reset fall alert
                        fall_start_time[idx] = None  # Reset fall timer
                        print(
                            f"Stopped recording for camera {idx} (no detection for {DETECTION_BUFFER_SECONDS}s)"
                        )

                        # Save last frame as screenshot and add to processing queue
                        if current_video_filename[idx]:
                            screenshot_path = save_last_frame_screenshot(
                                current_video_filename[idx], screenshot_output_dirs[idx]
                            )

                            # Add video task to processing queue
                            processing_queue.add_task(
                                video_path=current_video_filename[idx],
                                audio_path=current_audio_filename[idx],
                                screenshot_path=screenshot_path or "",
                                room_number=CAMERA_ROOM_MAPPING.get(idx, idx),
                                timestamp=recording_start_timestamp[idx],
                            )

                            current_video_filename[idx] = None
                            current_audio_filename[idx] = None
                    # else: continue recording during buffer period

                if recording_active[idx] and video_writers[idx] is not None:
                    video_writers[idx].write(frame)

                # Draw bounding boxes for detected persons with fall status colors
                for box in valid_boxes:
                    class_id = int(box.cls[0])

                    if class_id in (FALLEN_CLASS_ID, NOT_FALLEN_CLASS_ID):
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        confidence = float(box.conf[0])

                        # Choose color based on class: Red for fallen, Green for standing
                        if class_id == FALLEN_CLASS_ID:
                            color = FALLEN_COLOR
                            status_label = "FALLEN"
                        else:
                            color = STANDING_COLOR
                            status_label = "Standing"

                        # Draw bounding box
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)

                        # Draw label with confidence
                        label = f"{status_label}: {confidence:.2f}"
                        label_size, _ = cv2.getTextSize(
                            label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2
                        )

                        cv2.rectangle(
                            frame,
                            (x1, y1 - label_size[1] - 10),
                            (x1 + label_size[0], y1),
                            color,
                            -1,
                        )

                        cv2.putText(
                            frame,
                            label,
                            (x1, y1 - 5),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (255, 255, 255),  # White text for visibility
                            2,
                        )

            # Count persons detected (both fallen and standing)
            person_count = len(valid_boxes)

            # Count fallen persons
            fallen_count = sum(
                1 for box in valid_boxes if int(box.cls[0]) == FALLEN_CLASS_ID
            )

            # Display person count on frame
            count_text = f"Persons: {person_count} | Fallen: {fallen_count}"
            cv2.putText(
                frame, count_text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2
            )

            # Display FALL DETECTED warning if any fallen person detected
            if fallen_count > 0:
                cv2.putText(
                    frame,
                    "! FALL DETECTED !",
                    (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1.2,
                    (0, 0, 255),  # Red warning
                    3,
                )

            if recording_active[idx]:
                cv2.putText(
                    frame,
                    "Recording",
                    (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    1,
                    (0, 255, 135),
                    2,
                )

            # Display Camera ID at bottom right
            text = f"Camera ID: {idx}"
            text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
            text_x = frame.shape[1] - text_size[0] - 10
            text_y = frame.shape[0] - 10
            cv2.putText(
                frame,
                text,
                (text_x, text_y),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (255, 255, 255),  # White
                2,
            )

            # Display the frame with camera index in window name
            cv2.imshow(f"Camera {idx} - Fall Detection", frame)

        # Press 'q' to quit
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    # Cleanup - release all cameras and stop any active recordings
    print("\nShutting down camera feed...")
    for idx, cap in cameras:
        cap.release()
        if video_writers[idx] is not None:
            video_writers[idx].release()
        if recording_active.get(idx, False):
            audio_recorders[idx].stop_recording()
            # Save last frame as screenshot for any active recordings
            if current_video_filename.get(idx):
                screenshot_path = save_last_frame_screenshot(
                    current_video_filename[idx], screenshot_output_dirs[idx]
                )
                # Add active recording to queue before shutdown
                processing_queue.add_task(
                    video_path=current_video_filename[idx],
                    audio_path=current_audio_filename.get(idx, ""),
                    screenshot_path=screenshot_path or "",
                    room_number=CAMERA_ROOM_MAPPING.get(idx, idx),
                    timestamp=recording_start_timestamp.get(idx, now_local()),
                )
    cv2.destroyAllWindows()
    print("All cameras released and windows closed")

    # Wait for all queued videos to be processed before exiting
    processing_queue.stop()


if __name__ == "__main__":
    camera_feed()
