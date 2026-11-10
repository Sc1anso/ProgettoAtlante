import sklearn.linear_model
import open3d as o3d
import os
import shutil
from Colmap_handler import ColmapDatabase
import argparse
import numpy as np
from video_frame_extraction import extract_camera_info
from tqdm import tqdm
from matplotlib import pyplot as plt
from scipy.stats import gaussian_kde
from sklearn.cluster import KMeans
import time
import cv2
from datetime import datetime
import sklearn
from densify_sfm_pcd import import_from_database, compute_kde, kmean_thresholding, get_ransac_regression_parameters, get_kmeans_front_centroid, process_depth, import_rgbd, import_real_params, write_pcd_database 

parser = argparse.ArgumentParser(description='Add depth information projection to SFM result')

parser.add_argument('db_path', type=str,
                    help='path of sparse colmap database')
parser.add_argument('depth_npy_path', type=str,
                    help='path of the depth npy files')
parser.add_argument('camera_param_path', type=str,
                    help='path of the binary file containing camera params')
parser.add_argument('output_db_path', type=str,
                    help='path of the database file that will be copied')
parser.add_argument('--masks_path', type=str, default=None,
                    help='path of the folder of segmentation masks')
parser.add_argument('--show_results', action='store_true',
                    help='show point clouds using open3D library during the process')
parser.add_argument('--depth_trunc', type=float, default=-1,
                    help='value at which truncate depth maps')
parser.add_argument('--overwrite_scale', type=float, default=-1,
                    help='scale to overwrite the computed one')
parser.add_argument('--skip_write_new_db', action="store_true", help="skip the creation of the new database folder. Densified pcd will be lost")
parser.add_argument('--log', type = str, default='./log_file.txt',
                    help='Path of the logger file')

args = parser.parse_args()
with open(args.log, 'a') as f:
    today = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    f.write(f"Fusion densifying  {args.db_path} ({today})\n")
    

def prune_sfm_pcd_with_masks(database_root, mask_foldername):
    print("Pruning SFM's pcd using masks")
    image_db_filepath = os.path.join(database_root, "sparse/0/images.bin")
    camera_db_filepath = os.path.join(database_root, "sparse/0/cameras.bin")
    pcd_db_filepath = os.path.join(database_root, "sparse/0/points3D.bin")
    masks_path = os.path.join(database_root, mask_foldername)
    assert os.path.isdir(database_root) and os.path.isfile(image_db_filepath) and os.path.isfile(camera_db_filepath) and os.path.isfile(pcd_db_filepath), "The path is not a colmap database!!"
    assert os.path.isdir(masks_path), "Error! Missing mask database folder!"
    colmap_db = ColmapDatabase(database_root)
    cameras = colmap_db.cameras
    camera_id, model, w, h, params = ColmapDatabase.colmap2camera(list(cameras.values())[0])
    images = colmap_db.images
    points3D = colmap_db.points3D
    
    temp_xyz = [pt.xyz for pt in points3D.values()]
    temp_xyz = np.stack(temp_xyz)
    temp_colors = [pt.rgb for pt in points3D.values()]
    temp_colors = np.stack(temp_colors)/255

    initial_pcd = o3d.open3d.geometry.PointCloud(o3d.utility.Vector3dVector(temp_xyz))
    initial_pcd.colors = o3d.utility.Vector3dVector(temp_colors)

    #GETTING MASKS AND RGB IMAGES
    poses = []
    filenames = []
    filtered_images = []
    masks = []
    for image in images.values():
        image_id, pose, img_camera_id, image_name, _, _ = ColmapDatabase.colmap2imageview(image)
        if img_camera_id == camera_id:
            filenames.append(image_name)
            #pose[:3,3] = pose[:3,3]
            poses.append(pose)
            filtered_images.append(image)
            mask_filepath = os.path.join(masks_path, image_name)
            mask = cv2.imread(mask_filepath, cv2.IMREAD_GRAYSCALE)
            if False:
                rgb_mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2RGB)
                rgb_image = cv2.cvtColor(cv2.imread(os.path.join(database_root, "images"+"/"+image_name), cv2.IMREAD_ANYCOLOR), cv2.COLOR_BGR2RGB)
                plt.imshow(np.hstack([rgb_image, rgb_mask]))
                plt.show()
            masks.append(mask)

    #GETTING 3D points with reference
    array_point3Ds_xyz = np.zeros((np.array(list(points3D.keys())).max()+1, 3))
    array_point3Ds_colors = np.zeros((np.array(list(points3D.keys())).max()+1, 3))
    for i,p in points3D.items():
        array_point3Ds_xyz[i] = p.xyz
        array_point3Ds_colors[i] = p.rgb
    all_refs = []
    #PRUNING 3D points
    start_time = time.time()
    points = []
    pcd_colors = []
    for idx, colmap_image in enumerate(tqdm(filtered_images)):
        mask = masks[idx]
        image_id, _, _, _, xys, point3D_ids = ColmapDatabase.colmap2imageview(colmap_image)

        keys = point3D_ids[point3D_ids>-1]
        xyzs = array_point3Ds_xyz[keys]
        colors = array_point3Ds_colors[keys]
        xys = xys[point3D_ids>-1]
        point3D_ids = point3D_ids[point3D_ids>-1]
        xys = np.rint(xys).astype(int)
        #filter xys that are outside bounds
        h, w = mask.shape
        include_idxs = (xys[:,0]>=0) & (xys[:,0]<w) & (xys[:,1]>=0) & (xys[:,1]<h)
        xys = xys[include_idxs]
        keys = keys[include_idxs]
        #filter xys that are not in the mask
        include_idxs = mask[xys[:,1],xys[:,0]] > 0
        xys = xys[include_idxs]
        keys = keys[include_idxs]

        if False:
            rgb_mask = cv2.cvtColor(mask, cv2.COLOR_GRAY2RGB)
            rgb_image = cv2.cvtColor(cv2.imread(os.path.join(database_root, "images"+"/"+filenames[idx]), cv2.IMREAD_ANYCOLOR), cv2.COLOR_BGR2RGB)
            input_rgb = cv2.cvtColor(cv2.imread(os.path.join(database_root, "input"+"/"+filenames[idx]), cv2.IMREAD_ANYCOLOR), cv2.COLOR_BGR2RGB)
            input_rgb = cv2.resize(input_rgb, (rgb_image.shape[1],rgb_image.shape[0]) )
            print("maks",mask.shape,"masked image", rgb_image.shape, "input_image", input_rgb.shape)
            marked_rgb = np.copy(rgb_image)
            for xy_idx in range(xys.shape[0]):
                x,y = np.rint(xys[xy_idx,0]).astype(int), np.rint(xys[xy_idx,1]).astype(int)
                marked_rgb = cv2.drawMarker(marked_rgb, (x,y), color=(255,0,0), markerType=cv2.MARKER_TILTED_CROSS, thickness=2, markerSize=10)
            plt.imshow(np.hstack([input_rgb, rgb_mask, marked_rgb]))
            plt.show()
        #get xyzs from point3D_ids
        xyzs = array_point3Ds_xyz[keys, :]
        colors = array_point3Ds_colors[keys, :]
        points.append(xyzs)
        pcd_colors.append(colors)


    points = np.vstack(points)
    pcd_colors = np.vstack(pcd_colors)/255
    pruned_pcd = o3d.open3d.geometry.PointCloud(o3d.utility.Vector3dVector(points))
    pruned_pcd.colors = o3d.utility.Vector3dVector(pcd_colors)
    elapsed_time = time.time()-start_time

    if True and args.show_results:
        initial_pcd.paint_uniform_color([1, 0.706, 0])
        o3d.visualization.draw_geometries([initial_pcd, pruned_pcd],
                                        zoom=0.5,
                                        front=[1, 0, 0],
                                        lookat=[0, 0, 0],
                                        up=[0, 0, 1],
                                        )

    return pruned_pcd, elapsed_time


def project_pointclouds(rgbd_images, poses, intrinsic_param, scale, initial_pcd, pruned_pcd):
    print("Projecting point clouds")
    start_time = time.time()
    output_voxel_size = 0.1 #EDIT 0.05
    intrinsic = o3d.camera.PinholeCameraIntrinsic(o3d.camera.PinholeCameraIntrinsicParameters.PrimeSenseDefault)
    fx, fy, cx, cy, h, w = intrinsic_param
    intrinsic.set_intrinsics(w, h, fx, fy, cx, cy)
    pcds = []
    down_pcds = []
    cameras_lineset = []
    pcd_combined = o3d.geometry.PointCloud()
    for idx in tqdm(range(len(rgbd_images))):
        rgbd_image = rgbd_images[idx]
        pose = poses[idx]
        #scale = scale_params["per_image_scales"][idx] if scale_params["per_image_scales"][idx]>0 else mean_scale
        scaled_pose = pose
        #scaled_pose[:3,3] = scaled_pose[:3,3]*scale
        inv_pose = np.linalg.inv(scaled_pose)
        pcd = o3d.geometry.PointCloud.create_from_rgbd_image(rgbd_image, intrinsic)
        down_pcd = pcd.voxel_down_sample(voxel_size=output_voxel_size)
        down_pcd.transform(inv_pose) 
        down_pcd.scale(1/scale, inv_pose[:3,3])
        pcds.append(down_pcd)
        pcd_combined += down_pcd
        camera_line = o3d.geometry.LineSet.create_camera_visualization(intrinsic, np.eye(4,4), 0.15)
        camera_line.transform(inv_pose)
        camera_line.paint_uniform_color(np.array([1,0,0]))
        cameras_lineset.append(camera_line)
        
        if False:
            pcd.scale(1/scale, inv_pose[:3,3])
            o3d.visualization.draw_geometries([pcd,cameras_lineset[idx]],
                                        zoom=0.5,
                                        front=[1, 0, 0],
                                        lookat=[0, 0, 0],
                                        up=[0, 0, 1],
                                        )
    clear_pcd, removed_idxs = pcd_combined.remove_statistical_outlier(10, 1)
    removed_pcd = pcd_combined.select_by_index(removed_idxs, invert=True)
    boundBox = clear_pcd.get_axis_aligned_bounding_box()
    pruned_pcd = pruned_pcd.crop(boundBox)
    fusion_pcd = clear_pcd + pruned_pcd
    elapsed_time = time.time()-start_time
    print(f"Projection time took {elapsed_time:.4f}")
    with open(args.log, 'a') as f:
        f.write(f"Projection time took {elapsed_time}\n")
    #down_pcds = [pcd.voxel_down_sample(voxel_size=output_voxel_size) for pcd in pcds]
    #pcd_combined = pcd_combined.voxel_down_sample(voxel_size=output_voxel_size)
    if args.show_results:
        initial_pcd.paint_uniform_color([1, 0.706, 0])
        removed_pcd.paint_uniform_color([1, 0, 0])
        o3d.visualization.draw_geometries([initial_pcd, clear_pcd, removed_pcd]+cameras_lineset,
                                        zoom=0.5,
                                        front=[1, 0, 0],
                                        lookat=[0, 0, 0],
                                        up=[0, 0, 1],)
        clear_pcd.paint_uniform_color([1, 0.706, 0])
        o3d.visualization.draw_geometries([fusion_pcd]+cameras_lineset,
                                        zoom=0.5,
                                        front=[1, 0, 0],
                                        lookat=[0, 0, 0],
                                        up=[0, 0, 1],)
    #breaker
    return fusion_pcd, elapsed_time



start = time.time()
args = parser.parse_args()
filenames, poses, intrinsic_param, all_refs, initial_pcd = import_from_database(args.db_path)
images_path = os.path.join(args.db_path, "input")
#real_intrinsic_param = import_real_params(args.camera_param_path) #useless
pruned_pcd, prune_time = prune_sfm_pcd_with_masks(args.db_path, args.masks_path)
rgbd_images, scale, preproc_eltime = import_rgbd(filenames, images_path, args.depth_npy_path, all_refs, args.masks_path, args.depth_trunc, args.overwrite_scale)
#pcds, poses = align_pcds(rgbd_images, poses, intrinsic_param, scale, initial_pcd)
pcd, proj_eltime = project_pointclouds(rgbd_images, poses, intrinsic_param, scale, initial_pcd, pruned_pcd)
if not args.skip_write_new_db:
    write_pcd_database(args.db_path, pcd, args.output_db_path)
print(f"ELAPSED TIME FOR ALL COMPUTATIONS {time.time()-start} (of which {prune_time+preproc_eltime+proj_eltime} for fusion method)")
with open(args.log, 'a') as f:
    f.write(f"Ended fusion sfm pcd computations in {time.time()-start} seconds (of which {preproc_eltime+proj_eltime} for actual method).\n")


#COLMAP COMMAND TO EXECUTE AFTER
#python3 video_to_masked_colmap.py zed_capture/ images ../SuGaR/gaussian_splatting/data/test_pipeline -w
#python3 densify_sfm_pcd.py ../SuGaR/gaussian_splatting/data/test_pipeline depths zed_capture/camera_data.dp ../SuGaR/gaussian_splatting/data/test_pipeline_densified --masks_path masks
#path='test_pipeline'
#python ../SuGaR/gaussian_splatting/train.py -s ../SuGaR/gaussian_splatting/data/$path --iterations 30000 -m ../SuGaR/gaussian_splatting/output/$path --save_iterations 100 300 500 1000 3000 7000 12000 30000 --test_iterations 100 300 500 1000 3000 7000 12000 30000 -w

#2dgs
#python ../2DSplat/train.py -s ../SuGaR/gaussian_splatting/data/test_pipeline_densified --test_iterations 100 500 3000 7000 12000 --save_iterations 100 500 3000 7000 12000 --iterations 12000 --white
#python ../2DSplat/render.py -m output/test_pipeline/ -s ../SuGaR/gaussian_splatting/data/test_pipeline --iteration 7000 --skip_train --skip_test