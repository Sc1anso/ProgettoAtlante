# Third-party software and license notes

Project ATLANTE is an integration and deployment layer; it does not relicense bundled upstream code. Each component retains its own license and notice files, which govern that component and its assets. No top-level `LICENSE` is provided because distribution and commercial-use rights for the combined repository have not been established.

| Component | Location | Notices to review |
| --- | --- | --- |
| RaDe-GS | `RaDe-GS/` | `RaDe-GS/LICENSE.md` and notices in its bundled dependencies |
| SuGaR | `SuGaR/` | `SuGaR/LICENSE.md`, `SuGaR/gaussian_splatting/LICENSE.md`, and dependency notices |
| Gaussian Splatting Monitor / SIBR | `Gaussian-Splatting-Monitor/` | `Gaussian-Splatting-Monitor/LICENSE.md`, `SIBR_viewers/LICENSE.md`, and bundled dependency notices |
| DiGS | `DiGS/` | Review the source provenance and obtain/confirm applicable license terms before redistribution |
| COLMAP, PyTorch, Open3D, and Python packages | Docker/Python dependencies | Their respective upstream terms apply; consult dependency manifests and upstream notices |
| Pavarotti demo video | `server/samples/pavarotti-demo.mp4` | Confirm rights to distribute the recording, likeness, music, and other included media |

Some bundled research software restricts use to non-commercial research/evaluation unless additional permission is granted. A private GitHub repository does not waive those terms. Preserve original license files and seek guidance from the relevant rights holders for the intended use and distribution model. The demo is stored using Git LFS because it is about 203 MB; LFS does not change its copyright status.

Before any wider release, review bundled dependency notices recursively and confirm that every source file, model, dataset, image, and video may be redistributed. This notice is informational and is not legal advice.
