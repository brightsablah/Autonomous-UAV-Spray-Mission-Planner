from pathlib import Path
import argparse
import json
import math

import pandas as pd


# QGroundControl vehicle settings
FIRMWARE_TYPE_PX4 = 12
VEHICLE_TYPE_MULTIROTOR = 2

# MAVLink command IDs
MAV_CMD_NAV_WAYPOINT = 16
MAV_CMD_NAV_RETURN_TO_LAUNCH = 20
MAV_CMD_NAV_LAND = 21
MAV_CMD_NAV_TAKEOFF = 22
MAV_CMD_DO_CHANGE_SPEED = 178
MAV_CMD_DO_SET_RELAY = 181

# MAVLink frames
MAV_FRAME_MISSION = 2
MAV_FRAME_GLOBAL_RELATIVE_ALT = 3

# MAV_CMD_DO_CHANGE_SPEED parameter
SPEED_TYPE_GROUNDSPEED = 1


def get_qgc_output_paths(output_mission_dir):
    """Create output paths for the QGC mission."""

    output_mission_dir = Path(
        output_mission_dir
    )

    return {
        "plan": (
            output_mission_dir
            / "spray_mission.plan"
        ),
        "summary": (
            output_mission_dir
            / "qgc_mission_items_summary.csv"
        ),
    }


def to_bool(value):
    """Convert common CSV values to Boolean."""

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        return value.strip().lower() in {
            "true",
            "1",
            "yes",
            "y",
        }

    return False


def coordinates_are_same(
    latitude_a,
    longitude_a,
    latitude_b,
    longitude_b,
    tolerance=1e-9,
):
    """Compare two WGS84 positions."""

    return (
        abs(latitude_a - latitude_b)
        <= tolerance
        and abs(longitude_a - longitude_b)
        <= tolerance
    )


def make_simple_item(
    command,
    frame,
    params,
    do_jump_id,
    altitude=0,
    auto_continue=True,
):
    """Create one QGroundControl SimpleItem."""

    return {
        "AMSLAltAboveTerrain": None,
        "Altitude": altitude,
        "AltitudeMode": 1,
        "autoContinue": auto_continue,
        "command": command,
        "doJumpId": do_jump_id,
        "frame": frame,
        "params": params,
        "type": "SimpleItem",
    }


def make_takeoff_item(
    latitude,
    longitude,
    altitude,
    do_jump_id,
):
    """Create a takeoff command."""

    return make_simple_item(
        command=MAV_CMD_NAV_TAKEOFF,
        frame=MAV_FRAME_GLOBAL_RELATIVE_ALT,
        params=[
            0,
            0,
            0,
            None,
            latitude,
            longitude,
            altitude,
        ],
        do_jump_id=do_jump_id,
        altitude=altitude,
    )


def make_waypoint_item(
    latitude,
    longitude,
    altitude,
    acceptance_radius_m,
    do_jump_id,
):
    """Create a navigation waypoint."""

    return make_simple_item(
        command=MAV_CMD_NAV_WAYPOINT,
        frame=MAV_FRAME_GLOBAL_RELATIVE_ALT,
        params=[
            0,
            acceptance_radius_m,
            0,
            None,
            latitude,
            longitude,
            altitude,
        ],
        do_jump_id=do_jump_id,
        altitude=altitude,
    )


def make_speed_item(
    speed_mps,
    do_jump_id,
):
    """Create a groundspeed change command."""

    return make_simple_item(
        command=MAV_CMD_DO_CHANGE_SPEED,
        frame=MAV_FRAME_MISSION,
        params=[
            SPEED_TYPE_GROUNDSPEED,
            speed_mps,
            -1,
            0,
            0,
            0,
            0,
        ],
        do_jump_id=do_jump_id,
    )


def make_relay_item(
    relay_index,
    relay_value,
    do_jump_id,
):
    """Create a sprayer relay command."""

    return make_simple_item(
        command=MAV_CMD_DO_SET_RELAY,
        frame=MAV_FRAME_MISSION,
        params=[
            relay_index,
            relay_value,
            0,
            0,
            0,
            0,
            0,
        ],
        do_jump_id=do_jump_id,
    )


def make_return_to_launch_item(do_jump_id):
    """Create a return to launch command."""

    return make_simple_item(
        command=MAV_CMD_NAV_RETURN_TO_LAUNCH,
        frame=MAV_FRAME_MISSION,
        params=[
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ],
        do_jump_id=do_jump_id,
    )


def make_land_item(
    latitude,
    longitude,
    do_jump_id,
):
    """Create a landing command."""

    return make_simple_item(
        command=MAV_CMD_NAV_LAND,
        frame=MAV_FRAME_GLOBAL_RELATIVE_ALT,
        params=[
            0,
            0,
            0,
            None,
            latitude,
            longitude,
            0,
        ],
        do_jump_id=do_jump_id,
    )


def export_qgroundcontrol_plan(
    input_waypoints_csv,
    output_mission_dir,
    flight_altitude_m=10.0,
    transit_speed_mps=5.0,
    spray_speed_mps=2.0,
    acceptance_radius_m=1.0,
    home_latitude=None,
    home_longitude=None,
    home_altitude_amsl_m=0.0,
    include_speed_commands=True,
    include_spray_relay_commands=False,
    sprayer_relay_index=0,
    sprayer_on_value=1,
    sprayer_off_value=0,
    end_action="rtl",
    overwrite=False,
):
    """Export WGS84 mission waypoints to a QGC Plan file."""

    input_waypoints_csv = Path(
        input_waypoints_csv
    )

    output_mission_dir = Path(
        output_mission_dir
    )

    if not input_waypoints_csv.is_file():
        raise FileNotFoundError(
            f"Mission waypoint CSV not found: "
            f"{input_waypoints_csv}"
        )

    if flight_altitude_m <= 0:
        raise ValueError(
            "Flight altitude must be greater than zero."
        )

    if transit_speed_mps <= 0:
        raise ValueError(
            "Transit speed must be greater than zero."
        )

    if spray_speed_mps <= 0:
        raise ValueError(
            "Spray speed must be greater than zero."
        )

    if acceptance_radius_m < 0:
        raise ValueError(
            "Acceptance radius cannot be negative."
        )

    if sprayer_relay_index < 0:
        raise ValueError(
            "Relay index cannot be negative."
        )

    if end_action not in {"rtl", "land", "none"}:
        raise ValueError(
            "End action must be rtl, land or none."
        )

    output_paths = get_qgc_output_paths(
        output_mission_dir
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

    output_mission_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    waypoints_df = pd.read_csv(
        input_waypoints_csv
    )

    required_columns = {
        "mission_waypoint_id",
        "longitude",
        "latitude",
        "spray_on_to_next",
        "segment_type_to_next",
    }

    missing_columns = (
        required_columns
        - set(waypoints_df.columns)
    )

    if missing_columns:
        raise ValueError(
            "Mission waypoint CSV is missing columns: "
            + ", ".join(sorted(missing_columns))
        )

    waypoints_df = waypoints_df.sort_values(
        "mission_waypoint_id"
    ).reset_index(drop=True)

    if len(waypoints_df) < 2:
        raise ValueError(
            "At least two mission waypoints are required."
        )

    if waypoints_df[
        "mission_waypoint_id"
    ].duplicated().any():
        raise ValueError(
            "Duplicate mission waypoint IDs were found."
        )

    if waypoints_df[
        ["longitude", "latitude"]
    ].isna().any().any():
        raise ValueError(
            "Some mission coordinates are missing."
        )

    if not waypoints_df[
        "latitude"
    ].between(-90, 90).all():
        raise ValueError(
            "Some latitude values are invalid."
        )

    if not waypoints_df[
        "longitude"
    ].between(-180, 180).all():
        raise ValueError(
            "Some longitude values are invalid."
        )

    first_latitude = float(
        waypoints_df.loc[0, "latitude"]
    )

    first_longitude = float(
        waypoints_df.loc[0, "longitude"]
    )

    last_latitude = float(
        waypoints_df.loc[
            len(waypoints_df) - 1,
            "latitude",
        ]
    )

    last_longitude = float(
        waypoints_df.loc[
            len(waypoints_df) - 1,
            "longitude",
        ]
    )

    # Default home to the first route point
    if home_latitude is None:
        home_latitude = first_latitude

    if home_longitude is None:
        home_longitude = first_longitude

    if not -90 <= home_latitude <= 90:
        raise ValueError(
            "The home latitude is invalid."
        )

    if not -180 <= home_longitude <= 180:
        raise ValueError(
            "The home longitude is invalid."
        )

    if not math.isfinite(
        home_altitude_amsl_m
    ):
        raise ValueError(
            "The home AMSL altitude must be finite."
        )

    print("\nMission export settings")
    print("-" * 45)
    print(f"Input CSV: {input_waypoints_csv}")
    print(f"Route waypoints: {len(waypoints_df)}")
    print(f"Flight altitude: {flight_altitude_m:.2f} m")
    print(f"Transit speed: {transit_speed_mps:.2f} m/s")
    print(f"Spray speed: {spray_speed_mps:.2f} m/s")
    print(
        f"Acceptance radius: "
        f"{acceptance_radius_m:.2f} m"
    )
    print(f"Home latitude: {home_latitude}")
    print(f"Home longitude: {home_longitude}")
    print(
        f"Home AMSL altitude: "
        f"{home_altitude_amsl_m:.2f} m"
    )
    print(f"End action: {end_action}")
    print(
        f"Speed commands: "
        f"{include_speed_commands}"
    )
    print(
        f"Spray relay commands: "
        f"{include_spray_relay_commands}"
    )

    mission_items = []
    mission_summary_records = []

    do_jump_id = 1

    planned_home_position = [
        home_latitude,
        home_longitude,
        home_altitude_amsl_m,
    ]

    # Take off from the planned home location
    mission_items.append(
        make_takeoff_item(
            latitude=home_latitude,
            longitude=home_longitude,
            altitude=flight_altitude_m,
            do_jump_id=do_jump_id,
        )
    )

    mission_summary_records.append(
        {
            "do_jump_id": do_jump_id,
            "command": MAV_CMD_NAV_TAKEOFF,
            "command_name": "TAKEOFF",
            "latitude": home_latitude,
            "longitude": home_longitude,
            "altitude_m": flight_altitude_m,
            "speed_mps": transit_speed_mps,
            "spray_on": False,
        }
    )

    do_jump_id += 1

    current_spray_state = False
    current_speed_mps = transit_speed_mps

    home_is_route_start = coordinates_are_same(
        home_latitude,
        home_longitude,
        first_latitude,
        first_longitude,
    )

    # If home differs from the first route point,
    # navigate to the beginning of the route.
    if not home_is_route_start:
        mission_items.append(
            make_waypoint_item(
                latitude=first_latitude,
                longitude=first_longitude,
                altitude=flight_altitude_m,
                acceptance_radius_m=(
                    acceptance_radius_m
                ),
                do_jump_id=do_jump_id,
            )
        )

        mission_summary_records.append(
            {
                "do_jump_id": do_jump_id,
                "command": MAV_CMD_NAV_WAYPOINT,
                "command_name": (
                    "TRANSIT_TO_ROUTE_START"
                ),
                "latitude": first_latitude,
                "longitude": first_longitude,
                "altitude_m": flight_altitude_m,
                "speed_mps": transit_speed_mps,
                "spray_on": False,
            }
        )

        do_jump_id += 1

    # Row i describes the route segment from
    # waypoint i to waypoint i + 1.
    for waypoint_index in range(
        len(waypoints_df) - 1
    ):
        current_row = waypoints_df.loc[
            waypoint_index
        ]

        next_row = waypoints_df.loc[
            waypoint_index + 1
        ]

        next_latitude = float(
            next_row["latitude"]
        )

        next_longitude = float(
            next_row["longitude"]
        )

        spray_on_for_leg = to_bool(
            current_row["spray_on_to_next"]
        )

        segment_type = str(
            current_row["segment_type_to_next"]
        )

        desired_speed_mps = (
            spray_speed_mps
            if spray_on_for_leg
            else transit_speed_mps
        )

        # Change speed before starting the leg
        if (
            include_speed_commands
            and not math.isclose(
                current_speed_mps,
                desired_speed_mps,
                rel_tol=0,
                abs_tol=1e-6,
            )
        ):
            mission_items.append(
                make_speed_item(
                    speed_mps=desired_speed_mps,
                    do_jump_id=do_jump_id,
                )
            )

            mission_summary_records.append(
                {
                    "do_jump_id": do_jump_id,
                    "command": (
                        MAV_CMD_DO_CHANGE_SPEED
                    ),
                    "command_name": (
                        "SET_SPRAY_SPEED"
                        if spray_on_for_leg
                        else "SET_TRANSIT_SPEED"
                    ),
                    "latitude": None,
                    "longitude": None,
                    "altitude_m": None,
                    "speed_mps": desired_speed_mps,
                    "spray_on": spray_on_for_leg,
                }
            )

            do_jump_id += 1
            current_speed_mps = desired_speed_mps

        # Change sprayer state before starting the leg
        if (
            include_spray_relay_commands
            and spray_on_for_leg
            != current_spray_state
        ):
            relay_value = (
                sprayer_on_value
                if spray_on_for_leg
                else sprayer_off_value
            )

            mission_items.append(
                make_relay_item(
                    relay_index=sprayer_relay_index,
                    relay_value=relay_value,
                    do_jump_id=do_jump_id,
                )
            )

            mission_summary_records.append(
                {
                    "do_jump_id": do_jump_id,
                    "command": (
                        MAV_CMD_DO_SET_RELAY
                    ),
                    "command_name": (
                        "SPRAYER_ON"
                        if spray_on_for_leg
                        else "SPRAYER_OFF"
                    ),
                    "latitude": None,
                    "longitude": None,
                    "altitude_m": None,
                    "speed_mps": current_speed_mps,
                    "spray_on": spray_on_for_leg,
                }
            )

            do_jump_id += 1

        current_spray_state = spray_on_for_leg

        # Navigate to the end of the current leg
        mission_items.append(
            make_waypoint_item(
                latitude=next_latitude,
                longitude=next_longitude,
                altitude=flight_altitude_m,
                acceptance_radius_m=(
                    acceptance_radius_m
                ),
                do_jump_id=do_jump_id,
            )
        )

        mission_summary_records.append(
            {
                "do_jump_id": do_jump_id,
                "command": MAV_CMD_NAV_WAYPOINT,
                "command_name": (
                    f"WAYPOINT_{segment_type.upper()}"
                ),
                "latitude": next_latitude,
                "longitude": next_longitude,
                "altitude_m": flight_altitude_m,
                "speed_mps": desired_speed_mps,
                "spray_on": spray_on_for_leg,
            }
        )

        do_jump_id += 1

    # Ensure sprayer is off at mission end
    if (
        include_spray_relay_commands
        and current_spray_state
    ):
        mission_items.append(
            make_relay_item(
                relay_index=sprayer_relay_index,
                relay_value=sprayer_off_value,
                do_jump_id=do_jump_id,
            )
        )

        mission_summary_records.append(
            {
                "do_jump_id": do_jump_id,
                "command": MAV_CMD_DO_SET_RELAY,
                "command_name": "SPRAYER_OFF",
                "latitude": None,
                "longitude": None,
                "altitude_m": None,
                "speed_mps": current_speed_mps,
                "spray_on": False,
            }
        )

        do_jump_id += 1
        current_spray_state = False

    # Restore transit speed before ending
    if (
        include_speed_commands
        and not math.isclose(
            current_speed_mps,
            transit_speed_mps,
            rel_tol=0,
            abs_tol=1e-6,
        )
    ):
        mission_items.append(
            make_speed_item(
                speed_mps=transit_speed_mps,
                do_jump_id=do_jump_id,
            )
        )

        mission_summary_records.append(
            {
                "do_jump_id": do_jump_id,
                "command": MAV_CMD_DO_CHANGE_SPEED,
                "command_name": "SET_TRANSIT_SPEED",
                "latitude": None,
                "longitude": None,
                "altitude_m": None,
                "speed_mps": transit_speed_mps,
                "spray_on": False,
            }
        )

        do_jump_id += 1

    # End mission action
    if end_action == "rtl":
        mission_items.append(
            make_return_to_launch_item(
                do_jump_id=do_jump_id
            )
        )

        mission_summary_records.append(
            {
                "do_jump_id": do_jump_id,
                "command": (
                    MAV_CMD_NAV_RETURN_TO_LAUNCH
                ),
                "command_name": "RETURN_TO_LAUNCH",
                "latitude": home_latitude,
                "longitude": home_longitude,
                "altitude_m": None,
                "speed_mps": transit_speed_mps,
                "spray_on": False,
            }
        )

    elif end_action == "land":
        mission_items.append(
            make_land_item(
                latitude=last_latitude,
                longitude=last_longitude,
                do_jump_id=do_jump_id,
            )
        )

        mission_summary_records.append(
            {
                "do_jump_id": do_jump_id,
                "command": MAV_CMD_NAV_LAND,
                "command_name": "LAND",
                "latitude": last_latitude,
                "longitude": last_longitude,
                "altitude_m": 0,
                "speed_mps": 0,
                "spray_on": False,
            }
        )

    qgc_plan = {
        "fileType": "Plan",
        "geoFence": {
            "circles": [],
            "polygons": [],
            "version": 2,
        },
        "groundStation": "QGroundControl",
        "mission": {
            "cruiseSpeed": transit_speed_mps,
            "firmwareType": FIRMWARE_TYPE_PX4,
            "globalPlanAltitudeMode": 1,
            "hoverSpeed": transit_speed_mps,
            "items": mission_items,
            "plannedHomePosition": (
                planned_home_position
            ),
            "vehicleType": (
                VEHICLE_TYPE_MULTIROTOR
            ),
            "version": 2,
        },
        "rallyPoints": {
            "points": [],
            "version": 2,
        },
        "version": 1,
    }

    with open(
        output_paths["plan"],
        "w",
        encoding="utf-8",
    ) as plan_file:
        json.dump(
            qgc_plan,
            plan_file,
            indent=4,
        )

    mission_summary_df = pd.DataFrame(
        mission_summary_records
    )

    mission_summary_df.to_csv(
        output_paths["summary"],
        index=False,
    )

    print("\nQGroundControl export results")
    print("-" * 45)
    print(
        f"Plan file: {output_paths['plan']}"
    )
    print(
        f"Mission summary: "
        f"{output_paths['summary']}"
    )
    print(
        f"QGC mission items: "
        f"{len(mission_items)}"
    )
    print(f"End action: {end_action}")
    print(
        f"Speed commands included: "
        f"{include_speed_commands}"
    )
    print(
        f"Relay commands included: "
        f"{include_spray_relay_commands}"
    )

    return output_paths


def main():
    """Allow the script to run independently."""

    parser = argparse.ArgumentParser(
        description=(
            "Export WGS84 route to a "
            "QGroundControl Plan file."
        )
    )

    parser.add_argument(
        "input_waypoints_csv",
        help="Path to mission_waypoints_wgs84.csv",
    )

    parser.add_argument(
        "--output-mission-dir",
        default="outputs/missions",
    )

    parser.add_argument(
        "--flight-altitude-m",
        type=float,
        default=10.0,
    )

    parser.add_argument(
        "--transit-speed-mps",
        type=float,
        default=5.0,
    )

    parser.add_argument(
        "--spray-speed-mps",
        type=float,
        default=2.0,
    )

    parser.add_argument(
        "--acceptance-radius-m",
        type=float,
        default=1.0,
    )

    parser.add_argument(
        "--home-latitude",
        type=float,
    )

    parser.add_argument(
        "--home-longitude",
        type=float,
    )

    parser.add_argument(
        "--home-altitude-amsl-m",
        type=float,
        default=0.0,
    )

    parser.add_argument(
        "--no-speed-commands",
        action="store_true",
    )

    parser.add_argument(
        "--include-relay-commands",
        action="store_true",
    )

    parser.add_argument(
        "--relay-index",
        type=int,
        default=0,
    )

    parser.add_argument(
        "--end-action",
        choices=["rtl", "land", "none"],
        default="rtl",
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
    )

    args = parser.parse_args()

    try:
        export_qgroundcontrol_plan(
            input_waypoints_csv=(
                args.input_waypoints_csv
            ),
            output_mission_dir=(
                args.output_mission_dir
            ),
            flight_altitude_m=(
                args.flight_altitude_m
            ),
            transit_speed_mps=(
                args.transit_speed_mps
            ),
            spray_speed_mps=(
                args.spray_speed_mps
            ),
            acceptance_radius_m=(
                args.acceptance_radius_m
            ),
            home_latitude=args.home_latitude,
            home_longitude=args.home_longitude,
            home_altitude_amsl_m=(
                args.home_altitude_amsl_m
            ),
            include_speed_commands=(
                not args.no_speed_commands
            ),
            include_spray_relay_commands=(
                args.include_relay_commands
            ),
            sprayer_relay_index=(
                args.relay_index
            ),
            end_action=args.end_action,
            overwrite=args.overwrite,
        )

    except Exception as error:
        parser.exit(
            status=1,
            message=f"Error: {error}\n",
        )


if __name__ == "__main__":
    main()