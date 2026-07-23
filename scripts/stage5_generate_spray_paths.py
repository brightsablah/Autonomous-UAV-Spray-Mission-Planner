from pathlib import Path
import argparse
import math

import geopandas as gpd
import matplotlib.pyplot as plt

from shapely.affinity import rotate
from shapely.geometry import (
    LineString,
    MultiLineString,
    GeometryCollection,
    Point,
)


def get_spray_path_output_paths(
    output_path_dir,
    output_figure_dir,
):
    """Create output paths for spray lines and waypoints."""

    output_path_dir = Path(output_path_dir)
    output_figure_dir = Path(output_figure_dir)

    output_paths = {
        "lines": (
            output_path_dir
            / "spray_path_lines.gpkg"
        ),
        "waypoints": (
            output_path_dir
            / "spray_path_waypoints.gpkg"
        ),
        "preview": (
            output_figure_dir
            / "spray_path_preview.png"
        ),
    }

    return output_paths


def validate_metric_crs(crs):
    """Confirm that polygon coordinates use metres."""

    if crs is None:
        raise ValueError(
            "The input polygons do not have a CRS."
        )

    if not crs.is_projected:
        raise ValueError(
            "The input polygons must use a projected CRS."
        )

    metre_units = {
        "metre",
        "meter",
        "metres",
        "meters",
    }

    axis_units = [
        axis.unit_name.lower()
        for axis in crs.axis_info[:2]
        if axis.unit_name
    ]

    if (
        len(axis_units) < 2
        or not all(
            unit in metre_units
            for unit in axis_units
        )
    ):
        raise ValueError(
            "The polygon CRS must use metres."
        )


def extract_lines(geometry):
    """Extract LineStrings from intersection results."""

    if geometry.is_empty:
        return []

    if isinstance(geometry, LineString):
        return [geometry]

    if isinstance(geometry, MultiLineString):
        return list(geometry.geoms)

    if isinstance(geometry, GeometryCollection):
        lines = []

        for part in geometry.geoms:
            lines.extend(extract_lines(part))

        return lines

    return []


def orient_line(line, left_to_right):
    """Orient a line in the required travel direction."""

    coordinates = list(line.coords)

    # First arrange the line from left to right
    if coordinates[0][0] > coordinates[-1][0]:
        coordinates.reverse()

    # Reverse it when the pass travels right to left
    if not left_to_right:
        coordinates.reverse()

    return LineString(coordinates)


def generate_lawnmower_lines_for_polygon(
    polygon,
    spacing_m,
    angle_deg,
    minimum_length_m,
):
    """Generate ordered parallel spray lines inside a polygon."""

    centroid = polygon.centroid

    rotated_polygon = rotate(
        polygon,
        -angle_deg,
        origin=centroid,
        use_radians=False,
    )

    minx, miny, maxx, maxy = rotated_polygon.bounds

    polygon_height = maxy - miny

    if polygon_height <= 0:
        return []

    # Centre the passes within the polygon bounds
    number_of_passes = max(
        1,
        math.ceil(polygon_height / spacing_m),
    )

    occupied_height = (
        number_of_passes - 1
    ) * spacing_m

    first_y = miny + (
        polygon_height - occupied_height
    ) / 2

    margin = spacing_m * 2

    line_start_x = minx - margin
    line_end_x = maxx + margin

    path_records = []

    for pass_index in range(number_of_passes):
        y_position = first_y + (
            pass_index * spacing_m
        )

        base_line = LineString(
            [
                (line_start_x, y_position),
                (line_end_x, y_position),
            ]
        )

        clipped_geometry = base_line.intersection(
            rotated_polygon
        )

        clipped_lines = [
            line
            for line in extract_lines(clipped_geometry)
            if line.length >= minimum_length_m
        ]

        left_to_right = pass_index % 2 == 0

        # Correct ordering when one pass contains multiple segments
        clipped_lines = sorted(
            clipped_lines,
            key=lambda line: line.centroid.x,
            reverse=not left_to_right,
        )

        for segment_index, clipped_line in enumerate(
            clipped_lines,
            start=1,
        ):
            oriented_line = orient_line(
                clipped_line,
                left_to_right=left_to_right,
            )

            final_line = rotate(
                oriented_line,
                angle_deg,
                origin=centroid,
                use_radians=False,
            )

            path_records.append(
                {
                    "pass_id": pass_index + 1,
                    "segment_id": segment_index,
                    "geometry": final_line,
                }
            )

    return path_records


def generate_spray_paths(
    input_polygon_path,
    output_path_dir,
    output_figure_dir,
    spray_width_m=2.0,
    overlap_percent=20.0,
    path_angle_deg=0.0,
    minimum_line_length_m=1.0,
    show_preview=True,
    overwrite=False,
):
    """Generate spray paths and waypoints inside polygons."""

    input_polygon_path = Path(input_polygon_path)
    output_path_dir = Path(output_path_dir)
    output_figure_dir = Path(output_figure_dir)

    if not input_polygon_path.is_file():
        raise FileNotFoundError(
            f"Polygon file not found: {input_polygon_path}"
        )

    if spray_width_m <= 0:
        raise ValueError(
            "Spray width must be greater than zero."
        )

    if not 0 <= overlap_percent < 100:
        raise ValueError(
            "Overlap percentage must be from 0 to below 100."
        )

    if not 0 <= path_angle_deg < 180:
        raise ValueError(
            "Path angle must be from 0 to below 180 degrees."
        )

    if minimum_line_length_m < 0:
        raise ValueError(
            "Minimum line length cannot be negative."
        )

    line_spacing_m = spray_width_m * (
        1 - overlap_percent / 100
    )

    if line_spacing_m <= 0:
        raise ValueError(
            "The calculated line spacing must be positive."
        )

    output_paths = get_spray_path_output_paths(
        output_path_dir,
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

    output_path_dir.mkdir(
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

    polygons_gdf = gpd.read_file(
        input_polygon_path
    )

    if polygons_gdf.empty:
        raise ValueError(
            "No polygons were found in the input file."
        )

    validate_metric_crs(polygons_gdf.crs)

    polygons_gdf = polygons_gdf[
        polygons_gdf.geometry.notna()
        & ~polygons_gdf.geometry.is_empty
    ].copy()

    polygons_gdf = polygons_gdf[
        polygons_gdf.geometry.geom_type.isin(
            ["Polygon", "MultiPolygon"]
        )
    ].copy()

    if polygons_gdf.empty:
        raise ValueError(
            "The input does not contain valid polygons."
        )

    if "polygon_id" not in polygons_gdf.columns:
        polygons_gdf = polygons_gdf.reset_index(
            drop=True
        )

        polygons_gdf["polygon_id"] = (
            polygons_gdf.index + 1
        )

    print("\nInput polygon information")
    print("-" * 40)
    print(f"Input file: {input_polygon_path}")
    print(f"CRS: {polygons_gdf.crs}")
    print(f"Number of polygons: {len(polygons_gdf)}")
    print(
        f"Total polygon area: "
        f"{polygons_gdf.geometry.area.sum():.2f} m²"
    )

    line_records = []
    waypoint_records = []

    global_line_id = 1
    global_waypoint_id = 1

    for _, polygon_row in polygons_gdf.iterrows():
        polygon_id = int(polygon_row["polygon_id"])
        polygon = polygon_row.geometry

        generated_records = (
            generate_lawnmower_lines_for_polygon(
                polygon=polygon,
                spacing_m=line_spacing_m,
                angle_deg=path_angle_deg,
                minimum_length_m=minimum_line_length_m,
            )
        )

        print(
            f"Polygon {polygon_id}: generated "
            f"{len(generated_records)} spray lines"
        )

        for local_line_id, record in enumerate(
            generated_records,
            start=1,
        ):
            line = record["geometry"]
            pass_id = record["pass_id"]
            segment_id = record["segment_id"]

            line_records.append(
                {
                    "line_id": global_line_id,
                    "polygon_id": polygon_id,
                    "local_line_id": local_line_id,
                    "pass_id": pass_id,
                    "segment_id": segment_id,
                    "length_m": line.length,
                    "geometry": line,
                }
            )

            coordinates = list(line.coords)

            start_point = Point(coordinates[0])
            end_point = Point(coordinates[-1])

            waypoint_records.append(
                {
                    "waypoint_id": global_waypoint_id,
                    "line_id": global_line_id,
                    "polygon_id": polygon_id,
                    "local_line_id": local_line_id,
                    "point_type": "start",
                    "geometry": start_point,
                }
            )

            global_waypoint_id += 1

            waypoint_records.append(
                {
                    "waypoint_id": global_waypoint_id,
                    "line_id": global_line_id,
                    "polygon_id": polygon_id,
                    "local_line_id": local_line_id,
                    "point_type": "end",
                    "geometry": end_point,
                }
            )

            global_waypoint_id += 1
            global_line_id += 1

    if not line_records:
        raise ValueError(
            "No spray lines were generated. "
            "Check the polygon sizes and path parameters."
        )

    lines_gdf = gpd.GeoDataFrame(
        line_records,
        geometry="geometry",
        crs=polygons_gdf.crs,
    )

    waypoints_gdf = gpd.GeoDataFrame(
        waypoint_records,
        geometry="geometry",
        crs=polygons_gdf.crs,
    )

    total_path_length = lines_gdf[
        "length_m"
    ].sum()

    print("\nSpray path generation results")
    print("-" * 40)
    print(f"Spray width: {spray_width_m:.2f} m")
    print(f"Overlap: {overlap_percent:.2f}%")
    print(f"Line spacing: {line_spacing_m:.2f} m")
    print(f"Path angle: {path_angle_deg:.1f} degrees")
    print(
        f"Minimum line length: "
        f"{minimum_line_length_m:.2f} m"
    )
    print(f"Number of spray lines: {len(lines_gdf)}")
    print(
        f"Number of line endpoints: "
        f"{len(waypoints_gdf)}"
    )
    print(
        f"Total active spray line length: "
        f"{total_path_length:.2f} m"
    )

    lines_gdf.to_file(
        output_paths["lines"],
        layer="spray_lines",
        driver="GPKG",
        index=False,
    )

    waypoints_gdf.to_file(
        output_paths["waypoints"],
        layer="spray_waypoints",
        driver="GPKG",
        index=False,
    )

    print(
        f"\nSaved spray lines to: "
        f"{output_paths['lines']}"
    )

    print(
        f"Saved spray waypoints to: "
        f"{output_paths['waypoints']}"
    )

    figure, axis = plt.subplots(figsize=(8, 8))

    polygons_gdf.plot(
        ax=axis,
        facecolor="lightgray",
        edgecolor="black",
        linewidth=0.5,
    )

    lines_gdf.plot(
        ax=axis,
        color="blue",
        linewidth=1.0,
    )

    waypoints_gdf.plot(
        ax=axis,
        color="red",
        markersize=5,
    )

    axis.set_title("Generated Spray Paths")
    axis.set_axis_off()

    figure.savefig(
        output_paths["preview"],
        dpi=300,
        bbox_inches="tight",
    )

    print(
        f"Saved spray path preview to: "
        f"{output_paths['preview']}"
    )

    if show_preview:
        plt.show()

    plt.close(figure)

    return output_paths


def main():
    """Allow the script to run independently."""

    parser = argparse.ArgumentParser(
        description="Generate spray paths inside polygons."
    )

    parser.add_argument(
        "input_polygon_path",
        help="Path to the spray polygon file",
    )

    parser.add_argument(
        "--output-path-dir",
        default="outputs/paths",
    )

    parser.add_argument(
        "--output-figure-dir",
        default="outputs/figures/paths",
    )

    parser.add_argument(
        "--spray-width-m",
        type=float,
        default=2.0,
    )

    parser.add_argument(
        "--overlap-percent",
        type=float,
        default=20.0,
    )

    parser.add_argument(
        "--path-angle-deg",
        type=float,
        default=0.0,
    )

    parser.add_argument(
        "--minimum-line-length-m",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--no-preview",
        action="store_true",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
    )

    args = parser.parse_args()

    try:
        generate_spray_paths(
            input_polygon_path=args.input_polygon_path,
            output_path_dir=args.output_path_dir,
            output_figure_dir=args.output_figure_dir,
            spray_width_m=args.spray_width_m,
            overlap_percent=args.overlap_percent,
            path_angle_deg=args.path_angle_deg,
            minimum_line_length_m=(
                args.minimum_line_length_m
            ),
            show_preview=not args.no_preview,
            overwrite=args.overwrite,
        )

    except Exception as error:
        parser.exit(
            status=1,
            message=f"Error: {error}\n",
        )


if __name__ == "__main__":
    main()