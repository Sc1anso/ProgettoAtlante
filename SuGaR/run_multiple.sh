#!/bin/bash -l
path1='backpack'
path2='hairbrush'
path3='box_text'
path4='jacket'
path5='phone'
path6='tablet'
path7='pavarotti1'

<<create
for path in $path7
do
  
  mkdir -p ./gaussian_splatting/data/$path/2fps/input
  mkdir -p ./gaussian_splatting/data/$path/0_5fps/input
  ffmpeg -i ./gaussian_splatting/data/$path/video.mp4 -vf fps=fps=2 ./gaussian_splatting/data/$path/2fps/input/%04d.png
  ffmpeg -i ./gaussian_splatting/data/$path/video.mp4 -vf fps=fps=1/2 ./gaussian_splatting/data/$path/0_5fps/input/%04d.png
done
create

<<rembg
source /home/varlab/anaconda3/bin/deactivate
source /home/varlab/anaconda3/bin/activate rembg
cd ../rembg
for path in $path7
do
  mkdir -p ../SuGaR/gaussian_splatting/data/$path/2fps/masks_input
  mkdir -p ../SuGaR/gaussian_splatting/data/$path/0_5fps/masks_input
  
  rembg p -om ../SuGaR/gaussian_splatting/data/$path/2fps/input ../SuGaR/gaussian_splatting/data/$path/2fps/masks_input
  rembg p -om ../SuGaR/gaussian_splatting/data/$path/0_5fps/input ../SuGaR/gaussian_splatting/data/$path/0_5fps/masks_input

done
source /home/varlab/anaconda3/bin/deactivate
source /home/varlab/anaconda3/bin/activate sugar
cd ../SuGar
rembg

<<colmap
for path in $path7
do
  python gaussian_splatting/convert.py -s ./gaussian_splatting/data/$path/2fps --mask_path ./gaussian_splatting/data/$path/2fps/masks_input
  python gaussian_splatting/convert.py -s ./gaussian_splatting/data/$path/0_5fps --mask_path ./gaussian_splatting/data/$path/0_5fps/masks_input
done
colmap

<<hardmatchcorrection
colmap image_undistorter --image_path ./gaussian_splatting/data/$path/2fps/input --input_path ./gaussian_splatting/data/$path/2fps/distorted/sparse/1 --output_path ./gaussian_splatting/data/$path/2fps --output_type COLMAP
mv ./gaussian_splatting/data/$path/2fps/distorted/sparse/0 ./gaussian_splatting/data/$path/2fps/distorted/sparse/2
mv ./gaussian_splatting/data/$path/2fps/distorted/sparse/1 ./gaussian_splatting/data/$path/2fps/distorted/sparse/0
mv ./gaussian_splatting/data/$path/2fps/distorted/sparse/2 ./gaussian_splatting/data/$path/2fps/distorted/sparse/1

colmap image_undistorter --image_path ./gaussian_splatting/data/$path/0_5fps/input --input_path ./gaussian_splatting/data/$path/0_5fps/distorted/sparse/1 --output_path ./gaussian_splatting/data/$path/0_5fps --output_type COLMAP
mv ./gaussian_splatting/data/$path/0_5fps/distorted/sparse/0 ./gaussian_splatting/data/$path/0_5fps/distorted/sparse/2
mv ./gaussian_splatting/data/$path/0_5fps/distorted/sparse/1 ./gaussian_splatting/data/$path/0_5fps/distorted/sparse/0
mv ./gaussian_splatting/data/$path/0_5fps/distorted/sparse/2 ./gaussian_splatting/data/$path/0_5fps/distorted/sparse/1
hardmatchcorrection

<<segmentation
#source /Users/yourname/anaconda/bin/deactivate ?????
#source /Users/yourname/anaconda/bin/activate SAM ?????
#conda deactivate
#conda activate SAM
cd ../SAM
for path in $path7
do
  #mkdir -p ../SuGaR/gaussian_splatting/data/$path/2fps/copy_images
  #mkdir -p ../SuGaR/gaussian_splatting/data/$path/0_5fps/copy_images
  #cp -r ../SuGaR/gaussian_splatting/data/$path/2fps/images/. ../SuGaR/gaussian_splatting/data/$path/2fps/copy_images
  #cp -r ../SuGaR/gaussian_splatting/data/$path/0_5fps/images/. ../SuGaR/gaussian_splatting/data/$path/0_5fps/copy_images 
  

  python garment_segment.py --input ../SuGaR/gaussian_splatting/data/$path/2fps/copy_images --output ../SuGaR/gaussian_splatting/data/$path/2fps/images --model-type "vit_b" --checkpoint sam_vit_b_01ec64.pth --dilate-iterations 5 --patch-size 60 60 --reference-index 0
  python garment_segment.py --input ../SuGaR/gaussian_splatting/data/$path/0_5fps/copy_images --output ../SuGaR/gaussian_splatting/data/$path/0_5fps/images --model-type "vit_b" --checkpoint sam_vit_b_01ec64.pth --dilate-iterations 5 --patch-size 60 60 --reference-index 0
done
#conda deactivate
#conda activate sugar
cd ../SuGar
segmentation

<<rembg
source /home/varlab/anaconda3/bin/deactivate
source /home/varlab/anaconda3/bin/activate rembg
cd ../rembg
for path in $path7
do
  mkdir -p ../SuGaR/gaussian_splatting/data/$path/2fps/copy_images
  mkdir -p ../SuGaR/gaussian_splatting/data/$path/0_5fps/copy_images
  cp -r ../SuGaR/gaussian_splatting/data/$path/2fps/images/. ../SuGaR/gaussian_splatting/data/$path/2fps/copy_images
  cp -r ../SuGaR/gaussian_splatting/data/$path/0_5fps/images/. ../SuGaR/gaussian_splatting/data/$path/0_5fps/copy_images
  rm  ../SuGaR/gaussian_splatting/data/$path/2fps/images/*
  rm  ../SuGaR/gaussian_splatting/data/$path/0_5fps/images/*
  
  rembg p ../SuGaR/gaussian_splatting/data/$path/2fps/copy_images ../SuGaR/gaussian_splatting/data/$path/2fps/images
  rembg p ../SuGaR/gaussian_splatting/data/$path/0_5fps/copy_images ../SuGaR/gaussian_splatting/data/$path/0_5fps/images
done
source /home/varlab/anaconda3/bin/deactivate
source /home/varlab/anaconda3/bin/activate sugar
cd ../SuGar
rembg

<<recoverunsegmented
for path in $path7
do
  mv ./gaussian_splatting/data/${path}/2fps/images ./gaussian_splatting/data/${path}/2fps/temp_images
  mv ./gaussian_splatting/data/${path}/2fps/copy_images ./gaussian_splatting/data/${path}/2fps/images
  mv ./gaussian_splatting/data/${path}/2fps/temp_images ./gaussian_splatting/data/${path}/2fps/copy_images
  
  mv ./gaussian_splatting/data/${path}/0_5fps/images ./gaussian_splatting/data/${path}/0_5fps/temp_images
  mv ./gaussian_splatting/data/${path}/0_5fps/copy_images ./gaussian_splatting/data/${path}/0_5fps/images
  mv ./gaussian_splatting/data/${path}/0_5fps/temp_images ./gaussian_splatting/data/${path}/0_5fps/copy_images
done
recoverunsegmented


<<splatting
for path in $path7
do
  mkdir -p ./gaussian_splatting/output/$path/2fps
  mkdir -p ./gaussian_splatting/output/$path/0_5fps
  python gaussian_splatting/train.py -s ./gaussian_splatting/data/$path/2fps --iterations 12000 -m ./gaussian_splatting/output/$path/2fps --save_iterations 7000 12000
  python gaussian_splatting/train.py -s ./gaussian_splatting/data/$path/0_5fps --iterations 12000 -m ./gaussian_splatting/output/$path/0_5fps --save_iterations 7000 12000
done
splatting


<<sugar
for path in $path7
do
  python train.py -s ./gaussian_splatting/data/$path/2fps/ -c ./gaussian_splatting/output/$path/2fps/ -r "density" --refinement_time medium --high_poly True --iteration_to_load 7000 --eval False
done
sugar