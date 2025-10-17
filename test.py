# tracker_loop.py
from ultralytics import YOLO
import cv2, json, time, os
from datetime import datetime, timezone

model = YOLO("yolo11n.pt")
# Classes you care about (names will come from model.names)
INTEREST = {"person","cup","bottle","bowl","book","cell phone","backpack","handbag","suitcase"}

# Define rough zones as rectangles (x1,y1,x2,y2) in pixel coords of your camera
ZONES = {
    "desk_left": (40, 260, 320, 440),
    "shelf": (360, 120, 620, 320),
    "door": (600, 200, 800, 480)
}
def zone_of(box):
    x1,y1,x2,y2 = box
    cx, cy = (x1+x2)//2, (y1+y2)//2
    for name,(zx1,zy1,zx2,zy2) in ZONES.items():
        if zx1 <= cx <= zx2 and zy1 <= cy <= zy2:
            return name
    return None

def run_with_tracking(source=0, sidecar_path="detections.jsonl"):
    cap = cv2.VideoCapture(source)
    # Use Ultralytics tracking in stream mode (ByteTrack by default)
    results = model.track(
        source=source,
        stream=True,
        imgsz=640,
        conf=0.45,
        persist=True,          # keep tracker memory across frames
        tracker="bytetrack.yaml"
    )
    # Open sidecar for appending one line per frame
    with open(sidecar_path, "w") as f:
        for r in results:
            t_ms = int(time.time() * 1000)
            frame = r.orig_img
            frame_person_present = False
            frame_records = []
            names = r.names  # id -> class name

            if r.boxes is not None:
                ids = (r.boxes.id.cpu().numpy().tolist() if r.boxes.id is not None else [None]*len(r.boxes))
                clss = r.boxes.cls.cpu().numpy().tolist()
                confs = r.boxes.conf.cpu().numpy().tolist()
                bxs = r.boxes.xyxy.cpu().numpy().tolist()

                for (box, cls, conf, tid) in zip(bxs, clss, confs, ids):
                    label = names[int(cls)]
                    if label not in INTEREST: 
                        continue
                    if label == "person":
                        frame_person_present = True
                    z = zone_of([int(x) for x in box])
                    frame_records.append({
                        "id": int(tid) if tid is not None else None,
                        "label": label,
                        "conf": float(conf),
                        "bbox": list(map(int, box)),
                        "zone": z
                    })

            # Write one JSON line for this frame
            f.write(json.dumps({"t_ms": t_ms, "detections": frame_records}) + "\n")

            # (Optional) show preview with boxes & zones
            for rec in frame_records:
                x1,y1,x2,y2 = rec["bbox"]
                cv2.rectangle(frame,(x1,y1),(x2,y2),(0,0,255),2)
                cv2.putText(frame, f'{rec["label"]}:{rec["id"]}', (x1, y1-6),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)
            for name,(x1,y1,x2,y2) in ZONES.items():
                cv2.rectangle(frame,(x1,y1),(x2,y2),(255,0,0),1)
                cv2.putText(frame, name, (x1, y1-8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,0,0), 1)
            cv2.imshow("Tracked preview", frame)
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    cv2.destroyAllWindows()
