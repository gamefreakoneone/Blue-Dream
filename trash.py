import cv2
from ultralytics import YOLO
import threading

def camera_stream(camera_id, window_name):
    model = YOLO("yolo11n.pt")
    cap = cv2.VideoCapture(camera_id)
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        results = model(frame)
        annotated_frame = results[0].plot()
        
        cv2.imshow(window_name, annotated_frame)
        
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
    
    cap.release()
    cv2.destroyWindow(window_name)

# Start both cameras in separate threads
thread1 = threading.Thread(target=camera_stream, args=(0, 'Room 1'))
thread2 = threading.Thread(target=camera_stream, args=(1, 'Room 2'))

thread1.start()
thread2.start()

thread1.join()
thread2.join()