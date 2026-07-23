from pathlib import Path
import argparse

import matplotlib.colors as colors
import matplotlib.pyplot as plt
import numpy as np
import rasterio


def create_ndvi_spray_mask(
    ndvi_path,
    crop_mask_path,
    unhealthy_lower,
    unhealthy_upper,
    output_path,
    preview_output_path=None,
    show_preview=True,
    downsample_factor=20,
    overwrite=False,
):
    """Create a spray mask using NDVI and a crop mask."""

    ndvi_path = Path(ndvi_path)
    crop_mask_path = Path(crop_mask_path)
    output_path = Path(output_path)

    if preview_output_path:
        preview_output_path = Path(preview_output_path)

    if not ndvi_path.is_file():
        raise FileNotFoundError(
            f"NDVI raster not found: {ndvi_path}"
        )

    if not crop_mask_path.is_file():
        raise FileNotFoundError(
            f"Crop mask not found: {crop_mask_path}"
        )

    if not -1 <= unhealthy_lower <= 1:
        raise ValueError(
            "The lower NDVI value must be between -1 and 1."
        )

    if not -1 <= unhealthy_upper <= 1:
        raise ValueError(
            "The upper NDVI value must be between -1 and 1."
        )

    if unhealthy_lower > unhealthy_upper:
        raise ValueError(
            "The lower NDVI value cannot exceed the upper value."
        )

    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {output_path}"
        )

    if (
        preview_output_path
        and preview_output_path.exists()
        and not overwrite
    ):
        raise FileExistsError(
            f"Preview already exists: {preview_output_path}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if preview_output_path:
        preview_output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    with rasterio.open(ndvi_path) as ndvi_src:
        ndvi = ndvi_src.read(1).astype("float32")
        ndvi_valid = ndvi_src.read_masks(1) > 0

        profile = ndvi_src.profile.copy()
        ndvi_nodata = ndvi_src.nodata
        ndvi_crs = ndvi_src.crs
        ndvi_transform = ndvi_src.transform
        ndvi_shape = ndvi.shape

    if ndvi_crs is None:
        raise ValueError(
            "The NDVI raster does not have a CRS."
        )

    ndvi_valid &= np.isfinite(ndvi)

    if ndvi_nodata is not None:
        ndvi_valid &= ndvi != ndvi_nodata

    with rasterio.open(crop_mask_path) as crop_src:
        crop_mask = crop_src.read(1)
        crop_valid = crop_src.read_masks(1) > 0

        if crop_src.crs is None:
            raise ValueError(
                "The crop mask does not have a CRS."
            )

        if crop_mask.shape != ndvi_shape:
            raise ValueError(
                "The crop mask and NDVI raster have different sizes."
            )

        if crop_src.crs != ndvi_crs:
            raise ValueError(
                "The crop mask and NDVI raster have different CRS."
            )

        if crop_src.transform != ndvi_transform:
            raise ValueError(
                "The crop mask and NDVI raster are not aligned."
            )

    analysis_valid = ndvi_valid & crop_valid
    crop_pixels_mask = analysis_valid & (crop_mask == 1)

    spray_pixels_mask = (
        crop_pixels_mask
        & (ndvi >= unhealthy_lower)
        & (ndvi <= unhealthy_upper)
    )

    valid_pixels = np.count_nonzero(analysis_valid)
    crop_pixels = np.count_nonzero(crop_pixels_mask)
    spray_pixels = np.count_nonzero(spray_pixels_mask)

    if valid_pixels == 0:
        raise ValueError(
            "No common valid pixels were found."
        )

    spray_percentage_valid = spray_pixels / valid_pixels * 100

    spray_percentage_crop = (
        spray_pixels / crop_pixels * 100
        if crop_pixels > 0
        else 0
    )

    print("\nSpray mask results")
    print("-" * 30)
    print(
        f"Unhealthy NDVI range: "
        f"{unhealthy_lower} to {unhealthy_upper}"
    )
    print(f"Valid pixels: {valid_pixels}")
    print(f"Crop pixels: {crop_pixels}")
    print(f"Spray pixels: {spray_pixels}")
    print(
        f"Spray percentage of valid field: "
        f"{spray_percentage_valid:.2f}%"
    )
    print(
        f"Spray percentage of crop area: "
        f"{spray_percentage_crop:.2f}%"
    )

    spray_mask_to_save = np.full(
        ndvi.shape,
        255,
        dtype="uint8",
    )

    spray_mask_to_save[analysis_valid] = 0
    spray_mask_to_save[spray_pixels_mask] = 1

    profile.update(
        dtype="uint8",
        count=1,
        nodata=255,
    )

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(spray_mask_to_save, 1)

        dst.update_tags(
            unhealthy_lower=str(unhealthy_lower),
            unhealthy_upper=str(unhealthy_upper),
            class_values="0=non spray, 1=spray, 255=NoData",
        )

    print(f"\nSaved spray mask to: {output_path}")

    if show_preview or preview_output_path:
        display_mask = np.full(
            spray_mask_to_save.shape,
            np.nan,
            dtype="float32",
        )

        display_mask[spray_mask_to_save == 0] = 0
        display_mask[spray_mask_to_save == 1] = 1

        spray_cmap = colors.ListedColormap(
            ["lightgray", "red"]
        )

        figure, axis = plt.subplots(figsize=(8, 6))

        axis.imshow(
            display_mask[
                ::downsample_factor,
                ::downsample_factor,
            ],
            cmap=spray_cmap,
            vmin=0,
            vmax=1,
        )

        axis.set_title(
            "Spray Mask: "
            f"{unhealthy_lower} <= NDVI <= {unhealthy_upper}"
        )
        axis.axis("off")

        if preview_output_path:
            figure.savefig(
                preview_output_path,
                dpi=300,
                bbox_inches="tight",
            )

            print(
                f"Saved spray mask preview to: "
                f"{preview_output_path}"
            )

        if show_preview:
            plt.show()

        plt.close(figure)

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Create a spray mask from NDVI and crop mask."
    )

    parser.add_argument(
        "ndvi_path",
        help="Path to the NDVI raster",
    )

    parser.add_argument(
        "crop_mask_path",
        help="Path to the crop mask",
    )

    parser.add_argument(
        "--unhealthy-lower",
        type=float,
        default=0.10,
        help="Lower unhealthy NDVI value",
    )

    parser.add_argument(
        "--unhealthy-upper",
        type=float,
        default=0.25,
        help="Upper unhealthy NDVI value",
    )

    parser.add_argument(
        "--output",
        help="Spray mask output path",
    )

    parser.add_argument(
        "--preview-output",
        help="Optional preview output path",
    )

    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Do not display the preview",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing output files",
    )

    args = parser.parse_args()

    output_path = args.output or (
        "data/processed/"
        f"spray_mask_ndvi_{args.unhealthy_lower:.2f}"
        f"_to_{args.unhealthy_upper:.2f}.tif"
    )

    try:
        create_ndvi_spray_mask(
            ndvi_path=args.ndvi_path,
            crop_mask_path=args.crop_mask_path,
            unhealthy_lower=args.unhealthy_lower,
            unhealthy_upper=args.unhealthy_upper,
            output_path=output_path,
            preview_output_path=args.preview_output,
            show_preview=not args.no_preview,
            overwrite=args.overwrite,
        )

    except Exception as error:
        parser.exit(status=1, message=f"Error: {error}\n")


if __name__ == "__main__":
    main()