import json
import os
import re
import shutil
import time
import uuid
from io import BytesIO
from urllib.parse import urlparse
from zipfile import BadZipFile
from pathlib import Path

from celery.result import AsyncResult
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.worker import GLB_TRIANGLE_TARGETS, RECONSTRUCTION_PROFILES, VIEWER_TRIANGLE_TARGETS, celery_app, generate_gaussian_preview, generate_glb, generate_video_preview, generate_viewer_mesh, postprocess_mesh, run_reconstruction
from app.colmap_dataset import validate_colmap_archive
from app.zed_capture import validate_zed_archive

JOB_ROOT = Path(os.getenv("JOB_ROOT", "/jobs"))
SAMPLE_VIDEO = Path(os.getenv("SAMPLE_VIDEO", "/app/server/samples/pavarotti-demo.mp4"))
STATIC_ROOT = Path(__file__).parent / "static"
MOBILE_ASSET_VERSION = "20260929-2"
# Phones commonly label gallery videos as 3GPP or AVI instead of MP4/MOV.
# ffmpeg still performs the authoritative decoding validation in the worker.
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/quicktime", "video/x-matroska", "video/webm", "video/3gpp", "video/3gpp2", "video/x-msvideo"}
ALLOWED_ZED_TYPES = {"application/zip", "application/x-zip-compressed", "application/octet-stream"}

app = FastAPI(title="Pavarotti 3D Reconstruction")


class MeshRename(BaseModel):
    name: str


def job_directory(job_id: str) -> Path:
    """Resolve a job directory without allowing a path outside JOB_ROOT."""
    try:
        normalized_id = str(uuid.UUID(job_id))
    except ValueError as exc:
        raise HTTPException(404, "Ricostruzione non trovata") from exc
    job_dir = JOB_ROOT / normalized_id
    if not job_dir.is_dir():
        raise HTTPException(404, "Ricostruzione non trovata")
    return job_dir


def read_job_state(state_path: Path) -> dict:
    """Read a worker-updated state file without surfacing a transient 500."""
    for _ in range(3):
        try:
            return json.loads(state_path.read_text())
        except json.JSONDecodeError:
            time.sleep(0.05)
    raise HTTPException(503, "Stato del job in aggiornamento: riprova tra un istante")


def write_mesh_metadata(metadata_path: Path, metadata: dict) -> None:
    """Atomically persist mesh metadata shared by API and Celery workers."""
    temporary_path = metadata_path.with_name(f"{metadata_path.name}.{uuid.uuid4().hex}.tmp")
    temporary_path.write_text(json.dumps(metadata))
    os.replace(temporary_path, metadata_path)


def viewer_task_is_active(task_id: str) -> bool:
    """Return whether a viewer task is currently owned by a live worker.

    Celery's result backend does not reliably distinguish a queued task from a
    task that was lost during a worker restart.  The worker inspector does for
    tasks already running; if no worker reports it, the API can safely enqueue
    a replacement when the user opens the viewer again.
    """
    try:
        inspector = celery_app.control.inspect(timeout=1.0)
        for tasks_by_worker in (inspector.active() or {}).values():
            if any(task.get("id") == task_id for task in tasks_by_worker):
                return True
    except Exception:
        # Avoid creating duplicate expensive simplifications while Redis or a
        # worker is temporarily unavailable.  A later viewer request retries.
        return True
    return False


@app.get("/api/mobile-upload-qr.svg")
def mobile_upload_qr(request: Request, url: str = ""):
    """Return an offline-generated QR code for the dedicated mobile uploader."""
    candidate = url or f"{str(request.base_url).rstrip('/')}/mobile.html"
    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
        raise HTTPException(422, "Inserisci un indirizzo HTTP o HTTPS raggiungibile dal telefono")
    if len(candidate) > 512 or parsed.path not in {"", "/", "/mobile.html"}:
        raise HTTPException(422, "L'indirizzo del QR deve puntare alla pagina di upload mobile")
    query = parsed.query or f"v={MOBILE_ASSET_VERSION}"
    if not re.fullmatch(r"v=[A-Za-z0-9._-]{1,64}", query):
        raise HTTPException(422, "Il parametro di versione del QR non è valido")
    mobile_url = f"{parsed.scheme}://{parsed.netloc}/mobile.html?{query}"
    try:
        import qrcode
        from qrcode.image.svg import SvgPathImage
    except ImportError as exc:
        raise HTTPException(503, "Generatore QR non installato: ricostruisci il container API") from exc
    image = qrcode.make(mobile_url, image_factory=SvgPathImage, border=3)
    buffer = BytesIO()
    image.save(buffer)
    return Response(buffer.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@app.get("/api/jobs")
def list_jobs(response: Response):
    """Return completed, running and failed jobs stored in the shared volume."""
    response.headers["Cache-Control"] = "no-store"
    jobs = []
    if not JOB_ROOT.exists():
        return jobs
    for job_dir in JOB_ROOT.iterdir():
        state_path = job_dir / "state.json"
        if not job_dir.is_dir() or not state_path.exists():
            continue
        try:
            state = read_job_state(state_path)
        except HTTPException:
            continue
        metadata_path = job_dir / "mesh.json"
        try:
            metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
        except (json.JSONDecodeError, OSError):
            # One damaged metadata file must not hide every reconstruction.
            metadata = {}
        jobs.append({
            "id": job_dir.name,
            "status": state.get("status", "unknown"),
            "progress": state.get("progress", 0),
            "message": state.get("message", ""),
            "updated_at": state.get("updated_at", state_path.stat().st_mtime),
            "has_result": (job_dir / "output" / "recon.ply").is_file(),
            "mesh_name": metadata.get("name", ""),
            "input_mode": metadata.get("input_mode", "rgb"),
            "input_name": metadata.get("input_name", ""),
            "quality": metadata.get("quality", "balanced"),
            "postprocess_status": metadata.get("postprocess_status", ""),
            "postprocess_progress": metadata.get("postprocess_progress", 0),
            "postprocess_message": metadata.get("postprocess_message", ""),
            "has_processed": (job_dir / "output" / "processed" / "recon-repaired-conservative-v6.ply").is_file(),
            "glb": metadata.get("glb", {}),
            "viewer": metadata.get("viewer", {}),
            "gaussian_preview": metadata.get("gaussian_preview", {}),
            "video_preview": metadata.get("video_preview", {}),
        })
    return sorted(jobs, key=lambda job: job["updated_at"], reverse=True)


@app.post("/api/jobs", status_code=202)
async def create_job(video: UploadFile = File(...), quality: str = Form("balanced")):
    if video.content_type not in ALLOWED_VIDEO_TYPES:
        raise HTTPException(415, "Carica un video MP4, MOV, MKV o WebM.")
    if quality not in RECONSTRUCTION_PROFILES:
        raise HTTPException(422, "Profilo qualità non supportato")
    job_id = str(uuid.uuid4())
    job_dir = JOB_ROOT / job_id
    job_dir.mkdir(parents=True)
    input_name = Path(video.filename or "capture.mp4").name
    suffix = Path(input_name).suffix.lower() or ".mp4"
    input_path = job_dir / f"input{suffix}"
    with input_path.open("wb") as target:
        shutil.copyfileobj(video.file, target)
    (job_dir / "mesh.json").write_text(json.dumps({"quality": quality, "input_mode": "rgb", "input_name": input_name}))
    (job_dir / "state.json").write_text(json.dumps({"status": "queued", "progress": 0, "message": "In attesa della GPU"}))
    task = run_reconstruction.delay(job_id, str(input_path), "rgb", quality)
    (job_dir / "task.txt").write_text(task.id)
    return {"id": job_id, "status": "queued"}


@app.post("/api/jobs/zed", status_code=202)
async def create_zed_job(capture: UploadFile = File(...), quality: str = Form("balanced")):
    """Accept the portable ZED ZIP: recording.mp4, depth_data.dp, camera_data.dp."""
    if capture.content_type not in ALLOWED_ZED_TYPES:
        raise HTTPException(415, "Carica un archivio ZIP della cattura ZED.")
    if quality not in RECONSTRUCTION_PROFILES:
        raise HTTPException(422, "Profilo qualità non supportato")
    job_id = str(uuid.uuid4())
    job_dir = JOB_ROOT / job_id
    job_dir.mkdir(parents=True)
    archive_path = job_dir / "zed-capture.zip"
    with archive_path.open("wb") as target:
        shutil.copyfileobj(capture.file, target)
    try:
        validate_zed_archive(archive_path)
    except (BadZipFile, ValueError) as exc:
        shutil.rmtree(job_dir)
        raise HTTPException(422, f"Archivio ZED non valido: {exc}") from exc
    (job_dir / "mesh.json").write_text(json.dumps({"quality": quality, "input_mode": "zed", "input_name": Path(capture.filename or "zed-capture.zip").name}))
    (job_dir / "state.json").write_text(json.dumps({"status": "queued", "progress": 0, "message": "Cattura ZED in attesa della GPU"}))
    task = run_reconstruction.delay(job_id, str(archive_path), "zed", quality)
    (job_dir / "task.txt").write_text(task.id)
    return {"id": job_id, "status": "queued", "input_mode": "zed"}


@app.post("/api/jobs/colmap", status_code=202)
async def create_colmap_job(dataset: UploadFile = File(...), quality: str = Form("balanced")):
    """Queue a validated, preprocessed COLMAP scene without preprocessing it again."""
    if dataset.content_type not in ALLOWED_ZED_TYPES:
        raise HTTPException(415, "Carica un archivio ZIP contenente il dataset COLMAP.")
    if quality not in RECONSTRUCTION_PROFILES:
        raise HTTPException(422, "Profilo qualità non supportato")
    job_id = str(uuid.uuid4())
    job_dir = JOB_ROOT / job_id
    job_dir.mkdir(parents=True)
    archive_path = job_dir / "colmap-dataset.zip"
    with archive_path.open("wb") as target:
        shutil.copyfileobj(dataset.file, target)
    try:
        validate_colmap_archive(archive_path)
    except ValueError as exc:
        shutil.rmtree(job_dir)
        raise HTTPException(422, f"Dataset COLMAP non valido: {exc}") from exc
    (job_dir / "mesh.json").write_text(json.dumps({"quality": quality, "input_mode": "colmap", "input_name": Path(dataset.filename or "colmap-dataset.zip").name}))
    (job_dir / "state.json").write_text(json.dumps({"status": "queued", "progress": 0, "message": "Dataset COLMAP in attesa della GPU"}))
    task = run_reconstruction.delay(job_id, str(archive_path), "colmap", quality)
    (job_dir / "task.txt").write_text(task.id)
    return {"id": job_id, "status": "queued", "input_mode": "colmap"}


@app.post("/api/jobs/sample", status_code=202)
def create_sample_job():
    """Queue the included, redistributable Pavarotti RGB demonstration capture."""
    if not SAMPLE_VIDEO.exists():
        raise HTTPException(404, "Il video demo non è installato nel container")
    job_id = str(uuid.uuid4())
    job_dir = JOB_ROOT / job_id
    job_dir.mkdir(parents=True)
    input_path = job_dir / "pavarotti-demo.mp4"
    shutil.copyfile(SAMPLE_VIDEO, input_path)
    (job_dir / "mesh.json").write_text(json.dumps({"quality": "high", "input_mode": "rgb", "input_name": "pavarotti-demo.mp4"}))
    (job_dir / "state.json").write_text(json.dumps({"status": "queued", "progress": 0, "message": "Demo Pavarotti in attesa della GPU"}))
    # Preserve the demo's historical full-quality behaviour.
    task = run_reconstruction.delay(job_id, str(input_path), "rgb", "high")
    (job_dir / "task.txt").write_text(task.id)
    return {"id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, response: Response):
    state = JOB_ROOT / job_id / "state.json"
    if not state.exists():
        raise HTTPException(404, "Job non trovato")
    response.headers["Cache-Control"] = "no-store"
    return read_job_state(state)


@app.get("/api/jobs/{job_id}/result")
def get_result(job_id: str):
    result = JOB_ROOT / job_id / "output" / "recon.ply"
    if not result.exists():
        raise HTTPException(404, "La mesh non è ancora disponibile")
    return FileResponse(result, filename=f"{job_id}.ply", media_type="application/octet-stream")


@app.post("/api/jobs/{job_id}/viewer/{quality}", status_code=202)
def request_viewer_mesh(job_id: str, quality: str):
    if quality not in VIEWER_TRIANGLE_TARGETS:
        raise HTTPException(422, "Qualità viewer non supportata")
    job_dir = job_directory(job_id)
    raw_mesh = job_dir / "output" / "recon.ply"
    target = job_dir / "output" / "viewer" / f"mesh-{quality}.ply"
    metadata_path = job_dir / "mesh.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    viewer = metadata.setdefault("viewer", {})
    if not raw_mesh.is_file():
        raise HTTPException(404, "Mesh non trovata")
    if target.is_file():
        return {"status": "completed"}
    current = viewer.get(quality, {})
    if current.get("status") == "queued":
        return {"status": "queued"}
    if current.get("status") == "running" and current.get("task_id") and viewer_task_is_active(current["task_id"]):
        return {"status": "running"}

    # A pre-task-id record is from an older deployment.  Likewise, a running
    # task not reported by any worker was interrupted (for example by docker
    # compose rebuild) and must not leave the browser polling indefinitely.
    task_id = str(uuid.uuid4())
    viewer[quality] = {
        "status": "queued",
        "message": "In attesa del worker",
        "task_id": task_id,
    }
    write_mesh_metadata(metadata_path, metadata)
    generate_viewer_mesh.apply_async(args=(job_dir.name, quality), task_id=task_id)
    return {"status": "queued"}


@app.get("/api/jobs/{job_id}/viewer/{quality}")
def get_viewer_mesh(job_id: str, quality: str):
    if quality not in VIEWER_TRIANGLE_TARGETS:
        raise HTTPException(422, "Qualità viewer non supportata")
    result = job_directory(job_id) / "output" / "viewer" / f"mesh-{quality}.ply"
    if not result.is_file():
        raise HTTPException(404, "La mesh per il viewer non è ancora disponibile")
    return FileResponse(result, filename=f"{job_id}-viewer-{quality}.ply", media_type="application/octet-stream")


@app.post("/api/jobs/{job_id}/gaussian-preview", status_code=202)
def request_gaussian_preview(job_id: str):
    job_dir = job_directory(job_id)
    if not (job_dir / "output" / "recon.ply").is_file():
        raise HTTPException(404, "La mesh non è ancora disponibile")
    metadata_path = job_dir / "mesh.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    preview = metadata.setdefault("gaussian_preview", {})
    target = job_dir / "output" / "gaussian_preview" / "preview-500k.ply.gz"
    if target.is_file():
        return {"status": "completed"}
    if preview.get("status") in {"queued", "running"}:
        return {"status": preview["status"]}
    preview.update({"status": "queued", "message": "In attesa del worker"})
    write_mesh_metadata(metadata_path, metadata)
    generate_gaussian_preview.delay(job_dir.name)
    return {"status": "queued"}


@app.get("/api/jobs/{job_id}/gaussian-preview.ply")
def get_gaussian_preview(job_id: str):
    result = job_directory(job_id) / "output" / "gaussian_preview" / "preview-500k.ply.gz"
    if not result.is_file():
        raise HTTPException(404, "La preview Gaussian non è ancora disponibile")
    return FileResponse(result, filename=f"{job_id}-gaussian-preview.ply", media_type="application/octet-stream", headers={"Content-Encoding": "gzip", "Cache-Control": "no-store"})


@app.get("/api/jobs/{job_id}/input-video")
def get_input_video(job_id: str):
    """Serve only the original RGB input saved in this job's private folder."""
    job_dir = job_directory(job_id)
    metadata_path = job_dir / "mesh.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    if metadata.get("input_mode") != "rgb":
        raise HTTPException(404, "Questo job non ha un video RGB originale")
    videos = [path for path in job_dir.iterdir() if path.is_file() and path.stem in {"input", "pavarotti-demo"}]
    if len(videos) != 1:
        raise HTTPException(404, "Il video originale di questo job non è disponibile")
    media_types = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".3gp": "video/3gpp",
        ".avi": "video/x-msvideo",
    }
    return FileResponse(videos[0], media_type=media_types.get(videos[0].suffix.lower(), "application/octet-stream"), headers={"Cache-Control": "private, no-store"})


@app.post("/api/jobs/{job_id}/video-preview", status_code=202)
def request_video_preview(job_id: str):
    job_dir = job_directory(job_id)
    metadata_path = job_dir / "mesh.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    if metadata.get("input_mode") != "rgb":
        raise HTTPException(404, "Il confronto video è disponibile solo per job RGB")
    target = job_dir / "output" / "video_preview" / "comparison-720p.mp4"
    if target.is_file():
        return {"status": "completed"}
    preview = metadata.setdefault("video_preview", {})
    if preview.get("status") in {"queued", "running"}:
        return {"status": preview["status"]}
    preview.update({"status": "queued", "message": "In attesa del worker"})
    write_mesh_metadata(metadata_path, metadata)
    generate_video_preview.delay(job_dir.name)
    return {"status": "queued"}


@app.get("/api/jobs/{job_id}/video-preview.mp4")
def get_video_preview(job_id: str):
    result = job_directory(job_id) / "output" / "video_preview" / "comparison-720p.mp4"
    if not result.is_file():
        raise HTTPException(404, "Il video di confronto non è ancora disponibile")
    return FileResponse(result, media_type="video/mp4", headers={"Cache-Control": "private, max-age=604800, immutable"})


@app.get("/api/jobs/{job_id}/processed-result")
def get_processed_result(job_id: str):
    result = job_directory(job_id) / "output" / "processed" / "recon-repaired-conservative-v6.ply"
    if not result.exists():
        raise HTTPException(404, "La mesh post-processata non è ancora disponibile")
    return FileResponse(result, filename=f"{job_id}-closed.ply", media_type="application/octet-stream")


@app.post("/api/jobs/{job_id}/glb/{quality}", status_code=202)
def request_glb(job_id: str, quality: str):
    if quality not in GLB_TRIANGLE_TARGETS:
        raise HTTPException(422, "Qualità GLB non supportata")
    job_dir = JOB_ROOT / job_id
    raw_mesh = job_dir / "output" / "recon.ply"
    target = job_dir / "output" / "downloads" / f"mesh-{quality}.glb"
    metadata_path = job_dir / "mesh.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    glb = metadata.setdefault("glb", {})
    if not raw_mesh.is_file():
        raise HTTPException(404, "Mesh non trovata")
    if target.is_file():
        return {"status": "completed"}
    if glb.get(quality, {}).get("status") in {"queued", "running"}:
        return {"status": glb[quality]["status"]}
    glb[quality] = {"status": "queued", "message": "In attesa del worker"}
    temporary_path = metadata_path.with_name(f"{metadata_path.name}.{uuid.uuid4().hex}.tmp")
    temporary_path.write_text(json.dumps(metadata))
    os.replace(temporary_path, metadata_path)
    generate_glb.delay(job_id, quality)
    return {"status": "queued"}


@app.get("/api/jobs/{job_id}/glb/{quality}")
def get_glb(job_id: str, quality: str):
    if quality not in GLB_TRIANGLE_TARGETS:
        raise HTTPException(422, "Qualità GLB non supportata")
    result = JOB_ROOT / job_id / "output" / "downloads" / f"mesh-{quality}.glb"
    if not result.is_file():
        raise HTTPException(404, "Il GLB richiesto non è ancora disponibile")
    return FileResponse(result, filename=f"{job_id}-{quality}.glb", media_type="model/gltf-binary")


@app.post("/api/jobs/{job_id}/mesh-name")
def rename_mesh(job_id: str, payload: MeshRename):
    job_dir = JOB_ROOT / job_id
    result = job_dir / "output" / "recon.ply"
    name = payload.name.strip()
    if not result.is_file():
        raise HTTPException(404, "Mesh non trovata")
    if not name or len(name) > 80 or any(character in name for character in "\r\n\x00"):
        raise HTTPException(422, "Il nome deve contenere da 1 a 80 caratteri su una sola riga")
    metadata_path = job_dir / "mesh.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    metadata["name"] = name
    temporary_path = metadata_path.with_name(f"{metadata_path.name}.{uuid.uuid4().hex}.tmp")
    temporary_path.write_text(json.dumps(metadata))
    os.replace(temporary_path, metadata_path)
    return {"id": job_id, "name": name}


@app.post("/api/jobs/{job_id}/postprocess", status_code=202)
def request_mesh_postprocess(job_id: str):
    job_dir = job_directory(job_id)
    raw_mesh = job_dir / "output" / "recon.ply"
    processed_mesh = job_dir / "output" / "processed" / "recon-repaired-conservative-v6.ply"
    metadata_path = job_dir / "mesh.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    if not raw_mesh.is_file():
        raise HTTPException(404, "Mesh non trovata")
    if processed_mesh.is_file():
        return {"status": "completed"}
    if metadata.get("postprocess_status") in {"queued", "running"}:
        return {"status": metadata["postprocess_status"]}
    temporary_path = metadata_path.with_name(f"{metadata_path.name}.{uuid.uuid4().hex}.tmp")
    metadata.update({"postprocess_status": "queued", "postprocess_progress": 0, "postprocess_message": "In attesa del worker"})
    temporary_path.write_text(json.dumps(metadata))
    os.replace(temporary_path, metadata_path)
    postprocess_mesh.delay(job_id)
    return {"status": "queued"}


@app.delete("/api/jobs/{job_id}", status_code=204)
def delete_mesh(job_id: str):
    """Delete one completed reconstruction and all of its private job files."""
    job_dir = job_directory(job_id)
    state_path = job_dir / "state.json"
    state = read_job_state(state_path) if state_path.is_file() else {}
    metadata_path = job_dir / "mesh.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    # A historical mesh can be usable even when the pipeline later failed
    # (for example during the final extraction step). Permit removal of any
    # terminal job with a real output, but never a queued or running one.
    if state.get("status") not in {"completed", "failed"} or not (job_dir / "output" / "recon.ply").is_file():
        raise HTTPException(409, "Si possono eliminare soltanto ricostruzioni terminate con una mesh disponibile")
    if metadata.get("postprocess_status") in {"queued", "running"}:
        raise HTTPException(409, "Attendi il termine della chiusura buchi prima di eliminare la ricostruzione")
    shutil.rmtree(job_dir)
    return Response(status_code=204)


@app.post("/api/jobs/{job_id}/monitor")
def open_monitor(job_id: str):
    """Select a completed Gaussian model for the isolated SIBR monitor."""
    job_dir = JOB_ROOT / job_id
    state_path = job_dir / "state.json"
    point_clouds = list((job_dir / "output" / "point_cloud").glob("iteration_*/point_cloud.ply"))
    point_cloud = max(point_clouds, key=lambda path: int(path.parent.name.removeprefix("iteration_")), default=None)
    if not state_path.exists():
        raise HTTPException(404, "Job non trovato")
    if json.loads(state_path.read_text()).get("status") != "completed":
        raise HTTPException(409, "Il Monitor è disponibile quando il job è completato")
    if point_cloud is None:
        raise HTTPException(404, "Il Gaussian point cloud del job non è disponibile")
    # The monitor volume is read-only: the API is the sole writer of this request.
    (JOB_ROOT / "monitor-request.json").write_text(json.dumps({"job_id": job_id}))
    return {"monitor_port": 50001, "message": "Monitor avviato sul risultato selezionato"}


# Keep this catch-all mount last so /api/* remains reachable.
@app.get("/mobile.html", include_in_schema=False)
def mobile_upload_page():
    return FileResponse(STATIC_ROOT / "mobile.html", headers={"Cache-Control": "no-store, max-age=0"})


@app.get("/mobile.js", include_in_schema=False)
def mobile_upload_script():
    return FileResponse(STATIC_ROOT / "mobile.js", media_type="text/javascript", headers={"Cache-Control": "no-store, max-age=0"})


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
