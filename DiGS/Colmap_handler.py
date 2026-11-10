import struct
import os
import collections

import numpy as np

import importlib

import open3d as o3d

CameraModel = collections.namedtuple(
    "CameraModel", ["model_id", "model_name", "num_params"]
)
Camera = collections.namedtuple(
    "Camera", ["id", "model", "width", "height", "params"]
)
BaseImage = collections.namedtuple(
    "Image", ["id", "qvec", "tvec", "camera_id", "name", "xys", "point3D_ids"]
)
Point3D = collections.namedtuple(
    "Point3D", ["id", "xyz", "rgb", "error", "image_ids", "point2D_idxs"]
)
CAMERA_MODELS = {
    CameraModel(model_id=0, model_name="SIMPLE_PINHOLE", num_params=3),
    CameraModel(model_id=1, model_name="PINHOLE", num_params=4),
    CameraModel(model_id=2, model_name="SIMPLE_RADIAL", num_params=4),
    CameraModel(model_id=3, model_name="RADIAL", num_params=5),
    CameraModel(model_id=4, model_name="OPENCV", num_params=8),
    CameraModel(model_id=5, model_name="OPENCV_FISHEYE", num_params=8),
    CameraModel(model_id=6, model_name="FULL_OPENCV", num_params=12),
    CameraModel(model_id=7, model_name="FOV", num_params=5),
    CameraModel(model_id=8, model_name="SIMPLE_RADIAL_FISHEYE", num_params=4),
    CameraModel(model_id=9, model_name="RADIAL_FISHEYE", num_params=5),
    CameraModel(model_id=10, model_name="THIN_PRISM_FISHEYE", num_params=12),
}
CAMERA_MODEL_IDS = dict(
    [(camera_model.model_id, camera_model) for camera_model in CAMERA_MODELS]
)
CAMERA_MODEL_NAMES = dict(
    [(camera_model.model_name, camera_model) for camera_model in CAMERA_MODELS]
)
def qvec2rotmat(qvec):
    return np.array(
        [
            [
                1 - 2 * qvec[2] ** 2 - 2 * qvec[3] ** 2,
                2 * qvec[1] * qvec[2] - 2 * qvec[0] * qvec[3],
                2 * qvec[3] * qvec[1] + 2 * qvec[0] * qvec[2],
            ],
            [
                2 * qvec[1] * qvec[2] + 2 * qvec[0] * qvec[3],
                1 - 2 * qvec[1] ** 2 - 2 * qvec[3] ** 2,
                2 * qvec[2] * qvec[3] - 2 * qvec[0] * qvec[1],
            ],
            [
                2 * qvec[3] * qvec[1] - 2 * qvec[0] * qvec[2],
                2 * qvec[2] * qvec[3] + 2 * qvec[0] * qvec[1],
                1 - 2 * qvec[1] ** 2 - 2 * qvec[2] ** 2,
            ],
        ]
    )

def rotmat2qvec(R):
    Rxx, Ryx, Rzx, Rxy, Ryy, Rzy, Rxz, Ryz, Rzz = R.flat
    K = (
        np.array(
            [
                [Rxx - Ryy - Rzz, 0, 0, 0],
                [Ryx + Rxy, Ryy - Rxx - Rzz, 0, 0],
                [Rzx + Rxz, Rzy + Ryz, Rzz - Rxx - Ryy, 0],
                [Ryz - Rzy, Rzx - Rxz, Rxy - Ryx, Rxx + Ryy + Rzz],
            ]
        )
        / 3.0
    )
    eigvals, eigvecs = np.linalg.eigh(K)
    qvec = eigvecs[[3, 0, 1, 2], np.argmax(eigvals)]
    if qvec[0] < 0:
        qvec *= -1
    return qvec

class Image(BaseImage):
    def qvec2rotmat(self):
        return qvec2rotmat(self.qvec)







class ColmapDatabase():
    def __init__(self,
                 database_path :str = "./",
                 cameras  : list[Camera] = [],
                 images  : list[Image] = [],
                 points3D  : dict = {},
                 verbosity : int = 1,
                 args = {}) -> None:
        self.verbosity = verbosity
        #store values
        if len(images)==0 and len(cameras)==0:
            if len(points3D)==0:
                #read database
                self.database_path = database_path
                self.cameras = self.read_cameras_binary()
                self.images = self.read_images_binary()
                self.points3D = self.read_points3D_binary()
            else:
                #write pcd only db
                self.cameras = []
                self.images = []
                self.points3D = points3D
                self.database_path = database_path
        else:
            self.cameras = cameras
            self.images = images
            self.points3D = points3D
            self.database_path = database_path
        

    def read_next_bytes(self, fid, num_bytes, format_char_sequence, endian_character="<"):
        """Read and unpack the next bytes from a binary file.
        :param fid:
        :param num_bytes: Sum of combination of {2, 4, 8}, e.g. 2, 6, 16, 30, etc.
        :param format_char_sequence: List of {c, e, f, d, h, H, i, I, l, L, q, Q}.
        :param endian_character: Any of {@, =, <, >, !}
        :return: Tuple of read and unpacked values.
        """
        data = fid.read(num_bytes)
        return struct.unpack(endian_character + format_char_sequence, data)

    def write_next_bytes(self, fid, data, format_char_sequence, endian_character="<"):
        """pack and write to a binary file.
        :param fid:
        :param data: data to send, if multiple elements are sent at the same time,
        they should be encapsuled either in a list or a tuple
        :param format_char_sequence: List of {c, e, f, d, h, H, i, I, l, L, q, Q}.
        should be the same length as the data list or tuple
        :param endian_character: Any of {@, =, <, >, !}
        """
        if isinstance(data, (list, tuple)):
            bytes = struct.pack(endian_character + format_char_sequence, *data)
        else:
            bytes = struct.pack(endian_character + format_char_sequence, data)
        fid.write(bytes)



    def write_cameras_binary(self, path_to_model_file = "sparse/0/cameras.bin"):
        """
        see: src/colmap/scene/reconstruction.cc
            void Reconstruction::WriteCamerasBinary(const std::string& path)
            void Reconstruction::ReadCamerasBinary(const std::string& path)
        """
        with open(os.path.join(self.database_path, path_to_model_file), "wb") as fid:
            
            self.write_next_bytes(fid, len(self.cameras), "Q")
            for cam in self.cameras:
                model_id = CAMERA_MODEL_NAMES[cam.model].model_id
                camera_properties = [cam.id, model_id, cam.width, cam.height]
                if self.verbosity > 0:
                    print(f"Model id of the cameras written: {model_id}")
                self.write_next_bytes(fid, camera_properties, "iiQQ")
                for p in cam.params:
                    self.write_next_bytes(fid, float(p), "d")
        return None
    
    def read_cameras_binary(self, path_to_model_file = "sparse/0/cameras.bin"):
        cameras = {}
        with open(os.path.join(self.database_path, path_to_model_file), "rb") as fid:
            num_cameras = self.read_next_bytes(fid, 8, "Q")[0]
            if self.verbosity > 0:
                print(f"Collecting {num_cameras} cameras from colmap db")
            for _ in range(num_cameras):
                camera_properties = self.read_next_bytes(
                    fid, num_bytes=24, format_char_sequence="iiQQ"
                )
                camera_id = camera_properties[0]
                model_id = camera_properties[1]
                model_name = CAMERA_MODEL_IDS[camera_properties[1]].model_name
                width = camera_properties[2]
                height = camera_properties[3]
                num_params = CAMERA_MODEL_IDS[model_id].num_params
                params = self.read_next_bytes(
                    fid,
                    num_bytes=8 * num_params,
                    format_char_sequence="d" * num_params,
                )
                cameras[camera_id] = Camera(
                    id=camera_id,
                    model=model_name,
                    width=width,
                    height=height,
                    params=np.array(params),
                )
            assert len(cameras) == num_cameras
        return cameras
    
    @staticmethod
    def colmap2camera(camera) -> tuple:
        """For OpenCV camera, the parameter list is expected to be the following
          fx, fy, cx, cy, k1, k2, k3, k4"""
        camera_id = camera.id
        model = camera.model
        width = camera.width
        height = camera.height
        params = camera.params
        return camera_id, model, width, height, params

    
    @staticmethod
    def camera2colmap(camera_id, model, width, height, params) -> None:
        """For OpenCV camera, the parameter list is expected to be the following
          fx, fy, cx, cy, k1, k2, k3, k4"""
        return Camera(
                    id=camera_id,
                    model=model,
                    width=width,
                    height=height,
                    params=params,
                )
    
    def write_images_binary(self, path_to_model_file = "sparse/0/images.bin"):
        """
        see: src/colmap/scene/reconstruction.cc
            void Reconstruction::ReadImagesBinary(const std::string& path)
            void Reconstruction::WriteImagesBinary(const std::string& path)
        """
        with open(os.path.join(self.database_path, path_to_model_file), "wb") as fid:
            self.write_next_bytes(fid, len(self.images), "Q")
            for img in self.images:
                self.write_next_bytes(fid, img.id, "i")
                self.write_next_bytes(fid, img.qvec.tolist(), "dddd")
                self.write_next_bytes(fid, img.tvec.tolist(), "ddd")
                self.write_next_bytes(fid, img.camera_id, "i")
                for char in img.name:
                    self.write_next_bytes(fid, char.encode("utf-8"), "c")
                self.write_next_bytes(fid, b"\x00", "c")
                self.write_next_bytes(fid, len(img.point3D_ids), "Q")
                for xy, p3d_id in zip(img.xys, img.point3D_ids):
                    self.write_next_bytes(fid, [*xy, p3d_id], "ddq")

    def read_images_binary(self, path_to_model_file = "sparse/0/images.bin"):
        images = {}
        with open(os.path.join(self.database_path, path_to_model_file), "rb") as fid:
            num_reg_images = self.read_next_bytes(fid, 8, "Q")[0]
            if self.verbosity > 0:
                print(f"Reading {num_reg_images} images from db")
            for _ in range(num_reg_images):
                binary_image_properties = self.read_next_bytes(
                    fid, num_bytes=64, format_char_sequence="idddddddi"
                )
                image_id = binary_image_properties[0]
                qvec = np.array(binary_image_properties[1:5])
                tvec = np.array(binary_image_properties[5:8])
                camera_id = binary_image_properties[8]
                binary_image_name = b""
                current_char = self.read_next_bytes(fid, 1, "c")[0]
                while current_char != b"\x00":  # look for the ASCII 0 entry
                    binary_image_name += current_char
                    current_char = self.read_next_bytes(fid, 1, "c")[0]
                image_name = binary_image_name.decode("utf-8")
                num_points2D = self.read_next_bytes(
                    fid, num_bytes=8, format_char_sequence="Q"
                )[0]
                x_y_id_s = self.read_next_bytes(
                    fid,
                    num_bytes=24 * num_points2D,
                    format_char_sequence="ddq" * num_points2D,
                )
                xys = np.column_stack(
                    [
                        tuple(map(float, x_y_id_s[0::3])),
                        tuple(map(float, x_y_id_s[1::3])),
                    ]
                )
                point3D_ids = np.array(tuple(map(int, x_y_id_s[2::3])))
                images[image_id] = Image(
                    id=image_id,
                    qvec=qvec,
                    tvec=tvec,
                    camera_id=camera_id,
                    name=image_name,
                    xys=xys,
                    point3D_ids=point3D_ids,
                )
        return images
    
    @staticmethod
    def colmap2imageview(image) -> tuple:
        #gaussian splatting only need the pose of the image to get extrinsics of the cameras associated with images.
        image_id = image.id
        camera_id = image.camera_id
        image_name = image.name
        xys = image.xys
        point3D_ids = image.point3D_ids
        qvec = image.qvec
        tvec = image.tvec
        rotmat = qvec2rotmat(qvec)
        pose = np.identity(4)
        pose[:3,:3] = rotmat
        pose[:3,3] = tvec
        return image_id, pose, camera_id, image_name, xys, point3D_ids

    @staticmethod
    def imageview2colmap(image_id, pose, camera_id, image_name, xys=np.array([]), point3D_ids=np.array([])) -> None:
        #gaussian splatting only need the pose of the image to get extrinsics of the cameras associated with images.
        rotmat = pose[:3,:3]
        qvec = rotmat2qvec(rotmat)

        tvec = pose[:3, 3]
        return Image(
                id=image_id,
                qvec=qvec,
                tvec=tvec,
                camera_id=camera_id,
                name=image_name,
                xys=xys,
                point3D_ids=point3D_ids,
        )
    

    def write_points3D_binary(self, path_to_model_file = "sparse/0/points3D.bin"):
        """
        see: src/colmap/scene/reconstruction.cc
            void Reconstruction::ReadPoints3DBinary(const std::string& path)
            void Reconstruction::WritePoints3DBinary(const std::string& path)
        """
        if os.path.isfile(os.path.join(self.database_path, path_to_model_file[:-4]+".ply")):
            if self.verbosity > 0:
                print(f"removing .ply file {os.path.join(self.database_path, path_to_model_file[:-4]+'.ply')}")
            os.remove(os.path.join(self.database_path, path_to_model_file[:-4]+".ply"))
        with open(os.path.join(self.database_path, path_to_model_file), "wb") as fid:
            self.write_next_bytes(fid, len(self.points3D), "Q")
            for _, pt in self.points3D.items():
                self.write_next_bytes(fid, pt.id, "Q")
                self.write_next_bytes(fid, pt.xyz.tolist(), "ddd")
                self.write_next_bytes(fid, pt.rgb.tolist(), "BBB")
                self.write_next_bytes(fid, pt.error, "d")
                track_length = pt.image_ids.shape[0]
                self.write_next_bytes(fid, track_length, "Q")
                for image_id, point2D_id in zip(pt.image_ids, pt.point2D_idxs):
                    self.write_next_bytes(fid, [image_id, point2D_id], "ii")

    def read_points3D_binary(self, path_to_model_file = "sparse/0/points3D.bin"):
        points3D = {}
        with open(os.path.join(self.database_path, path_to_model_file), "rb") as fid:
            num_points = self.read_next_bytes(fid, 8, "Q")[0]
            for _ in range(num_points):
                binary_point_line_properties = self.read_next_bytes(
                    fid, num_bytes=43, format_char_sequence="QdddBBBd"
                )
                point3D_id = binary_point_line_properties[0]
                xyz = np.array(binary_point_line_properties[1:4])
                rgb = np.array(binary_point_line_properties[4:7])
                error = np.array(binary_point_line_properties[7])
                track_length = self.read_next_bytes(
                    fid, num_bytes=8, format_char_sequence="Q"
                )[0]
                track_elems = self.read_next_bytes(
                    fid,
                    num_bytes=8 * track_length,
                    format_char_sequence="ii" * track_length,
                )
                image_ids = np.array(tuple(map(int, track_elems[0::2])))
                point2D_idxs = np.array(tuple(map(int, track_elems[1::2])))
                points3D[point3D_id] = Point3D(
                    id=point3D_id,
                    xyz=xyz,
                    rgb=rgb,
                    error=error,
                    image_ids=image_ids,
                    point2D_idxs=point2D_idxs,
                )
        return points3D
    
    @staticmethod
    def colmap2point(point3D)->tuple:
        xyz = point3D.xyz
        id = point3D.id
        rgb = point3D.rgb
        error = point3D.error
        image_ids = point3D.image_ids
        point2D_idxs = point3D.point2D_idxs
        return xyz, id, rgb, error, image_ids, point2D_idxs

    @staticmethod
    def pcd2colmap(pcd)->None:
        xyz = np.asarray(pcd.points)
        rgb = np.asarray(pcd.colors)
        if rgb.max()<=1:
            rgb = (rgb*255).astype(np.uint8)
        points3D = {}
        for point3D_id in range(len(xyz)):

            points3D[point3D_id] = Point3D(
                        id=point3D_id,
                        xyz=xyz[point3D_id],
                        rgb=rgb[point3D_id],
                        error=0.,
                        image_ids=np.array([]),
                        point2D_idxs=np.array([]),
                    )
        return points3D
    
    def write_db(self,):
        self.write_cameras_binary()
        self.write_images_binary()
        self.write_points3D_binary()
        
    

        




