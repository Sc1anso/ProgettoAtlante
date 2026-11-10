import argparse
import os

import pymeshlab

parser = argparse.ArgumentParser(description="Riparazione conservativa della mesh RaDe-GS")
parser.add_argument("mesh_path", type=str, help="Mesh PLY risultante da RaDe-GS")
parser.add_argument("--output_folder", "-o", type=str, default="./output/", help="Cartella di destinazione")


def conservative_repair(ms, output_folder):
    # Only caps short, valid boundary loops. It does not remesh, smooth, or
    # alter measured surface regions such as folds and thin subject details.
    print("POSTPROCESS_PROGRESS: 25 Individuazione dei piccoli buchi", flush=True)
    ms.apply_filter(
        "meshing_close_holes",
        maxholesize=128,
        selfintersection=True,
        newfaceselected=False,
    )
    return os.path.join(output_folder, "recon-repaired-conservative-v6.ply")


def main(args):
    os.makedirs(args.output_folder, exist_ok=True)
    print("POSTPROCESS_PROGRESS: 10 Caricamento della mesh", flush=True)
    ms = pymeshlab.MeshSet(verbose=True)
    ms.load_new_mesh(args.mesh_path)
    print("POSTPROCESS_PROGRESS: 18 Pulizia della mesh", flush=True)
    ms.apply_filter("meshing_remove_unreferenced_vertices")
    output_path = conservative_repair(ms, args.output_folder)
    print("POSTPROCESS_PROGRESS: 90 Salvataggio della mesh", flush=True)
    ms.save_current_mesh(output_path)
    print("POSTPROCESS_PROGRESS: 100 Mesh riparata pronta", flush=True)


if __name__ == "__main__":
    main(parser.parse_args())
