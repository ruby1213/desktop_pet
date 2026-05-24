import os
import re
import numpy as np
from PIL import Image

def create_gif(directory, duration = 100, loop = 0, output_dir = None, mirror= False):
    """
    Create a GIF from images in a directory, sorted by number in filename.
    """
    if not os.path.isdir(directory):
        print(f"Not a directory: {directory}")
        return

    # Collect image files
    valid_ext = (".png", ".jpg", ".jpeg", ".webp")
    files = [ f for f in os.listdir(directory) if f.lower().endswith(valid_ext)]

    if not files:
        print(f"No images found in {directory}")
        return

     # Sort by the number found in filename
    def sort_key(filename):
        numbers = re.findall(r"\d+",filename)
        return int(numbers[-1]) if numbers else 0

    files.sort(key=sort_key)
    print(f"Frame order: {files}")

    # Load all frames first
    raw_frames = [Image.open(os.path.join(directory,f)) for f in files]

    if mirror:
        raw_frames = [f.transpose(Image.FLIP_LEFT_RIGHT) for f in raw_frames]

    # Find the largest canvas size across all frames
    max_width = max(f.size[0] for f in raw_frames)
    max_height = max(f.size[1] for f in raw_frames)
    print(f"Canvas size: {max_width} x {max_height}")

    frames = []

    for img in raw_frames:
        canvas = Image.new("RGBA", (max_width, max_height),(0,0,0,0))

        x = (max_width - img.width) // 2
        y = (max_height - img.height) // 2

        canvas.paste(img,( x, y),mask=img.split()[3])

        # Capture alpha before quantizing (transparent pixels will be set to index 255)
        alpha = np.array(canvas.split()[3])

        frame = canvas.convert("P",palette=Image.ADAPTIVE, colors=255)
        palette = frame.getpalette()

        # Overwrite transparent pixels with the transparency index
        frame_np = np.array(frame)
        frame_np[alpha == 0] = 255
        frame = Image.fromarray(frame_np, "P")
        frame.putpalette(palette)
        frame.info["transparency"] = 255
        # frame.info["disposal"] = 2  # restore to background before each frame
        frames.append(frame)


    # Output path
    dir_name = os.path.basename(directory)
    output_dir = output_dir or os.path.dirname(directory)
    gif_name = f"{dir_name}-mirror.gif" if mirror else f"{dir_name}.gif"
    output_path = os.path.join(output_dir, gif_name)

    # Save GIF
    frames[0].save(
        output_path,
        save_all = True,
        append_images = frames[1:],
        duration = duration,
        loop = loop, # use this if want loop
        format = "GIF",
        disposal = 2,
        optimize = False,
        transparency = 255
    )
    print(f"✓ Saved: {output_path} ({len(frames)} frames, {duration}ms/frame)")



if __name__ =="__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Create GIF animations from image directories.")
    parser.add_argument("--duration", type=int, default=124, help="Frame duration in ms (default: 100)")
    parser.add_argument("--loop", type=int, default=0, help="Loop count, 0 = infinite (default: 0)") # for looping
    parser.add_argument("--output", default=None, help="Output directory for GIFs")
    parser.add_argument("--directory", default=None, help="Process a single directory only")
    parser.add_argument("--mirror", action="store_true", help="Rotate frames 180° and save as {directory}-mirror.gif")

    args = parser.parse_args()

    create_gif(args.directory, duration=args.duration, output_dir=args.output, mirror=args.mirror)
