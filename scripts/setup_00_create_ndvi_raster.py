from pathlib import Path
import argparse

import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling


def create_ndvi_raster(
    nir_path,
    red_path,
    ndvi_output_path,
    preview_output_path=None,
    show_preview=True,
    downsample_factor=20,
    overwrite=False,
):
    """Create an NDVI raster using NIR and RED orthophotos."""

    nir_path = Path(nir_path)
    red_path = Path(red_path)
    ndvi_output_path = Path(ndvi_output_path)

    if preview_output_path:
        preview_output_path = Path(preview_output_path)

    if not nir_path.is_file():
        raise FileNotFoundError(f"NIR raster not found: {nir_path}")

    if not red_path.is_file():
        raise FileNotFoundError(f"RED raster not found: {red_path}")

    if downsample_factor < 1:
        raise ValueError("Downsample factor must be at least 1.")

    if ndvi_output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {ndvi_output_path}"
        )

    if (
        preview_output_path
        and preview_output_path.exists()
        and not overwrite
    ):
        raise FileExistsError(
            f"Preview already exists: {preview_output_path}"
        )

    ndvi_output_path.parent.mkdir(parents=True, exist_ok=True)

    if preview_output_path:
        preview_output_path.parent.mkdir(parents=True, exist_ok=True)

    # Read NIR as the reference raster
    with rasterio.open(nir_path) as nir_src:
        if nir_src.count < 2:
            raise ValueError(
                "The NIR raster must contain a data band and mask band."
            )

        if nir_src.crs is None:
            raise ValueError("The NIR raster does not have a CRS.")

        nir = nir_src.read(1).astype("float32")
        nir_mask = nir_src.read(2) > 0

        profile = nir_src.profile.copy()
        reference_transform = nir_src.transform
        reference_crs = nir_src.crs
        reference_shape = nir.shape

    # Prepare arrays matching the NIR raster
    red_resampled = np.zeros(reference_shape, dtype="float32")
    red_mask_resampled = np.zeros(reference_shape, dtype="float32")

    # Read and resample RED to match NIR
    with rasterio.open(red_path) as red_src:
        if red_src.count < 2:
            raise ValueError(
                "The RED raster must contain a data band and mask band."
            )

        if red_src.crs is None:
            raise ValueError("The RED raster does not have a CRS.")

        red = red_src.read(1).astype("float32")
        red_mask = red_src.read(2).astype("float32")

        reproject(
            source=red,
            destination=red_resampled,
            src_transform=red_src.transform,
            src_crs=red_src.crs,
            dst_transform=reference_transform,
            dst_crs=reference_crs,
            dst_nodata=0,
            resampling=Resampling.bilinear,
        )

        reproject(
            source=red_mask,
            destination=red_mask_resampled,
            src_transform=red_src.transform,
            src_crs=red_src.crs,
            dst_transform=reference_transform,
            dst_crs=reference_crs,
            src_nodata=0,
            dst_nodata=0,
            resampling=Resampling.nearest,
        )

    # Identify pixels with valid data
    valid_mask = (
        nir_mask
        & (red_mask_resampled > 0)
        & np.isfinite(nir)
        & np.isfinite(red_resampled)
        & ((nir + red_resampled) > 0)
    )

    if not np.any(valid_mask):
        raise ValueError(
            "No overlapping valid pixels were found between the rasters."
        )

    # Calculate NDVI
    ndvi = np.full(reference_shape, np.nan, dtype="float32")

    ndvi[valid_mask] = (
        nir[valid_mask] - red_resampled[valid_mask]
    ) / (
        nir[valid_mask] + red_resampled[valid_mask]
    )

    valid_ndvi = ndvi[np.isfinite(ndvi)]

    print("\nNDVI statistics")
    print("-" * 30)
    print(f"Minimum: {valid_ndvi.min():.4f}")
    print(f"Maximum: {valid_ndvi.max():.4f}")
    print(f"Mean: {valid_ndvi.mean():.4f}")
    print(f"Standard deviation: {valid_ndvi.std():.4f}")

    # Save the NDVI GeoTIFF
    profile.update(
        dtype="float32",
        count=1,
        nodata=-9999,
    )

    ndvi_to_save = np.where(
        np.isfinite(ndvi),
        ndvi,
        -9999,
    ).astype("float32")

    with rasterio.open(ndvi_output_path, "w", **profile) as dst:
        dst.write(ndvi_to_save, 1)

    print(f"\nSaved NDVI raster to: {ndvi_output_path}")

    # Create the preview when requested
    if show_preview or preview_output_path:
        figure, axis = plt.subplots(figsize=(8, 6))

        image = axis.imshow(
            ndvi[::downsample_factor, ::downsample_factor],
            cmap="RdYlGn",
            vmin=-1,
            vmax=1,
        )

        figure.colorbar(image, ax=axis, label="NDVI")
        axis.set_title("NDVI Preview")
        axis.axis("off")

        if preview_output_path:
            figure.savefig(
                preview_output_path,
                dpi=300,
                bbox_inches="tight",
            )
            print(f"Saved preview to: {preview_output_path}")

        if show_preview:
            plt.show()

        plt.close(figure)

    return ndvi_output_path


def main():
    """Allow the script to run independently."""

    parser = argparse.ArgumentParser(
        description="Create an NDVI raster from NIR and RED rasters."
    )

    parser.add_argument("nir_path", help="Path to the NIR raster")
    parser.add_argument("red_path", help="Path to the RED raster")

    parser.add_argument(
        "--output",
        default="data/processed/odm_ndvi.tif",
        help="NDVI output path",
    )

    parser.add_argument(
        "--preview-output",
        help="Optional path for saving the preview image",
    )

    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Do not display the NDVI preview",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow existing outputs to be replaced",
    )

    args = parser.parse_args()

    try:
        create_ndvi_raster(
            nir_path=args.nir_path,
            red_path=args.red_path,
            ndvi_output_path=args.output,
            preview_output_path=args.preview_output,
            show_preview=not args.no_preview,
            overwrite=args.overwrite,
        )

    except Exception as error:
        parser.exit(status=1, message=f"Error: {error}\n")


if __name__ == "__main__":
    main()