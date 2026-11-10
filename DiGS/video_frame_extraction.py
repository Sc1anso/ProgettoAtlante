import numpy as np
import struct
import cv2
import os
from tqdm import tqdm
from matplotlib import pyplot as plt
import shutil


def extract_camera_info(path):
    #data in the format of (fx, fy, cx, cy, h, w), (k1, k2, p1, p2, k3)
    f = open(path, "rb")
    intrinsics = np.fromfile(f, dtype=np.int32, count=6)
    print(f"intrinsics!! {intrinsics}")
    distortion_param = np.fromfile(f, dtype=np.float32, count=5)
    f.close()
    return intrinsics, distortion_param

def extract_depths(path):
    print("Reading depth data ...")
    f = open(path, "rb")
    w = struct.unpack("i", f.read(4))[0]
    h = struct.unpack("i", f.read(4))[0]
    fps = struct.unpack("f", f.read(4))[0]
    frames = []
    i = 0
    while True:
        frame = np.fromfile(f, dtype=np.float32, count=h*w)
        if (frame.size == 0):
            print(f"End of file with {i} frames")
            break
        elif (frame.size<h*w):
            print(f"End of file with {i} frames, but remaining bytes!")
            break
        else:
            frame = frame.reshape((h,w))
            frames.append(frame)
        i += 1
    f.close()
    depths = np.stack(frames)
    print(f"Read binary video {h}x{w}, fps {fps}, and shape {depths.shape}. Max {depths.max()} min {depths.min()}")
    return depths

def extract_frames(video_filepath, depth_filepath, output_path, depths_path = "./depths", depth_image_path = "./depth_images", n_frames = 10, rotation = 0):
    if not os.path.isdir(output_path):
        print("Creating images folder")
        os.makedirs(output_path)
    else:
        print("Clearing images folder")
        shutil.rmtree(output_path)
        os.makedirs(output_path)
    if not os.path.isdir(depth_image_path):
        print("Creating depth folder")
        os.makedirs(depth_image_path)
    else:
        print("Clearing depth folder")
        shutil.rmtree(depth_image_path)
        os.makedirs(depth_image_path)
    if not os.path.isdir(depths_path):
        print("Creating depth npy folder")
        os.makedirs(depths_path)
    else:
        print("Clearing depth npy folder")
        shutil.rmtree(depths_path)
        os.makedirs(depths_path)
    video_depth = extract_depths(depth_filepath)
    frames = []
    depths = []
    d_min, d_max = video_depth.min(), video_depth.max()
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
            depth = video_depth[frame_idx]
            #Rotation
            if rotation == -90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
                depth = cv2.rotate(depth, cv2.ROTATE_90_COUNTERCLOCKWISE)
            elif rotation == 90:
                frame = cv2.rotate(frame, cv2.ROTATE_90_CLOCKWISE)
                depth = cv2.rotate(depth, cv2.ROTATE_90_CLOCKWISE)
            elif rotation == 180:
                frame = cv2.rotate(frame, cv2.ROTATE_180)
                depth = cv2.rotate(depth, cv2.ROTATE_180)
            
            norm_depth = ((depth-d_min)/(d_max - d_min)*255).astype(np.uint8)
            color_map = cv2.applyColorMap(norm_depth, cv2.COLORMAP_JET)
            cv2.imwrite(os.path.join(depth_image_path, f"{t:04d}.png"),  color_map)
            # remove_depth = depth[frame_idx] > 2500
            # depth[frame_idx][remove_depth] = 0
            depths.append(depth)
            np.save(os.path.join(depths_path, f"{t:04d}.npy"), depth)

            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            cv2.imwrite(os.path.join(output_path, f"{t:04d}.png"), frame)
    cap.release()
        
    print(f"Extracted {len(frames)} frames")
    return frames, depths

def extract_monocular_depths(path):
    print("Reading monocular depth data ...")
    frames = []
    for filename in os.listdir(path):
        frame = np.load(os.path.join(path, filename))
        frames.append(frame)
    depths = np.stack(frames)
    n_frames, h, w = depths.shape
    print(f"Read {n_frames} monocular depths {h}x{w}, shape {depths.shape}. Max {depths.max()} min {depths.min()}")
    #inverting depth values
    depths = (depths * -1) + depths.max()
    return depths

def extract_monocular_frames(video_path, depth_path, output_path, n_frames):
    if not os.path.isdir(output_path):
        print("Creating folder")
        os.makedirs(output_path)
    if not os.path.isdir("./depth_images"):
        print("Creating depth folder")
        os.makedirs("./depth_images")
    print("Clearing output path")
    for filename in os.listdir(output_path):
        os.remove(os.path.join(output_path, filename))
    for filename in os.listdir("./depth_images"):
        os.remove(os.path.join("./depth_images", filename))
    depths_stack = extract_monocular_depths(depth_path)
    depths = []
    frames = []
    d_min, d_max = depths_stack.min(), depths_stack.max()
    cap = cv2.VideoCapture(video_path)
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
            norm_depth = ((depths_stack[t]-d_min)/(d_max - d_min)*255).astype(np.uint8)
            color_map = cv2.applyColorMap(norm_depth, cv2.COLORMAP_JET)
            cv2.imwrite(os.path.join("./depth_images", f"{t:04d}.png"),  color_map)

            frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            cv2.imwrite(os.path.join(output_path, f"{t:04d}.png"), frame)
            depths.append(depths_stack[t])
    cap.release()
    print(f"Extracted {len(frames)} frames. Depths with {len(depths)} of dim {depths[0].shape}")
    return frames, depths

def apply_maks(frames, depths, mask_path):
    n = len(frames)
    flag = False #EDIT
    for i in range(n):
        mask = cv2.imread(os.path.join(mask_path, f"{i:04d}.png"), cv2.IMREAD_GRAYSCALE)
        #print("MASK!", mask.shape, mask.max(), mask.min(), mask)
        frame = frames[i]
        depth = depths[i]
        # print("FRAME!", frame.shape, frame.max(), frame.min(), frame)
        # print("DEPTH!", depth.shape, depth.max(), depth.min(), depth)
        res_frame = cv2.bitwise_and(frame,frame,mask=mask)
        # print("RES FRAME!", res_frame.shape, res_frame.max(), res_frame.min(), res_frame)
        res_depth = cv2.bitwise_and(depth,depth,mask=mask)
        # print("RES DEPTH!", res_depth.shape, res_depth.max(), res_depth.min(), res_depth)
        # print(f"Shapes! res frame {res_frame.shape}, res depth {res_depth.shape}")
        frames[i] = res_frame
        depths[i] = res_depth
        if flag:
            plt.imshow(res_frame)
            plt.show()
            plt.imshow(res_depth/res_depth.max())
            plt.show()
            flag = False

    return frames, depths
