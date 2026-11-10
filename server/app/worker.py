import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Optional

import open3d as o3d

from celery import Celery
from app.colmap_dataset import extract_colmap_archive
from app.zed_capture import extract_zed_archive

ROOT = Path("/app")
JOB_ROOT = Path(os.getenv("JOB_ROOT", "/jobs"))
celery_app = Celery("radegs", broker=os.getenv("REDIS_URL", "redis://redis:6379/0"), backend=os.getenv("REDIS_URL", "redis://redis:6379/0"))

GLB_TRIANGLE_TARGETS = {
    "low": 100_000,
    "medium": 500_000,
    "high": None,
}

# Browser-safe copies of the original mesh. The source PLY is never changed.
VIEWER_TRIANGLE_TARGETS = {
    "low": 250_000,
    "medium": 750_000,
    "high": 1_500_000,
}

GAUSSIAN_PREVIEW_SPLATS = 500_000
VIDEO_PREVIEW_HEIGHT = 720

# A reconstruction profile governs the complete pipeline, not just training.
RECONSTRUCTION_PROFILES = {
    "fast": {"rgb_fps": 1, "zed_frames": 60, "iterations": 15_000, "resolution": 2, "voxel_size": 0.008},
    "balanced": {"rgb_fps": 1.5, "zed_frames": 90, "iterations": 22_000, "resolution": 1, "voxel_size": 0.006},
    "high": {"rgb_fps": 2, "zed_frames": 120, "iterations": 30_000, "resolution": 1, "voxel_size": 0.004},
    "very_high": {"rgb_fps": 4, "zed_frames": 160, "iterations": 45_000, "resolution": 1, "voxel_size": 0.003},
}


def update(job: Path, status: str, progress: int, message: str, eta_seconds: Optional[int] = None):
    state_path = job / "state.json"
    previous = json.loads(state_path.read_text()) if state_path.exists() else {}
    now = time.time()
    if status == "running":
        # Different COLMAP stages emit unrelated n/total counters. Keep the
        # visible job progress monotonic rather than appearing to go backward.
        progress = max(progress, int(previous.get("progress", 0)))
    progress = max(0, min(100, progress))
    state = {
        "status": status,
        "progress": progress,
        "message": message,
        "started_at": previous.get("started_at", now),
        "updated_at": now,
    }
    if eta_seconds is not None:
        state["eta_seconds"] = eta_seconds
    # Replace is atomic on the shared Docker volume: API readers never observe
    # a partially written (or temporarily empty) JSON document.
    temporary_path = state_path.with_name(f"{state_path.name}.{uuid.uuid4().hex}.tmp")
    temporary_path.write_text(json.dumps(state))
    os.replace(temporary_path, state_path)


def update_mesh_metadata(job: Path, **values):
    metadata_path = job / "mesh.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    metadata.update(values)
    temporary_path = metadata_path.with_name(f"{metadata_path.name}.{uuid.uuid4().hex}.tmp")
    temporary_path.write_text(json.dumps(metadata))
    os.replace(temporary_path, metadata_path)


def ensure_monitor_checkpoint(output: Path, iteration: int) -> None:
    """Keep the existing fixed-iteration Gaussian Monitor compatible."""
    if iteration == 30_000:
        return
    source = output / "point_cloud" / f"iteration_{iteration}" / "point_cloud.ply"
    target = output / "point_cloud" / "iteration_30000" / "point_cloud.ply"
    if not source.is_file() or target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def run(job: Path, command: list[str], progress_start: int, progress_end: int, message: str, cwd: Path = ROOT):
    update(job, "running", progress_start, message)
    recent_output = []
    with (job / "worker.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in process.stdout:
            log.write(line)
            if line.strip():
                recent_output = (recent_output + [line.strip()])[-12:]
            phase = re.search(r"COLMAP_STAGE:\s*(.+)", line)
            if phase:
                update(job, "running", progress_start, f"{message} — {phase.group(1)}")
            # Only consume progress counters emitted by known tools. Generic
            # n/total matching also caught unrelated values and could display
            # percentages above 100.
            feature_match = re.search(r"Processed file \[(\d+)/(\d+)\]", line)
            training_match = re.search(r"Training progress:.*?(\d+)\s*/\s*(\d+).*?<([0-9:]+)", line)
            mesh_match = re.search(r"Mesh fusion \[(\d+)/(\d+)\]", line)
            match = training_match or feature_match or mesh_match
            if match and int(match.group(2)):
                pct = int(match.group(1)) / int(match.group(2))
                eta_seconds = None
                if training_match:
                    eta_seconds = sum(value * factor for value, factor in zip(
                        reversed([int(value) for value in training_match.group(3).split(":")]),
                        (1, 60, 3600),
                    ))
                update(
                    job,
                    "running",
                    progress_start + int((progress_end - progress_start) * pct),
                    message,
                    eta_seconds,
                )
        if process.wait() != 0:
            diagnostic = next((line for line in reversed(recent_output) if "error" in line.lower() or "exception" in line.lower()), recent_output[-1] if recent_output else "vedi worker.log")
            raise RuntimeError(f"Comando fallito: {' '.join(command)} — {diagnostic}")


@celery_app.task(bind=True)
def run_reconstruction(self, job_id: str, input_file: str, input_mode: str = "rgb", quality: str = "balanced"):
    job = JOB_ROOT / job_id
    scene = job / "scene"
    frames = scene / "input"
    output = job / "output"
    output.mkdir(parents=True, exist_ok=True)
    try:
        if input_mode not in {"rgb", "zed", "colmap"}:
            raise ValueError(f"Modalità di input non supportata: {input_mode}")
        if quality not in RECONSTRUCTION_PROFILES:
            raise ValueError(f"Profilo qualità non supportato: {quality}")
        profile = RECONSTRUCTION_PROFILES[quality]
        training_scene = scene
        if input_mode == "colmap":
            update(job, "running", 2, "Validazione e preparazione dataset COLMAP")
            extract_colmap_archive(Path(input_file), scene)
            if not (scene / "sparse" / "0" / "points3D.bin").is_file():
                raise RuntimeError("Il dataset COLMAP estratto non contiene il modello sparse richiesto")
            update(job, "running", 5, "Dataset COLMAP pronto per il training")
        else:
            frames.mkdir(parents=True, exist_ok=True)
        if input_mode == "zed":
            capture = extract_zed_archive(Path(input_file), job / "zed_capture")
            run(job, ["python", "video_to_masked_colmap.py", str(capture), str(frames), str(scene), "--n_frames", str(profile["zed_frames"]), "--mode", "zed", "--white", "--avoid_colmap_masks", "--log", str(job / "digs.log")], 1, 28, "Frame, maschere e COLMAP ZED", ROOT / "DiGS")
            training_scene = job / "scene_densified"
            run(job, ["python", "densify_sfm_pcd.py", str(scene), str(scene / "depths"), str(capture / "camera_data.dp"), str(training_scene), "--masks_path", str(scene / "masks"), "--voxel_size", "0.1", "--log", str(job / "digs.log")], 28, 45, "Densificazione depth-aware ZED", ROOT / "DiGS")
        elif input_mode == "rgb":
            run(job, ["ffmpeg", "-y", "-i", input_file, "-vf", f"fps={profile['rgb_fps']}", str(frames / "%04d.png")], 1, 8, "Estrazione dei fotogrammi")
            run(job, ["python", str(ROOT / "server/app/frame_quality.py"), str(frames)], 8, 9, "Controllo qualità e frame mossi")
            # COLMAP uses GPU SIFT. The Docker services expose NVIDIA's
            # graphics capability and Qt runs through the offscreen backend.
            # Deliberately keep frames unmasked here: environmental features
            # stabilize camera poses. Segmentation is applied afterwards only
            # to scene/images, which is what RaDe-GS trains on.
            run(job, ["python", str(ROOT / "SuGaR/gaussian_splatting/convert.py"), "-s", str(scene), "--matching_method", "sequential", "--sequential_overlap", "15"], 9, 23, "Ricostruzione COLMAP GPU")
            run(job, ["python", str(ROOT / "server/app/mask_refinement.py"), "--images", str(scene / "images"), "--masks", str(scene / "masks"), "--generate", "--apply-white"], 23, 25, "Segmentazione per il training RaDe-GS")
        if not (training_scene / "sparse" / "0" / "points3D.bin").is_file():
            raise RuntimeError("COLMAP non ha generato il modello sparse richiesto per il training RaDe-GS")
        train_start = 45 if input_mode == "zed" else 5 if input_mode == "colmap" else 25
        run(job, ["python", str(ROOT / "RaDe-GS/train.py"), "-s", str(training_scene), "-m", str(output), "--iterations", str(profile["iterations"]), "--resolution", str(profile["resolution"]), "--white_background", "--use_decoupled_appearance"], train_start, 90, "Training geometrico RaDe-GS")
        ensure_monitor_checkpoint(output, profile["iterations"])
        run(job, ["python", str(ROOT / "RaDe-GS/mesh_extract.py"), "-s", str(training_scene), "-m", str(output), "--resolution", str(profile["resolution"]), "--voxel_size", str(profile["voxel_size"]), "--white_background", "--use_decoupled_appearance"], 90, 94, "Estrazione della mesh")
        queue_viewer_meshes(job)
    except Exception as exc:
        update(job, "failed", 0, str(exc))
        raise


@celery_app.task(bind=True)
def postprocess_mesh(self, job_id: str):
    job = JOB_ROOT / job_id
    raw_mesh = job / "output" / "recon.ply"
    processed_dir = job / "output" / "processed"
    if not raw_mesh.is_file():
        raise FileNotFoundError("Mesh originale non trovata")
    label = "Riparazione conservativa dei piccoli buchi"
    update_mesh_metadata(job, postprocess_status="running", postprocess_progress=5, postprocess_message=f"Avvio: {label}")
    last_output = ""
    with (job / "postprocess.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen(
            ["python", str(ROOT / "RaDe-GS/postprocessing.py"), str(raw_mesh), "--output_folder", str(processed_dir)],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in process.stdout:
            log.write(line)
            if line.strip():
                last_output = line.strip()
            progress_match = re.search(r"POSTPROCESS_PROGRESS:\s*(\d+)\s*(.*)", line)
            if progress_match:
                update_mesh_metadata(
                    job,
                    postprocess_status="running",
                    postprocess_progress=max(0, min(99, int(progress_match.group(1)))),
                    postprocess_message=progress_match.group(2).strip() or label,
                )
        return_code = process.wait()
    processed_mesh = processed_dir / "recon-repaired-conservative-v6.ply"
    if return_code or not processed_mesh.is_file():
        detail = last_output[:240] if last_output else "output finale non creato"
        update_mesh_metadata(
            job,
            postprocess_status="failed",
            postprocess_progress=0,
            postprocess_message=f"{label} non completata: {detail}",
        )
        raise RuntimeError(f"Post-processing mesh fallito: {detail}")
    update_mesh_metadata(job, postprocess_status="completed", postprocess_progress=100, postprocess_message=f"{label} pronta")


def create_viewer_mesh(job_id: str, quality: str, task_id: str) -> None:
    """Create a cached, browser-friendly PLY without changing the source mesh."""
    if quality not in VIEWER_TRIANGLE_TARGETS:
        raise ValueError("Profilo viewer non supportato")
    job = JOB_ROOT / job_id
    raw_mesh = job / "output" / "recon.ply"
    viewer_dir = job / "output" / "viewer"
    target = viewer_dir / f"mesh-{quality}.ply"
    temporary = target.with_suffix(".tmp.ply")
    if not raw_mesh.is_file():
        raise FileNotFoundError("Mesh originale non trovata")

    metadata_path = job / "mesh.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    viewer = metadata.setdefault("viewer", {})
    current = viewer.get(quality, {})
    # Do not let an obsolete task overwrite the status of a newer retry.
    if current.get("task_id") and current["task_id"] != task_id:
        return
    viewer[quality] = {
        **current,
        "status": "running",
        "message": "Semplificazione mesh per il viewer",
        "task_id": task_id,
    }
    update_mesh_metadata(job, viewer=viewer)
    try:
        viewer_dir.mkdir(parents=True, exist_ok=True)
        mesh = o3d.io.read_triangle_mesh(str(raw_mesh))
        if mesh.is_empty():
            raise RuntimeError("La mesh originale non contiene triangoli")
        original_triangles = len(mesh.triangles)
        triangle_target = VIEWER_TRIANGLE_TARGETS[quality]
        if original_triangles > triangle_target:
            mesh = mesh.simplify_quadric_decimation(triangle_target)
            mesh.remove_degenerate_triangles()
            mesh.remove_duplicated_triangles()
            mesh.remove_unreferenced_vertices()
        mesh.compute_vertex_normals()
        if not o3d.io.write_triangle_mesh(str(temporary), mesh, write_ascii=False, compressed=True):
            raise RuntimeError("Open3D non ha potuto esportare il PLY per il viewer")
        os.replace(temporary, target)
        viewer[quality] = {
            **viewer[quality],
            "status": "completed",
            "message": "Mesh viewer pronta",
            "triangles": len(mesh.triangles),
            "source_triangles": original_triangles,
        }
        update_mesh_metadata(job, viewer=viewer)
    except Exception as exc:
        if temporary.exists():
            temporary.unlink()
        viewer[quality] = {**viewer[quality], "status": "failed", "message": str(exc)}
        update_mesh_metadata(job, viewer=viewer)
        raise


def queue_viewer_meshes(job: Path) -> None:
    """Prepare every viewer preset before marking the job completed."""
    metadata_path = job / "mesh.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    viewer = metadata.setdefault("viewer", {})
    pending = [quality for quality in VIEWER_TRIANGLE_TARGETS if not (job / "output" / "viewer" / f"mesh-{quality}.ply").is_file()]
    if not pending:
        update(job, "completed", 100, "Mesh e preset viewer pronti")
        return
    task_id = str(uuid.uuid4())
    for quality in pending:
        viewer[quality] = {
            "status": "queued",
            "message": "Preparazione automatica dopo la ricostruzione",
            "task_id": task_id,
        }
    update_mesh_metadata(job, viewer=viewer)
    update(job, "running", 94, "Preparazione preset viewer (1/3)")
    generate_viewer_meshes.apply_async(args=(job.name,), task_id=task_id)


@celery_app.task(bind=True)
def generate_viewer_mesh(self, job_id: str, quality: str):
    return create_viewer_mesh(job_id, quality, self.request.id)


@celery_app.task(bind=True)
def generate_viewer_meshes(self, job_id: str):
    """Generate viewer presets one at a time to avoid competing for memory."""
    job = JOB_ROOT / job_id
    profiles = (("medium", "Bilanciato"), ("low", "Rapido"), ("high", "Dettagliato"))
    failures = []
    for index, (quality, label) in enumerate(profiles, start=1):
        target = job / "output" / "viewer" / f"mesh-{quality}.ply"
        if target.is_file():
            continue
        update(job, "running", 94 + (index - 1) * 2, f"Preparazione preset viewer ({index}/3): {label}")
        try:
            create_viewer_mesh(job_id, quality, self.request.id)
        except Exception as exc:
            # Keep preparing the remaining profiles: a single export should
            # not make the other viewer choices unavailable.
            failures.append(label)
            continue
    if failures:
        update(job, "completed", 100, f"Mesh pronta; preset non disponibili: {', '.join(failures)}")
    else:
        update(job, "completed", 100, "Mesh e preset viewer pronti")


def gaussian_point_cloud(job: Path) -> Path:
    point_clouds = job / "output" / "point_cloud"
    preferred = point_clouds / "iteration_30000" / "point_cloud.ply"
    if preferred.is_file():
        return preferred
    candidates = list(point_clouds.glob("iteration_*/point_cloud.ply"))
    if not candidates:
        raise FileNotFoundError("Gaussian point cloud non disponibile")
    return max(candidates, key=lambda path: int(path.parent.name.removeprefix("iteration_")))


@celery_app.task(bind=True)
def generate_gaussian_preview(self, job_id: str):
    """Cache a sampled and gzip-compressed Gaussian PLY for the web viewer."""
    job = JOB_ROOT / job_id
    source = gaussian_point_cloud(job)
    preview_dir = job / "output" / "gaussian_preview"
    target = preview_dir / "preview-500k.ply.gz"
    temporary = preview_dir / "preview-500k.tmp.ply.gz"
    metadata_path = job / "mesh.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    preview = metadata.setdefault("gaussian_preview", {})
    preview.update({"status": "running", "message": "Preparazione preview Gaussian compressa"})
    update_mesh_metadata(job, gaussian_preview=preview)
    try:
        with (job / "gaussian-preview.log").open("a", encoding="utf-8") as log:
            process = subprocess.run(["python", str(ROOT / "server/app/gaussian_preview.py"), str(source), str(temporary), "--max-splats", str(GAUSSIAN_PREVIEW_SPLATS)], stdout=log, stderr=subprocess.STDOUT, text=True, check=False)
        if process.returncode or not temporary.is_file():
            raise RuntimeError("Conversione della preview Gaussian non riuscita")
        os.replace(temporary, target)
        preview.update({"status": "completed", "message": "Preview Gaussian pronta", "splats": GAUSSIAN_PREVIEW_SPLATS, "source_bytes": source.stat().st_size, "preview_bytes": target.stat().st_size})
        update_mesh_metadata(job, gaussian_preview=preview)
    except Exception as exc:
        if temporary.exists():
            temporary.unlink()
        preview.update({"status": "failed", "message": str(exc)})
        update_mesh_metadata(job, gaussian_preview=preview)
        raise


@celery_app.task(bind=True)
def generate_video_preview(self, job_id: str):
    """Create a streamable comparison copy without changing the source upload."""
    job = JOB_ROOT / job_id
    metadata_path = job / "mesh.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    if metadata.get("input_mode") != "rgb":
        raise ValueError("Il confronto video è disponibile solo per input RGB")
    sources = [path for path in job.iterdir() if path.is_file() and path.stem in {"input", "pavarotti-demo"}]
    if len(sources) != 1:
        raise FileNotFoundError("Video originale non disponibile")
    preview_dir = job / "output" / "video_preview"
    target = preview_dir / "comparison-720p.mp4"
    temporary = preview_dir / "comparison-720p.tmp.mp4"
    preview = metadata.setdefault("video_preview", {})
    preview.update({"status": "running", "message": "Preparazione video di confronto leggero"})
    update_mesh_metadata(job, video_preview=preview)
    try:
        preview_dir.mkdir(parents=True, exist_ok=True)
        with (job / "video-preview.log").open("a", encoding="utf-8") as log:
            process = subprocess.run(
                [
                    "ffmpeg", "-y", "-i", str(sources[0]), "-map", "0:v:0", "-an",
                    "-vf", f"scale=-2:{VIDEO_PREVIEW_HEIGHT}", "-r", "24",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "25",
                    "-maxrate", "1200k", "-bufsize", "2400k", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart", str(temporary),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
            )
        if process.returncode or not temporary.is_file():
            raise RuntimeError("FFmpeg non ha potuto creare il video di confronto")
        os.replace(temporary, target)
        preview.update({"status": "completed", "message": "Video di confronto pronto", "bytes": target.stat().st_size})
        update_mesh_metadata(job, video_preview=preview)
    except Exception as exc:
        if temporary.exists():
            temporary.unlink()
        preview.update({"status": "failed", "message": str(exc)})
        update_mesh_metadata(job, video_preview=preview)
        raise


@celery_app.task(bind=True)
def generate_glb(self, job_id: str, quality: str):
    """Create and cache a web-friendly (or full-quality) GLB download."""
    if quality not in GLB_TRIANGLE_TARGETS:
        raise ValueError("Profilo GLB non supportato")
    job = JOB_ROOT / job_id
    raw_mesh = job / "output" / "recon.ply"
    downloads_dir = job / "output" / "downloads"
    target = downloads_dir / f"mesh-{quality}.glb"
    temporary = target.with_suffix(".tmp.glb")
    if not raw_mesh.is_file():
        raise FileNotFoundError("Mesh originale non trovata")

    metadata_path = job / "mesh.json"
    metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
    glb = metadata.setdefault("glb", {})
    glb[quality] = {"status": "running", "message": "Preparazione GLB in corso"}
    update_mesh_metadata(job, glb=glb)
    try:
        downloads_dir.mkdir(parents=True, exist_ok=True)
        mesh = o3d.io.read_triangle_mesh(str(raw_mesh))
        if mesh.is_empty():
            raise RuntimeError("La mesh originale non contiene triangoli")
        triangle_target = GLB_TRIANGLE_TARGETS[quality]
        if triangle_target is not None and len(mesh.triangles) > triangle_target:
            mesh = mesh.simplify_quadric_decimation(triangle_target)
            mesh.remove_degenerate_triangles()
            mesh.remove_duplicated_triangles()
            mesh.remove_unreferenced_vertices()
            mesh.compute_vertex_normals()
        if not o3d.io.write_triangle_mesh(str(temporary), mesh):
            raise RuntimeError("Open3D non ha potuto esportare il GLB")
        os.replace(temporary, target)
        glb[quality] = {"status": "completed", "message": "GLB pronto", "triangles": len(mesh.triangles)}
        update_mesh_metadata(job, glb=glb)
    except Exception as exc:
        if temporary.exists():
            temporary.unlink()
        glb[quality] = {"status": "failed", "message": str(exc)}
        update_mesh_metadata(job, glb=glb)
        raise
