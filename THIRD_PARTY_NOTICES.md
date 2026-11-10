# Third-party software and redistribution notes

This repository is an integration/deployment project, not a relicensing of the included upstream code. Each component retains its own license and notice files; those terms govern the corresponding code and assets. No project-wide `LICENSE` is supplied because redistribution and commercial-use rights have not been established for the combined package.

| Component | Location | Notice to review |
| --- | --- | --- |
| RaDe-GS | `RaDe-GS/` | `RaDe-GS/LICENSE.md` and upstream notices in its submodules |
| SuGaR | `SuGaR/` | `SuGaR/LICENSE.md`, `SuGaR/gaussian_splatting/LICENSE.md` and submodule notices |
| Gaussian Splatting Monitor / SIBR | `Gaussian-Splatting-Monitor/` | `Gaussian-Splatting-Monitor/LICENSE.md`, `SIBR_viewers/LICENSE.md` and bundled dependency notices |
| DiGS | `DiGS/` | Inspect the source distribution for its license/notice before redistribution |
| COLMAP, PyTorch, Open3D and other packages | Docker/Python dependencies | Their respective upstream license terms apply; see dependency manifests and upstream sites |
| Pavarotti demo video | `server/samples/pavarotti-demo.mp4` | Confirm permission, likeness, music and other media rights before publishing or redistributing |

Some included research components contain non-commercial/research-use restrictions. That does not automatically authorize placing the combined source or sample media in a public repository. Obtain rights-holder guidance for the exact use and distribution model, and retain all upstream notices. The demo video is tracked with Git LFS because it is about 203 MB; Git LFS does not change its copyright or redistribution status.

Before public release, review submodule/dependency notices recursively, remove any private data or credentials, and confirm that every model, dataset, image, video and source file can be redistributed. This notice is informational and is not legal advice.
