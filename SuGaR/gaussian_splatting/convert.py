#
# Copyright (C) 2023, Inria
# GRAPHDECO research group, https://team.inria.fr/graphdeco
# All rights reserved.
#
# This software is free for non-commercial, research and evaluation use
# under the terms of the LICENSE.md file.
#
# For inquiries contact  george.drettakis@inria.fr
#

import os
import logging
import struct
from argparse import ArgumentParser
import shutil

# This Python script is based on the shell converter script provided in the MipNerF 360 repository.
parser = ArgumentParser("Colmap converter")
parser.add_argument("--no_gpu", action='store_true')
parser.add_argument("--skip_matching", action='store_true')
parser.add_argument("--source_path", "-s", required=True, type=str)
parser.add_argument("--camera", default="OPENCV", type=str)
parser.add_argument("--colmap_executable", default="", type=str)
parser.add_argument("--resize", action="store_true")
parser.add_argument("--magick_executable", default="", type=str)
parser.add_argument("--mask_path", default="", type=str) #EDIT
parser.add_argument("--matching_method", choices=("exhaustive", "sequential"), default="sequential")
parser.add_argument("--sequential_overlap", default=15, type=int)
args = parser.parse_args()
colmap_command = '"{}"'.format(args.colmap_executable) if len(args.colmap_executable) > 0 else "colmap"
magick_command = '"{}"'.format(args.magick_executable) if len(args.magick_executable) > 0 else "magick"
use_gpu = 1 if not args.no_gpu else 0


def registered_images(model_path):
    """Return the number of registered images recorded in COLMAP images.bin."""
    images_bin = os.path.join(model_path, "images.bin")
    try:
        with open(images_bin, "rb") as handle:
            return struct.unpack("<Q", handle.read(8))[0]
    except (OSError, struct.error):
        return -1

if not args.skip_matching:
    os.makedirs(args.source_path + "/distorted/sparse", exist_ok=True)

    ## Feature extraction
    print(f"USING MASK PATH {args.mask_path}!") #EDIT
    mask_path_arg = " --ImageReader.mask_path " + args.mask_path if args.mask_path else ""
    print("COLMAP_STAGE: estrazione feature GPU", flush=True)
    feat_extracton_cmd = colmap_command + " feature_extractor "\
        "--database_path " + args.source_path + "/distorted/database.db \
        --image_path " + args.source_path + "/input \
        --ImageReader.single_camera 1 \
        --ImageReader.camera_model " + args.camera + " \
        " + mask_path_arg + " \
        --SiftExtraction.use_gpu " + str(use_gpu)
    exit_code = os.system(feat_extracton_cmd)
    if exit_code != 0:
        logging.error(f"Feature extraction failed with code {exit_code}. Exiting.")
        exit(exit_code)

    ## Feature matching
    if args.matching_method == "sequential":
        print("COLMAP_STAGE: matching sequenziale GPU", flush=True)
        feat_matching_cmd = colmap_command + " sequential_matcher \
            --database_path " + args.source_path + "/distorted/database.db \
            --SequentialMatching.overlap " + str(args.sequential_overlap) + " \
            --SiftMatching.use_gpu " + str(use_gpu)
    else:
        print("COLMAP_STAGE: matching esaustivo GPU", flush=True)
        feat_matching_cmd = colmap_command + " exhaustive_matcher \
            --database_path " + args.source_path + "/distorted/database.db \
            --SiftMatching.use_gpu " + str(use_gpu)
    exit_code = os.system(feat_matching_cmd)
    if exit_code != 0:
        logging.error(f"Feature matching failed with code {exit_code}. Exiting.")
        exit(exit_code)

    ### Bundle adjustment
    # The default Mapper tolerance is unnecessarily large,
    # decreasing it speeds up bundle adjustment steps.
    print("COLMAP_STAGE: stima pose e sparse model", flush=True)
    mapper_cmd = (colmap_command + " mapper \
        --database_path " + args.source_path + "/distorted/database.db \
        --image_path "  + args.source_path + "/input \
        --output_path "  + args.source_path + "/distorted/sparse \
        --Mapper.ba_global_function_tolerance=0.000001")
    exit_code = os.system(mapper_cmd)
    if exit_code != 0:
        logging.error(f"Mapper failed with code {exit_code}. Exiting.")
        exit(exit_code)

    model_root = args.source_path + "/distorted/sparse"
    candidates = [
        os.path.join(model_root, name)
        for name in os.listdir(model_root)
        if os.path.isdir(os.path.join(model_root, name))
    ]
    selected_model = max(candidates, key=registered_images, default="")
    selected_count = registered_images(selected_model) if selected_model else -1
    if selected_count < 1:
        logging.error("COLMAP did not create a readable sparse model. Exiting.")
        exit(1)
    print(f"COLMAP_STAGE: modello sparse selezionato ({os.path.basename(selected_model)}, {selected_count} immagini)", flush=True)

### Image undistortion
## We need to undistort our images into ideal pinhole intrinsics.
print("COLMAP_STAGE: undistortion immagini", flush=True)
img_undist_cmd = (colmap_command + " image_undistorter \
    --image_path " + args.source_path + "/input \
    --input_path " + (selected_model if not args.skip_matching else args.source_path + "/distorted/sparse/0") + " \
    --output_path " + args.source_path + "\
    --output_type COLMAP")
exit_code = os.system(img_undist_cmd)
if exit_code != 0:
    logging.error(f"Mapper failed with code {exit_code}. Exiting.")
    exit(exit_code)

files = os.listdir(args.source_path + "/sparse")
os.makedirs(args.source_path + "/sparse/0", exist_ok=True)
# Copy each file from the source directory to the destination directory
for file in files:
    if file == '0':
        continue
    source_file = os.path.join(args.source_path, "sparse", file)
    destination_file = os.path.join(args.source_path, "sparse", "0", file)
    shutil.move(source_file, destination_file)

if(args.resize):
    print("Copying and resizing...")

    # Resize images.
    os.makedirs(args.source_path + "/images_2", exist_ok=True)
    os.makedirs(args.source_path + "/images_4", exist_ok=True)
    os.makedirs(args.source_path + "/images_8", exist_ok=True)
    # Get the list of files in the source directory
    files = os.listdir(args.source_path + "/images")
    # Copy each file from the source directory to the destination directory
    for file in files:
        source_file = os.path.join(args.source_path, "images", file)

        destination_file = os.path.join(args.source_path, "images_2", file)
        shutil.copy2(source_file, destination_file)
        exit_code = os.system(magick_command + " mogrify -resize 50% " + destination_file)
        if exit_code != 0:
            logging.error(f"50% resize failed with code {exit_code}. Exiting.")
            exit(exit_code)

        destination_file = os.path.join(args.source_path, "images_4", file)
        shutil.copy2(source_file, destination_file)
        exit_code = os.system(magick_command + " mogrify -resize 25% " + destination_file)
        if exit_code != 0:
            logging.error(f"25% resize failed with code {exit_code}. Exiting.")
            exit(exit_code)

        destination_file = os.path.join(args.source_path, "images_8", file)
        shutil.copy2(source_file, destination_file)
        exit_code = os.system(magick_command + " mogrify -resize 12.5% " + destination_file)
        if exit_code != 0:
            logging.error(f"12.5% resize failed with code {exit_code}. Exiting.")
            exit(exit_code)

print("Done.")
