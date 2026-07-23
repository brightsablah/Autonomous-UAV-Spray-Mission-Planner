from pathlib import Path
import argparse

import geopandas as gpd
import rasterio
from rasterio.mask import mask


def apply_tif_boundary(
    ndvi_path,
    boundary_path,
    output_path,
    all_touched=False,
    nodata=-9999,
    overwrite=False,
):
    """Clip an NDVI raster using a field boundary."""

    ndvi_path = Path(ndvi_path)
    boundary_path = Path(boundary_path)
    output_path = Path(output_path)

    if not ndvi_path.is_file():
        raise FileNotFoundError(
            f"NDVI raster not found: {ndvi_path}"
        )

    if not boundary_path.is_file():
        raise FileNotFoundError(
            f"Boundary file not found: {boundary_path}"
        )

    if ndvi_path.resolve() == output_path.resolve():
        raise ValueError(
            "The output path must be different from the input path."
        )

    if output_path.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {output_path}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)

    with rasterio.open(ndvi_path) as src:
        if src.crs is None:
            raise ValueError(
                "The NDVI raster does not have a CRS."
            )

        boundary = gpd.read_file(boundary_path)

        if boundary.empty:
            raise ValueError(
                "The boundary file does not contain any features."
            )

        if boundary.crs is None:
            raise ValueError(
                "The boundary file does not have a CRS."
            )

        # Remove empty geometries
        boundary = boundary[
            boundary.geometry.notna()
            & ~boundary.geometry.is_empty
        ].copy()

        if boundary.empty:
            raise ValueError(
                "The boundary file does not contain valid geometries."
            )

        # Match the raster coordinate system
        boundary = boundary.to_crs(src.crs)

        shapes = [
            geometry.__geo_interface__
            for geometry in boundary.geometry
        ]

        try:
            clipped_ndvi, clipped_transform = mask(
                src,
                shapes,
                crop=True,
                nodata=nodata,
                all_touched=all_touched,
            )

        except ValueError as error:
            raise ValueError(
                "The boundary does not overlap the NDVI raster."
            ) from error

        clipped_meta = src.meta.copy()

        clipped_meta.update(
            {
                "driver": "GTiff",
                "height": clipped_ndvi.shape[1],
                "width": clipped_ndvi.shape[2],
                "transform": clipped_transform,
                "nodata": nodata,
                "dtype": "float32",
            }
        )

    with rasterio.open(output_path, "w", **clipped_meta) as dst:
        dst.write(clipped_ndvi.astype("float32"))

    print(f"\nSaved clipped NDVI raster to: {output_path}")

    return output_path


def main():
    """Allow the script to run independently."""

    parser = argparse.ArgumentParser(
        description="Clip an NDVI raster using a boundary file."
    )

    parser.add_argument(
        "ndvi_path",
        help="Path to the NDVI raster",
    )

    parser.add_argument(
        "boundary_path",
        help="Path to the boundary file",
    )

    parser.add_argument(
        "--output",
        default="data/processed/odm_ndvi_clipped_boundary.tif",
        help="Output path for the clipped raster",
    )

    parser.add_argument(
        "--all-touched",
        action="store_true",
        help="Include all pixels touched by the boundary",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow an existing output to be replaced",
    )

    args = parser.parse_args()

    try:
        apply_tif_boundary(
            ndvi_path=args.ndvi_path,
            boundary_path=args.boundary_path,
            output_path=args.output,
            all_touched=args.all_touched,
            overwrite=args.overwrite,
        )

    except Exception as error:
        parser.exit(status=1, message=f"Error: {error}\n")


if __name__ == "__main__":
    main()