from pathlib import Path
import argparse
import rasterio


def inspect_tif(tif_path):
    """Print the metadata and band statistics of one TIF file."""

    print("=" * 80)
    print(f"File: {tif_path}")

    try:
        with rasterio.open(tif_path) as src:
            print(f"CRS: {src.crs}")
            print(f"Bands: {src.count}")
            print(f"Data type: {src.dtypes}")
            print(f"NoData: {src.nodata}")
            print(f"Width: {src.width}")
            print(f"Height: {src.height}")
            print(f"Transform: {src.transform}")

            for band in range(1, src.count + 1):
                data = src.read(band, masked=True)
                valid = data.compressed()

                if valid.size > 0:
                    print(
                        f"Band {band}: "
                        f"min={valid.min()}, "
                        f"max={valid.max()}, "
                        f"mean={valid.mean():.2f}"
                    )
                else:
                    print(f"Band {band}: No valid data")

    except Exception as error:
        print(f"Error reading file: {error}")

    print()


def inspect_path(path, recursive=False):
    """Find and inspect TIF files from a file or folder path."""

    input_path = Path(path)

    if input_path.is_file():
        if input_path.suffix.lower() not in {".tif", ".tiff"}:
            print("The selected file is not a TIF file.")
            return

        tif_files = [input_path]

    elif input_path.is_dir():
        search_method = input_path.rglob("*") if recursive else input_path.glob("*")

        tif_files = sorted(
            file
            for file in search_method
            if file.is_file() and file.suffix.lower() in {".tif", ".tiff"}
        )

    else:
        print("Invalid path. Please provide a valid TIF file or folder.")
        return

    print(f"Found {len(tif_files)} TIF file(s)\n")

    if not tif_files:
        print("No TIF files were found.")
        return

    for tif_file in tif_files:
        inspect_tif(tif_file)


def main():
    """Allow this script to run independently from the terminal."""

    parser = argparse.ArgumentParser(
        description="Inspect TIF files and print raster metadata."
    )

    parser.add_argument(
        "path",
        help="Path to a TIF file or folder containing TIF files",
    )

    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search inside subfolders",
    )

    args = parser.parse_args()

    inspect_path(
        path=args.path,
        recursive=args.recursive,
    )


if __name__ == "__main__":
    main()