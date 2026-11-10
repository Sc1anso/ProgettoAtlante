import sklearn.linear_model
import open3d as o3d
import os
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
parser.add_argument('--voxel_size', type=float, default=0.1,
                    help='Voxel size to control resulting pcd density')
parser.add_argument('--skip_write_new_db', action="store_true", help="skip the creation of the new database folder. Densified pcd will be lost")
parser.add_argument('--log', type = str, default='./log_file.txt',
                    help='Path of the logger file')

args = parser.parse_args()
with open(args.log, 'a') as f:
    today = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    f.write(f"Densifying  {args.db_path} ({today})\n")





def compute_kde(arr: np.ndarray, precision = 0.001):
    #remove outliers
    std = arr.std()
    mean = arr.mean()
    arr = arr[(arr>mean-3*std) & (arr<mean+3*std)]
    print(f"KDE reducing samples to {30000} and in the range [{mean}-3*{std}({mean-3*std}),{mean}+3*{std}({mean+3*std})]")
    #sampling from data (in case)
    np.random.shuffle(arr)
    arr = arr[:30000]
    kde = gaussian_kde(arr)
    samples = np.arange(int(arr.max()/precision))*precision
    #print(samples)
    probs = kde.evaluate(samples)
    maxima_index = probs.argmax()
    maxima = samples[maxima_index]
    print("Maxima", maxima)
    return maxima

def kmean_thresholding(arr: np.ndarray):
    labels = KMeans(n_clusters=2, random_state=0, n_init="auto").fit_predict(arr)
    group_1_mean = arr[labels==0].mean()
    group_2_mean = arr[labels==1].mean()
    if group_1_mean< group_2_mean:
        return arr[labels==0], labels==0
    else:
        return arr[labels==1], labels==1
    
def get_ransac_regression_parameters(X:np.ndarray, y:np.ndarray):
    regressor = sklearn.linear_model.RANSACRegressor()
    regressor.fit(X.reshape(-1, 1),y)
    values = np.array([0,1]).reshape(-1,1)
    pred_y = regressor.predict(values)
    print("pred_y",pred_y.shape)
    q,p = pred_y[0],pred_y[1]
    m = p-q
    return m,q

def get_kmeans_front_centroid(depth, vmin, vmax):
    X = depth.flatten().reshape(-1,1)
    random_idxs = np.random.randint(0,len(X),size=30000)
    X = X[random_idxs]
    predictor = KMeans(n_clusters=2, random_state=0, n_init=1, max_iter=2, init=[[vmin],[vmax]])
    predictor.fit(X)
    front_centroid, back_centroid = predictor.cluster_centers_[0,0], predictor.cluster_centers_[1,0]
    #print(f"Found centroids {front_centroid}, {back_centroid}")
    return (back_centroid*0.25+front_centroid*0.75)


def process_depth(depth_image: np.ndarray)->np.ndarray:
    gradient_image = cv2.Laplacian(depth_image, cv2.CV_64F, ksize=5)
    #mask = np.ones_like(gradient_image, dtype=np.uint8)
    # before_depth = np.copy(depth_image)
    depth_image[np.abs(gradient_image)>(gradient_image.std()*0.1)] = 0
    # plt.figure(figsize=(14,8))
    # plt.imshow(np.hstack([before_depth,depth_image]), cmap="gray")
    # plt.show()
    return depth_image


def import_from_database(database_root):
    print("Extracting from database")
    image_db_filepath = os.path.join(database_root, "sparse/0/images.bin")
    camera_db_filepath = os.path.join(database_root, "sparse/0/cameras.bin")
    pcd_db_filepath = os.path.join(database_root, "sparse/0/points3D.bin")
    assert os.path.isdir(database_root) and os.path.isfile(image_db_filepath) and os.path.isfile(camera_db_filepath) and os.path.isfile(pcd_db_filepath), "The path is not a colmap database!!"
    colmap_db = ColmapDatabase(database_root)
    cameras = colmap_db.cameras
    assert len(cameras) == 1, f"Found database with {len(cameras)} different cameras, instead of 1"
    camera_id, model, w, h, params = ColmapDatabase.colmap2camera(list(cameras.values())[0])
    print(f"Camera of the model {model} with params {params}")
    fx, fy, cx, cy = params
    intrinsic_param = (fx, fy, cx, cy, h, w)
    images = colmap_db.images
    points3D = colmap_db.points3D
    
    temp_xyz = [pt.xyz for pt in points3D.values()]
    temp_xyz = np.stack(temp_xyz)
    temp_colors = [pt.rgb for pt in points3D.values()]
    temp_colors = np.stack(temp_colors)/255
    
    initial_pcd = o3d.open3d.geometry.PointCloud(o3d.utility.Vector3dVector(temp_xyz))
    initial_pcd.colors = o3d.utility.Vector3dVector(temp_colors)
    # o3d.visualization.draw_geometries([initial_pcd],
    #                                 zoom=0.5,
    #                                 front=[1, 0, 0],
    #                                 lookat=[0, 0, 0],
    #                                 up=[0, 0, 1],)

    #filtering images associated with the camera
    poses = []
    filenames = []
    filtered_images = []
    for image in images.values():
        image_id, pose, img_camera_id, image_name, _, _ = ColmapDatabase.colmap2imageview(image)
        if img_camera_id == camera_id:
            filenames.append(image_name)
            #pose[:3,3] = pose[:3,3]
            poses.append(pose)
            filtered_images.append(image)
    
    images = filtered_images
    print("Collecting reference points")
    #creating point3D array with row-index == id. Numpy array is necessary for fast computations
    array_point3Ds_xyz = np.zeros((np.array(list(points3D.keys())).max()+1, 3))
    for i,p in points3D.items():
        array_point3Ds_xyz[i] = p.xyz
    all_refs = []
    for idx,image in enumerate(tqdm(images)):
        
        ref_tvec = np.array(poses[idx][:3,3]).reshape((1,3))
        inv_tvec = np.linalg.inv(np.array(poses[idx]))[:3,3].reshape((1,3))
        _, _, _, _, xys, point3D_ids = ColmapDatabase.colmap2imageview(image)
        keys = point3D_ids[point3D_ids>-1]
        xyzs = array_point3Ds_xyz[keys]
        xys = xys[point3D_ids>-1]
        assert xyzs.ndim == 2 and xyzs.shape[1] == 3, f"ERROR. Uncorrect shapes! tvec {inv_tvec.shape}, xysz {xyzs.shape}"
        colmap_depths = np.sqrt(((xyzs-inv_tvec)**2).sum(axis=1))
        all_refs.append((xys, colmap_depths))

    if False and args.show_results:
        distances = np.copy(np.concatenate([colmap_depths[colmap_depths<10] for _, colmap_depths in all_refs]))
        distances.sort()
        print(f"{len(distances)} Distances. mean: {distances.mean()}, std: {distances.std()}")
        plt.scatter(range(len(distances)), distances)
        plt.show()
        breaker

    return filenames, poses, intrinsic_param, all_refs, initial_pcd



def import_rgbd(filenames, images_path, depth_npy_path, all_refs, masks_path, depth_trunc, overwrite_scale):
    print("Import RGBD images")
    rgb_images = []
    np_depths = []
    rgbd_images = []
    masks = []
    for name in tqdm(filenames):
        rgb_path = os.path.join(images_path, name)
        depth_path = os.path.join(depth_npy_path, name.split(".")[0]+".npy")
        #rgb_image = o3d.io.read_image(rgb_path) #EDIT
        rgb_data = cv2.cvtColor(cv2.imread(rgb_path, cv2.IMREAD_COLOR), cv2.COLOR_BGR2RGB)
        rgb_image = o3d.geometry.Image(rgb_data)
        rgb_images.append(rgb_image)
        np_depth = np.load(depth_path).astype(np.float32)
        np_depths.append(np_depth)
        if not masks_path is None:
            mask_filepath = os.path.join(masks_path, name)
            mask = cv2.imread(mask_filepath, cv2.IMREAD_GRAYSCALE)
            masks.append(mask)
        else:
            masks.append([])
    assert (len(rgb_images)==len(np_depths)) and ((masks_path is None) or (len(rgb_images)==len(masks))), f"ERROR! Found mismatching loads! rgb_images {len(rgb_images)}, np_depths {len(np_depths)}, masks {len(masks)}"
    #Start getting time of computations
    print("Pre-Processing depth and mask images")
    start_time = time.time()
    for i in tqdm(range(len(rgb_images))):
        rgb_image = rgb_images[i]
        np_depth = np_depths[i]
        np_depth = process_depth(np_depth)
        kmean_depth_trunc = 4000
        kmean_depth_trunc = get_kmeans_front_centroid(np_depth, 0, 4000)
        if not masks_path is None:            
            mask_filepath = os.path.join(masks_path, name)
            mask = masks[i]
            #mask = np.asarray(o3d.io.read_image(mask_filepath)) #EDIT
            uint_mask_thr = 20
            np_depth[mask <= uint_mask_thr] = 0
            masks.append(mask > uint_mask_thr)
            
            # plt.figure(figsize=(16,8))
            # plt.imshow(np.hstack([depth_before_masking,depth_before_processing,np_depth]),cmap='gray')
            # plt.show()
        depth_image = o3d.geometry.Image(np_depth)

        if depth_trunc == -1: depth_trunc = kmean_depth_trunc/1000
        elif depth_trunc > 20: depth_trunc = depth_trunc/1000
        rgbd_image = o3d.geometry.RGBDImage.create_from_color_and_depth(rgb_image, depth_image, depth_scale=1000, depth_trunc=depth_trunc, convert_rgb_to_intensity = False)
        rgbd_images.append(rgbd_image)
    scales = []
    point_depths = []
    print("Searching for scale parameter")
    reject_count = 0
    out_of_bound_reject_count = 0
    out_of_maks_reject_count = 0
    for idx, (xys, colmap_depths) in enumerate(tqdm(all_refs)):
        ref_depth = np.asarray(rgbd_images[idx].depth)
        height, width = ref_depth.shape
        if False:
            #Print points over images reference
            ref_rgb = np.asarray(rgbd_images[idx].color)
            marked_rgb = cv2.cvtColor(ref_rgb, cv2.COLOR_RGB2BGR)
            marked_depth = cv2.cvtColor((ref_depth/4*255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
            marked_mask = cv2.cvtColor(masks[idx].astype(np.uint8)*255, cv2.COLOR_GRAY2BGR)
            for xy_idx in range(xys.shape[0]):
                x,y = np.rint(xys[xy_idx,0]).astype(int), np.rint(xys[xy_idx,1]).astype(int)
                marked_rgb = cv2.drawMarker(marked_rgb, (x,y), color=(255,0,0), markerType=cv2.MARKER_TILTED_CROSS, thickness=2, markerSize=10)
                marked_depth = cv2.drawMarker(marked_depth, (x,y), color=(255,0,0), markerType=cv2.MARKER_TILTED_CROSS, thickness=2, markerSize=10)
                marked_mask = cv2.drawMarker(marked_mask, (x,y), color=(255,0,0), markerType=cv2.MARKER_TILTED_CROSS, thickness=2, markerSize=10)
            plt.figure(figsize=(14,8))
            plt.imshow(cv2.cvtColor(np.hstack([marked_rgb, marked_depth, marked_mask]), cv2.COLOR_BGR2RGB))
            plt.show()
                
        #remove xys out of bonds
        include_idxs = (xys[:,0]>=0) & (xys[:,0]<=width-1) & (xys[:,1]>=0) & (xys[:,1]<=height-1)
        reject_count += np.count_nonzero(~include_idxs)
        out_of_bound_reject_count += np.count_nonzero(~include_idxs)
        xys = xys[include_idxs]
        colmap_depths = colmap_depths[include_idxs]
        #remove idx out of mask
        mask = masks[idx]
        xys = np.rint(xys).astype(int)
        include_idxs = mask[xys[:,1],xys[:,0]] > 0
        reject_count += np.count_nonzero(~include_idxs)
        out_of_maks_reject_count += np.count_nonzero(~include_idxs)
        xys = xys[include_idxs]
        colmap_depths = colmap_depths[include_idxs]
        if True: #max strategy
            xys = np.rint(xys).astype(int)
            depths = ref_depth[xys[:,1],xys[:,0]]
            #avoid 0 divisions and don't use masked depth values
            include_idxs = (depths>0) & (colmap_depths>0)
            reject_count += np.count_nonzero(~include_idxs)
            scales.append(depths[include_idxs]/colmap_depths[include_idxs])
            point_depths.append(depths[include_idxs])
       
        else:  #weighted strategy
            #implement weighted values of depths...
            floor_xys = np.floor(xys).astype(int)
            ceil_xys = np.ceil(xys).astype(int)
            top_right_xys = np.hstack([ceil_xys[:,0],floor_xys[:,1]])
            bottom_left_xys = np.hstack([floor_xys[:,0],ceil_xys[:,1]])
            weights = np.hstack([
                1/np.sqrt(((xys-floor_xys)**2).sum(axis=1)),
                1/np.sqrt(((xys-top_right_xys)**2).sum(axis=1)),
                1/np.sqrt(((xys-bottom_left_xys)**2).sum(axis=1)),
                1/np.sqrt(((xys-ceil_xys)**2).sum(axis=1)),
            ])
            depths = np.sum(weights*np.hstack([
                ref_depth(floor_xys[:,1],floor_xys[:,0]),
                ref_depth(top_right_xys[:,1],top_right_xys[:,0]),
                ref_depth(bottom_left_xys[:,1],bottom_left_xys[:,0]),
                ref_depth(ceil_xys[:,1],ceil_xys[:,0]),
            ]))
            include_idxs = (ref_depth(floor_xys[:,1],floor_xys[:,0])>0) & (ref_depth(top_right_xys[:,1],top_right_xys[:,0])>0) & ref_(depth(bottom_left_xys[:,1],bottom_left_xys[:,0])>0) & (ref_depth(ceil_xys[:,1],ceil_xys[:,0])>0) & (colmap_depths>0)
            reject_count += np.count_nonzero(~include_idxs)
            scales.append(depths[include_idxs]/colmap_depths[include_idxs])
    
    scales = np.concatenate(scales)
    mean_scale = compute_kde(np.array(scales))
    if args.show_results:
        #scale correlation
        plt.scatter(np.concatenate(point_depths),scales)
        plt.show()
        plt.violinplot(scales)
        plt.show()
    elapsed_time = time.time() - start_time
    print(f"Scale! {mean_scale}, rejected {reject_count} (of which out of bound {out_of_bound_reject_count}, out of mask {out_of_maks_reject_count}), accepted {len(scales)}")
    print(f"Preprocessing of rgbd_images took {elapsed_time:.4f}")
    with open(args.log, 'a') as f:
        f.write(f"Found scale of {mean_scale} {'(overloadeded '+ str(overwrite_scale) +')' if overwrite_scale>0 else ''}. Rejected points {reject_count} (of which out of bound {out_of_bound_reject_count}, out of mask {out_of_maks_reject_count}), accepted {len(scales)}\n")
        f.write(f"Preprocessing of rgbd_images took {elapsed_time}\n")
    if overwrite_scale != -1 and overwrite_scale > 0:
        mean_scale = overwrite_scale
    return rgbd_images, mean_scale, elapsed_time



def import_real_params(camera_param_filepath):
    intrinsics, distortion_param =  extract_camera_info(camera_param_filepath)
    #print(f"Real params are {intrinsics}")
    return intrinsics



def align_pcds(rgbd_images, poses, intrinsic_param, scale=1, initial_pcd=[]):
    """DEPRECATED! THIS IS JUST A TEST!"""
    print("Projecting point clouds")
    #create pcds
    #rgbd_images = rgbd_images[:3] #EDIT
    output_voxel_size = 0.02 #EDIT 0.05
    coarse_distance = output_voxel_size*15
    fine_distance = output_voxel_size*1.5
    normal_kdtree_radius = output_voxel_size*2
    intrinsic = o3d.camera.PinholeCameraIntrinsic(o3d.camera.PinholeCameraIntrinsicParameters.PrimeSenseDefault)
    fx, fy, cx, cy, h, w = intrinsic_param
    intrinsic.set_intrinsics(w, h, fx, fy, cx, cy)
    pcds = []
    cameras_lineset = []
    pcd_combined = o3d.geometry.PointCloud()
    for idx in tqdm(range(len(rgbd_images))):
        rgbd_image = rgbd_images[idx]
        pose = poses[idx]
        scaled_pose = pose
        #scaled_pose[:3,3] = scaled_pose[:3,3]*scale
        inv_pose = np.linalg.inv(scaled_pose)
        pcd = o3d.geometry.PointCloud.create_from_rgbd_image(rgbd_image, intrinsic)
        down_pcd = pcd.voxel_down_sample(voxel_size=output_voxel_size)
        down_pcd.transform(inv_pose) 
        down_pcd.scale(1/scale, inv_pose[:3,3])
        down_pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=normal_kdtree_radius, max_nn=30))
        down_pcd.orient_normals_towards_camera_location(camera_location = inv_pose[:3,3])
        pcds.append(down_pcd)
        pcd_combined += down_pcd
        camera_line = o3d.geometry.LineSet.create_camera_visualization(intrinsic, np.eye(4,4), 0.15)
        camera_line.transform(inv_pose)
        camera_line.paint_uniform_color(np.array([1,0,0]))
        cameras_lineset.append(camera_line)
    down_pcds = pcds
    print("Aligning pcds for better estimation")
    def pairwise_registration(source, target, max_correspondence_distance_coarse, max_correspondence_distance_fine):
        #print("Appcd point-to-plane ICP")
        icp_coarse = o3d.pipelines.registration.registration_icp(
            source, target, max_correspondence_distance_coarse, np.identity(4),
            o3d.pipelines.registration.TransformationEstimationPointToPlane())
        icp_fine = o3d.pipelines.registration.registration_icp(
            source, target, max_correspondence_distance_fine,
            icp_coarse.transformation,
            o3d.pipelines.registration.TransformationEstimationPointToPlane())
        transformation_icp = icp_fine.transformation
        information_icp = o3d.pipelines.registration.get_information_matrix_from_point_clouds(
            source, target, max_correspondence_distance_fine,
            icp_fine.transformation)
        return transformation_icp, information_icp
    pose_graph = o3d.pipelines.registration.PoseGraph()
    odometry = np.identity(4)
    pose_graph.nodes.append(o3d.pipelines.registration.PoseGraphNode(odometry))
    n_pcds = len(down_pcds)
    print("Build o3d.pipelines.registration.PoseGraph")
    for source_id in tqdm(range(n_pcds)):
        for target_id in range(source_id + 1, n_pcds):
            transformation_icp, information_icp = pairwise_registration(
                down_pcds[source_id], down_pcds[target_id], coarse_distance, fine_distance)
            if target_id == source_id + 1:  # odometry case
                odometry = np.dot(transformation_icp, odometry)
                pose_graph.nodes.append(
                    o3d.pipelines.registration.PoseGraphNode(
                        np.linalg.inv(odometry)))
                pose_graph.edges.append(
                    o3d.pipelines.registration.PoseGraphEdge(source_id,
                                                             target_id,
                                                             transformation_icp,
                                                             information_icp,
                                                             uncertain=False))
            else:  # loop closure case
                pose_graph.edges.append(
                    o3d.pipelines.registration.PoseGraphEdge(source_id,
                                                             target_id,
                                                             transformation_icp,
                                                             information_icp,
                                                             uncertain=True))
    print("Optimizing posegraph")
    option = o3d.pipelines.registration.GlobalOptimizationOption(
            max_correspondence_distance=fine_distance,
            edge_prune_threshold=0.25,
            reference_node=0)
    with o3d.utility.VerbosityContextManager(o3d.utility.VerbosityLevel.Debug):
        o3d.pipelines.registration.global_optimization(
            pose_graph,
            o3d.pipelines.registration.GlobalOptimizationLevenbergMarquardt(),
            o3d.pipelines.registration.GlobalOptimizationConvergenceCriteria(),
            option)
    corrected_cameras_lineset = []
    corrected_poses = []
    corrected_pcd_combined = o3d.geometry.PointCloud()
    for point_id in range(len(down_pcds)):
        down_pcds[point_id].transform(pose_graph.nodes[point_id].pose)
        corrected_poses.append(np.linalg.inv(pose_graph.nodes[point_id].pose))
        # camera = o3d.geometry.LineSet.create_camera_visualization(intrinsic, np.eye(4,4), 0.1*long_dim_scale)
        # camera.transform(pose_graph.nodes[point_id].pose)
        # camera_line.paint_uniform_color(np.array([0,1,0]))
        # corrected_cameras_lineset.append(camera)
        corrected_pcd_combined+=down_pcds[point_id]
    if args.show_results:
        o3d.visualization.draw_geometries([initial_pcd]+cameras_lineset,
                                        zoom=0.5,
                                        front=[1, 0, 0],
                                        lookat=[0, 0, 0],
                                        up=[0, 0, 1],
                                        )
        initial_pcd.paint_uniform_color([1, 0.706, 0])
        o3d.visualization.draw_geometries(pcds+cameras_lineset+[initial_pcd],
                                        zoom=0.5,
                                        front=[1, 0, 0],
                                        lookat=[0, 0, 0],
                                        up=[0, 0, 1],)
        o3d.visualization.draw_geometries([corrected_pcd_combined]+cameras_lineset+corrected_cameras_lineset+[initial_pcd],
                                        zoom=0.5,
                                        front=[1, 0, 0],
                                        lookat=[0, 0, 0],
                                        up=[0, 0, 1],)
    breaker
    


def project_pointclouds(rgbd_images, poses, intrinsic_param, scale, initial_pcd=[]):
    print("Projecting point clouds")
    start_time = time.time()
    output_voxel_size = args.voxel_size #EDIT 0.05
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
    full_pcd = pcd_combined
    pcd_combined, removed_points = full_pcd.remove_statistical_outlier(10, 1)
    elapsed_time = time.time()-start_time
    removed_pcd = full_pcd.select_by_index(removed_points, invert=True)
    print(f"Projection time took {elapsed_time:.4f}")
    with open(args.log, 'a') as f:
        f.write(f"Projection time took {elapsed_time}\n")
    #down_pcds = [pcd.voxel_down_sample(voxel_size=output_voxel_size) for pcd in pcds]
    #pcd_combined = pcd_combined.voxel_down_sample(voxel_size=output_voxel_size)
    if args.show_results:
        o3d.visualization.draw_geometries([initial_pcd]+cameras_lineset,
                                        zoom=0.5,
                                        front=[1, 0, 0],
                                        lookat=[0, 0, 0],
                                        up=[0, 0, 1],
                                        )
        initial_pcd.paint_uniform_color([1, 0.706, 0])
        removed_pcd.paint_uniform_color([1,0,0])
        o3d.visualization.draw_geometries(pcds+cameras_lineset+[initial_pcd, removed_pcd],
                                        zoom=0.5,
                                        front=[1, 0, 0],
                                        lookat=[0, 0, 0],
                                        up=[0, 0, 1],)
        o3d.visualization.draw_geometries([pcd_combined]+cameras_lineset,
                                        zoom=0.5,
                                        front=[1, 0, 0],
                                        lookat=[0, 0, 0],
                                        up=[0, 0, 1],)
    #breaker
    return pcd_combined, elapsed_time

    
import shutil
def write_pcd_database(db_path, pcd, output_db_path):
    if os.path.isdir(output_db_path):
        print(f"Clearing output dir {output_db_path}")
        shutil.rmtree(output_db_path)
    print(f"Copying the database in {db_path} to {output_db_path}")
    shutil.copytree(db_path, output_db_path)
    print("Writing new pcd {output_db_path}")
    db = ColmapDatabase( output_db_path, points3D=ColmapDatabase.pcd2colmap(pcd) )
    db.write_points3D_binary()



def densify_sfm_pcd_pipeline(frames, depths, source_db_path, depth_npy_path, zed_camera_path, output_db_path, mask_foldername):
    """
    DEPRECATED: 
    """
    #do things like normal! copy the main
    start = time.time()
    args = parser.parse_args()
    filenames, poses, intrinsic_param, all_refs, initial_pcd = import_from_database(source_db_path)
    images_path = os.path.join(source_db_path, "input")
    #real_intrinsic_param = import_real_params(args.camera_param_path) #useless
    rgbd_images, scale = import_rgbd(filenames, images_path, depth_npy_path, all_refs, mask_foldername, already_depths=depths, already_frames=frames)
    #pcds, poses = align_pcds(rgbd_images, poses, intrinsic_param, scale, initial_pcd)
    pcd = project_pointclouds(rgbd_images, poses, intrinsic_param, scale, initial_pcd)
    if not args.skip_write_new_db:
        write_pcd_database(args.db_path, pcd, args.output_db_path)
    print(f"ELAPSED TIME FOR ALL COMPUTATIONS {time.time()-start}")
    with open(args.log, 'a') as f:
        f.write(f"Ended densify computations in {time.time()-start} seconds.\n")


if __name__ == "__main__":
    start = time.time()
    args = parser.parse_args()
    filenames, poses, intrinsic_param, all_refs, initial_pcd = import_from_database(args.db_path)
    images_path = os.path.join(args.db_path, "input")
    #real_intrinsic_param = import_real_params(args.camera_param_path) #useless
    rgbd_images, scale, preproc_eltime = import_rgbd(filenames, images_path, args.depth_npy_path, all_refs, args.masks_path, args.depth_trunc, args.overwrite_scale)
    #pcds, poses = align_pcds(rgbd_images, poses, intrinsic_param, scale, initial_pcd)
    pcd, proj_eltime = project_pointclouds(rgbd_images, poses, intrinsic_param, scale, initial_pcd)
    if not args.skip_write_new_db:
        write_pcd_database(args.db_path, pcd, args.output_db_path)
    print(f"ELAPSED TIME FOR ALL COMPUTATIONS {time.time()-start} (of which {preproc_eltime+proj_eltime} for actual method)")
    with open(args.log, 'a') as f:
        f.write(f"Ended densify computations in {time.time()-start} seconds (of which {preproc_eltime+proj_eltime} for actual method).\n")


#COLMAP COMMAND TO EXECUTE AFTER
#python3 video_to_masked_colmap.py zed_capture/ images ../SuGaR/gaussian_splatting/data/test_pipeline -w
#python3 densify_sfm_pcd.py ../SuGaR/gaussian_splatting/data/test_pipeline depths zed_capture/camera_data.dp ../SuGaR/gaussian_splatting/data/test_pipeline_densified --masks_path masks
#path='test_pipeline'
#python ../SuGaR/gaussian_splatting/train.py -s ../SuGaR/gaussian_splatting/data/$path --iterations 30000 -m ../SuGaR/gaussian_splatting/output/$path --save_iterations 100 300 500 1000 3000 7000 12000 30000 --test_iterations 100 300 500 1000 3000 7000 12000 30000 -w

#2dgs
#python ../2DSplat/train.py -s ../SuGaR/gaussian_splatting/data/test_pipeline_densified --test_iterations 100 500 3000 7000 12000 --save_iterations 100 500 3000 7000 12000 --iterations 12000 --white
#python ../2DSplat/render.py -m output/test_pipeline/ -s ../SuGaR/gaussian_splatting/data/test_pipeline --iteration 7000 --skip_train --skip_test