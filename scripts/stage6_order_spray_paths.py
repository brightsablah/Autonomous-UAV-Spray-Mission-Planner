from pathlib import Path
import argparse

import geopandas as gpd
import matplotlib.pyplot as plt

from pyproj import Transformer
from shapely.geometry import LineString, Point


def get_ordered_path_output_paths(
    output_route_dir,
    output_figure_dir,
):
    """Create output paths for the ordered spray paths."""

    output_route_dir = Path(output_route_dir)
    output_figure_dir = Path(output_figure_dir)

    return {
        "gpkg": (
            output_route_dir
            / "ordered_spray_paths.gpkg"
        ),
        "csv": (
            output_route_dir
            / "spray_path_visit_order.csv"
        ),
        "preview": (
            output_figure_dir
            / "spray_path_order_preview.png"
        ),
    }


def validate_metric_crs(crs):
    """Confirm that path coordinates use metres."""

    if crs is None:
        raise ValueError(
            "The spray paths do not have a CRS."
        )

    if not crs.is_projected:
        raise ValueError(
            "The spray paths must use a projected CRS."
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
            "The spray path CRS must use metres."
        )


def reverse_line(line):
    """Reverse the travel direction of a LineString."""

    return LineString(
        list(line.coords)[::-1]
    )


def prepare_path_groups(lines_gdf):
    """Group the spray lines belonging to each polygon."""

    path_groups = {}

    for polygon_id, group in lines_gdf.groupby(
        "polygon_id"
    ):
        group = group.sort_values(
            "local_line_id"
        ).copy()

        first_line = group.iloc[0].geometry
        last_line = group.iloc[-1].geometry

        forward_start = Point(
            list(first_line.coords)[0]
        )

        forward_end = Point(
            list(last_line.coords)[-1]
        )

        path_groups[int(polygon_id)] = {
            "lines": group,
            "forward_start": forward_start,
            "forward_end": forward_end,
            "reverse_start": forward_end,
            "reverse_end": forward_start,
            "spray_length_m": (
                group.geometry.length.sum()
            ),
            "line_count": len(group),
        }

    return path_groups


def choose_nearest_path_group(
    path_groups,
    remaining_polygon_ids,
    current_point,
):
    """Select the closest path entry point."""

    best_choice = None

    for polygon_id in sorted(
        remaining_polygon_ids
    ):
        group = path_groups[polygon_id]

        direction_options = [
            (
                "forward",
                group["forward_start"],
                group["forward_end"],
            ),
            (
                "reverse",
                group["reverse_start"],
                group["reverse_end"],
            ),
        ]

        for (
            direction,
            entry_point,
            exit_point,
        ) in direction_options:
            distance = current_point.distance(
                entry_point
            )

            candidate = {
                "polygon_id": polygon_id,
                "direction": direction,
                "entry_point": entry_point,
                "exit_point": exit_point,
                "selection_distance_m": distance,
            }

            if best_choice is None:
                best_choice = candidate
                continue

            if (
                distance
                < best_choice["selection_distance_m"]
            ):
                best_choice = candidate

    return best_choice


def create_start_reference(
    lines_gdf,
    start_mode,
    takeoff_latitude=None,
    takeoff_longitude=None,
):
    """Create the point used to select the first path."""

    minx, miny, maxx, maxy = (
        lines_gdf.total_bounds
    )

    if start_mode == "south_west":
        return Point(minx, miny)

    if start_mode == "north_west":
        return Point(minx, maxy)

    if start_mode == "takeoff":
        if (
            takeoff_latitude is None
            or takeoff_longitude is None
        ):
            raise ValueError(
                "Takeoff latitude and longitude are required."
            )

        transformer = Transformer.from_crs(
            "EPSG:4326",
            lines_gdf.crs,
            always_xy=True,
        )

        takeoff_x, takeoff_y = transformer.transform(
            takeoff_longitude,
            takeoff_latitude,
        )

        print("\nTakeoff position")
        print("-" * 40)
        print(f"Latitude: {takeoff_latitude}")
        print(f"Longitude: {takeoff_longitude}")
        print(f"Projected X: {takeoff_x:.2f} m")
        print(f"Projected Y: {takeoff_y:.2f} m")

        return Point(takeoff_x, takeoff_y)

    return None


def order_path_groups(
    path_groups,
    start_mode,
    start_reference,
):
    """Order polygon path groups using nearest endpoints."""

    remaining = set(path_groups.keys())
    visits = []

    forced_first_polygon = None

    if start_mode == "first_id":
        forced_first_polygon = min(remaining)

    elif start_mode == "longest_path":
        forced_first_polygon = max(
            remaining,
            key=lambda polygon_id: (
                path_groups[polygon_id][
                    "spray_length_m"
                ]
            ),
        )

    current_point = start_reference
    cumulative_transition_m = 0.0

    while remaining:
        if (
            not visits
            and forced_first_polygon is not None
        ):
            group = path_groups[
                forced_first_polygon
            ]

            choice = {
                "polygon_id": forced_first_polygon,
                "direction": "forward",
                "entry_point": group[
                    "forward_start"
                ],
                "exit_point": group[
                    "forward_end"
                ],
                "selection_distance_m": 0.0,
            }

        else:
            choice = choose_nearest_path_group(
                path_groups=path_groups,
                remaining_polygon_ids=remaining,
                current_point=current_point,
            )

        polygon_id = choice["polygon_id"]

        # Southwest and northwest are only selection
        # references, not actual flight positions.
        if (
            not visits
            and start_mode
            in {"south_west", "north_west"}
        ):
            transition_distance_m = 0.0
        else:
            transition_distance_m = choice[
                "selection_distance_m"
            ]

        cumulative_transition_m += (
            transition_distance_m
        )

        group = path_groups[polygon_id]

        visits.append(
            {
                "visit_order": len(visits) + 1,
                "polygon_id": polygon_id,
                "direction": choice["direction"],
                "entry_point": choice["entry_point"],
                "exit_point": choice["exit_point"],
                "transition_distance_m": (
                    transition_distance_m
                ),
                "cumulative_transition_m": (
                    cumulative_transition_m
                ),
                "spray_length_m": group[
                    "spray_length_m"
                ],
                "line_count": group[
                    "line_count"
                ],
            }
        )

        remaining.remove(polygon_id)
        current_point = choice["exit_point"]

    return visits


def order_spray_paths(
    input_lines_path,
    output_route_dir,
    output_figure_dir,
    start_mode="south_west",
    takeoff_latitude=None,
    takeoff_longitude=None,
    show_preview=True,
    overwrite=False,
):
    """Order spray path groups using nearest endpoints."""

    input_lines_path = Path(input_lines_path)
    output_route_dir = Path(output_route_dir)
    output_figure_dir = Path(output_figure_dir)

    valid_start_modes = {
        "south_west",
        "north_west",
        "first_id",
        "longest_path",
        "takeoff",
    }

    if start_mode not in valid_start_modes:
        raise ValueError(
            f"Unknown start mode: {start_mode}"
        )

    if not input_lines_path.is_file():
        raise FileNotFoundError(
            f"Spray path file not found: {input_lines_path}"
        )

    output_paths = get_ordered_path_output_paths(
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

    lines_gdf = gpd.read_file(
        input_lines_path,
        layer="spray_lines",
    )

    if lines_gdf.empty:
        raise ValueError(
            "No spray lines were found."
        )

    validate_metric_crs(lines_gdf.crs)

    required_columns = {
        "polygon_id",
        "local_line_id",
    }

    missing_columns = (
        required_columns
        - set(lines_gdf.columns)
    )

    if missing_columns:
        raise ValueError(
            "The spray path file is missing columns: "
            + ", ".join(sorted(missing_columns))
        )

    lines_gdf = lines_gdf[
        lines_gdf.geometry.notna()
        & ~lines_gdf.geometry.is_empty
        & (
            lines_gdf.geometry.geom_type
            == "LineString"
        )
    ].copy()

    if lines_gdf.empty:
        raise ValueError(
            "No valid spray LineStrings were found."
        )

    lines_gdf["length_m"] = (
        lines_gdf.geometry.length
    )

    path_groups = prepare_path_groups(
        lines_gdf
    )

    start_reference = create_start_reference(
        lines_gdf=lines_gdf,
        start_mode=start_mode,
        takeoff_latitude=takeoff_latitude,
        takeoff_longitude=takeoff_longitude,
    )

    visits = order_path_groups(
        path_groups=path_groups,
        start_mode=start_mode,
        start_reference=start_reference,
    )

    ordered_line_records = []
    visit_records = []
    transition_records = []

    route_line_order = 1
    previous_exit = None

    # Only takeoff is a real first transition
    if start_mode == "takeoff":
        previous_exit = start_reference

    for visit in visits:
        polygon_id = visit["polygon_id"]
        direction = visit["direction"]

        group = path_groups[
            polygon_id
        ]["lines"].copy()

        if direction == "reverse":
            group = group.sort_values(
                "local_line_id",
                ascending=False,
            ).copy()

            group["geometry"] = (
                group.geometry.apply(
                    reverse_line
                )
            )

        else:
            group = group.sort_values(
                "local_line_id"
            ).copy()

        entry_point = visit["entry_point"]
        exit_point = visit["exit_point"]

        if previous_exit is not None:
            transition_distance = (
                previous_exit.distance(entry_point)
            )

            if transition_distance > 0:
                transition_records.append(
                    {
                        "from_visit": (
                            visit["visit_order"] - 1
                            if visit["visit_order"] > 1
                            else 0
                        ),
                        "to_visit": (
                            visit["visit_order"]
                        ),
                        "distance_m": (
                            transition_distance
                        ),
                        "geometry": LineString(
                            [
                                (
                                    previous_exit.x,
                                    previous_exit.y,
                                ),
                                (
                                    entry_point.x,
                                    entry_point.y,
                                ),
                            ]
                        ),
                    }
                )

        visit_records.append(
            {
                "visit_order": (
                    visit["visit_order"]
                ),
                "polygon_id": polygon_id,
                "direction": direction,
                "line_count": visit["line_count"],
                "spray_length_m": (
                    visit["spray_length_m"]
                ),
                "transition_distance_m": (
                    visit["transition_distance_m"]
                ),
                "cumulative_transition_m": (
                    visit["cumulative_transition_m"]
                ),
                "entry_x": entry_point.x,
                "entry_y": entry_point.y,
                "exit_x": exit_point.x,
                "exit_y": exit_point.y,
                "geometry": entry_point,
            }
        )

        for _, line_row in group.iterrows():
            record = line_row.drop(
                labels=["geometry"]
            ).to_dict()

            record.update(
                {
                    "route_line_order": (
                        route_line_order
                    ),
                    "polygon_visit_order": (
                        visit["visit_order"]
                    ),
                    "travel_direction": direction,
                    "geometry": line_row.geometry,
                }
            )

            ordered_line_records.append(record)
            route_line_order += 1

        previous_exit = exit_point

    ordered_lines_gdf = gpd.GeoDataFrame(
        ordered_line_records,
        geometry="geometry",
        crs=lines_gdf.crs,
    )

    visits_gdf = gpd.GeoDataFrame(
        visit_records,
        geometry="geometry",
        crs=lines_gdf.crs,
    )

    transition_gdf = None

    if transition_records:
        transition_gdf = gpd.GeoDataFrame(
            transition_records,
            geometry="geometry",
            crs=lines_gdf.crs,
        )

    total_spray_length = ordered_lines_gdf[
        "length_m"
    ].sum()

    total_transition_length = sum(
        visit["transition_distance_m"]
        for visit in visits
    )

    print("\nSpray path visit order")
    print("-" * 50)
    print(f"Start mode: {start_mode}")

    for visit in visits:
        print(
            f"Visit {visit['visit_order']}: "
            f"Polygon {visit['polygon_id']}, "
            f"Direction = {visit['direction']}, "
            f"Transition = "
            f"{visit['transition_distance_m']:.2f} m"
        )

    print("\nOrdering summary")
    print("-" * 50)
    print(f"Polygons ordered: {len(visits)}")
    print(
        f"Active spray length: "
        f"{total_spray_length:.2f} m"
    )
    print(
        f"Inter-polygon transition distance: "
        f"{total_transition_length:.2f} m"
    )

    ordered_lines_gdf.to_file(
        output_paths["gpkg"],
        layer="ordered_spray_lines",
        driver="GPKG",
        index=False,
    )

    visits_gdf.to_file(
        output_paths["gpkg"],
        layer="polygon_visits",
        driver="GPKG",
        mode="a",
        index=False,
    )

    if transition_gdf is not None:
        transition_gdf.to_file(
            output_paths["gpkg"],
            layer="polygon_transitions",
            driver="GPKG",
            mode="a",
            index=False,
        )

    visits_gdf.drop(
        columns=["geometry"]
    ).to_csv(
        output_paths["csv"],
        index=False,
    )

    print(
        f"\nSaved ordered spray paths to: "
        f"{output_paths['gpkg']}"
    )

    print(
        f"Saved visit order CSV to: "
        f"{output_paths['csv']}"
    )

    figure, axis = plt.subplots(
        figsize=(9, 9)
    )

    ordered_lines_gdf.plot(
        ax=axis,
        column="polygon_visit_order",
        cmap="viridis",
        linewidth=1.2,
        legend=True,
    )

    if transition_gdf is not None:
        transition_gdf.plot(
            ax=axis,
            color="black",
            linewidth=0.8,
            linestyle="--",
        )

    visits_gdf.plot(
        ax=axis,
        color="red",
        markersize=25,
    )

    for _, row in visits_gdf.iterrows():
        axis.annotate(
            text=str(int(row["visit_order"])),
            xy=(
                row.geometry.x,
                row.geometry.y,
            ),
            xytext=(3, 3),
            textcoords="offset points",
            fontsize=9,
        )

    if (
        start_mode == "takeoff"
        and start_reference is not None
    ):
        axis.scatter(
            start_reference.x,
            start_reference.y,
            marker="*",
            s=100,
            color="green",
            label="Takeoff",
        )

        axis.legend()

    axis.set_title(
        "Nearest Endpoint Spray Path Order"
    )

    axis.set_axis_off()

    figure.savefig(
        output_paths["preview"],
        dpi=300,
        bbox_inches="tight",
    )

    print(
        f"Saved route preview to: "
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
            "Order spray paths using nearest endpoints."
        )
    )

    parser.add_argument(
        "input_lines_path",
        help="Path to spray_path_lines.gpkg",
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
        "--start-mode",
        choices=[
            "south_west",
            "north_west",
            "first_id",
            "longest_path",
            "takeoff",
        ],
        default="south_west",
    )

    parser.add_argument(
        "--takeoff-latitude",
        type=float,
    )

    parser.add_argument(
        "--takeoff-longitude",
        type=float,
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
        order_spray_paths(
            input_lines_path=args.input_lines_path,
            output_route_dir=args.output_route_dir,
            output_figure_dir=args.output_figure_dir,
            start_mode=args.start_mode,
            takeoff_latitude=args.takeoff_latitude,
            takeoff_longitude=args.takeoff_longitude,
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