"""
generate_icons.py — Generate custom icons for Multi-Agent Travel Planner UI.

Uses Azure OpenAI gpt-image-1.5 with Entra (Azure AD) authentication
to create consistent, modern flat-design icons.

Usage:
    uv run generate_icons.py             # Generate all icons
    uv run generate_icons.py app-icon    # Generate a single icon by name
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from io import BytesIO
from pathlib import Path

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from dotenv import load_dotenv
from openai import AzureOpenAI
from PIL import Image

load_dotenv()

ENDPOINT = os.getenv(
    "AZURE_OPENAI_IMAGE_ENDPOINT",
    "https://sw-v2-project-resource.openai.azure.com/openai/v1/",
)
MODEL = os.getenv("AZURE_OPENAI_IMAGE_MODEL", "gpt-image-1.5")
OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "../frontend/src/assets/icons"))

# Icon size for the UI (px) — generated at 1024x1024, resized to this
ICON_SIZE = 128

# Consistent style prefix applied to every icon prompt
STYLE_PREFIX = (
    "A single flat-design icon on a pure white background, minimalist modern style, "
    "clean vector-like look with smooth rounded shapes, soft pastel accent colors, "
    "no text, no shadows, no gradients, centered composition, suitable for a "
    "professional light-mode web application UI at small sizes. "
    "The icon should be simple, recognizable, and elegant. "
)

# Icon definitions: name -> subject-specific prompt addition
ICONS: dict[str, str] = {
    # Agent icons
    "agent-facilitator": (
        "A stylized crosshair / target symbol representing coordination and facilitation. "
        "Use soft purple tones (#7C3AED, #A78BFA)."
    ),
    "agent-logistics": (
        "A stylized modern train or transport vehicle representing logistics and travel routing. "
        "Use soft blue tones (#2563EB, #60A5FA)."
    ),
    "agent-sightseeing": (
        "A stylized classical landmark building with columns representing sightseeing and tourism. "
        "Use soft green tones (#059669, #34D399)."
    ),
    "agent-experience": (
        "A stylized theater mask (comedy mask) representing cultural experiences and entertainment. "
        "Use soft amber/orange tones (#D97706, #FBBF24)."
    ),
    "agent-food": (
        "A stylized beer glass and fork representing food and drinks culture. "
        "Use soft red/warm tones (#DC2626, #F87171)."
    ),
    # Section header icons
    "app-icon": (
        "A stylized paper airplane or travel airplane taking off, representing a travel planner application. "
        "Use vibrant purple and blue tones (#7C3AED, #3B82F6)."
    ),
    "timeline": (
        "A stylized clock or timeline with small dots along a line, representing a sequence of events. "
        "Use soft gray and blue tones (#6B7280, #93C5FD)."
    ),
    "chat": (
        "A stylized speech bubble representing chat and conversation. "
        "Use soft gray and purple tones (#6B7280, #A78BFA)."
    ),
    "taskboard": (
        "A stylized clipboard with checkmark lines representing a task board or checklist. "
        "Use soft gray and green tones (#6B7280, #34D399)."
    ),
    "document": (
        "A stylized document or paper with text lines representing a shared document. "
        "Use soft gray and blue tones (#6B7280, #60A5FA)."
    ),
    # Status / action icons
    "globe": (
        "A stylized earth globe showing continents, representing world travel and exploration. "
        "Use soft blue and green tones (#3B82F6, #34D399)."
    ),
    "tool": (
        "A stylized lightning bolt representing a tool action or API call. "
        "Use soft yellow and gray tones (#EAB308, #6B7280)."
    ),
    "rocket": (
        "A stylized rocket launching upward representing workflow start or launch. "
        "Use soft blue and orange tones (#3B82F6, #F97316)."
    ),
    "finish-flag": (
        "A stylized checkered flag representing completion or finish line. "
        "Use soft green and dark tones (#059669, #374151)."
    ),
    "message": (
        "A stylized small speech bubble with three dots representing a message being typed. "
        "Use soft gray tones (#6B7280, #9CA3AF)."
    ),
    "warning": (
        "A stylized triangle with exclamation mark representing a warning or error. "
        "Use soft red and orange tones (#DC2626, #F97316)."
    ),
    "checkmark": (
        "A stylized checkmark inside a circle representing task completion or success. "
        "Use soft green tones (#059669, #34D399)."
    ),
    "hourglass": (
        "A stylized hourglass with sand representing pending or in-progress state. "
        "Use soft amber and gray tones (#D97706, #9CA3AF)."
    ),
}


def get_client() -> AzureOpenAI:
    """Create an AzureOpenAI client with Entra token authentication."""
    # Strip trailing slash and /openai/v1/ suffix to get base endpoint
    endpoint = ENDPOINT.rstrip("/")
    if endpoint.endswith("/openai/v1"):
        endpoint = endpoint[: -len("/openai/v1")]

    credential = DefaultAzureCredential()
    token_provider = get_bearer_token_provider(
        credential, "https://cognitiveservices.azure.com/.default"
    )

    return AzureOpenAI(
        azure_endpoint=endpoint,
        azure_ad_token_provider=token_provider,
        api_version="2025-04-01-preview",
    )


def generate_icon(client: AzureOpenAI, name: str, prompt_detail: str) -> Image.Image:
    """Generate a single icon and return it as a PIL Image."""
    full_prompt = STYLE_PREFIX + prompt_detail
    print(f"  Generating '{name}' ...")

    result = client.images.generate(
        model=MODEL,
        prompt=full_prompt,
        size="1024x1024",
        n=1,
        quality="medium",
        background="transparent",
        output_format="png",
    )

    # Decode base64 image data
    image_bytes = base64.b64decode(result.data[0].b64_json)
    img = Image.open(BytesIO(image_bytes)).convert("RGBA")
    return img


def resize_and_save(img: Image.Image, output_path: Path, size: int = ICON_SIZE) -> None:
    """Resize image to target size and save as PNG."""
    resized = img.resize((size, size), Image.Resampling.LANCZOS)
    resized.save(output_path, "PNG", optimize=True)
    print(f"  Saved: {output_path} ({size}x{size})")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate icons for Multi-Agent Travel Planner")
    parser.add_argument(
        "icons",
        nargs="*",
        help="Icon names to generate (default: all). Use --list to see available names.",
    )
    parser.add_argument("--list", action="store_true", help="List all available icon names")
    parser.add_argument("--size", type=int, default=ICON_SIZE, help=f"Output icon size in px (default: {ICON_SIZE})")
    args = parser.parse_args()

    if args.list:
        print("Available icons:")
        for name in sorted(ICONS):
            print(f"  {name}")
        return

    icon_size = args.size

    # Determine which icons to generate
    targets = args.icons if args.icons else list(ICONS.keys())
    unknown = [n for n in targets if n not in ICONS]
    if unknown:
        print(f"Error: Unknown icon(s): {', '.join(unknown)}", file=sys.stderr)
        print("Use --list to see available names.", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(__file__).parent / OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Generating {len(targets)} icon(s) → {output_dir.resolve()}")
    print(f"Model: {MODEL} | Size: {icon_size}x{icon_size}")
    print()

    client = get_client()

    for name in targets:
        try:
            img = generate_icon(client, name, ICONS[name])
            resize_and_save(img, output_dir / f"{name}.png", icon_size)
            print()
        except Exception as e:
            print(f"  ERROR generating '{name}': {e}", file=sys.stderr)
            print()

    print("Done!")


if __name__ == "__main__":
    main()
