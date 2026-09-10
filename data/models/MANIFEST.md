# Model manifest
Every weights file in this folder must have a row here. Verify with `shasum -a 256 <file>`.

| File | sha256 (first 12) | Source / training | Input | Classes | Notes |
|---|---|---|---|---|---|
| human.tflite | TODO | SaR project `robin_package/human.tflite` (YOLOv8n COCO, 13 MB) | 640? | 80 (filter: person) | copy from SaR project; confirm input size |
