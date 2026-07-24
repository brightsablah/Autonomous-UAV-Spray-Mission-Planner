from pathlib import Path

from scripts.setup_00_inspect_tif import inspect_path
from scripts.setup_00_create_ndvi_raster import create_ndvi_raster
from scripts.setup_00_apply_tif_boundary import apply_tif_boundary
from scripts.setup_00_visualise_tif import visualise_path
from scripts.stage1_create_ndvi_crop_mask import create_ndvi_crop_mask
from scripts.stage2_create_ndvi_spray_mask import create_ndvi_spray_mask
from scripts.stage3_clean_spray_mask import clean_spray_mask, get_cleaning_output_paths
from scripts.stage4_extract_spray_polygon import extract_spray_polygons, get_polygon_output_paths
from scripts.stage5_generate_spray_paths import generate_spray_paths, get_spray_path_output_paths
from scripts.stage6_order_spray_paths import order_spray_paths, get_ordered_path_output_paths
from scripts.stage7_connect_ordered_spray_paths import connect_ordered_spray_paths, get_connected_route_output_paths
from scripts.stage8_convert_route_to_wgs84 import convert_route_to_wgs84, get_wgs84_output_paths
from scripts.stage9_export_qgroundcontrol_plan import export_qgroundcontrol_plan, get_qgc_output_paths


def ask_with_default(prompt, default):
    """Request user input while providing a default value."""

    value = input(f"{prompt} [{default}]: ").strip().strip('"')
    return value if value else default


def ask_float_in_range(
    prompt,
    default,
    minimum,
    maximum,
    include_maximum=True,
):
    """Request a decimal number within a given range."""

    while True:
        default_display = (
            f" [{default}]"
            if default is not None
            else ""
        )

        value = input(
            f"{prompt}{default_display}: "
        ).strip()

        if not value:
            if default is not None:
                return default

            print("This value is required.")
            continue

        try:
            value = float(value)

            if not float("-inf") < value < float("inf"):
                print("Please enter a finite number.")
                continue

            below_minimum = value < minimum

            above_maximum = (
                value > maximum
                if include_maximum
                else value >= maximum
            )

            if below_minimum or above_maximum:
                ending = (
                    f"to {maximum}"
                    if include_maximum
                    else f"to below {maximum}"
                )

                print(
                    f"Enter a value from "
                    f"{minimum} {ending}."
                )
                continue

            return value

        except ValueError:
            print("Please enter a numerical value.")


def ask_nonnegative_float(
    prompt,
    default,
    allow_zero=True,
):
    """Request a positive or nonnegative decimal value."""

    while True:
        value = input(
            f"{prompt} [{default}]: "
        ).strip()

        if not value:
            return default

        try:
            value = float(value)

            if allow_zero and value < 0:
                print("The value cannot be negative.")
                continue

            if not allow_zero and value <= 0:
                print("The value must be greater than zero.")
                continue

            return value

        except ValueError:
            print("Please enter a numerical value.")


def ask_float(prompt, default, minimum=-1, maximum=1):
    while True:
        value = input(
            f"{prompt} [{default}]: "
        ).strip()

        if not value:
            return default

        try:
            value = float(value)

            if value < minimum or value > maximum:
                print(
                    f"Enter a value between "
                    f"{minimum} and {maximum}."
                )
                continue

            return value

        except ValueError:
            print("Please enter a numerical value.")


def ask_yes_no(prompt, default=True):
    """Request a yes or no response."""

    default_text = "y" if default else "n"

    while True:
        answer = input(
            f"{prompt} (y/n) [{default_text}]: "
        ).strip().lower()

        if not answer:
            return default

        if answer in {"y", "yes"}:
            return True

        if answer in {"n", "no"}:
            return False

        print("Please enter y or n.")

def ask_integer(prompt, default, minimum=1):
    """Request an integer with a default value."""

    while True:
        value = input(
            f"{prompt} [{default}]: "
        ).strip()

        if not value:
            return default

        try:
            value = int(value)

            if value < minimum:
                print(
                    f"Please enter a value of at least {minimum}."
                )
                continue

            return value

        except ValueError:
            print("Please enter a whole number.")


def run_spray_path_ordering():
    print("\nORDER SPRAY PATHS")
    print("-" * 40)

    print(
        "Enter a path, or press Enter to use the default "
        "shown in square brackets.\n"
    )

    input_lines_path = ask_with_default(
        "Enter the spray path lines file",
        "outputs/paths/spray_path_lines.gpkg",
    )

    output_route_dir = ask_with_default(
        "Enter the ordered route output directory",
        "outputs/routes",
    )

    output_figure_dir = ask_with_default(
        "Enter the preview output directory",
        "outputs/figures/routes",
    )

    print("\nSelect the starting method:")
    print("1. South west path")
    print("2. North west path")
    print("3. Lowest polygon ID")
    print("4. Longest polygon path")
    print("5. UAV takeoff position")

    start_choices = {
        "1": "south_west",
        "2": "north_west",
        "3": "first_id",
        "4": "longest_path",
        "5": "takeoff",
    }

    while True:
        start_choice = input(
            "Select the starting method [1]: "
        ).strip()

        if not start_choice:
            start_choice = "1"

        if start_choice in start_choices:
            start_mode = start_choices[
                start_choice
            ]
            break

        print("Please select an option from 1 to 5.")

    takeoff_latitude = None
    takeoff_longitude = None

    if start_mode == "takeoff":
        takeoff_latitude = ask_float_in_range(
            "Enter the takeoff latitude",
            default=None,
            minimum=-90,
            maximum=90,
        )

        takeoff_longitude = ask_float_in_range(
            "Enter the takeoff longitude",
            default=None,
            minimum=-180,
            maximum=180,
        )

    show_preview = ask_yes_no(
        "Display the path order preview?",
        default=True,
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

    overwrite = False

    if existing_outputs:
        print(
            "\nSome ordered route outputs already exist:"
        )

        for path in existing_outputs:
            print(f"  {path}")

        overwrite = ask_yes_no(
            "Replace the existing ordered route outputs?",
            default=False,
        )

        if not overwrite:
            print("Spray path ordering cancelled.")
            input(
                "Press Enter to return to the menu..."
            )
            return

    try:
        order_spray_paths(
            input_lines_path=input_lines_path,
            output_route_dir=output_route_dir,
            output_figure_dir=output_figure_dir,
            start_mode=start_mode,
            takeoff_latitude=takeoff_latitude,
            takeoff_longitude=takeoff_longitude,
            show_preview=show_preview,
            overwrite=overwrite,
        )

    except Exception as error:
        print(
            f"\nSpray path ordering failed: {error}"
        )

    input(
        "\nPress Enter to return to the menu..."
    )


def run_spray_mask_cleaning():
    print("\nCLEAN SPRAY MASK")
    print("-" * 40)

    print(
        "Enter a value or path, or press Enter to use the "
        "default shown in square brackets."
    )

    print(
        "Area parameters use square metres. "
        "Distance parameters use metres.\n"
    )

    input_mask_path = ask_with_default(
        "Enter the spray mask path",
        "data/processed/spray_mask_ndvi_0.10_to_0.25.tif",
    )

    output_data_dir = ask_with_default(
        "Enter the cleaned raster output directory",
        "data/processed/cleaning",
    )

    output_figure_dir = ask_with_default(
        "Enter the preview output directory",
        "outputs/figures/cleaning",
    )

    initial_patch_area_m2 = ask_nonnegative_float(
        "Enter the initial minimum patch area in m²",
        default=25.0,
        allow_zero=False,
    )

    closing_distance_m = ask_nonnegative_float(
        "Enter the closing distance in metres",
        default=5.0,
        allow_zero=True,
    )

    maximum_hole_area_m2 = ask_nonnegative_float(
        "Enter the maximum hole area to fill in m²",
        default=9.0,
        allow_zero=True,
    )

    opening_distance_m = ask_nonnegative_float(
        "Enter the opening distance in metres",
        default=4.0,
        allow_zero=True,
    )

    final_patch_area_m2 = ask_nonnegative_float(
        "Enter the final minimum patch area in m²",
        default=144.0,
        allow_zero=False,
    )

    raster_paths, figure_paths = get_cleaning_output_paths(
        output_data_dir,
        output_figure_dir,
    )

    all_outputs = (
        list(raster_paths.values())
        + list(figure_paths.values())
    )

    existing_outputs = [
        path
        for path in all_outputs
        if path.exists()
    ]

    overwrite = False

    if existing_outputs:
        print("\nSome cleaning outputs already exist:")

        for path in existing_outputs:
            print(f"  {path}")

        overwrite = ask_yes_no(
            "Replace the existing cleaning outputs?",
            default=False,
        )

        if not overwrite:
            print("Spray mask cleaning cancelled.")
            input("Press Enter to return to the menu...")
            return

    try:
        clean_spray_mask(
            input_mask_path=input_mask_path,
            output_data_dir=output_data_dir,
            output_figure_dir=output_figure_dir,
            initial_patch_area_m2=initial_patch_area_m2,
            closing_distance_m=closing_distance_m,
            maximum_hole_area_m2=maximum_hole_area_m2,
            opening_distance_m=opening_distance_m,
            final_patch_area_m2=final_patch_area_m2,
            overwrite=overwrite,
        )

    except Exception as error:
        print(f"\nSpray mask cleaning failed: {error}")

    input("\nPress Enter to return to the menu...")

def run_crop_mask_creation():
    print("\nCREATE CROP MASK")
    print("-" * 40)

    print(
        "Enter a value or path, or press Enter to use the "
        "default shown in square brackets.\n"
    )

    ndvi_path = ask_with_default(
        "Enter the clipped NDVI raster path",
        "data/processed/odm_ndvi_clipped_boundary.tif",
    )

    crop_threshold = ask_float(
        "Enter the minimum NDVI value classified as crop",
        default=0.0,
    )

    threshold_text = f"{crop_threshold:.2f}"

    output_path = ask_with_default(
        "Enter the crop mask output path",
        (
            "data/processed/"
            f"crop_mask_ndvi_gte_{threshold_text}.tif"
        ),
    )

    show_preview = ask_yes_no(
        "Display the crop mask preview?",
        default=True,
    )

    save_preview = ask_yes_no(
        "Save the crop mask preview?",
        default=True,
    )

    preview_output_path = None

    if save_preview:
        preview_output_path = ask_with_default(
            "Enter the preview output path",
            (
                "outputs/figures/"
                f"crop_mask_ndvi_gte_{threshold_text}.png"
            ),
        )

    existing = [
        path
        for path in [output_path, preview_output_path]
        if path and Path(path).exists()
    ]

    overwrite = False

    if existing:
        print("\nThe following outputs already exist:")

        for path in existing:
            print(f"  {path}")

        overwrite = ask_yes_no(
            "Replace the existing outputs?",
            default=False,
        )

        if not overwrite:
            print("Crop mask creation cancelled.")
            input("Press Enter to return to the menu...")
            return

    try:
        create_ndvi_crop_mask(
            ndvi_path=ndvi_path,
            crop_threshold=crop_threshold,
            output_path=output_path,
            preview_output_path=preview_output_path,
            show_preview=show_preview,
            overwrite=overwrite,
        )

    except Exception as error:
        print(f"\nCrop mask creation failed: {error}")

    input("\nPress Enter to return to the menu...")


def run_spray_mask_creation():
    print("\nCREATE SPRAY MASK")
    print("-" * 40)

    print(
        "Enter a value or path, or press Enter to use the "
        "default shown in square brackets.\n"
    )

    ndvi_path = ask_with_default(
        "Enter the clipped NDVI raster path",
        "data/processed/odm_ndvi_clipped_boundary.tif",
    )

    crop_mask_path = ask_with_default(
        "Enter the crop mask path",
        "data/processed/crop_mask_ndvi_gte_0.00.tif",
    )

    unhealthy_lower = ask_float(
        "Enter the lower unhealthy NDVI value",
        default=0.10,
    )

    unhealthy_upper = ask_float(
        "Enter the upper unhealthy NDVI value",
        default=0.25,
    )

    if unhealthy_lower > unhealthy_upper:
        print(
            "\nThe lower NDVI value cannot exceed "
            "the upper value."
        )
        input("Press Enter to return to the menu...")
        return

    lower_text = f"{unhealthy_lower:.2f}"
    upper_text = f"{unhealthy_upper:.2f}"

    output_path = ask_with_default(
        "Enter the spray mask output path",
        (
            "data/processed/"
            f"spray_mask_ndvi_{lower_text}_to_{upper_text}.tif"
        ),
    )

    show_preview = ask_yes_no(
        "Display the spray mask preview?",
        default=True,
    )

    save_preview = ask_yes_no(
        "Save the spray mask preview?",
        default=True,
    )

    preview_output_path = None

    if save_preview:
        preview_output_path = ask_with_default(
            "Enter the preview output path",
            (
                "outputs/figures/"
                f"spray_mask_ndvi_{lower_text}_to_"
                f"{upper_text}.png"
            ),
        )

    existing = [
        path
        for path in [output_path, preview_output_path]
        if path and Path(path).exists()
    ]

    overwrite = False

    if existing:
        print("\nThe following outputs already exist:")

        for path in existing:
            print(f"  {path}")

        overwrite = ask_yes_no(
            "Replace the existing outputs?",
            default=False,
        )

        if not overwrite:
            print("Spray mask creation cancelled.")
            input("Press Enter to return to the menu...")
            return

    try:
        create_ndvi_spray_mask(
            ndvi_path=ndvi_path,
            crop_mask_path=crop_mask_path,
            unhealthy_lower=unhealthy_lower,
            unhealthy_upper=unhealthy_upper,
            output_path=output_path,
            preview_output_path=preview_output_path,
            show_preview=show_preview,
            overwrite=overwrite,
        )

    except Exception as error:
        print(f"\nSpray mask creation failed: {error}")

    input("\nPress Enter to return to the menu...")


def run_tif_inspection():
    print("\nTIF METADATA INSPECTION")
    print("-" * 40)

    path = input(
        "Enter the path to a TIF file or folder: "
    ).strip().strip('"')

    recursive = ask_yes_no(
        "Search inside subfolders?",
        default=False,
    )

    inspect_path(
        path=path,
        recursive=recursive,
    )

    input("Press Enter to return to the menu...")


def run_ndvi_creation():
    print("\nCREATE NDVI RASTER")
    print("-" * 40)

    print(
        "Enter a response, or press Enter to use the default path shown in square brackets.\n"
        )

    nir_path = ask_with_default(
        "Enter the NIR raster path",
        "data/pre-processed/odm_orthophoto NIR.tif",
    )

    red_path = ask_with_default(
        "Enter the RED raster path",
        "data/pre-processed/odm_orthophoto RED.tif",
    )

    output_path = ask_with_default(
        "Enter the NDVI output path",
        "data/processed/odm_ndvi.tif",
    )

    show_preview = ask_yes_no(
        "Display the NDVI preview?",
        default=True,
    )

    save_preview = ask_yes_no(
        "Save the NDVI preview?",
        default=False,
    )

    preview_output_path = None

    if save_preview:
        preview_output_path = ask_with_default(
            "Enter the preview output path",
            "outputs/figures/odm_ndvi_preview.png",
        )

    existing_outputs = [
        path
        for path in [output_path, preview_output_path]
        if path and Path(path).exists()
    ]

    overwrite = False

    if existing_outputs:
        print("\nThe following output files already exist:")

        for existing_path in existing_outputs:
            print(f"  {existing_path}")

        overwrite = ask_yes_no(
            "Replace the existing files?",
            default=False,
        )

        if not overwrite:
            print("NDVI creation cancelled.")
            input("Press Enter to return to the menu...")
            return

    try:
        create_ndvi_raster(
            nir_path=nir_path,
            red_path=red_path,
            ndvi_output_path=output_path,
            preview_output_path=preview_output_path,
            show_preview=show_preview,
            overwrite=overwrite,
        )

    except Exception as error:
        print(f"\nNDVI creation failed: {error}")

    input("\nPress Enter to return to the menu...")


def run_boundary_clipping():
    print("\nAPPLY FIELD BOUNDARY")
    print("-" * 40)

    print(
        "Enter a path, or press Enter to use the default path "
        "shown in square brackets.\n"
    )

    ndvi_path = ask_with_default(
        "Enter the NDVI raster path",
        "data/processed/odm_ndvi.tif",
    )

    boundary_path = ask_with_default(
        "Enter the boundary file path",
        (
            "data/extracted/example_rostock_sequoia_msp/"
            "boundary/boundaries.shp"
        ),
    )

    output_path = ask_with_default(
        "Enter the clipped raster output path",
        "data/processed/odm_ndvi_clipped_boundary.tif",
    )

    print(
        "\nNormally, a pixel is included when its centre is "
        "inside the boundary."
    )

    all_touched = ask_yes_no(
        "Include every pixel touched by the boundary edge?",
        default=False,
    )

    overwrite = False

    if Path(output_path).exists():
        print(f"\nThe output already exists: {output_path}")

        overwrite = ask_yes_no(
            "Replace the existing output?",
            default=False,
        )

        if not overwrite:
            print("Boundary clipping cancelled.")
            input("Press Enter to return to the menu...")
            return

    try:
        apply_tif_boundary(
            ndvi_path=ndvi_path,
            boundary_path=boundary_path,
            output_path=output_path,
            all_touched=all_touched,
            overwrite=overwrite,
        )

    except Exception as error:
        print(f"\nBoundary clipping failed: {error}")

    input("\nPress Enter to return to the menu...")

def run_tif_visualisation():
    print("\nVISUALISE TIF")
    print("-" * 40)

    print(
        "Enter a path, or press Enter to use the default path "
        "shown in square brackets.\n"
    )

    tif_path = ask_with_default(
        "Enter the TIF file or folder path",
        "data/processed/odm_ndvi_clipped_boundary.tif",
    )

    band = ask_integer(
        "Enter the band number",
        default=1,
        minimum=1,
    )

    ndvi = ask_yes_no(
        "Use the NDVI colour scale?",
        default=True,
    )

    recursive = False

    if Path(tif_path).is_dir():
        recursive = ask_yes_no(
            "Search inside subfolders?",
            default=False,
        )

    try:
        visualise_path(
            path=tif_path,
            band=band,
            ndvi=ndvi,
            recursive=recursive,
        )

    except Exception as error:
        print(f"\nTIF visualisation failed: {error}")

    input("\nPress Enter to return to the menu...")


def run_spray_polygon_extraction():
    print("\nEXTRACT SPRAY POLYGONS")
    print("-" * 40)

    print(
        "Enter a value or path, or press Enter to use the "
        "default shown in square brackets."
    )

    print(
        "Area is entered in square metres and "
        "simplification tolerance in metres.\n"
    )

    input_mask_path = ask_with_default(
        "Enter the cleaned spray mask path",
        (
            "data/processed/cleaning/"
            "clean_step5_final_cleanup.tif"
        ),
    )

    output_vector_dir = ask_with_default(
        "Enter the polygon output directory",
        "outputs/polygons",
    )

    output_figure_dir = ask_with_default(
        "Enter the preview output directory",
        "outputs/figures/polygons",
    )

    minimum_polygon_area_m2 = ask_nonnegative_float(
        "Enter the minimum polygon area in m²",
        default=5.0,
        allow_zero=True,
    )

    simplification_tolerance_m = ask_nonnegative_float(
        "Enter the simplification tolerance in metres",
        default=1.0,
        allow_zero=True,
    )

    show_preview = ask_yes_no(
        "Display the polygon preview?",
        default=True,
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

    overwrite = False

    if existing_outputs:
        print("\nSome polygon outputs already exist:")

        for path in existing_outputs:
            print(f"  {path}")

        overwrite = ask_yes_no(
            "Replace the existing polygon outputs?",
            default=False,
        )

        if not overwrite:
            print("Polygon extraction cancelled.")
            input("Press Enter to return to the menu...")
            return

    try:
        extract_spray_polygons(
            input_mask_path=input_mask_path,
            output_vector_dir=output_vector_dir,
            output_figure_dir=output_figure_dir,
            minimum_polygon_area_m2=(
                minimum_polygon_area_m2
            ),
            simplification_tolerance_m=(
                simplification_tolerance_m
            ),
            show_preview=show_preview,
            overwrite=overwrite,
        )

    except Exception as error:
        print(f"\nPolygon extraction failed: {error}")

    input("\nPress Enter to return to the menu...")


def run_spray_path_generation():
    print("\nGENERATE SPRAY PATHS")
    print("-" * 40)

    print(
        "Enter a value or path, or press Enter to use the "
        "default shown in square brackets.\n"
    )

    input_polygon_path = ask_with_default(
        "Enter the spray polygon path",
        "outputs/polygons/spray_zone_polygons.gpkg",
    )

    output_path_dir = ask_with_default(
        "Enter the spray path output directory",
        "outputs/paths",
    )

    output_figure_dir = ask_with_default(
        "Enter the preview output directory",
        "outputs/figures/paths",
    )

    spray_width_m = ask_nonnegative_float(
        "Enter the effective spray width in metres",
        default=2.0,
        allow_zero=False,
    )

    overlap_percent = ask_float_in_range(
        "Enter the spray overlap percentage",
        default=20.0,
        minimum=0.0,
        maximum=100.0,
        include_maximum=False,
    )

    path_angle_deg = ask_float_in_range(
        "Enter the path angle in degrees",
        default=0.0,
        minimum=0.0,
        maximum=180.0,
        include_maximum=False,
    )

    minimum_line_length_m = ask_nonnegative_float(
        "Enter the minimum spray line length in metres",
        default=1.0,
        allow_zero=True,
    )

    line_spacing_m = spray_width_m * (
        1 - overlap_percent / 100
    )

    print(
        f"\nCalculated line spacing: "
        f"{line_spacing_m:.2f} m"
    )

    show_preview = ask_yes_no(
        "Display the spray path preview?",
        default=True,
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

    overwrite = False

    if existing_outputs:
        print("\nSome spray path outputs already exist:")

        for path in existing_outputs:
            print(f"  {path}")

        overwrite = ask_yes_no(
            "Replace the existing spray path outputs?",
            default=False,
        )

        if not overwrite:
            print("Spray path generation cancelled.")
            input("Press Enter to return to the menu...")
            return

    try:
        generate_spray_paths(
            input_polygon_path=input_polygon_path,
            output_path_dir=output_path_dir,
            output_figure_dir=output_figure_dir,
            spray_width_m=spray_width_m,
            overlap_percent=overlap_percent,
            path_angle_deg=path_angle_deg,
            minimum_line_length_m=(
                minimum_line_length_m
            ),
            show_preview=show_preview,
            overwrite=overwrite,
        )

    except Exception as error:
        print(f"\nSpray path generation failed: {error}")

    input("\nPress Enter to return to the menu...")


def run_spray_path_connection():
    print("\nCONNECT ORDERED SPRAY PATHS")
    print("-" * 40)

    print(
        "Enter a path, or press Enter to use the default "
        "shown in square brackets.\n"
    )

    input_ordered_path = ask_with_default(
        "Enter the ordered spray path file",
        "outputs/routes/ordered_spray_paths.gpkg",
    )

    output_route_dir = ask_with_default(
        "Enter the connected route output directory",
        "outputs/routes",
    )

    output_figure_dir = ask_with_default(
        "Enter the preview output directory",
        "outputs/figures/routes",
    )

    show_preview = ask_yes_no(
        "Display the connected route preview?",
        default=True,
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

    overwrite = False

    if existing_outputs:
        print(
            "\nSome connected route outputs already exist:"
        )

        for path in existing_outputs:
            print(f"  {path}")

        overwrite = ask_yes_no(
            "Replace the existing connected route outputs?",
            default=False,
        )

        if not overwrite:
            print("Route connection cancelled.")
            input(
                "Press Enter to return to the menu..."
            )
            return

    try:
        connect_ordered_spray_paths(
            input_ordered_path=input_ordered_path,
            output_route_dir=output_route_dir,
            output_figure_dir=output_figure_dir,
            show_preview=show_preview,
            overwrite=overwrite,
        )

    except Exception as error:
        print(
            f"\nRoute connection failed: {error}"
        )

    input(
        "\nPress Enter to return to the menu..."
    )


def run_wgs84_conversion():
    print("\nCONVERT ROUTE TO WGS84")
    print("-" * 40)

    print(
        "Enter a path, or press Enter to use the default "
        "shown in square brackets.\n"
    )

    input_route_path = ask_with_default(
        "Enter the connected route file",
        "outputs/routes/connected_spray_route.gpkg",
    )

    output_route_dir = ask_with_default(
        "Enter the WGS84 output directory",
        "outputs/routes",
    )

    output_paths = get_wgs84_output_paths(
        output_route_dir
    )

    existing_outputs = [
        path
        for path in output_paths.values()
        if path.exists()
    ]

    overwrite = False

    if existing_outputs:
        print(
            "\nSome WGS84 outputs already exist:"
        )

        for path in existing_outputs:
            print(f"  {path}")

        overwrite = ask_yes_no(
            "Replace the existing WGS84 outputs?",
            default=False,
        )

        if not overwrite:
            print("WGS84 conversion cancelled.")
            input(
                "Press Enter to return to the menu..."
            )
            return

    try:
        convert_route_to_wgs84(
            input_route_path=input_route_path,
            output_route_dir=output_route_dir,
            overwrite=overwrite,
        )

    except Exception as error:
        print(
            f"\nWGS84 conversion failed: {error}"
        )

    input(
        "\nPress Enter to return to the menu..."
    )


def run_qgroundcontrol_export():
    print("\nEXPORT QGROUNDCONTROL PLAN")
    print("-" * 40)

    print(
        "Enter a value or path, or press Enter to use the "
        "default shown in square brackets.\n"
    )

    input_waypoints_csv = ask_with_default(
        "Enter the WGS84 mission waypoint CSV",
        "outputs/routes/mission_waypoints_wgs84.csv",
    )

    output_mission_dir = ask_with_default(
        "Enter the mission output directory",
        "outputs/missions",
    )

    flight_altitude_m = ask_nonnegative_float(
        "Enter the relative flight altitude in metres",
        default=10.0,
        allow_zero=False,
    )

    transit_speed_mps = ask_nonnegative_float(
        "Enter the transit speed in m/s",
        default=5.0,
        allow_zero=False,
    )

    spray_speed_mps = ask_nonnegative_float(
        "Enter the spray speed in m/s",
        default=2.0,
        allow_zero=False,
    )

    acceptance_radius_m = ask_nonnegative_float(
        "Enter the waypoint acceptance radius in metres",
        default=1.0,
        allow_zero=True,
    )

    use_first_point_as_home = ask_yes_no(
        "Use the first route point as the home and takeoff position?",
        default=True,
    )

    home_latitude = None
    home_longitude = None

    if not use_first_point_as_home:
        home_latitude = ask_float_in_range(
            "Enter the home latitude",
            default=None,
            minimum=-90,
            maximum=90,
        )

        home_longitude = ask_float_in_range(
            "Enter the home longitude",
            default=None,
            minimum=-180,
            maximum=180,
        )

    home_altitude_amsl_m = ask_float_in_range(
        "Enter the planned home AMSL altitude in metres",
        default=0.0,
        minimum=-500,
        maximum=10000,
    )

    include_speed_commands = ask_yes_no(
        "Include separate spray and transit speed commands?",
        default=True,
    )

    include_relay_commands = ask_yes_no(
        "Include sprayer relay ON and OFF commands?",
        default=False,
    )

    relay_index = 0

    if include_relay_commands:
        relay_index = ask_integer(
            "Enter the sprayer relay index",
            default=0,
            minimum=0,
        )

    print("\nSelect the mission end action:")
    print("1. Return to launch")
    print("2. Land at the final waypoint")
    print("3. No automatic end action")

    end_actions = {
        "1": "rtl",
        "2": "land",
        "3": "none",
    }

    while True:
        end_choice = input(
            "Select the end action [1]: "
        ).strip()

        if not end_choice:
            end_choice = "1"

        if end_choice in end_actions:
            end_action = end_actions[end_choice]
            break

        print("Please select option 1, 2 or 3.")

    output_paths = get_qgc_output_paths(
        output_mission_dir
    )

    existing_outputs = [
        path
        for path in output_paths.values()
        if path.exists()
    ]

    overwrite = False

    if existing_outputs:
        print(
            "\nSome mission outputs already exist:"
        )

        for path in existing_outputs:
            print(f"  {path}")

        overwrite = ask_yes_no(
            "Replace the existing mission outputs?",
            default=False,
        )

        if not overwrite:
            print("Mission export cancelled.")
            input(
                "Press Enter to return to the menu..."
            )
            return

    try:
        export_qgroundcontrol_plan(
            input_waypoints_csv=input_waypoints_csv,
            output_mission_dir=output_mission_dir,
            flight_altitude_m=flight_altitude_m,
            transit_speed_mps=transit_speed_mps,
            spray_speed_mps=spray_speed_mps,
            acceptance_radius_m=acceptance_radius_m,
            home_latitude=home_latitude,
            home_longitude=home_longitude,
            home_altitude_amsl_m=(
                home_altitude_amsl_m
            ),
            include_speed_commands=(
                include_speed_commands
            ),
            include_spray_relay_commands=(
                include_relay_commands
            ),
            sprayer_relay_index=relay_index,
            end_action=end_action,
            overwrite=overwrite,
        )

    except Exception as error:
        print(
            f"\nQGroundControl export failed: {error}"
        )

    input(
        "\nPress Enter to return to the menu..."
    )



def display_menu():
    print("\n" + "=" * 60)
    print("AUTONOMOUS UAV SPRAY MISSION PLANNER")
    print("=" * 60)
    print("1.  Inspect TIF metadata")
    print("2.  Create NDVI raster")
    print("3.  Apply field boundary")
    print("4.  Visualise TIF")
    print("5.  Create crop mask")
    print("6.  Create spray mask")
    print("7.  Clean spray mask")
    print("8.  Extract spray polygons")
    print("9.  Generate spray paths")
    print("10. Order spray paths")
    print("11. Connect ordered spray paths")
    print("12. Convert route to WGS84")
    print("13. Export QGroundControl plan")
    print("0. Exit")


def main():
    while True:
        display_menu()

        choice = input("\nSelect an option: ").strip()

        if choice == "1":
            run_tif_inspection()

        elif choice == "2":
            run_ndvi_creation()

        elif choice == "3":
            run_boundary_clipping()

        elif choice == "4":
            run_tif_visualisation()

        elif choice == "5":
            run_crop_mask_creation()

        elif choice == "6":
            run_spray_mask_creation()

        elif choice == "7":
            run_spray_mask_cleaning()

        elif choice == "8":
            run_spray_polygon_extraction()

        elif choice == "9":
            run_spray_path_generation()
            
        elif choice == "10":
            run_spray_path_ordering()  

        elif choice == "11":
            run_spray_path_connection()
    
        elif choice == "12":
            run_wgs84_conversion()

        elif choice == "13":
            run_qgroundcontrol_export()

        elif choice == "0":
            print("Application closed.")
            break

        else:
            print("Invalid option. Please select 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, or 0.")


if __name__ == "__main__":
    main()