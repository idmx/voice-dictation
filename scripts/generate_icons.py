"""Generate placeholder tray icon PNGs for Voice Dictation.

Creates three icons:
  - idle.png (gray circle)
  - recording.png (red circle)
  - processing.png (yellow circle)
"""

from pathlib import Path

from PIL import Image, ImageDraw


ICON_SIZE = 64
CIRCLE_MARGIN = 8


def create_circle_icon(
    size: int = ICON_SIZE,
    fill_color: tuple[int, int, int, int] = (128, 128, 128, 255),
    outline_color: tuple[int, int, int, int] = (255, 255, 255, 255),
    outline_width: int = 2,
) -> Image.Image:
    """Create a circular icon with the given fill color."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bbox = [
        CIRCLE_MARGIN,
        CIRCLE_MARGIN,
        size - CIRCLE_MARGIN - 1,
        size - CIRCLE_MARGIN - 1,
    ]
    draw.ellipse(bbox, fill=fill_color, outline=outline_color, width=outline_width)

    return img


def create_microphone_icon(
    size: int = ICON_SIZE,
    body_color: tuple[int, int, int, int] = (128, 128, 128, 255),
) -> Image.Image:
    """Create a microphone-style icon with a circle background and mic shape."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    circle_bbox = [2, 2, size - 3, size - 3]
    draw.ellipse(circle_bbox, fill=(40, 40, 40, 200), outline=body_color, width=2)

    mic_x = size // 2
    mic_top = size // 4
    mic_bottom = size * 3 // 5
    mic_width = size // 6

    draw.rounded_rectangle(
        [mic_x - mic_width, mic_top, mic_x + mic_width, mic_bottom],
        radius=mic_width // 2,
        fill=body_color,
    )

    arc_bbox = [mic_x - mic_width - 4, mic_top + 4, mic_x + mic_width + 4, mic_bottom + 8]
    draw.arc(arc_bbox, start=0, end=180, fill=body_color, width=2)

    stand_y = mic_bottom + 4
    draw.line([mic_x, mic_bottom, mic_x, stand_y + 6], fill=body_color, width=2)
    draw.line([mic_x - mic_width, stand_y + 6, mic_x + mic_width, stand_y + 6], fill=body_color, width=2)

    return img


def main() -> None:
    """Generate all icon files."""
    output_dir = Path(__file__).parent.parent / "assets" / "icons"
    output_dir.mkdir(parents=True, exist_ok=True)

    icons = {
        "idle.png": create_microphone_icon(
            body_color=(140, 140, 140, 255),
        ),
        "recording.png": create_microphone_icon(
            body_color=(220, 50, 50, 255),
        ),
        "processing.png": create_microphone_icon(
            body_color=(230, 200, 50, 255),
        ),
        "idle_circle.png": create_circle_icon(
            fill_color=(140, 140, 140, 255),
        ),
        "recording_circle.png": create_circle_icon(
            fill_color=(220, 50, 50, 255),
        ),
        "processing_circle.png": create_circle_icon(
            fill_color=(230, 200, 50, 255),
        ),
    }

    for filename, icon in icons.items():
        filepath = output_dir / filename
        icon.save(filepath, "PNG")
        print(f"Generated: {filepath}")

    print(f"\nAll {len(icons)} icons generated in {output_dir}")


if __name__ == "__main__":
    main()
