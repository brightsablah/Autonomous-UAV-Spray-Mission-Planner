from pathlib import Path
import argparse

import matplotlib.colors as colors
import matplotlib.pyplot as plt
import numpy as np
import rasterio


def create_ndvi_crop_mask(
    ndvi_path,
    crop_threshold,
    output_path,
    preview_output_path=None,
    show_preview=True,
    downsample_factor=20,
    overwrite=False,
):
    """Create a crop and non crop mask from an NDVI raster."""

    ndvi_path = Path(ndvi_path)
    output_path = Path(output_path)

    if preview_output_path:
        preview_output_path = Path(preview_output_path)

    if not ndvi_path.is_file():
        raise FileNotFoundError(
            f"NDVI raster not found: {ndvi_path}"
        )

    if not -1 <= crop_threshold <= 1:
        raise ValueError(
            "The crop threshold must be between -1 and 1."
        )

    if downsample_factor < 1:
        raise ValueError(
            "The downsample factor must be at least 1."
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

    with rasterio.open(ndvi_path) as src:
        if src.crs is None:
            raise ValueError(
                "The NDVI raster does not have a CRS."
            )

        ndvi = src.read(1).astype("float32")
        raster_mask = src.read_masks(1) > 0
        profile = src.profile.copy()
        nodata = src.nodata

    valid_mask = np.isfinite(ndvi) & raster_mask

    if nodata is not None:
        valid_mask &= ndvi != nodata

    if not np.any(valid_mask):
        raise ValueError(
            "The NDVI raster does not contain valid pixels."
        )

    # 1 = crop
    # 0 = non crop
    crop_mask = valid_mask & (ndvi >= crop_threshold)

    crop_mask_to_save = np.full(
        ndvi.shape,
        255,
        dtype="uint8",
    )

    crop_mask_to_save[valid_mask] = 0
    crop_mask_to_save[crop_mask] = 1

    valid_pixels = np.count_nonzero(valid_mask)
    crop_pixels = np.count_nonzero(crop_mask)
    crop_percentage = crop_pixels / valid_pixels * 100

    print("\nCrop mask results")
    print("-" * 30)
    print(f"Crop threshold: NDVI >= {crop_threshold}")
    print(f"Valid pixels: {valid_pixels}")
    print(f"Crop pixels: {crop_pixels}")
    print(f"Non crop pixels: {valid_pixels - crop_pixels}")
    print(
        f"Crop percentage of valid field: "
        f"{crop_percentage:.2f}%"
    )

    if crop_pixels > 0:
        crop_ndvi = ndvi[crop_mask]

        print("\nCrop NDVI statistics")
        print("-" * 30)
        print(f"Minimum: {crop_ndvi.min():.4f}")
        print(f"Maximum: {crop_ndvi.max():.4f}")
        print(f"Mean: {crop_ndvi.mean():.4f}")
        print(f"Standard deviation: {crop_ndvi.std():.4f}")
    else:
        print("\nNo crop pixels were identified.")

    profile.update(
        dtype="uint8",
        count=1,
        nodata=255,
    )

    with rasterio.open(output_path, "w", **profile) as dst:
        dst.write(crop_mask_to_save, 1)

        dst.update_tags(
            crop_threshold=str(crop_threshold),
            class_values="0=non crop, 1=crop, 255=NoData",
        )

    print(f"\nSaved crop mask to: {output_path}")

    if show_preview or preview_output_path:
        display_mask = np.full(
            crop_mask_to_save.shape,
            np.nan,
            dtype="float32",
        )

        display_mask[crop_mask_to_save == 0] = 0
        display_mask[crop_mask_to_save == 1] = 1

        crop_cmap = colors.ListedColormap(
            ["lightgray", "green"]
        )

        figure, axis = plt.subplots(figsize=(8, 6))

        axis.imshow(
            display_mask[
                ::downsample_factor,
                ::downsample_factor,
            ],
            cmap=crop_cmap,
            vmin=0,
            vmax=1,
        )

        axis.set_title(
            f"Crop Mask: NDVI >= {crop_threshold}"
        )
        axis.axis("off")

        if preview_output_path:
            figure.savefig(
                preview_output_path,
                dpi=300,
                bbox_inches="tight",
            )

            print(
                f"Saved crop mask preview to: "
                f"{preview_output_path}"
            )

        if show_preview:
            plt.show()

        plt.close(figure)

    return output_path


def main():
    parser = argparse.ArgumentParser(
        description="Create a crop mask from an NDVI raster."
    )

    parser.add_argument(
        "ndvi_path",
        help="Path to the NDVI raster",
    )

    parser.add_argument(
        "--crop-threshold",
        type=float,
        default=0.0,
        help="Minimum NDVI value classified as crop",
    )

    parser.add_argument(
        "--output",
        help="Crop mask output path",
    )

    parser.add_argument(
        "--preview-output",
        help="Optional preview image output path",
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
        f"crop_mask_ndvi_gte_{args.crop_threshold:.2f}.tif"
    )

    try:
        create_ndvi_crop_mask(
            ndvi_path=args.ndvi_path,
            crop_threshold=args.crop_threshold,
            output_path=output_path,
            preview_output_path=args.preview_output,
            show_preview=not args.no_preview,
            overwrite=args.overwrite,
        )

    except Exception as error:
        parser.exit(status=1, message=f"Error: {error}\n")


if __name__ == "__main__":
    main()