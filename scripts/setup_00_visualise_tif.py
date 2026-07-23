import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import rasterio


def visualise_tif(tif_path, band=1, ndvi=False):
    """Display one band from a TIF file."""

    tif_path = Path(tif_path)

    if not tif_path.is_file():
        raise FileNotFoundError(
            f"TIF file not found: {tif_path}"
        )

    with rasterio.open(tif_path) as src:
        if band < 1 or band > src.count:
            raise ValueError(
                f"Band {band} is invalid. "
                f"{tif_path.name} contains {src.count} band(s)."
            )

        data = src.read(
            band,
            masked=True,
        ).astype("float32")

        data = data.filled(np.nan)

    valid_data = data[np.isfinite(data)]

    if valid_data.size == 0:
        raise ValueError(
            f"Band {band} does not contain any valid data."
        )

    figure, axis = plt.subplots(figsize=(8, 8))

    if ndvi:
        image = axis.imshow(
            data,
            cmap="RdYlGn",
            vmin=-1,
            vmax=1,
        )

        figure.colorbar(image, ax=axis, label="NDVI")
        axis.set_title(f"NDVI Preview: {tif_path.name}")

    else:
        vmin = np.nanpercentile(data, 2)
        vmax = np.nanpercentile(data, 98)

        if vmin == vmax:
            vmin -= 0.5
            vmax += 0.5

        image = axis.imshow(
            data,
            cmap="gray",
            vmin=vmin,
            vmax=vmax,
        )

        figure.colorbar(
            image,
            ax=axis,
            label="Pixel value",
        )

        axis.set_title(f"TIF Preview: {tif_path.name}")

    axis.axis("off")

    print(f"Displaying: {tif_path.name}, band {band}")

    plt.show()
    plt.close(figure)


def visualise_path(
    path,
    band=1,
    ndvi=False,
    recursive=False,
):
    """Visualise one TIF file or all TIF files in a folder."""

    input_path = Path(path)

    if input_path.is_file():
        if input_path.suffix.lower() not in {".tif", ".tiff"}:
            raise ValueError(
                "The selected file is not a TIF file."
            )

        tif_files = [input_path]

    elif input_path.is_dir():
        search_method = (
            input_path.rglob("*")
            if recursive
            else input_path.glob("*")
        )

        tif_files = sorted(
            file
            for file in search_method
            if file.is_file()
            and file.suffix.lower() in {".tif", ".tiff"}
        )

    else:
        raise FileNotFoundError(
            f"Invalid file or folder path: {input_path}"
        )

    if not tif_files:
        raise FileNotFoundError(
            f"No TIF files were found in: {input_path}"
        )

    print(f"\nFound {len(tif_files)} TIF file(s).")

    for tif_file in tif_files:
        visualise_tif(
            tif_path=tif_file,
            band=band,
            ndvi=ndvi,
        )


def main():
    """Allow the script to run independently."""

    parser = argparse.ArgumentParser(
        description="Visualise TIF files."
    )

    parser.add_argument(
        "path",
        help="Path to a TIF file or folder",
    )

    parser.add_argument(
        "--band",
        type=int,
        default=1,
        help="Band number to display",
    )

    parser.add_argument(
        "--ndvi",
        action="store_true",
        help="Use the NDVI colour scale from -1 to 1",
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search inside subfolders",
    )

    args = parser.parse_args()

    try:
        visualise_path(
            path=args.path,
            band=args.band,
            ndvi=args.ndvi,
            recursive=args.recursive,
        )

    except Exception as error:
        parser.exit(status=1, message=f"Error: {error}\n")


if __name__ == "__main__":
    main()