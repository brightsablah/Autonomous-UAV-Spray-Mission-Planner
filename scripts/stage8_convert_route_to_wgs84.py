from pathlib import Path
import argparse

import geopandas as gpd

from shapely.geometry import Point


WGS84_CRS = "EPSG:4326"


def get_wgs84_output_paths(output_route_dir):
    """Create output paths for the WGS84 route."""

    output_route_dir = Path(output_route_dir)

    return {
        "gpkg": (
            output_route_dir
            / "connected_spray_route_wgs84.gpkg"
        ),
        "route_csv": (
            output_route_dir
            / "route_waypoints_wgs84.csv"
        ),
        "mission_csv": (
            output_route_dir
            / "mission_waypoints_wgs84.csv"
        ),
    }


def convert_to_boolean(value):
    """Convert common stored values to Boolean."""

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "1",
            "yes",
            "y",
        }

    return bool(value)


def create_mission_waypoints(
    route_segments_wgs84,
):
    """Create one continuous mission waypoint sequence."""

    route_segments_wgs84 = (
        route_segments_wgs84.sort_values(
            "segment_id"
        ).reset_index(drop=True)
    )

    if route_segments_wgs84.empty:
        raise ValueError(
            "No route segments are available."
        )

    mission_records = []
    mission_waypoint_id = 1

    # Add the start of the first segment
    first_segment = (
        route_segments_wgs84.iloc[0]
    )

    first_coordinates = list(
        first_segment.geometry.coords
    )

    first_start = Point(
        first_coordinates[0]
    )

    mission_records.append(
        {
            "mission_waypoint_id": (
                mission_waypoint_id
            ),
            "arrived_from_segment_id": None,
            "next_segment_id": int(
                first_segment["segment_id"]
            ),
            "visit_order": int(
                first_segment["visit_order"]
            ),
            "polygon_id": int(
                first_segment["polygon_id"]
            ),
            "segment_type_to_next": (
                first_segment["segment_type"]
            ),
            "spray_on_to_next": (
                convert_to_boolean(
                    first_segment["spray_on"]
                )
            ),
            "longitude": first_start.x,
            "latitude": first_start.y,
            "geometry": first_start,
        }
    )

    mission_waypoint_id += 1

    # Add the endpoint of each segment
    for segment_index, segment in (
        route_segments_wgs84.iterrows()
    ):
        coordinates = list(
            segment.geometry.coords
        )

        end_point = Point(
            coordinates[-1]
        )

        next_index = segment_index + 1

        if next_index < len(
            route_segments_wgs84
        ):
            next_segment = (
                route_segments_wgs84.iloc[
                    next_index
                ]
            )

            next_segment_id = int(
                next_segment["segment_id"]
            )

            segment_type_to_next = (
                next_segment["segment_type"]
            )

            spray_on_to_next = (
                convert_to_boolean(
                    next_segment["spray_on"]
                )
            )

        else:
            next_segment_id = None
            segment_type_to_next = "end"
            spray_on_to_next = False

        mission_records.append(
            {
                "mission_waypoint_id": (
                    mission_waypoint_id
                ),
                "arrived_from_segment_id": int(
                    segment["segment_id"]
                ),
                "next_segment_id": (
                    next_segment_id
                ),
                "visit_order": int(
                    segment["visit_order"]
                ),
                "polygon_id": int(
                    segment["polygon_id"]
                ),
                "segment_type_to_next": (
                    segment_type_to_next
                ),
                "spray_on_to_next": (
                    spray_on_to_next
                ),
                "longitude": end_point.x,
                "latitude": end_point.y,
                "geometry": end_point,
            }
        )

        mission_waypoint_id += 1

    return gpd.GeoDataFrame(
        mission_records,
        geometry="geometry",
        crs=WGS84_CRS,
    )


def convert_route_to_wgs84(
    input_route_path,
    output_route_dir,
    overwrite=False,
):
    """Convert connected route layers to WGS84."""

    input_route_path = Path(input_route_path)
    output_route_dir = Path(output_route_dir)

    if not input_route_path.is_file():
        raise FileNotFoundError(
            f"Connected route file not found: "
            f"{input_route_path}"
        )

    output_paths = get_wgs84_output_paths(
        output_route_dir
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

    if overwrite:
        for output_path in existing_outputs:
            output_path.unlink()

    route_segments = gpd.read_file(
        input_route_path,
        layer="route_segments",
    )

    route_waypoints = gpd.read_file(
        input_route_path,
        layer="route_waypoints",
    )

    if route_segments.empty:
        raise ValueError(
            "No route segments were found."
        )

    if route_waypoints.empty:
        raise ValueError(
            "No route waypoints were found."
        )

    if route_segments.crs is None:
        raise ValueError(
            "The route segments do not have a CRS."
        )

    if route_waypoints.crs is None:
        raise ValueError(
            "The route waypoints do not have a CRS."
        )

    if route_segments.crs != route_waypoints.crs:
        raise ValueError(
            "The route segments and waypoints "
            "have different CRS."
        )

    required_segment_columns = {
        "segment_id",
        "visit_order",
        "polygon_id",
        "segment_type",
        "spray_on",
    }

    missing_segment_columns = (
        required_segment_columns
        - set(route_segments.columns)
    )

    if missing_segment_columns:
        raise ValueError(
            "The route segments are missing columns: "
            + ", ".join(
                sorted(missing_segment_columns)
            )
        )

    required_waypoint_columns = {
        "waypoint_id",
        "segment_id",
        "visit_order",
        "polygon_id",
        "segment_type",
        "spray_on",
        "point_role",
    }

    missing_waypoint_columns = (
        required_waypoint_columns
        - set(route_waypoints.columns)
    )

    if missing_waypoint_columns:
        raise ValueError(
            "The route waypoints are missing columns: "
            + ", ".join(
                sorted(missing_waypoint_columns)
            )
        )

    print("\nInput route information")
    print("-" * 45)
    print(f"Input file: {input_route_path}")
    print(f"Input CRS: {route_segments.crs}")
    print(
        f"Route segments: "
        f"{len(route_segments)}"
    )
    print(
        f"Route waypoint rows: "
        f"{len(route_waypoints)}"
    )

    # Convert the route layers
    route_segments_wgs84 = (
        route_segments.to_crs(WGS84_CRS)
    )

    route_waypoints_wgs84 = (
        route_waypoints.to_crs(WGS84_CRS)
    )

    route_waypoints_wgs84[
        "longitude"
    ] = route_waypoints_wgs84.geometry.x

    route_waypoints_wgs84[
        "latitude"
    ] = route_waypoints_wgs84.geometry.y

    route_waypoints_wgs84 = (
        route_waypoints_wgs84[
            [
                "waypoint_id",
                "segment_id",
                "visit_order",
                "polygon_id",
                "segment_type",
                "spray_on",
                "point_role",
                "longitude",
                "latitude",
                "geometry",
            ]
        ]
    )

    mission_waypoints_wgs84 = (
        create_mission_waypoints(
            route_segments_wgs84
        )
    )

    minimum_longitude = (
        mission_waypoints_wgs84[
            "longitude"
        ].min()
    )

    maximum_longitude = (
        mission_waypoints_wgs84[
            "longitude"
        ].max()
    )

    minimum_latitude = (
        mission_waypoints_wgs84[
            "latitude"
        ].min()
    )

    maximum_latitude = (
        mission_waypoints_wgs84[
            "latitude"
        ].max()
    )

    print("\nWGS84 conversion results")
    print("-" * 45)
    print(f"Output CRS: {WGS84_CRS}")
    print(
        f"Route waypoint rows: "
        f"{len(route_waypoints_wgs84)}"
    )
    print(
        f"Mission waypoint rows: "
        f"{len(mission_waypoints_wgs84)}"
    )
    print(
        f"Longitude range: "
        f"{minimum_longitude:.8f} to "
        f"{maximum_longitude:.8f}"
    )
    print(
        f"Latitude range: "
        f"{minimum_latitude:.8f} to "
        f"{maximum_latitude:.8f}"
    )

    print("\nFirst five mission waypoints")
    print("-" * 45)

    print(
        mission_waypoints_wgs84[
            [
                "mission_waypoint_id",
                "next_segment_id",
                "segment_type_to_next",
                "spray_on_to_next",
                "longitude",
                "latitude",
            ]
        ].head()
    )

    route_segments_wgs84.to_file(
        output_paths["gpkg"],
        layer="route_segments_wgs84",
        driver="GPKG",
        index=False,
    )

    route_waypoints_wgs84.to_file(
        output_paths["gpkg"],
        layer="route_waypoints_wgs84",
        driver="GPKG",
        mode="a",
        index=False,
    )

    mission_waypoints_wgs84.to_file(
        output_paths["gpkg"],
        layer="mission_waypoints_wgs84",
        driver="GPKG",
        mode="a",
        index=False,
    )

    route_waypoints_wgs84.drop(
        columns=["geometry"]
    ).to_csv(
        output_paths["route_csv"],
        index=False,
        float_format="%.10f",
    )

    mission_waypoints_wgs84.drop(
        columns=["geometry"]
    ).to_csv(
        output_paths["mission_csv"],
        index=False,
        float_format="%.10f",
    )

    print(
        f"\nSaved WGS84 GeoPackage to: "
        f"{output_paths['gpkg']}"
    )

    print(
        f"Saved route waypoints CSV to: "
        f"{output_paths['route_csv']}"
    )

    print(
        f"Saved mission waypoints CSV to: "
        f"{output_paths['mission_csv']}"
    )

    return output_paths


def main():
    """Allow the script to run independently."""

    parser = argparse.ArgumentParser(
        description=(
            "Convert a connected spray route to WGS84."
        )
    )

    parser.add_argument(
        "input_route_path",
        help="Path to connected_spray_route.gpkg",
    )

    parser.add_argument(
        "--output-route-dir",
        default="outputs/routes",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
    )

    args = parser.parse_args()

    try:
        convert_route_to_wgs84(
            input_route_path=args.input_route_path,
            output_route_dir=args.output_route_dir,
            overwrite=args.overwrite,
        )

    except Exception as error:
        parser.exit(
            status=1,
            message=f"Error: {error}\n",
        )


if __name__ == "__main__":
    main()