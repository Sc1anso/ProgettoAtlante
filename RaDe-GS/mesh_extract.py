import os
import torch
from random import randint
import sys
from scene import Scene, GaussianModel
from argparse import ArgumentParser, Namespace
from arguments import ModelParams, PipelineParams, OptimizationParams
import matplotlib.pyplot as plt
import math
import numpy as np
from scene.cameras import Camera
from gaussian_renderer import render
import open3d as o3d
from scene.dataset_readers import sceneLoadTypeCallbacks
from utils.camera_utils import cameraList_from_camInfos, camera_to_JSON
import json


def load_camera(args):
    if os.path.exists(os.path.join(args.source_path, "sparse")):
        scene_info = sceneLoadTypeCallbacks["Colmap"](args.source_path, args.images, args.eval)
    elif os.path.exists(os.path.join(args.source_path, "transforms_train.json")):
        print("Found transforms_train.json file, assuming Blender data set!")
        scene_info = sceneLoadTypeCallbacks["Blender"](args.source_path, args.white_background, args.eval)
    return cameraList_from_camInfos(scene_info.train_cameras, 1.0, args)




def extract_mesh(dataset, pipe, checkpoint_iterations=None, voxel_size=0.004):
    gaussians = GaussianModel(dataset.sh_degree)
    output_path = os.path.join(dataset.model_path,"point_cloud")
    iteration = 0
    if checkpoint_iterations is None:
        for folder_name in os.listdir(output_path):
            iteration= max(iteration,int(folder_name.split('_')[1]))
    else:
        iteration = checkpoint_iterations
    output_path = os.path.join(output_path,"iteration_"+str(iteration),"point_cloud.ply")

    gaussians.load_ply(output_path)
    print(f'Loaded gaussians from {output_path}')
    
    kernel_size = dataset.kernel_size
    
    bg_color = [1, 1, 1]
    background = torch.tensor(bg_color, dtype=torch.float32, device="cuda")
    viewpoint_cam_list = load_camera(dataset)

    # The tensor VoxelBlockGrid backend segfaults in Open3D's native pybind
    # code when extracting a large CPU mesh. The legacy scalable TSDF backend
    # is stable for this CPU-only reconstruction step.
    volume = o3d.pipelines.integration.ScalableTSDFVolume(
        voxel_length=voxel_size,
        sdf_trunc=voxel_size * 8,
        color_type=o3d.pipelines.integration.TSDFVolumeColorType.RGB8,
    )
    alpha_thres = 0.5
    camera_count = len(viewpoint_cam_list)
    for camera_index, viewpoint_cam in enumerate(viewpoint_cam_list, start=1):
        # Integrate immediately rather than keeping all full-resolution renders
        # in RAM. A 167-frame capture otherwise retains several GiB at once.
        render_pkg = render(viewpoint_cam, gaussians, pipe, background, kernel_size)
        rendered_img = torch.clamp(render_pkg["render"], min=0, max=1.0).cpu().numpy().transpose(1,2,0)
        depth_img = render_pkg["median_depth"].clone()
        if viewpoint_cam.gt_mask is not None:
            depth_img[(viewpoint_cam.gt_mask < 0.5)] = 0
        depth_img[render_pkg["mask"] < alpha_thres] = 0
        depth = depth_img[0].cpu().numpy().astype(np.float32)
        color = np.ascontiguousarray((rendered_img * 255).clip(0, 255).astype(np.uint8))
        W, H = viewpoint_cam.image_width, viewpoint_cam.image_height
        fx = W / (2 * math.tan(viewpoint_cam.FoVx / 2.))
        fy = H / (2 * math.tan(viewpoint_cam.FoVy / 2.))
        intrinsic = o3d.camera.PinholeCameraIntrinsic(W, H, fx, fy, float(W) / 2, float(H) / 2)
        extrinsic = (viewpoint_cam.world_view_transform.T).cpu().numpy().astype(np.float64)
        rgbd = o3d.geometry.RGBDImage.create_from_color_and_depth(
            o3d.geometry.Image(color),
            o3d.geometry.Image(depth),
            depth_scale=1.0,
            depth_trunc=8.0,
            convert_rgb_to_intensity=False,
        )
        volume.integrate(rgbd, intrinsic, extrinsic)
        del render_pkg, rendered_img, depth_img, depth, color
        torch.cuda.empty_cache()
        print(f"Mesh fusion [{camera_index}/{camera_count}]", flush=True)

    mesh = volume.extract_triangle_mesh()
    mesh.compute_vertex_normals()
    o3d.io.write_triangle_mesh(os.path.join(dataset.model_path,"recon.ply"), mesh)
    print("done!")

if __name__ == "__main__":
    parser = ArgumentParser(description="Training script parameters")
    lp = ModelParams(parser)
    pp = PipelineParams(parser)
    parser.add_argument("--checkpoint_iterations", nargs="+", type=int, default=None)
    parser.add_argument("--voxel_size", type=float, default=0.004, help="TSDF voxel size in scene units")
    args = parser.parse_args(sys.argv[1:])
    with torch.no_grad():
        if args.voxel_size <= 0:
            parser.error("--voxel_size deve essere positivo")
        extract_mesh(lp.extract(args), pp.extract(args), args.checkpoint_iterations, args.voxel_size)
        
        
    
    
