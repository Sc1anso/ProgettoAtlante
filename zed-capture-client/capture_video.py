import pyzed.sl as sl
import sys
import enum
import cv2
import struct
from matplotlib import pyplot as plt
import numpy as np

def get_camera_parameters(zed):
    calibration_params = zed.get_camera_information().camera_configuration.calibration_parameters
    fx = calibration_params.left_cam.fx
    fy = calibration_params.left_cam.fy
    k1 = calibration_params.left_cam.disto[0]
    k2 = calibration_params.left_cam.disto[1]
    p1 = calibration_params.left_cam.disto[2]
    p2 = calibration_params.left_cam.disto[3]
    k3 = calibration_params.left_cam.disto[4]
    # Horizontal field of view of the left eye in degrees
    h_fov = calibration_params.left_cam.h_fov
    v_fov = calibration_params.left_cam.v_fov
    image_size = zed.get_camera_information().camera_configuration.resolution
    w = image_size.width
    h = image_size.height
    cx = w//2 - 1
    cy = h//2 -1
    return (fx, fy, cx, cy, h, w), (k1, k2, p1, p2, k3)

zed = sl.Camera() 

init_params = sl.InitParameters()
init_params.camera_resolution = sl.RESOLUTION.HD2K
init_params.depth_mode = sl.DEPTH_MODE.NEURAL
init_params.coordinate_units = sl.UNIT.MILLIMETER
init_params.depth_stabilization = 0
init_params.depth_maximum_distance = 4000
init_params.depth_minimum_distance = 50

err = zed.open(init_params)
if err != sl.ERROR_CODE.SUCCESS:
    sys.stdout.write(repr(err))
    zed.close()
    exit()

    
zed.set_camera_settings(sl.VIDEO_SETTINGS.EXPOSURE, 10)
zed.set_camera_settings(sl.VIDEO_SETTINGS.GAIN, 50)
zed.set_camera_settings(sl.VIDEO_SETTINGS.SHARPNESS, 5)
zed.set_camera_settings(sl.VIDEO_SETTINGS.BRIGHTNESS, 5)
zed.set_camera_settings(sl.VIDEO_SETTINGS.CONTRAST, 5)



# record_params = sl.RecordingParameters("myVideoFile.svo")
# record_params.compression_mode = sl.SVO_COMPRESSION_MODE.H264
# init_params.svo_real_time_mode = False
# err = zed.enable_recording(record_params)
# if (err != sl.ERROR_CODE.SUCCESS):
#     print(repr(err))
#     exit(-1)

intrinsics_param, dist_param = get_camera_parameters(zed)
_,_,_,_,height,width = intrinsics_param
width_sbs = width * 2

left_image = sl.Mat()
right_image = sl.Mat()
depth_image = sl.Mat()

left_video_writer = cv2.VideoWriter("recording.mp4",
                                cv2.VideoWriter_fourcc(*'mp4v'),
                                max(zed.get_camera_information().camera_configuration.fps, 15),
                                (width, height))
if not left_video_writer.isOpened():
    sys.stdout.write("OpenCV video writer cannot be opened. Please check the .avi file path and write "
                        "permissions.\n")
    zed.close()
    exit()
#depth video file
depth_f = open("depth_data.dp", "wb")
video_info = struct.pack('i', width) + struct.pack('i', height) + struct.pack('f', max(zed.get_camera_information().camera_configuration.fps, 15)) #3 numbers at the beginning
depth_f.write(video_info)
#video of 8bit file
depth_video_writer = cv2.VideoWriter("8bit_depth_recording.mp4",
                                cv2.VideoWriter_fourcc(*'mp4v'),
                                max(zed.get_camera_information().camera_configuration.fps, 15),
                                (width, height), isColor=0)
if not depth_video_writer.isOpened():
    sys.stdout.write("OpenCV video writer cannot be opened. Please check the .avi file path and write "
                        "permissions.\n")
    depth_f.close()
    zed.close()
    exit()
#camera parameters
camera_param_f = open("camera_data.dp", "wb")
np.array(intrinsics_param).astype(int).tofile(camera_param_f) #size 6
np.array(dist_param).astype(np.float32).tofile(camera_param_f) #size 5
camera_param_f.close()

rt_param = sl.RuntimeParameters()
rt_param.enable_fill_mode = True
cv2.namedWindow("Capturing", cv2.WINDOW_KEEPRATIO)

print("All set!! Start recording?")
input()
print("Starting recording")
t = 0
try:
    while True:
        if zed.grab(rt_param) == sl.ERROR_CODE.SUCCESS:
            zed.retrieve_image(left_image, sl.VIEW.LEFT)
            zed.retrieve_measure(depth_image, sl.MEASURE.DEPTH)

            left_rgb_image = cv2.cvtColor(left_image.get_data(), cv2.COLOR_RGBA2RGB)
            left_video_writer.write(left_rgb_image)
            np_depth = depth_image.get_data() #only lasts for 1 dimensions
            #filtering depth values
            np_depth[np.isnan(np_depth)] = 0
            np_depth[np.isinf(np_depth)] = init_params.depth_maximum_distance
            np_depth.tofile(depth_f)
            min_d, max_d = np_depth.min(), np_depth.max()
            uint_depth = ((np_depth-min_d)/(max_d-min_d)*255).astype(np.uint8)
            depth_video_writer.write(uint_depth)
            uint_depth_3ch = cv2.cvtColor(uint_depth, cv2.COLOR_GRAY2BGR)
            #display_image = cv2.resize(np.hstack((left_rgb_image, uint_depth_3ch)), (left_rgb_image.shape[0]//2, left_rgb_image.shape[1]))
            display_image = np.hstack((left_rgb_image, uint_depth_3ch))
            cv2.imshow("Capturing", display_image)
            key = cv2.waitKey(5)
            
            #print(f"frames with shape: left_rgb_image {left_rgb_image.shape} max {left_rgb_image.max()}, np_dept {np_depth.shape} max {np_depth.max()} type {np_depth.dtype}, ")
            t+=1
            if False:
                print(np_depth)
                plt.imshow(np_depth, cmap="gray")
                plt.show()
                left_video_writer.release()
                depth_video_writer.release()
                depth_f.close()
                zed.close()
                breaker


except KeyboardInterrupt:
    cv2.destroyAllWindows()
    print("Ending recording.")
    left_video_writer.release()
    depth_video_writer.release()
    depth_f.close()
    print("Saving video")
    zed.close()

