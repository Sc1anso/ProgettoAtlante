# User Manual — Project ATLANTE

This guide covers capture preparation, starting a reconstruction, and reviewing or downloading results. The formatted DOCX version accompanies this Markdown file.

## 1. Record a suitable video

A reconstruction cannot recover surfaces that were never captured. Keep the subject still and move the camera slowly:

- Move around the subject for at least 180 degrees, preferably 360 degrees, keeping a similar distance and overlapping consecutive views.
- Make a second pass at a different height, including oblique views and visible top/bottom areas.
- Use even, diffuse light and sharp footage. Avoid sudden movement, digital zoom, motion blur, and abrupt exposure changes.
- Prefer a simple background separated from the subject. Reduce reflections, transparent or glossy surfaces, and moving objects.
- Keep the entire subject in frame and large enough to show useful detail.

If the background occupies much of the frame or masks include the room, improving the capture and separating the subject from the background often helps more than aggressive post-processing.

## 2. Start a reconstruction

1. In **New reconstruction**, choose **Video RGB** to upload an MP4, MOV, MKV, or WebM file. Alternatively, choose **Prepared COLMAP dataset** and upload a ZIP containing `images/` and `sparse/0/{cameras.bin,images.bin,points3D.bin}`. A single outer scene directory inside the ZIP is also supported.
2. Choose a preset: **Fast** for tests, **Balanced** for general use, and **High** or **Very High** for clean footage when more time and GPU memory are available.
3. Select the file and click **Start reconstruction**. On a phone, click **Upload from phone · QR**, scan the code, then choose **Choose from gallery** or **Record video**.
4. Follow the individual job card, which shows its ID, input, preset, phase, and progress. Each GPU worker processes one job at a time, so later jobs may wait in the queue.

For RGB video, the server extracts and filters frames, prepares/refines masks, runs COLMAP and RaDe-GS, and extracts a mesh. The prepared-COLMAP workflow skips frame extraction, masking, COLMAP, and DiGS. DiGS-produced `*_densified` scenes are suitable candidates when they retain the required structure.

## 3. Mesh history and viewers

In the history panel, you can rename or delete a reconstruction, download the original PLY, or choose a quality for the GLB export. **GLB quality** applies only to GLB export; the original PLY remains at the quality produced by the job.

**View** opens the mesh viewer: drag to rotate, use the scroll wheel to zoom, and right-click-drag to pan. **Viewer quality** selects a lighter version for browser viewing without changing the original download. Use **Expand** to dedicate the page to the scene and **Reduce** to return to the card.

**Gaussian preview** opens the Gaussian Splatting viewer alongside the original RGB video when available. The model rotates automatically; use the standard viewer controls to inspect it. The preview is sampled and compressed and does not replace the PLY.

**Improve holes** creates a conservative variant aimed at small topological boundaries. It cannot restore sides that were never captured and does not guarantee closure of large openings.

## 4. Upload from a phone

The QR code opens the mobile upload page. Choose **Choose from gallery** to select an existing video or **Record video** to capture one. Wait for the upload to finish before closing the page. The phone and server must be able to communicate on the same network, or the service must be reachable over HTTPS. The QR code does not make a private host reachable automatically.

External access requires public DNS, a TLS certificate, and correctly configured ports/reverse proxy. The included deployment has no authentication; do not expose it directly to the Internet.

## 5. Common issues

| Symptom | What to check |
| --- | --- |
| Job is waiting for a GPU | A worker may be processing another job or may not see the GPU; check job status and worker logs. |
| Background or noise appears in the reconstruction | Improve subject/background separation, lighting, and mask quality in the source video. |
| Mesh has large holes | Check video coverage; conservative repair targets only small boundaries, not missing surfaces. |
| Viewer is slow | Try a lighter viewer quality; the original PLY may be much larger. |
| Mobile upload stalls | Check network connectivity, phone storage, and whether the QR address is reachable. |

For installation, logs, and troubleshooting, see [Deployment and usage](../server/DEPLOYMENT_AND_USAGE.md).
