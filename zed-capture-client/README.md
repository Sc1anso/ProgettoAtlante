# ZED capture client

Run this client on the Windows/Linux computer connected to the ZED camera. Do not run it inside the server container.

## Requirements

1. Install the [ZED SDK](https://www.stereolabs.com/developers/release/) and the `pyzed.sl` Python binding for the Python version in use.
2. Install the Python dependencies used by the capture script:

   ```bash
   pip install numpy opencv-python matplotlib
   ```

## Capture and package

Start capture in a new directory:

```bash
python capture_video.py
```

When capture ends, the directory contains `recording.mp4`, `depth_data.dp`, and `camera_data.dp`. Create a portable ZIP archive with:

```bash
python make_capture_zip.py . zed-capture.zip
```

The current web UI hides the ZED upload selector. The backend compatibility route expects the three files at the ZIP root; do not rename them or place them in a subdirectory. See the deployment guide before re-enabling this input mode.
