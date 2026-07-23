from pathlib import Path
import argparse
import math

import matplotlib.colors as colors
import matplotlib.pyplot as plt
import numpy as np
import rasterio

from skimage.measure import label
from skimage.morphology import (
    remove_small_objects,
    remove_small_holes,
    binary_closing,
    binary_opening,
    disk,
)


def get_cleaning_output_paths(
    output_data_dir,
    output_figure_dir,
):
    """Create output paths for the five cleaning stages."""

    output_data_dir = Path(output_data_dir)
    output_figure_dir = Path(output_figure_dir)

    raster_paths = {
        "step1": output_data_dir
        / "clean_step1_remove_small_objects.tif",

        "step2": output_data_dir
        / "clean_step2_binary_closing.tif",

        "step3": output_data_dir
        / "clean_step3_remove_small_holes.tif",

        "step4": output_data_dir
        / "clean_step4_remove_thin_strings.tif",

        "step5": output_data_dir
        / "clean_step5_final_cleanup.tif",
    }

    figure_paths = {
        "step1": output_figure_dir
        / "clean_step1_remove_small_objects.png",

        "step2": output_figure_dir
        / "clean_step2_binary_closing.png",

        "step3": output_figure_dir
        / "clean_step3_remove_small_holes.png",

        "step4": output_figure_dir
        / "clean_step4_remove_thin_strings.png",

        "step5": output_figure_dir
        / "clean_step5_final_cleanup.png",
    }

    return raster_paths, figure_paths


def get_pixel_measurements(transform, crs):
    """Calculate pixel dimensions in metres and square metres."""

    if crs is None:
        raise ValueError(
            "The spray mask does not have a CRS."
        )

    if not crs.is_projected:
        raise ValueError(
            "The spray mask must use a projected CRS."
        )

    linear_units = crs.linear_units.lower()

    metre_units = {
        "metre",
        "meter",
        "metres",
        "meters",
    }

    if linear_units not in metre_units:
        raise ValueError(
            "The projected CRS must use metres. "
            f"Current units: {crs.linear_units}"
        )

    # Works with normal and rotated rasters
    pixel_width_m = math.sqrt(
        transform.a ** 2 + transform.d ** 2
    )

    pixel_height_m = math.sqrt(
        transform.b ** 2 + transform.e ** 2
    )

    pixel_area_m2 = abs(
        transform.a * transform.e
        - transform.b * transform.d
    )

    if pixel_width_m <= 0 or pixel_height_m <= 0:
        raise ValueError(
            "The raster has an invalid pixel resolution."
        )

    if pixel_area_m2 <= 0:
        raise ValueError(
            "The raster has an invalid pixel area."
        )

    # A circular pixel footprint assumes approximately square pixels
    if not np.isclose(
        pixel_width_m,
        pixel_height_m,
        rtol=0.01,
    ):
        raise ValueError(
            "The raster pixels are not square. "
            "Reproject or resample the raster before cleaning."
        )

    pixel_size_m = (
        pixel_width_m + pixel_height_m
    ) / 2

    return (
        pixel_width_m,
        pixel_height_m,
        pixel_size_m,
        pixel_area_m2,
    )


def area_to_pixels(area_m2, pixel_area_m2):
    """Convert an area in square metres to pixels."""

    if area_m2 == 0:
        return 0

    return max(
        1,
        int(round(area_m2 / pixel_area_m2)),
    )


def distance_to_pixels(distance_m, pixel_size_m):
    """Convert a distance in metres to a pixel radius."""

    if distance_m == 0:
        return 0

    return max(
        1,
        int(round(distance_m / pixel_size_m)),
    )


def save_mask(
    mask_bool,
    valid_mask,
    profile,
    output_path,
    nodata=255,
):
    """Save a Boolean spray mask as a GeoTIFF."""

    mask_to_save = np.full(
        mask_bool.shape,
        nodata,
        dtype="uint8",
    )

    mask_to_save[valid_mask] = 0
    mask_to_save[mask_bool] = 1

    save_profile = profile.copy()

    save_profile.update(
        dtype="uint8",
        count=1,
        nodata=nodata,
    )

    with rasterio.open(output_path, "w", **save_profile) as dst:
        dst.write(mask_to_save, 1)

    return mask_to_save


def save_preview(
    mask_to_save,
    figure_path,
    title,
    downsample_factor=20,
):
    """Save a preview of a spray mask."""

    display_mask = np.full(
        mask_to_save.shape,
        np.nan,
        dtype="float32",
    )

    display_mask[mask_to_save == 0] = 0
    display_mask[mask_to_save == 1] = 1

    colour_map = colors.ListedColormap(
        ["lightgray", "red"]
    )

    figure, axis = plt.subplots(figsize=(8, 6))

    axis.imshow(
        display_mask[
            ::downsample_factor,
            ::downsample_factor,
        ],
        cmap=colour_map,
        vmin=0,
        vmax=1,
    )

    axis.set_title(title)
    axis.axis("off")

    figure.savefig(
        figure_path,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close(figure)


def print_stats(
    step_name,
    mask_bool,
    valid_mask,
    pixel_area_m2,
):
    """Print pixel and physical area statistics."""

    spray_pixels = np.count_nonzero(mask_bool)
    valid_pixels = np.count_nonzero(valid_mask)

    spray_area_m2 = spray_pixels * pixel_area_m2
    valid_area_m2 = valid_pixels * pixel_area_m2

    spray_percentage = (
        spray_pixels / valid_pixels * 100
        if valid_pixels > 0
        else 0
    )

    print(f"\n{step_name}")
    print("-" * len(step_name))
    print(f"Spray pixels: {spray_pixels}")
    print(f"Spray area: {spray_area_m2:.2f} m²")
    print(f"Valid field area: {valid_area_m2:.2f} m²")
    print(
        f"Spray area percentage: "
        f"{spray_percentage:.2f}%"
    )


def save_cleaning_step(
    step_name,
    mask_bool,
    valid_mask,
    pixel_area_m2,
    profile,
    raster_path,
    figure_path,
    figure_title,
):
    """Print, save and preview one cleaning stage."""

    print_stats(
        step_name=step_name,
        mask_bool=mask_bool,
        valid_mask=valid_mask,
        pixel_area_m2=pixel_area_m2,
    )

    mask_to_save = save_mask(
        mask_bool=mask_bool,
        valid_mask=valid_mask,
        profile=profile,
        output_path=raster_path,
    )

    save_preview(
        mask_to_save=mask_to_save,
        figure_path=figure_path,
        title=figure_title,
    )

    print(f"Saved raster to: {raster_path}")
    print(f"Saved preview to: {figure_path}")


def clean_spray_mask(
    input_mask_path,
    output_data_dir,
    output_figure_dir,
    initial_patch_area_m2=121.5,
    closing_distance_m=2.70,
    maximum_hole_area_m2=162.0,
    opening_distance_m=2.25,
    final_patch_area_m2=243.0,
    overwrite=False,
):
    """Clean a spray mask using metric user inputs."""

    input_mask_path = Path(input_mask_path)
    output_data_dir = Path(output_data_dir)
    output_figure_dir = Path(output_figure_dir)

    if not input_mask_path.is_file():
        raise FileNotFoundError(
            f"Spray mask not found: {input_mask_path}"
        )

    if initial_patch_area_m2 <= 0:
        raise ValueError(
            "Initial patch area must be greater than zero."
        )

    if closing_distance_m < 0:
        raise ValueError(
            "Closing distance cannot be negative."
        )

    if maximum_hole_area_m2 < 0:
        raise ValueError(
            "Maximum hole area cannot be negative."
        )

    if opening_distance_m < 0:
        raise ValueError(
            "Opening distance cannot be negative."
        )

    if final_patch_area_m2 <= 0:
        raise ValueError(
            "Final patch area must be greater than zero."
        )

    raster_paths, figure_paths = get_cleaning_output_paths(
        output_data_dir,
        output_figure_dir,
    )

    all_output_paths = (
        list(raster_paths.values())
        + list(figure_paths.values())
    )

    existing_outputs = [
        path
        for path in all_output_paths
        if path.exists()
    ]

    if existing_outputs and not overwrite:
        raise FileExistsError(
            f"Output already exists: {existing_outputs[0]}"
        )

    output_data_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_figure_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    with rasterio.open(input_mask_path) as src:
        spray_mask = src.read(1)
        valid_mask = src.read_masks(1) > 0

        profile = src.profile.copy()
        nodata = src.nodata

        (
            pixel_width_m,
            pixel_height_m,
            pixel_size_m,
            pixel_area_m2,
        ) = get_pixel_measurements(
            transform=src.transform,
            crs=src.crs,
        )

    if nodata is not None:
        valid_mask &= spray_mask != nodata

    if not np.any(valid_mask):
        raise ValueError(
            "The spray mask does not contain valid pixels."
        )

    spray_bool = (spray_mask == 1) & valid_mask

    # Convert physical inputs into pixel values
    initial_patch_pixels = area_to_pixels(
        initial_patch_area_m2,
        pixel_area_m2,
    )

    closing_radius_pixels = distance_to_pixels(
        closing_distance_m,
        pixel_size_m,
    )

    maximum_hole_pixels = area_to_pixels(
        maximum_hole_area_m2,
        pixel_area_m2,
    )

    opening_radius_pixels = distance_to_pixels(
        opening_distance_m,
        pixel_size_m,
    )

    final_patch_pixels = area_to_pixels(
        final_patch_area_m2,
        pixel_area_m2,
    )

    print("\nRaster measurements")
    print("-" * 40)
    print(f"Pixel width: {pixel_width_m:.4f} m")
    print(f"Pixel height: {pixel_height_m:.4f} m")
    print(f"Pixel area: {pixel_area_m2:.6f} m²")
    print(
        f"Pixels per square metre: "
        f"{1 / pixel_area_m2:.2f}"
    )

    print("\nCleaning parameter conversions")
    print("-" * 40)

    print(
        f"Initial patch area: "
        f"{initial_patch_area_m2:.2f} m² "
        f"= {initial_patch_pixels} pixels"
    )

    print(
        f"Closing distance: "
        f"{closing_distance_m:.2f} m "
        f"= {closing_radius_pixels} pixels"
    )

    print(
        f"Maximum hole area: "
        f"{maximum_hole_area_m2:.2f} m² "
        f"= {maximum_hole_pixels} pixels"
    )

    print(
        f"Opening distance: "
        f"{opening_distance_m:.2f} m "
        f"= {opening_radius_pixels} pixels"
    )

    print(
        f"Final patch area: "
        f"{final_patch_area_m2:.2f} m² "
        f"= {final_patch_pixels} pixels"
    )

    print_stats(
        step_name="Original spray mask",
        mask_bool=spray_bool,
        valid_mask=valid_mask,
        pixel_area_m2=pixel_area_m2,
    )

    # Step 1: Remove small isolated patches
    step1_bool = remove_small_objects(
        spray_bool,
        min_size=initial_patch_pixels,
        connectivity=2,
    )

    step1_bool &= valid_mask

    save_cleaning_step(
        step_name="Step 1: remove small objects",
        mask_bool=step1_bool,
        valid_mask=valid_mask,
        pixel_area_m2=pixel_area_m2,
        profile=profile,
        raster_path=raster_paths["step1"],
        figure_path=figure_paths["step1"],
        figure_title=(
            "Step 1: Remove Small Objects "
            f"({initial_patch_area_m2:.2f} m²)"
        ),
    )

    # Step 2: Connect nearby spray pixels
    step2_bool = binary_closing(
        step1_bool,
        footprint=disk(closing_radius_pixels),
    )

    step2_bool &= valid_mask

    save_cleaning_step(
        step_name="Step 2: binary closing",
        mask_bool=step2_bool,
        valid_mask=valid_mask,
        pixel_area_m2=pixel_area_m2,
        profile=profile,
        raster_path=raster_paths["step2"],
        figure_path=figure_paths["step2"],
        figure_title=(
            "Step 2: Binary Closing "
            f"({closing_distance_m:.2f} m)"
        ),
    )

    # Step 3: Fill small holes inside spray areas
    step3_bool = remove_small_holes(
        step2_bool,
        area_threshold=maximum_hole_pixels,
        connectivity=2,
    )

    step3_bool &= valid_mask

    save_cleaning_step(
        step_name="Step 3: remove small holes",
        mask_bool=step3_bool,
        valid_mask=valid_mask,
        pixel_area_m2=pixel_area_m2,
        profile=profile,
        raster_path=raster_paths["step3"],
        figure_path=figure_paths["step3"],
        figure_title=(
            "Step 3: Fill Holes "
            f"(< {maximum_hole_area_m2:.2f} m²)"
        ),
    )

    # Step 4: Remove thin strings
    step4_bool = binary_opening(
        step3_bool,
        footprint=disk(opening_radius_pixels),
    )

    step4_bool &= valid_mask

    save_cleaning_step(
        step_name="Step 4: remove thin strings",
        mask_bool=step4_bool,
        valid_mask=valid_mask,
        pixel_area_m2=pixel_area_m2,
        profile=profile,
        raster_path=raster_paths["step4"],
        figure_path=figure_paths["step4"],
        figure_title=(
            "Step 4: Remove Thin Strings "
            f"({opening_distance_m:.2f} m)"
        ),
    )

    # Patch diagnostic after Step 4
    labelled_patches = label(
        step4_bool,
        connectivity=2,
    )

    patch_sizes = np.bincount(
        labelled_patches.ravel()
    )[1:]

    print("\nPatch diagnostic after Step 4")
    print("-" * 40)
    print(f"Number of spray patches: {len(patch_sizes)}")

    if len(patch_sizes) > 0:
        patch_areas = patch_sizes * pixel_area_m2

        print(
            f"Smallest patch: "
            f"{patch_sizes.min()} pixels "
            f"({patch_areas.min():.2f} m²)"
        )

        print(
            f"Largest patch: "
            f"{patch_sizes.max()} pixels "
            f"({patch_areas.max():.2f} m²)"
        )

        print(
            f"Mean patch area: "
            f"{patch_areas.mean():.2f} m²"
        )

        print(
            f"Patches below {final_patch_area_m2:.2f} m²: "
            f"{np.sum(patch_sizes < final_patch_pixels)}"
        )

        print(
            f"Patches kept: "
            f"{np.sum(patch_sizes >= final_patch_pixels)}"
        )

        print("\nAll spray patches after Step 4")
        print("-" * 40)

        sorted_patch_sizes = sorted(
            enumerate(patch_sizes, start=1),
            key=lambda item: item[1],
            reverse=True,
        )

        for patch_id, patch_pixels in sorted_patch_sizes:
            patch_area_m2 = (
                patch_pixels * pixel_area_m2
            )

            status = (
                "KEEP"
                if patch_pixels >= final_patch_pixels
                else "REMOVE"
            )

            print(
                f"Patch {patch_id}: "
                f"{patch_area_m2:.2f} m² "
                f"({patch_pixels} pixels) - {status}"
            )

    # Step 5: Final cleanup
    step5_bool = remove_small_objects(
        step4_bool,
        min_size=final_patch_pixels,
        connectivity=2,
    )

    step5_bool &= valid_mask

    save_cleaning_step(
        step_name="Step 5: final cleanup",
        mask_bool=step5_bool,
        valid_mask=valid_mask,
        pixel_area_m2=pixel_area_m2,
        profile=profile,
        raster_path=raster_paths["step5"],
        figure_path=figure_paths["step5"],
        figure_title=(
            "Step 5: Final Cleanup "
            f"({final_patch_area_m2:.2f} m²)"
        ),
    )

    print(
        "\nFinal cleaned spray mask: "
        f"{raster_paths['step5']}"
    )

    return raster_paths["step5"]


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Clean a spray mask using metric parameters."
        )
    )

    parser.add_argument(
        "input_mask_path",
        help="Path to the original spray mask",
    )

    parser.add_argument(
        "--output-data-dir",
        default="data/processed/cleaning",
    )

    parser.add_argument(
        "--output-figure-dir",
        default="outputs/figures/cleaning",
    )

    parser.add_argument(
        "--initial-patch-area-m2",
        type=float,
        default=121.5,
    )

    parser.add_argument(
        "--closing-distance-m",
        type=float,
        default=2.70,
    )

    parser.add_argument(
        "--maximum-hole-area-m2",
        type=float,
        default=162.0,
    )

    parser.add_argument(
        "--opening-distance-m",
        type=float,
        default=2.25,
    )

    parser.add_argument(
        "--final-patch-area-m2",
        type=float,
        default=243.0,
    )

    parser.add_argument(
        "--overwrite",
        action="store_true",
    )

    args = parser.parse_args()

    try:
        clean_spray_mask(
            input_mask_path=args.input_mask_path,
            output_data_dir=args.output_data_dir,
            output_figure_dir=args.output_figure_dir,
            initial_patch_area_m2=args.initial_patch_area_m2,
            closing_distance_m=args.closing_distance_m,
            maximum_hole_area_m2=args.maximum_hole_area_m2,
            opening_distance_m=args.opening_distance_m,
            final_patch_area_m2=args.final_patch_area_m2,
            overwrite=args.overwrite,
        )

    except Exception as error:
        parser.exit(status=1, message=f"Error: {error}\n")


if __name__ == "__main__":
    main()