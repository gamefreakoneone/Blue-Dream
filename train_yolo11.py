import os
os.environ['KMP_DUPLICATE_LIB_OK'] = 'TRUE'

from ultralytics import YOLO

# Load a pretrained YOLO11n model
model = YOLO("yolo11n.pt")

# Train the model on the COCO8 dataset for 100 epochs
train_results = model.train(
    data="coco8.yaml",
    epochs=100,
    imgsz=640,
    device="cpu",
)

# Evaluate the model's performance on the validation set
metrics = model.val()

# Perform object detection on an image
results = model(r"C:\Users\amogh\OneDrive\Pictures\20211207_160417.jpg")
results[0].show()

# Export the model to ONNX format
path = model.export(format="onnx")