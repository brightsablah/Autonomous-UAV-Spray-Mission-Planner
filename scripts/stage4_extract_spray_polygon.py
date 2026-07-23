from pathlib import Path
import argparse

import geopandas as gpd
import matplotlib.pyplot as plt
import numpy as np
import rasterio

from rasterio.features import shapes
from shapely.geometry import shape


def get_polygon_output_paths(
    output_vector_dir,
    output_figure_dir,
):
    """Create the polygon output paths."""

    output_vector_dir = Path(output_vector_dir)
    output_figure_dir = Path(output_figure_dir)

    output_paths = {
        "gpkg": (
            output_vector_dir
            / "spray_zone_polygons.gpkg"
        ),
        "geojson": (
            output_vector_dir
            / "spray_zone_polygons.geojson"
        ),
        "preview": (
            output_figure_dir
            / "spray_zone_polygons_preview.png"
        ),
    }

    return output_paths


def validate_metric_crs(crs):
    """Confirm that the CRS is projected in metres."""

    if crs is None:
        raise ValueError(
            "The input spray mask does not have a CRS."
        )

    if not crs.is_projected:
        raise ValueError(
            "The input spray mask must use a projected CRS."
        )

    metre_units = {
        "metre",
        "meter",
        "metres",
        "meters",
    }

    if crs.linear_units.lower() not in metre_units:
        raise ValueError(
            "The projected CRS must use metres. "
            f"Current units: {crs.linear_units}"
        )


def clean_polygon_geometries(gdf):
    """Repair invalid polygons and remove empty geometries."""

    gdf = gdf[
        gdf.geometry.notna()
        & ~gdf.geometry.is_empty
    ].copy()

    if gdf.empty:
        return gdf

    invalid_geometry = ~gdf.geometry.is_valid

    if invalid_geometry.any():
        gdf.loc[
            invalid_geometry,
            "geometry",
        ] = (
            gdf.loc[
                invalid_geometry,
                "geometry",
            ].buffer(0)
        )

    gdf = gdf[
        gdf.geometry.notna()
        & ~gdf.geometry.is_empty
    ].copy()

    gdf = gdf[
        gdf.geometry.geom_type.isin(
            ["Polygon", "MultiPolygon"]
        )
    ].copy()

    if not gdf.empty:
        gdf = gdf.explode(
            index_parts=False,
            ignore_index=True,
        )

    return gdf


def extract_spray_polygons(
    input_mask_path,
    output_vector_dir,
    output_figure_dir,
    minimum_polygon_area_m2=5.0,
    simplification_tolerance_m=1.0,
    show_preview=False,
    overwrite=False,
):
    """Convert a cleaned spray mask into spray polygons."""

    input_mask_path = Path(input_mask_path)
    output_vector_dir = Path(output_vector_dir)
    output_figure_dir = Path(output_figure_dir)

    if not input_mask_path.is_file():
        raise FileNotFoundError(
            f"Cleaned spray mask not found: {input_mask_path}"
        )

    if minimum_polygon_area_m2 < 0:
        raise ValueError(
            "Minimum polygon area cannot be negative."
        )

    if simplification_tolerance_m < 0:
        raise ValueError(
            "Simplification tolerance cannot be negative."
        )

    output_paths = get_polygon_output_paths(
        output_vector_dir,
        output_figure_dir,
    )

    existing_outputs = [
        path
        for path in output_paths.values()
        if path.exists()
    ]

    if existing_outputs and not overwrite:
        raise FileExistsError(
            f"Output already exists: {existing_outputs[0]}"
        )

    output_vector_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_figure_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    if overwrite:
        for output_path in existing_outputs:
            output_path.unlink()

    with rasterio.open(input_mask_path) as src:
        mask_raster = src.read(1)
        raster_valid = src.read_masks(1) > 0

        transform = src.transform
        crs = src.crs
        nodata = src.nodata
        width = src.width
        height = src.height

    validate_metric_crs(crs)

    if nodata is not None:
        raster_valid &= mask_raster != nodata

    spray_mask = (
        raster_valid
        & (mask_raster == 1)
    )

    spray_pixel_count = np.count_nonzero(spray_mask)

    if spray_pixel_count == 0:
        raise ValueError(
            "No spray pixels were found. "
            "Spray zones must have a value of 1."
        )

    pixel_area_m2 = abs(
        transform.a * transform.e
        - transform.b * transform.d
    )

    raster_spray_area_m2 = (
        spray_pixel_count * pixel_area_m2
    )

    print("\nInput raster information")
    print("-" * 40)
    print(f"Path: {input_mask_path}")
    print(f"CRS: {crs}")
    print(f"Width: {width}")
    print(f"Height: {height}")
    print(f"NoData: {nodata}")
    print(f"Unique values: {np.unique(mask_raster)}")
    print(f"Spray pixels: {spray_pixel_count}")
    print(
        f"Raster spray area: "
        f"{raster_spray_area_m2:.2f} m²"
    )

    # Convert connected spray regions to polygons
    polygon_records = []

    for geometry, value in shapes(
        spray_mask.astype("uint8"),
        mask=spray_mask,
        transform=transform,
        connectivity=8,
    ):
        if value != 1:
            continue

        polygon = shape(geometry)

        if not polygon.is_empty:
            polygon_records.append(
                {
                    "geometry": polygon,
                    "raster_value": 1,
                }
            )

    if not polygon_records:
        raise ValueError(
            "No polygons were extracted from the spray mask."
        )

    gdf = gpd.GeoDataFrame(
        polygon_records,
        crs=crs,
    )

    print("\nRaw polygon extraction")
    print("-" * 40)
    print(f"Number of raw polygons: {len(gdf)}")

    # Repair and remove unsuitable geometries
    gdf = clean_polygon_geometries(gdf)

    if gdf.empty:
        raise ValueError(
            "No valid polygon geometries remain."
        )

    # Calculate and filter using physical area
    gdf["area_m2"] = gdf.geometry.area

    gdf = gdf[
        gdf["area_m2"] >= minimum_polygon_area_m2
    ].copy()

    if gdf.empty:
        raise ValueError(
            "All polygons were removed by the minimum "
            "polygon area setting."
        )

    polygons_after_area_filter = len(gdf)

    # Simplify polygon boundaries
    if simplification_tolerance_m > 0:
        gdf["geometry"] = gdf.geometry.simplify(
            tolerance=simplification_tolerance_m,
            preserve_topology=True,
        )

    gdf = clean_polygon_geometries(gdf)

    if gdf.empty:
        raise ValueError(
            "No polygons remain after simplification."
        )

    # Recalculate and apply the minimum area again
    gdf["area_m2"] = gdf.geometry.area

    gdf = gdf[
        gdf["area_m2"] >= minimum_polygon_area_m2
    ].copy()

    if gdf.empty:
        raise ValueError(
            "No polygons remain after final filtering."
        )

    gdf = gdf.reset_index(drop=True)
    gdf["polygon_id"] = gdf.index + 1

    gdf = gdf[
        [
            "polygon_id",
            "area_m2",
            "raster_value",
            "geometry",
        ]
    ]

    print("\nFiltered polygon results")
    print("-" * 40)
    print(
        f"Minimum polygon area: "
        f"{minimum_polygon_area_m2:.2f} m²"
    )
    print(
        f"Simplification tolerance: "
        f"{simplification_tolerance_m:.2f} m"
    )
    print(
        f"Polygons after initial area filter: "
        f"{polygons_after_area_filter}"
    )
    print(f"Number of final polygons: {len(gdf)}")
    print(
        f"Total spray polygon area: "
        f"{gdf['area_m2'].sum():.2f} m²"
    )

    print("\nPolygon area summary")
    print("-" * 40)
    print(
        f"Smallest polygon: "
        f"{gdf['area_m2'].min():.2f} m²"
    )
    print(
        f"Largest polygon: "
        f"{gdf['area_m2'].max():.2f} m²"
    )
    print(
        f"Mean polygon area: "
        f"{gdf['area_m2'].mean():.2f} m²"
    )

    # Save projected polygons
    gdf.to_file(
        output_paths["gpkg"],
        layer="spray_zones",
        driver="GPKG",
        index=False,
    )

    gdf.to_file(
        output_paths["geojson"],
        driver="GeoJSON",
        index=False,
    )

    print(
        f"\nSaved GeoPackage to: "
        f"{output_paths['gpkg']}"
    )

    print(
        f"Saved GeoJSON to: "
        f"{output_paths['geojson']}"
    )

    # Save polygon preview
    figure, axis = plt.subplots(figsize=(8, 8))

    gdf.plot(
        ax=axis,
        facecolor="red",
        edgecolor="black",
        linewidth=0.5,
        alpha=0.7,
    )

    axis.set_title("Extracted Spray Zone Polygons")
    axis.set_axis_off()

    figure.savefig(
        output_paths["preview"],
        dpi=300,
        bbox_inches="tight",
    )

    print(
        f"Saved polygon preview to: "
        f"{output_paths['preview']}"
    )

    if show_preview:
        plt.show()

    plt.close(figure)

    return output_paths


def main():
    """Allow the script to run independently."""

    parser = argparse.ArgumentParser(
        description=(
            "Extract spray polygons from a cleaned spray mask."
        )
    )

    parser.add_argument(
        "input_mask_path",
        help="Path to the cleaned spray mask",
    )

    parser.add_argument(
        "--output-vector-dir",
        default="outputs/polygons",
    )

    parser.add_argument(
        "--output-figure-dir",
        default="outputs/figures/polygons",
    )

    parser.add_argument(
        "--minimum-polygon-area-m2",
        type=float,
        default=5.0,
    )

    parser.add_argument(
        "--simplification-tolerance-m",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--show-preview",
        action="store_true",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
    )

    args = parser.parse_args()

    try:
        extract_spray_polygons(
            input_mask_path=args.input_mask_path,
            output_vector_dir=args.output_vector_dir,
            output_figure_dir=args.output_figure_dir,
            minimum_polygon_area_m2=(
                args.minimum_polygon_area_m2
            ),
            simplification_tolerance_m=(
                args.simplification_tolerance_m
            ),
            show_preview=args.show_preview,
            overwrite=args.overwrite,
        )

    except Exception as error:
        parser.exit(
            status=1,
            message=f"Error: {error}\n",
        )


if __name__ == "__main__":
    main()