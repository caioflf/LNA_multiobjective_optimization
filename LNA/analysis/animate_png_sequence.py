#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create a GIF or MP4 animation from ordered PNG frames."
    )
    parser.add_argument(
        "input",
        help="Directory containing PNG files, or a glob pattern.",
    )
    parser.add_argument(
        "--output",
        help="Output animation path. Extension decides format: .gif or .mp4.",
    )
    parser.add_argument(
        "--pattern",
        default="*.png",
        help="Glob used when input is a directory. Default: *.png.",
    )
    parser.add_argument("--fps", type=float, default=8.0)
    parser.add_argument(
        "--engine",
        choices=("auto", "ffmpeg", "pillow"),
        default="auto",
        help="Animation backend. Pillow supports GIF only.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output file.",
    )
    parser.add_argument(
        "--loop",
        type=int,
        default=0,
        help="GIF loop count. 0 means loop forever.",
    )
    return parser.parse_args()


def natural_key(path):
    parts = re.split(r"(\d+)", str(path))
    return [int(part) if part.isdigit() else part.lower() for part in parts]


def resolve_frames(input_path, pattern):
    input_path = Path(input_path)
    if input_path.is_dir():
        frames = sorted(input_path.glob(pattern), key=natural_key)
    else:
        frames = sorted(input_path.parent.glob(input_path.name), key=natural_key)

    frames = [frame for frame in frames if frame.is_file()]
    if not frames:
        raise FileNotFoundError(
            f"No PNG frames found for input={input_path} pattern={pattern}"
        )
    return frames


def default_output_path(input_path):
    input_path = Path(input_path)
    if input_path.is_dir():
        return input_path.with_suffix(".gif")
    return input_path.parent / "animation.gif"


def require_output_path(path, overwrite):
    path = Path(path)
    if path.exists() and not overwrite:
        raise FileExistsError(
            f"Output already exists: {path}. Pass --overwrite to replace it."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def choose_engine(engine, output_path):
    if engine != "auto":
        return engine
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    if output_path.suffix.lower() == ".gif":
        return "pillow"
    return "ffmpeg"


def link_frames(frames, temp_dir):
    temp_dir = Path(temp_dir)
    for index, frame in enumerate(frames):
        target = temp_dir / f"frame_{index:06d}.png"
        try:
            target.symlink_to(frame.resolve())
        except OSError:
            shutil.copy2(frame, target)


def animate_with_ffmpeg(frames, output_path, fps):
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg was not found. Install ffmpeg or use GIF output with "
            "--engine pillow."
        )

    suffix = output_path.suffix.lower()
    with tempfile.TemporaryDirectory(prefix="png_animation_") as temp_dir:
        link_frames(frames, temp_dir)
        input_pattern = str(Path(temp_dir) / "frame_%06d.png")
        command = [
            "ffmpeg",
            "-y",
            "-framerate",
            f"{fps:g}",
            "-i",
            input_pattern,
        ]
        if suffix == ".mp4":
            command.extend(
                [
                    "-vf",
                    "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                    "-pix_fmt",
                    "yuv420p",
                ]
            )
        elif suffix == ".gif":
            command.extend(["-loop", "0"])
        else:
            raise ValueError("Unsupported output extension. Use .gif or .mp4.")
        command.append(str(output_path))
        subprocess.run(command, check=True)


def animate_with_pillow(frames, output_path, fps, loop):
    if output_path.suffix.lower() != ".gif":
        raise ValueError("Pillow backend only supports .gif output.")
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required for GIF output without ffmpeg. Use "
            "ANALYSIS_PLOT_PYTHON=/opt/homebrew/bin/python3 on this machine."
        ) from exc

    duration_ms = max(1, int(round(1000.0 / fps)))
    images = []
    for frame in frames:
        image = Image.open(frame)
        images.append(image.convert("P", palette=Image.Palette.ADAPTIVE))
    first, rest = images[0], images[1:]
    first.save(
        output_path,
        save_all=True,
        append_images=rest,
        duration=duration_ms,
        loop=loop,
        optimize=True,
    )
    for image in images:
        image.close()


def main():
    args = parse_args()
    if args.fps <= 0:
        raise ValueError("--fps must be positive")

    frames = resolve_frames(args.input, args.pattern)
    output_path = require_output_path(
        args.output or default_output_path(args.input),
        args.overwrite,
    )
    engine = choose_engine(args.engine, output_path)

    if engine == "ffmpeg":
        animate_with_ffmpeg(frames, output_path, args.fps)
    else:
        animate_with_pillow(frames, output_path, args.fps, args.loop)

    print(f"[animate_png_sequence] frames: {len(frames):,}")
    print(f"[animate_png_sequence] engine: {engine}")
    print(f"[animate_png_sequence] output: {output_path}")


if __name__ == "__main__":
    main()
