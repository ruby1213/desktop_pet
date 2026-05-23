import os
import shutil
import re


def sort_by_name(dir = ".",pattern = "_"):
    """
    Sort files into folders based on prefix before a separator pattern.
    """
    moved, skipped = 0, 0

    for filename in os.listdir(dir):
        if os.path.isdir(os.path.join(dir, filename)):
            continue

        match = re.match(rf"^([^{re.escape(pattern)}]+){re.escape(pattern)}",filename)

        if not match:
            skipped += 1
            continue

        prefix = match.group(1)

        folder_path = os.path.join(dir,prefix)
        os.makedirs(folder_path, exist_ok=True)

        src = os.path.join(dir,filename)
        dst = os.path.join(folder_path,filename)
        shutil.move(src,dst)

        moved += 1
        print(f"Move: {filename} -> {prefix}/")
    print(f"{moved} files moved, {skipped} files skipped")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sort files into folders by prefix.")
    parser.add_argument("directory", nargs="?", default=".", help="Target directory")
    parser.add_argument("--pattern", default="_", help="Separator pattern (default: _)")

    args = parser.parse_args()
    sort_by_name(args.directory, args.pattern)
