import subprocess
import sys
from video_frame_extraction import extract_frames
import argparse
import os
import shutil
import cv2
import time
from tqdm import tqdm
import numpy as np
from datetime import datetime

parser = argparse.ArgumentParser(description='Extract frames from video with depth, run colmap and mask images')

parser.add_argument('source_path', type=str,
                    help='path of the source folder where capture is contained. Video file should be called "recording.mp4" and depth data "depth_data.dp" if present')
parser.add_argument('images_path', type=str,
                    help='path of the extracted frames to be saved')
parser.add_argument('--n_frames', type=int, default=100,
                    help="Number of frames to be extracted from the video")
parser.add_argument('db_path', type=str,
                    help='path of the desired database path')
parser.add_argument('-w','--white', action='store_true',
                    help='if object have to be masked with white or black')
parser.add_argument('--masks_foldername', type=str, default="masks",
                    help='name of the folder to use for store masks')
parser.add_argument('--avoid_colmap_masks', '-acm', action='store_true',
                    help='Avoid colmap to use masks if it can t reconstruct the scene')
parser.add_argument('--unmasked','-u', action='store_true',
                    help='To execute standard pipeline without masking')
parser.add_argument('--mode','-m', type=str, default='zed',
                    help='Type of data to execute the pipeline from. [zed|smartphone|smartphone_monodepth|blender]')
parser.add_argument('--rotation','-r', type=int, default=0,
                    help='Rotation in signed degrees to rotate the image by [only 90 degrees steps are possibles]')
parser.add_argument('--fix_colmap_only','-fix', action='store_true',
                    help='Execute only the fixing of colmap found')
parser.add_argument('--log', type = str, default='./log_file.txt',
                    help='Path of the logger file')
parser.add_argument('--densify_after', action='store_true',
                    help='Start directly the denisfy pipeline to save some time with import and export')


args = parser.parse_args()
with open(args.log, 'a') as f:
    today = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    f.write(today+"\n")
    f.write(f"Extracting frames and creating colmap for {args.source_path}\n")



def extract_frames_from_zed_camera(zed_capture_path, images_path, n_frames, rotation):
    #standard path. video: "zed_capture/recording.mp4", camera info "zed_capture/camera_data.dp", depth point "zed_capture/depth_data.dp"
    video_path = os.path.join(zed_capture_path, "recording.mp4")
    depth_path = os.path.join(zed_capture_path, "depth_data.dp")
    depth_npy_path = os.path.join(images_path, "../depths")
    depth_images_path = os.path.join(images_path, "../depth_images")
    frames, depths = extract_frames(video_path, depth_path, images_path, depth_npy_path, depth_images_path, n_frames, rotation)
    with open(args.log, 'a') as f:
        n = len(frames)
        size = frames[0].shape
        f.write(f"Extracted {n} frames and depths of size {size} with 'zed' mode.\n")
    return frames, depths


def extract_frames_from_video(source_path, images_path, n_frames, rotation, has_depth = False):
    video_filepath = os.path.join(source_path, "recording.mp4")
    if not os.path.isdir(images_path):
        print("Creating images folder")
        os.makedirs(images_path)
    else:
        print("Clearing images folder")
        shutil.rmtree(images_path)
        os.makedirs(images_path)
    frames = []
    depths = [] #used only if depths
    cap = cv2.VideoCapture(video_filepath)
    tot_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    sample_every = int(tot_frames//n_frames)
    print(f"Found video with {tot_frames}. Sampling every {sample_every}")
    for t in tqdm(range(n_frames)):
        frame_idx = t*sample_every + int(sample_every//2)
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret,frame = cap.read()
        if not ret:
            print(f"Error in reading the frame {frame_idx}")
        else:
            if rotation == -90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
            elif rotation == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
            elif rotation == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
            
            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            cv2.imwrite(os.path.join(images_path, f"{t:04d}.png"), frame)
    cap.release()
    print(f"Extracted {len(frames)} frames")
    #EXTRACTING DEPTH FROM VIDEO-DEPTH
    if has_depth:
        print("Extracting monocular consistent video depth")
        MAX_DEPTH = 4000
        MIN_DEPTH = 20
        depth_npy_path = os.path.join(images_path, "../depths")
        depth_filepath = os.path.join(source_path, "depth_video.mp4")
        print("Clearing npy_depth folder")
        shutil.rmtree(depth_npy_path)
        os.makedirs(depth_npy_path)
        depths = []
        cap = cv2.VideoCapture(depth_filepath)
        assert tot_frames == int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), f"ERROR! depth video and original one have different number of frames! {tot_frames} vs {int(cap.get(cv2.CAP_PROP_FRAME_COUNT))}"
        for t in tqdm(range(n_frames)):
            frame_idx = t*sample_every + int(sample_every//2)
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret,frame = cap.read()
            if not ret:
                print(f"Error in reading the frame {frame_idx}")
            else:
                if rotation == -90:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                elif rotation == 90:
                    frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                elif rotation == 180:
                    frame = cv2.rotate(frame, cv2.ROTATE_180)
                depths.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        np_depths = np.array(depths)
        max_depth, min_depth = np_depths.max(), np_depths.min()
        np_depths = ((np_depths-min_depth)/(max_depth-min_depth)*-1 +1)*(MAX_DEPTH-MIN_DEPTH)+MIN_DEPTH
        for t in range(np_depths.shape[0]):
            np.save(os.path.join(depth_npy_path, f"{t:04d}.npy"), np_depths[t])
    with open(args.log, 'a') as f:
        n = len(frames)
        size = frames[0].shape
        f.write(f"Extracted {n} frames {'with depths' if has_depth else 'without depths'} of size {size} with {'smartphone_monodepth' if has_depth else 'smartphone'} mode.\n")
    return frames, depths



def copy_after_blender_preprocessing(source_path, images_path, has_depth = True):
    input_renders_path = os.path.join(source_path, "renders")
    input_depth_npy_path = os.path.join(source_path, "depths")
    depth_npy_path = os.path.join(images_path, "../depths")
    depth_images_path = os.path.join(images_path, "../depth_images")
    print("Clearing images folder")
    shutil.rmtree(images_path, ignore_errors=True)
    os.makedirs(images_path, exist_ok=True)
    print("Clearing npy_depth folder")
    shutil.rmtree(depth_npy_path, ignore_errors=True)
    os.makedirs(depth_npy_path, exist_ok=True)
    print("Clearing depth_images folder")
    shutil.rmtree(depth_images_path, ignore_errors=True)
    os.makedirs(depth_images_path, exist_ok=True)
    frames = []
    depths = []
    for filename in os.listdir(input_renders_path):
        image_filepath = os.path.join(input_renders_path, filename)
        depth_npy_filepath = os.path.join(input_depth_npy_path, filename[:-4]+".npy")
        output_image_filepath = os.path.join(images_path, filename)
        output_depth_npy_filepath = os.path.join(depth_npy_path, filename[:-4]+".npy")
        output_depth_image_filepath = os.path.join(depth_images_path, filename)

        shutil.copy2(image_filepath, output_image_filepath)
        shutil.copy2(depth_npy_filepath, output_depth_npy_filepath)

        frame = cv2.imread(image_filepath, cv2.IMREAD_COLOR)
        frames.append(frame)
        depth = np.load(depth_npy_filepath).astype(np.float32)
        depths.append(depth)
        norm_depth = ((depth-0)/(4000 - 0)*255).astype(np.uint8)
        color_map = cv2.applyColorMap(norm_depth, cv2.COLORMAP_JET)
        cv2.imwrite(output_depth_image_filepath,  color_map)
    with open(args.log, 'a') as f:
        n = len(list(os.listdir(input_renders_path)))
        size = depth.shape
        f.write(f"Copied {n} frames and depths of size {size} with 'blender' mode.\n")
    return frames, depths



def start_colmap_database(db_path, images_path):
    if not os.path.isdir(db_path):
        print("Creating colmap database folder")
        os.makedirs(db_path)
    else:
        print("Clearing colmap database folder")
        shutil.rmtree(db_path)
        os.makedirs(db_path)
    input_path = os.path.join(db_path, "input")
    if os.path.isdir(input_path):
        print("removing older input folder")
        shutil.rmtree(input_path)
    shutil.copytree(images_path, input_path)

def run_colmap(db_path, masks_foldername, avoid_colmap_masks):
    masks_foldername = "input_"+masks_foldername
    premask_path = os.path.join(db_path, masks_foldername)

    print(f"Starting Sfm in {db_path}...")
    if avoid_colmap_masks:
        print("Using  non-masked images in feature extractions")
        subprocess.run([sys.executable, "../SuGaR/gaussian_splatting/convert.py", "-s", f"{db_path}"], check=True)
    else:
        subprocess.run([sys.executable, "../SuGaR/gaussian_splatting/convert.py", "-s", f"{db_path}", "--mask_path", f"{premask_path}"], check=True)

    fix_colmap_models(db_path)

def fix_colmap_models(db_path):
    #Check multiple sparse...
    sparse_path = os.path.join(db_path,"distorted/sparse/1")
    colmap_images_path = os.path.join(db_path,"images")
    colmap_input_path = os.path.join(db_path,"input")
    if os.path.isdir(sparse_path):
        print("WARNING! Found multiple reconstruction models with colmap")
        if len(os.listdir(colmap_images_path)) < len(os.listdir(colmap_input_path))/2:
            print(f"WARNING! Collected wrong model. Found {len(os.listdir(colmap_images_path))} iamges instead of {len(os.listdir(colmap_input_path))}. Changing model and rerunning undistortion")
            zero_sparse_path = os.path.join(db_path,"distorted/sparse/0")
            shutil.rmtree(zero_sparse_path)
            shutil.rmtree(os.path.join(db_path, 'sparse'))
            shutil.move(sparse_path, zero_sparse_path)
            #re-do image undistortion
            img_undist_cmd = ("colmap" + " image_undistorter \
                --image_path " + db_path + "/input \
                --input_path " + db_path + "/distorted/sparse/0 \
                --output_path " + db_path + "\
                --output_type COLMAP")
            exit_code = os.system(img_undist_cmd)
            files = os.listdir(db_path + "/sparse")
            os.makedirs(db_path + "/sparse/0", exist_ok=True)
            # Copy each file from the source directory to the destination directory
            for file in files:
                if file == '0':
                    continue
                source_file = os.path.join(db_path, "sparse", file)
                destination_file = os.path.join(db_path, "sparse", "0", file)
                shutil.move(source_file, destination_file)



def extract_before_colmap_masks(images_path, db_path, masks_foldername, avoid_colmap_masks):
    base_path = os.path.join(images_path, "..")
    masks_path = os.path.join(base_path, masks_foldername)
    if os.path.isdir(masks_path):
        print("removing previous masks")
        shutil.rmtree(masks_path)
    print("Extracting masks for extracted frames")
    subprocess.run(["rembg", "p", "-om", images_path, masks_path, "-m", "isnet-general-use"], check=True) # model isnet-general-use

    if not avoid_colmap_masks:
        input_masks_foldername = "input_"+masks_foldername
        input_masks_path = os.path.join(db_path, input_masks_foldername)
        #remove previous
        if os.path.isdir(input_masks_path):
            print("Clearing previous input masks")
            shutil.rmtree(input_masks_path)

        print("Copying masks to input masks colmap folder")
        shutil.copytree(masks_path, input_masks_path)
        for filename in os.listdir(input_masks_path):
            filepath = os.path.join(input_masks_path, filename)
            img = cv2.imread(filepath, cv2.IMREAD_GRAYSCALE)
            UINT_MASK_THR = 20
            img[img<UINT_MASK_THR] = 0
            cv2.imwrite(filepath, img)
    


def extract_colmap_masks(db_path, masks_foldername, w_option):
    input_path = os.path.join(db_path, "images")
    masks_path = os.path.join(db_path, masks_foldername)
    copy_images_path = os.path.join(db_path, "copy_images")
    #remove all
    if os.path.isdir(masks_path):
        print("Clearing previous masks")
        shutil.rmtree(masks_path)
    if os.path.isdir(copy_images_path):
        print("Clearing previous copy_images")
        shutil.rmtree(copy_images_path)
    shutil.copytree(input_path, copy_images_path)

    print("Applying masks to undistorted images")
    if w_option:
        subprocess.run(["rembg", "p", "-om", input_path, masks_path, "-m", "isnet-general-use"], check=True)
        #compute them with white background
        print("Applying white masking")
        for filename in os.listdir(input_path):
            filepath = os.path.join(input_path, filename)
            mask_filepath = os.path.join(masks_path, filename)
            img = cv2.imread(filepath)
            mask = cv2.imread(mask_filepath, cv2.IMREAD_GRAYSCALE)
            UINT_MASK_THR = 20
            img[mask<UINT_MASK_THR,:] = 255
            cv2.imwrite(filepath, img)
    else:
        shutil.rmtree(input_path)
        subprocess.run(["rembg", "p", copy_images_path, input_path, "-m", "isnet-general-use"], check=True)



def extract_zed_masks(images_path, masks_foldername):
    base_path = os.path.join(images_path, "..")
    masks_path = os.path.join(base_path, masks_foldername)
    if os.path.isdir(masks_path):
        print("removing previous masks")
        shutil.rmtree(masks_path)
    print("Extracting masks for extracted frames")
    subprocess.run(["rembg", "p", "-om", images_path, masks_path, "-m", "isnet-general-use"], check=True)



start = time.time()
args = parser.parse_args()
assert args.rotation in [0, -90, 90, 180], "Error! requested angles are not possible! Only [-90, 0, 90, 180] angles are allowed!"
assert args.mode in ["zed", "smartphone", "smartphone_monodepth", "blender"], f"Error! {args.mode} is not a mode! Select one of the following [zed|smartphone|smartphone_monodepth|blender]"

if args.fix_colmap_only:
    fix_colmap_models(args.db_path)
    breaker

if args.mode == "smartphone":
    frames, _ = extract_frames_from_video(args.source_path, args.images_path, args.n_frames, args.rotation)
elif args.mode == "smartphone_monodepth":
    frames, depths = extract_frames_from_video(args.source_path, args.images_path, args.n_frames, args.rotation, has_depth=True)
elif args.mode == "blender":
    frames, depths = copy_after_blender_preprocessing(args.source_path, args.images_path)
elif args.mode == "zed":
    frames, depths = extract_frames_from_zed_camera(args.source_path, args.images_path, args.n_frames, args.rotation)

extract_before_colmap_masks(args.images_path, args.db_path, args.masks_foldername, args.avoid_colmap_masks)
start_colmap_database(args.db_path, args.images_path)
if args.unmasked:
    args.avoid_colmap_masks = True
    star_colmap = time.time()
    run_colmap(args.db_path, args.masks_foldername, args.avoid_colmap_masks)
    print(f"COLMAP ELAPSED TIME {time.time()-star_colmap}")
    with open(args.log, 'a') as f:
        f.write(f"Computed COLMAP Sfm (without masking) in {time.time()-star_colmap} seconds.\n")
else:
    star_colmap = time.time()
    run_colmap(args.db_path, args.masks_foldername, args.avoid_colmap_masks)
    print(f"COLMAP ELAPSED TIME {time.time()-star_colmap}")
    with open(args.log, 'a') as f:
        f.write(f"Computed COLMAP Sfm (without masking) in {time.time()-star_colmap} seconds.\n")
    extract_colmap_masks(args.db_path, args.masks_foldername, args.white)
#extract_zed_masks(args.images_path, args.masks_foldername)
print(f"ELAPSED TIME FOR ALL COMPUTATIONS {time.time()-start}")
with open(args.log, 'a') as f:
    f.write(f"Ended all computation in {time.time()-start} seconds.\n")

#CALL DENSIFY IF NEEDED!
# if args.densify_after:
#     densify_sfm_pcd_pipeline(frames, depths, args.db_path, "depths", os.path.join(args.source_path, "camera_data.dp"), args.db_path+"_densified", args.masks_foldername)


#python3 video_to_masked_colmap.py zed_capture/ images ../SuGaR/gaussian_splatting/data/test_pipeline -w
