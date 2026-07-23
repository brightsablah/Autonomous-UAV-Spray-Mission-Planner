from pathlib import Path
import argparse

import geopandas as gpd
import matplotlib.pyplot as plt

from shapely.geometry import LineString, Point


def get_connected_route_output_paths(
    output_route_dir,
    output_figure_dir,
):
    """Create output paths for the connected route."""

    output_route_dir = Path(output_route_dir)
    output_figure_dir = Path(output_figure_dir)

    return {
        "gpkg": (
            output_route_dir
            / "connected_spray_route.gpkg"
        ),
        "csv": (
            output_route_dir
            / "connected_spray_route_segments.csv"
        ),
        "preview": (
            output_figure_dir
            / "connected_spray_route_preview.png"
        ),
    }


def validate_metric_crs(crs):
    """Confirm that route coordinates use metres."""

    if crs is None:
        raise ValueError(
            "The ordered spray paths do not have a CRS."
        )

    if not crs.is_projected:
        raise ValueError(
            "The ordered spray paths must use a projected CRS."
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
            "The ordered spray path CRS must use metres."
        )


def get_line_start(line):
    """Return the first point of a line."""

    return Point(
        list(line.coords)[0]
    )


def get_line_end(line):
    """Return the final point of a line."""

    return Point(
        list(line.coords)[-1]
    )


def make_connector_line(point_a, point_b):
    """Create a straight connector between two points."""

    return LineString(
        [
            (point_a.x, point_a.y),
            (point_b.x, point_b.y),
        ]
    )


def points_are_same(
    point_a,
    point_b,
    tolerance_m=1e-6,
):
    """Check whether two route points are effectively equal."""

    return (
        point_a.distance(point_b)
        <= tolerance_m
    )


def add_segment(
    segment_records,
    segment_id,
    polygon_id,
    visit_order,
    segment_type,
    line,
    source_line_id=None,
    from_polygon_id=None,
    to_polygon_id=None,
):
    """Add a spray, turn or transit segment."""

    segment_records.append(
        {
            "segment_id": segment_id,
            "visit_order": visit_order,
            "polygon_id": polygon_id,
            "from_polygon_id": from_polygon_id,
            "to_polygon_id": to_polygon_id,
            "source_line_id": source_line_id,
            "segment_type": segment_type,
            "spray_on": (
                segment_type == "spray"
            ),
            "length_m": line.length,
            "geometry": line,
        }
    )


def create_waypoints_from_segments(
    route_segments_gdf,
):
    """Create projected start and end waypoints."""

    waypoint_records = []
    waypoint_id = 1

    for _, segment in route_segments_gdf.iterrows():
        coordinates = list(
            segment.geometry.coords
        )

        start_point = Point(coordinates[0])
        end_point = Point(coordinates[-1])

        common_values = {
            "segment_id": segment["segment_id"],
            "visit_order": segment["visit_order"],
            "polygon_id": segment["polygon_id"],
            "segment_type": segment["segment_type"],
            "spray_on": segment["spray_on"],
        }

        waypoint_records.append(
            {
                "waypoint_id": waypoint_id,
                **common_values,
                "point_role": "start",
                "geometry": start_point,
            }
        )

        waypoint_id += 1

        waypoint_records.append(
            {
                "waypoint_id": waypoint_id,
                **common_values,
                "point_role": "end",
                "geometry": end_point,
            }
        )

        waypoint_id += 1

    return waypoint_records


def connect_ordered_spray_paths(
    input_ordered_path,
    output_route_dir,
    output_figure_dir,
    connection_tolerance_m=1e-6,
    show_preview=True,
    overwrite=False,
):
    """Connect ordered spray lines into one route."""

    input_ordered_path = Path(input_ordered_path)
    output_route_dir = Path(output_route_dir)
    output_figure_dir = Path(output_figure_dir)

    if not input_ordered_path.is_file():
        raise FileNotFoundError(
            f"Ordered spray path file not found: "
            f"{input_ordered_path}"
        )

    if connection_tolerance_m < 0:
        raise ValueError(
            "Connection tolerance cannot be negative."
        )

    output_paths = get_connected_route_output_paths(
        output_route_dir,
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

    output_route_dir.mkdir(
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

    ordered_lines_gdf = gpd.read_file(
        input_ordered_path,
        layer="ordered_spray_lines",
    )

    if ordered_lines_gdf.empty:
        raise ValueError(
            "No ordered spray lines were found."
        )

    validate_metric_crs(
        ordered_lines_gdf.crs
    )

    required_columns = {
        "route_line_order",
        "polygon_visit_order",
        "polygon_id",
    }

    missing_columns = (
        required_columns
        - set(ordered_lines_gdf.columns)
    )

    if missing_columns:
        raise ValueError(
            "The ordered path file is missing columns: "
            + ", ".join(sorted(missing_columns))
        )

    ordered_lines_gdf = ordered_lines_gdf[
        ordered_lines_gdf.geometry.notna()
        & ~ordered_lines_gdf.geometry.is_empty
        & (
            ordered_lines_gdf.geometry.geom_type
            == "LineString"
        )
    ].copy()

    if ordered_lines_gdf.empty:
        raise ValueError(
            "No valid ordered spray LineStrings were found."
        )

    if ordered_lines_gdf[
        "route_line_order"
    ].duplicated().any():
        raise ValueError(
            "Duplicate route line order values were found."
        )

    ordered_lines_gdf = (
        ordered_lines_gdf.sort_values(
            "route_line_order"
        ).copy()
    )

    segment_records = []
    segment_id = 1

    current_point = None
    current_polygon_id = None

    for _, spray_line_row in (
        ordered_lines_gdf.iterrows()
    ):
        polygon_id = int(
            spray_line_row["polygon_id"]
        )

        visit_order = int(
            spray_line_row[
                "polygon_visit_order"
            ]
        )

        spray_line = spray_line_row.geometry

        source_line_id = (
            spray_line_row["line_id"]
            if "line_id"
            in ordered_lines_gdf.columns
            else None
        )

        line_start = get_line_start(
            spray_line
        )

        line_end = get_line_end(
            spray_line
        )

        # Connect the previous endpoint to this line
        if (
            current_point is not None
            and not points_are_same(
                current_point,
                line_start,
                tolerance_m=connection_tolerance_m,
            )
        ):
            if current_polygon_id == polygon_id:
                connector_type = "turn"
            else:
                connector_type = "transit"

            connector_line = make_connector_line(
                current_point,
                line_start,
            )

            add_segment(
                segment_records=segment_records,
                segment_id=segment_id,
                polygon_id=polygon_id,
                visit_order=visit_order,
                segment_type=connector_type,
                line=connector_line,
                source_line_id=None,
                from_polygon_id=current_polygon_id,
                to_polygon_id=polygon_id,
            )

            segment_id += 1

        # Add the active spray line
        add_segment(
            segment_records=segment_records,
            segment_id=segment_id,
            polygon_id=polygon_id,
            visit_order=visit_order,
            segment_type="spray",
            line=spray_line,
            source_line_id=source_line_id,
            from_polygon_id=polygon_id,
            to_polygon_id=polygon_id,
        )

        segment_id += 1

        current_point = line_end
        current_polygon_id = polygon_id

    if not segment_records:
        raise ValueError(
            "No connected route segments were created."
        )

    route_segments_gdf = gpd.GeoDataFrame(
        segment_records,
        geometry="geometry",
        crs=ordered_lines_gdf.crs,
    )

    route_segments_gdf[
        "cumulative_distance_m"
    ] = route_segments_gdf[
        "length_m"
    ].cumsum()

    waypoint_records = (
        create_waypoints_from_segments(
            route_segments_gdf
        )
    )

    route_waypoints_gdf = gpd.GeoDataFrame(
        waypoint_records,
        geometry="geometry",
        crs=ordered_lines_gdf.crs,
    )

    total_distance = route_segments_gdf[
        "length_m"
    ].sum()

    spray_distance = route_segments_gdf[
        route_segments_gdf[
            "segment_type"
        ] == "spray"
    ]["length_m"].sum()

    transit_distance = route_segments_gdf[
        route_segments_gdf[
            "segment_type"
        ] == "transit"
    ]["length_m"].sum()

    turn_distance = route_segments_gdf[
        route_segments_gdf[
            "segment_type"
        ] == "turn"
    ]["length_m"].sum()

    spray_percentage = (
        spray_distance / total_distance * 100
        if total_distance > 0
        else 0
    )

    print("\nConnected route summary")
    print("-" * 45)
    print(
        f"Total route segments: "
        f"{len(route_segments_gdf)}"
    )
    print(
        f"Total route waypoints: "
        f"{len(route_waypoints_gdf)}"
    )
    print(
        f"Total route distance: "
        f"{total_distance:.2f} m"
    )
    print(
        f"Active spray distance: "
        f"{spray_distance:.2f} m"
    )
    print(
        f"Transit distance between polygons: "
        f"{transit_distance:.2f} m"
    )
    print(
        f"Turn distance inside polygons: "
        f"{turn_distance:.2f} m"
    )
    print(
        f"Spray proportion of route: "
        f"{spray_percentage:.2f}%"
    )

    route_segments_gdf.to_file(
        output_paths["gpkg"],
        layer="route_segments",
        driver="GPKG",
        index=False,
    )

    route_waypoints_gdf.to_file(
        output_paths["gpkg"],
        layer="route_waypoints",
        driver="GPKG",
        mode="a",
        index=False,
    )

    route_segments_gdf.drop(
        columns=["geometry"]
    ).to_csv(
        output_paths["csv"],
        index=False,
    )

    print(
        f"\nSaved connected route to: "
        f"{output_paths['gpkg']}"
    )

    print(
        f"Saved route segment CSV to: "
        f"{output_paths['csv']}"
    )

    figure, axis = plt.subplots(
        figsize=(9, 9)
    )

    spray_segments = route_segments_gdf[
        route_segments_gdf[
            "segment_type"
        ] == "spray"
    ]

    turn_segments = route_segments_gdf[
        route_segments_gdf[
            "segment_type"
        ] == "turn"
    ]

    transit_segments = route_segments_gdf[
        route_segments_gdf[
            "segment_type"
        ] == "transit"
    ]

    if not spray_segments.empty:
        spray_segments.plot(
            ax=axis,
            color="red",
            linewidth=1.2,
            label="Spray segments",
        )

    if not turn_segments.empty:
        turn_segments.plot(
            ax=axis,
            color="orange",
            linewidth=0.8,
            linestyle="dotted",
            label="Turn segments",
        )

    if not transit_segments.empty:
        transit_segments.plot(
            ax=axis,
            color="black",
            linewidth=1.0,
            linestyle="dashed",
            label="Transit segments",
        )

    route_waypoints_gdf.plot(
        ax=axis,
        color="blue",
        markersize=4,
    )

    axis.set_title("Connected Spray Route")
    axis.set_axis_off()
    axis.legend(loc="best")

    figure.savefig(
        output_paths["preview"],
        dpi=300,
        bbox_inches="tight",
    )

    print(
        f"Saved connected route preview to: "
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
            "Connect ordered spray paths into one route."
        )
    )

    parser.add_argument(
        "input_ordered_path",
        help="Path to ordered_spray_paths.gpkg",
    )

    parser.add_argument(
        "--output-route-dir",
        default="outputs/routes",
    )

    parser.add_argument(
        "--output-figure-dir",
        default="outputs/figures/routes",
    )

    parser.add_argument(
        "--connection-tolerance-m",
        type=float,
        default=1e-6,
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
        connect_ordered_spray_paths(
            input_ordered_path=args.input_ordered_path,
            output_route_dir=args.output_route_dir,
            output_figure_dir=args.output_figure_dir,
            connection_tolerance_m=(
                args.connection_tolerance_m
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