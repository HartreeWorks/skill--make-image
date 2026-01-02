#!/usr/bin/env python3
"""Generate images using Krea AI API (Nano Banana Pro)."""

import argparse
import ftplib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from datetime import datetime

import requests
from dotenv import load_dotenv

# Load .env from the skill directory
SKILL_DIR = Path(__file__).parent
load_dotenv(SKILL_DIR / ".env")

API_KEY = os.getenv("KREA_API_KEY")
BASE_URL = "https://api.krea.ai"
JOBS_URL = f"{BASE_URL}/jobs"
IMAGES_DIR = SKILL_DIR / "images"
LAST_IMAGE_FILE = SKILL_DIR / ".last_image.json"
LOG_FILE = SKILL_DIR / "generation_log.jsonl"

# FTP configuration for uploading local images
FTP_HOST = os.getenv("FTP_HOST")
FTP_PORT = int(os.getenv("FTP_PORT", "21"))
FTP_USER = os.getenv("FTP_USER")
FTP_PASS = os.getenv("FTP_PASS")
FTP_REMOTE_PATH = os.getenv("FTP_REMOTE_PATH", "/")
FTP_PUBLIC_URL = os.getenv("FTP_PUBLIC_URL", "")

# Model configurations
MODELS = {
    "nano": {
        "url": f"{BASE_URL}/generate/image/google/nano-banana",
        "cost": 0.08,
        "name": "Nano Banana",
    },
    "pro": {
        "url": f"{BASE_URL}/generate/image/google/nano-banana-pro",
        "cost": 0.30,
        "name": "Nano Banana Pro",
    },
}

TOPAZ_URL = f"{BASE_URL}/generate/enhance/topaz/standard-enhance"
BLOOM_URL = f"{BASE_URL}/generate/enhance/topaz/bloom-enhance"
TOPAZ_COST = 0.15  # ~51 compute units, ~19 seconds
BLOOM_COST = 0.75  # ~256 compute units, ~132 seconds

# Upscale presets for different image types
UPSCALE_PRESETS = {
    "portrait": {
        "description": "Portrait photograph (face preservation enabled)",
        "engine": "topaz",
        "topaz": {
            "model": "High Fidelity V2",
            "sharpen": 0.4,
            "denoise": 0.3,
            "fix_compression": 0.4,
            "face_enhancement": True,
        },
        "bloom": {
            "creativity": 2,
            "face_preservation": True,
            "color_preservation": True,
        },
    },
    "photo": {
        "description": "General photograph (realistic, preserve details)",
        "engine": "topaz",
        "topaz": {
            "model": "High Fidelity V2",
            "sharpen": 0.5,
            "denoise": 0.3,
            "fix_compression": 0.5,
            "face_enhancement": False,
        },
        "bloom": {
            "creativity": 2,
            "face_preservation": False,
            "color_preservation": True,
        },
    },
    "artwork": {
        "description": "Digital art, illustration, or AI-generated image",
        "engine": "topaz",
        "topaz": {
            "model": "Standard V2",
            "sharpen": 0.6,
            "denoise": 0.2,
            "fix_compression": 0.3,
            "face_enhancement": False,
        },
        "bloom": {
            "creativity": 4,
            "face_preservation": False,
            "color_preservation": False,
        },
    },
    "cgi": {
        "description": "3D render or CGI content",
        "engine": "topaz",
        "topaz": {
            "model": "CGI",
            "sharpen": 0.5,
            "denoise": 0.1,
            "fix_compression": 0.2,
            "face_enhancement": False,
        },
        "bloom": {
            "creativity": 3,
            "face_preservation": False,
            "color_preservation": True,
        },
    },
    "lowres": {
        "description": "Low resolution or heavily compressed source",
        "engine": "bloom",
        "topaz": {
            "model": "Low Resolution V2",
            "sharpen": 0.3,
            "denoise": 0.7,
            "fix_compression": 0.8,
            "face_enhancement": False,
        },
        "bloom": {
            "creativity": 5,
            "face_preservation": False,
            "color_preservation": False,
        },
    },
    "text": {
        "description": "Image with important text/typography",
        "engine": "topaz",
        "topaz": {
            "model": "Text Refine",
            "sharpen": 0.7,
            "denoise": 0.2,
            "fix_compression": 0.5,
            "face_enhancement": False,
        },
        "bloom": {
            "creativity": 1,
            "face_preservation": False,
            "color_preservation": True,
        },
    },
    "creative": {
        "description": "Creative reimagining (adds details, more artistic)",
        "engine": "bloom",
        "topaz": {
            "model": "Standard V2",
            "sharpen": 0.5,
            "denoise": 0.3,
            "fix_compression": 0.5,
            "face_enhancement": False,
        },
        "bloom": {
            "creativity": 6,
            "face_preservation": False,
            "color_preservation": False,
        },
    },
}


def log_generation(entry: dict) -> None:
    """Append a generation entry to the log file."""
    with open(LOG_FILE, "a") as f:
        f.write(json.dumps(entry) + "\n")


def upload_to_ftp(local_path: str) -> str:
    """Upload a local image to FTP server and return the public URL.

    Args:
        local_path: Path to the local image file

    Returns:
        Public URL of the uploaded image

    Raises:
        ValueError: If FTP is not configured
        RuntimeError: If upload fails
    """
    if not all([FTP_HOST, FTP_USER, FTP_PASS, FTP_PUBLIC_URL]):
        raise ValueError(
            "FTP not configured. Please set FTP_HOST, FTP_USER, FTP_PASS, and FTP_PUBLIC_URL in .env"
        )

    local_file = Path(local_path)
    if not local_file.exists():
        raise ValueError(f"File not found: {local_path}")

    # Generate unique filename to avoid collisions
    ext = local_file.suffix or ".png"
    unique_name = f"{uuid.uuid4().hex[:12]}{ext}"
    remote_filename = f"{FTP_REMOTE_PATH.rstrip('/')}/{unique_name}"

    print(f"Uploading {local_file.name} to FTP server...")

    try:
        # Connect to FTP server
        ftp = ftplib.FTP()
        ftp.connect(FTP_HOST, FTP_PORT, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.set_pasv(True)  # Use passive mode

        # Ensure remote directory exists (create if needed)
        remote_dir = FTP_REMOTE_PATH.rstrip('/')
        if remote_dir:
            try:
                ftp.cwd(remote_dir)
            except ftplib.error_perm:
                # Try to create the directory structure
                parts = remote_dir.strip('/').split('/')
                current = ""
                for part in parts:
                    current = f"{current}/{part}"
                    try:
                        ftp.cwd(current)
                    except ftplib.error_perm:
                        try:
                            ftp.mkd(current)
                            ftp.cwd(current)
                        except ftplib.error_perm:
                            pass

        # Upload the file
        with open(local_file, 'rb') as f:
            ftp.storbinary(f'STOR {unique_name}', f)

        ftp.quit()

        # Construct public URL
        public_url = f"{FTP_PUBLIC_URL.rstrip('/')}/{unique_name}"
        print(f"Uploaded to: {public_url}")
        return public_url

    except ftplib.all_errors as e:
        raise RuntimeError(f"FTP upload failed: {e}")


def is_url(path: str) -> bool:
    """Check if a string is a URL."""
    return path.startswith(('http://', 'https://'))


def is_local_file(path: str) -> bool:
    """Check if a string is a local file path that exists."""
    if is_url(path):
        return False
    return Path(path).exists()


def resolve_image_url(path: str) -> str:
    """Resolve an image path to a URL, uploading if necessary.

    Args:
        path: Either a URL or local file path

    Returns:
        A publicly accessible URL
    """
    if is_url(path):
        return path

    if is_local_file(path):
        return upload_to_ftp(path)

    raise ValueError(f"Invalid image path: {path} (not a URL or existing file)")


def slugify(text: str, max_length: int = 50) -> str:
    """Convert text to a URL-friendly slug."""
    # Lowercase and replace spaces with hyphens
    slug = text.lower().strip()
    # Remove special characters, keep only alphanumeric and spaces
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    # Replace whitespace with hyphens
    slug = re.sub(r'[\s_]+', '-', slug)
    # Remove consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    # Strip leading/trailing hyphens
    slug = slug.strip('-')
    # Truncate to max length at word boundary
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit('-', 1)[0]
    return slug or "image"


def generate_image(
    prompt: str,
    model: str = "nano",
    aspect_ratio: str = "1:1",
    resolution: str = "1K",
    source_image_url: str = None,
    edit_strength: float = 0.8,
) -> tuple[str, str, str]:
    """Generate an image from a text prompt using Krea AI.

    Args:
        prompt: Text description of the image to generate
        model: Model to use ("nano" or "pro")
        aspect_ratio: Image aspect ratio (1:1, 16:9, 9:16, 4:3, 3:4, etc.)
        resolution: Image resolution for Pro (1K, 2K, or 4K)
        source_image_url: URL of source image for editing (enables edit mode)
        edit_strength: How much to preserve the source image (0.0-1.0, default 0.8)

    Returns:
        Tuple of (local_file_path, folder_path, krea_image_url)
    """
    if not API_KEY:
        raise ValueError("KREA_API_KEY not found. Please set it in ~/.claude/skills/generate-image/.env")

    model_config = MODELS[model]
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    # Build payload - both Nano models use the same parameters
    payload = {
        "prompt": prompt,
        "aspectRatio": aspect_ratio,
        "numImages": 1,
    }
    # Only Nano Banana Pro supports resolution parameter
    if model == "pro":
        payload["resolution"] = resolution

    # Add source image for editing
    if source_image_url:
        payload["styleImages"] = [{"url": source_image_url, "strength": edit_strength}]
        print(f"Editing image with {model_config['name']}...")
        print(f"Source: {source_image_url[:60]}...")
        print(f"Edit strength: {edit_strength}")
    else:
        print(f"Generating image with {model_config['name']}...")

    print(f"Prompt: {prompt[:100]}{'...' if len(prompt) > 100 else ''}")
    print(f"Aspect ratio: {aspect_ratio}" + (f", Resolution: {resolution}" if model == "pro" else ""))

    # Submit job
    response = requests.post(model_config["url"], headers=headers, json=payload, timeout=30)

    if response.status_code == 401:
        raise RuntimeError("Invalid API key. Check your KREA_API_KEY.")
    if response.status_code == 402:
        raise RuntimeError("Insufficient credits. Top up at krea.ai")
    if response.status_code != 200:
        raise RuntimeError(f"API request failed ({response.status_code}): {response.text}")

    data = response.json()
    job_id = data.get("job_id")

    if not job_id:
        raise RuntimeError(f"No job_id in response: {data}")

    print(f"Job submitted: {job_id}")

    # Poll for completion
    max_wait = 120  # seconds
    poll_interval = 2
    elapsed = 0

    while elapsed < max_wait:
        job_response = requests.get(f"{JOBS_URL}/{job_id}", headers=headers, timeout=30)

        if job_response.status_code != 200:
            raise RuntimeError(f"Failed to get job status: {job_response.text}")

        job_data = job_response.json()
        status = job_data.get("status")

        if status == "completed":
            print("Generation complete!")
            break
        elif status == "failed":
            raise RuntimeError(f"Job failed: {job_data}")
        elif status == "cancelled":
            raise RuntimeError("Job was cancelled")

        # Show progress
        print(f"  Status: {status}...", end="\r")
        time.sleep(poll_interval)
        elapsed += poll_interval
    else:
        raise RuntimeError(f"Job timed out after {max_wait}s")

    # Get image URL
    result = job_data.get("result", {})
    urls = result.get("urls", [])

    if not urls:
        raise RuntimeError(f"No image URLs in result: {job_data}")

    image_url = urls[0]

    # Download image
    img_response = requests.get(image_url, timeout=60)
    if img_response.status_code != 200:
        raise RuntimeError(f"Failed to download image: {img_response.status_code}")

    # Determine extension from content-type or URL
    content_type = img_response.headers.get("Content-Type", "")
    if "png" in content_type or image_url.endswith(".png"):
        ext = ".png"
    elif "webp" in content_type or image_url.endswith(".webp"):
        ext = ".webp"
    else:
        ext = ".jpg"

    # Generate output path: /images/yyyy-mm-dd/hh-mm-ss-slug.ext
    now = datetime.now()
    date_folder = IMAGES_DIR / now.strftime("%Y-%m-%d")
    date_folder.mkdir(parents=True, exist_ok=True)

    time_prefix = now.strftime("%H-%M-%S")
    slug = slugify(prompt)
    filename = f"{time_prefix}-{model}-{slug}{ext}"
    output_file = date_folder / filename

    # Save image
    output_file.write_bytes(img_response.content)
    print(f"Image saved to: {output_file.absolute()}")

    # Show estimated cost
    print(f"Estimated cost: ${model_config['cost']:.2f}")

    # Build log entry
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "local_path": str(output_file.absolute()),
        "krea_url": image_url,
        "prompt": prompt,
        "model": model,
        "model_name": model_config["name"],
        "aspect_ratio": aspect_ratio,
        "cost": model_config["cost"],
        "is_edit": source_image_url is not None,
    }
    if source_image_url:
        log_entry["source_image_url"] = source_image_url
        log_entry["edit_strength"] = edit_strength
    if model == "pro":
        log_entry["resolution"] = resolution

    # Log the generation
    log_generation(log_entry)

    # Save last image info for easy editing
    LAST_IMAGE_FILE.write_text(json.dumps(log_entry, indent=2))
    print(f"Krea URL: {image_url}")

    return str(output_file.absolute()), str(date_folder.absolute()), image_url


def upscale_image(
    image_url: str,
    scale_factor: int = 2,
    output_format: str = "png",
    model: str = "Standard V2",
    sharpen: float = 0.5,
    denoise: float = 0.3,
    fix_compression: float = 0.5,
    face_enhancement: bool = False,
    source_width: int = None,
    source_height: int = None,
) -> tuple[str, str, str]:
    """Upscale an image using Topaz enhancement.

    Args:
        image_url: URL of the image to upscale
        scale_factor: How much to scale (1-32, default 2)
        output_format: Output format (png, jpg, webp)
        model: Enhancement model (Standard V2, Low Resolution V2, CGI, High Fidelity V2, Text Refine)
        sharpen: Sharpening amount (0.0-1.0, default 0.5)
        denoise: Denoising amount (0.0-1.0, default 0.3)
        fix_compression: Compression artifact fix (0.0-1.0, default 0.5)
        face_enhancement: Enable face enhancement (default False)
        source_width: Source image width (auto-detected if not provided)
        source_height: Source image height (auto-detected if not provided)

    Returns:
        Tuple of (local_file_path, folder_path, krea_image_url)
    """
    if not API_KEY:
        raise ValueError("KREA_API_KEY not found. Please set it in ~/.claude/skills/generate-image/.env")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    # Try to get source image dimensions if not provided
    if source_width is None or source_height is None:
        try:
            # Fetch image headers to get dimensions (some CDNs include this)
            # Fallback to reasonable defaults for Krea-generated images
            source_width = source_width or 1024
            source_height = source_height or 1024
        except Exception:
            source_width = 1024
            source_height = 1024

    # Calculate target dimensions based on scale factor
    target_width = min(source_width * scale_factor, 22000)  # Cap at 22K (Topaz max)
    target_height = min(source_height * scale_factor, 22000)

    payload = {
        "image_url": image_url,
        "width": target_width,
        "height": target_height,
        "model": model,
        "upscaling_activated": True,
        "image_scaling_factor": scale_factor,
        "output_format": output_format,
        "sharpen": sharpen,
        "denoise": denoise,
        "fix_compression": fix_compression,
        "face_enhancement": face_enhancement,
    }

    if face_enhancement:
        payload["face_enhancement_creativity"] = 0.5
        payload["face_enhancement_strength"] = 0.5

    print(f"Upscaling image with Topaz {model} ({scale_factor}x)...")
    print(f"Source: {image_url[:60]}...")
    print(f"Target dimensions: {target_width}x{target_height}")

    # Submit job
    response = requests.post(TOPAZ_URL, headers=headers, json=payload, timeout=30)

    if response.status_code == 401:
        raise RuntimeError("Invalid API key. Check your KREA_API_KEY.")
    if response.status_code == 402:
        raise RuntimeError("Insufficient credits. Top up at krea.ai")
    if response.status_code != 200:
        raise RuntimeError(f"API request failed ({response.status_code}): {response.text}")

    data = response.json()
    job_id = data.get("job_id")

    if not job_id:
        raise RuntimeError(f"No job_id in response: {data}")

    print(f"Job submitted: {job_id}")

    # Poll for completion
    max_wait = 120
    poll_interval = 2
    elapsed = 0

    while elapsed < max_wait:
        job_response = requests.get(f"{JOBS_URL}/{job_id}", headers=headers, timeout=30)

        if job_response.status_code != 200:
            raise RuntimeError(f"Failed to get job status: {job_response.text}")

        job_data = job_response.json()
        status = job_data.get("status")

        if status == "completed":
            print("Upscale complete!")
            break
        elif status == "failed":
            raise RuntimeError(f"Job failed: {job_data}")
        elif status == "cancelled":
            raise RuntimeError("Job was cancelled")

        print(f"  Status: {status}...", end="\r")
        time.sleep(poll_interval)
        elapsed += poll_interval
    else:
        raise RuntimeError(f"Job timed out after {max_wait}s")

    # Get image URL
    result = job_data.get("result", {})
    urls = result.get("urls", [])

    if not urls:
        raise RuntimeError(f"No image URLs in result: {job_data}")

    upscaled_url = urls[0]

    # Download image
    img_response = requests.get(upscaled_url, timeout=60)
    if img_response.status_code != 200:
        raise RuntimeError(f"Failed to download image: {img_response.status_code}")

    # Determine extension
    ext = f".{output_format}" if output_format != "jpg" else ".jpg"

    # Generate output path
    now = datetime.now()
    date_folder = IMAGES_DIR / now.strftime("%Y-%m-%d")
    date_folder.mkdir(parents=True, exist_ok=True)

    time_prefix = now.strftime("%H-%M-%S")
    filename = f"{time_prefix}-upscale-{scale_factor}x{ext}"
    output_file = date_folder / filename

    # Save image
    output_file.write_bytes(img_response.content)
    print(f"Image saved to: {output_file.absolute()}")
    print(f"Estimated cost: ${TOPAZ_COST:.2f}")

    # Log the upscale
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "local_path": str(output_file.absolute()),
        "krea_url": upscaled_url,
        "source_url": image_url,
        "operation": "upscale_topaz",
        "engine": "topaz",
        "scale_factor": scale_factor,
        "upscale_model": model,
        "target_dimensions": f"{target_width}x{target_height}",
        "sharpen": sharpen,
        "denoise": denoise,
        "fix_compression": fix_compression,
        "face_enhancement": face_enhancement,
        "cost": TOPAZ_COST,
    }
    log_generation(log_entry)

    # Save as last image
    LAST_IMAGE_FILE.write_text(json.dumps(log_entry, indent=2))
    print(f"Krea URL: {upscaled_url}")

    return str(output_file.absolute()), str(date_folder.absolute()), upscaled_url


def upscale_bloom(
    image_url: str,
    scale_factor: int = 2,
    output_format: str = "png",
    creativity: int = 3,
    face_preservation: bool = False,
    color_preservation: bool = False,
    prompt: str = "",
    source_width: int = None,
    source_height: int = None,
) -> tuple[str, str, str]:
    """Upscale an image using Bloom creative enhancement.

    Bloom is a creative upscaler that adds details while upscaling.
    Better for low-res sources or when you want artistic enhancement.

    Args:
        image_url: URL of the image to upscale
        scale_factor: How much to scale (1-32, default 2)
        output_format: Output format (png, jpg, webp)
        creativity: How creative the enhancement should be (1-9, default 3)
        face_preservation: Preserve faces accurately (default False)
        color_preservation: Preserve original colors (default False)
        prompt: Optional prompt to guide enhancement
        source_width: Source image width (auto-detected if not provided)
        source_height: Source image height (auto-detected if not provided)

    Returns:
        Tuple of (local_file_path, folder_path, krea_image_url)
    """
    if not API_KEY:
        raise ValueError("KREA_API_KEY not found. Please set it in ~/.claude/skills/generate-image/.env")

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    # Default dimensions for Krea-generated images
    if source_width is None:
        source_width = 1024
    if source_height is None:
        source_height = 1024

    # Calculate target dimensions (Bloom max is 10K)
    target_width = min(source_width * scale_factor, 10000)
    target_height = min(source_height * scale_factor, 10000)

    payload = {
        "image_url": image_url,
        "width": target_width,
        "height": target_height,
        "model": "Reimagine",
        "creativity": creativity,
        "face_preservation": face_preservation,
        "color_preservation": color_preservation,
        "upscaling_activated": True,
        "image_scaling_factor": scale_factor,
        "output_format": output_format,
    }

    if prompt:
        payload["prompt"] = prompt

    print(f"Upscaling image with Bloom ({scale_factor}x, creativity={creativity})...")
    print(f"Source: {image_url[:60]}...")
    print(f"Target dimensions: {target_width}x{target_height}")
    if face_preservation:
        print("Face preservation: enabled")
    if color_preservation:
        print("Color preservation: enabled")

    # Submit job
    response = requests.post(BLOOM_URL, headers=headers, json=payload, timeout=30)

    if response.status_code == 401:
        raise RuntimeError("Invalid API key. Check your KREA_API_KEY.")
    if response.status_code == 402:
        raise RuntimeError("Insufficient credits. Top up at krea.ai")
    if response.status_code != 200:
        raise RuntimeError(f"API request failed ({response.status_code}): {response.text}")

    data = response.json()
    job_id = data.get("job_id")

    if not job_id:
        raise RuntimeError(f"No job_id in response: {data}")

    print(f"Job submitted: {job_id}")
    print("(Bloom takes ~2 minutes to complete)")

    # Poll for completion (Bloom takes longer ~132s)
    max_wait = 300  # 5 minutes max
    poll_interval = 5
    elapsed = 0

    while elapsed < max_wait:
        job_response = requests.get(f"{JOBS_URL}/{job_id}", headers=headers, timeout=30)

        if job_response.status_code != 200:
            raise RuntimeError(f"Failed to get job status: {job_response.text}")

        job_data = job_response.json()
        status = job_data.get("status")

        if status == "completed":
            print("Upscale complete!")
            break
        elif status == "failed":
            raise RuntimeError(f"Job failed: {job_data}")
        elif status == "cancelled":
            raise RuntimeError("Job was cancelled")

        print(f"  Status: {status} ({elapsed}s)...", end="\r")
        time.sleep(poll_interval)
        elapsed += poll_interval
    else:
        raise RuntimeError(f"Job timed out after {max_wait}s")

    # Get image URL
    result = job_data.get("result", {})
    urls = result.get("urls", [])

    if not urls:
        raise RuntimeError(f"No image URLs in result: {job_data}")

    upscaled_url = urls[0]

    # Download image
    img_response = requests.get(upscaled_url, timeout=120)
    if img_response.status_code != 200:
        raise RuntimeError(f"Failed to download image: {img_response.status_code}")

    # Determine extension
    ext = f".{output_format}" if output_format != "jpg" else ".jpg"

    # Generate output path
    now = datetime.now()
    date_folder = IMAGES_DIR / now.strftime("%Y-%m-%d")
    date_folder.mkdir(parents=True, exist_ok=True)

    time_prefix = now.strftime("%H-%M-%S")
    filename = f"{time_prefix}-bloom-{scale_factor}x{ext}"
    output_file = date_folder / filename

    # Save image
    output_file.write_bytes(img_response.content)
    print(f"Image saved to: {output_file.absolute()}")
    print(f"Estimated cost: ${BLOOM_COST:.2f}")

    # Log the upscale
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "local_path": str(output_file.absolute()),
        "krea_url": upscaled_url,
        "source_url": image_url,
        "operation": "upscale_bloom",
        "engine": "bloom",
        "scale_factor": scale_factor,
        "creativity": creativity,
        "face_preservation": face_preservation,
        "color_preservation": color_preservation,
        "target_dimensions": f"{target_width}x{target_height}",
        "cost": BLOOM_COST,
    }
    if prompt:
        log_entry["prompt"] = prompt
    log_generation(log_entry)

    # Save as last image
    LAST_IMAGE_FILE.write_text(json.dumps(log_entry, indent=2))
    print(f"Krea URL: {upscaled_url}")

    return str(output_file.absolute()), str(date_folder.absolute()), upscaled_url


def interactive_upscale(image_url: str) -> tuple[str, str, str]:
    """Interactive upscale mode - asks user for image type and settings."""
    print("\n=== Interactive Upscale Mode ===\n")
    print("What type of image is this?\n")

    # Show preset options
    presets_list = list(UPSCALE_PRESETS.items())
    for i, (key, preset) in enumerate(presets_list, 1):
        recommended = preset["engine"]
        print(f"  {i}. {preset['description']} [{recommended}]")

    print(f"\n  0. Custom settings")

    # Get user choice
    while True:
        try:
            choice = input("\nSelect option (1-7, or 0 for custom): ").strip()
            choice_num = int(choice)
            if 0 <= choice_num <= len(presets_list):
                break
            print(f"Please enter a number between 0 and {len(presets_list)}")
        except ValueError:
            print("Please enter a valid number")

    # Get scale factor
    while True:
        try:
            scale_input = input("\nScale factor (1-32, default 2): ").strip()
            if not scale_input:
                scale_factor = 2
                break
            scale_factor = int(scale_input)
            if 1 <= scale_factor <= 32:
                break
            print("Please enter a number between 1 and 32")
        except ValueError:
            print("Please enter a valid number")

    if choice_num == 0:
        # Custom settings
        return interactive_custom_upscale(image_url, scale_factor)

    # Use preset
    preset_key = presets_list[choice_num - 1][0]
    preset = UPSCALE_PRESETS[preset_key]

    # Ask which engine to use (default to preset recommendation)
    print(f"\nUpscale engine (recommended: {preset['engine']}):")
    print("  1. Topaz - Fast (~19s), precise, $0.15")
    print("  2. Bloom - Slow (~2min), creative, $0.75")

    while True:
        engine_input = input(f"\nSelect engine (1-2, default {1 if preset['engine'] == 'topaz' else 2}): ").strip()
        if not engine_input:
            engine = preset["engine"]
            break
        if engine_input == "1":
            engine = "topaz"
            break
        if engine_input == "2":
            engine = "bloom"
            break
        print("Please enter 1 or 2")

    settings = preset[engine]
    print(f"\nUsing {preset_key} preset with {engine} engine...")

    if engine == "topaz":
        return upscale_image(
            image_url,
            scale_factor=scale_factor,
            model=settings["model"],
            sharpen=settings["sharpen"],
            denoise=settings["denoise"],
            fix_compression=settings["fix_compression"],
            face_enhancement=settings["face_enhancement"],
        )
    else:
        return upscale_bloom(
            image_url,
            scale_factor=scale_factor,
            creativity=settings["creativity"],
            face_preservation=settings["face_preservation"],
            color_preservation=settings["color_preservation"],
        )


def interactive_custom_upscale(image_url: str, scale_factor: int) -> tuple[str, str, str]:
    """Custom upscale settings."""
    print("\n--- Custom Upscale Settings ---\n")

    # Choose engine
    print("Select engine:")
    print("  1. Topaz - Fast (~19s), precise enhancement")
    print("  2. Bloom - Creative (~2min), adds details")

    while True:
        engine_input = input("\nEngine (1-2): ").strip()
        if engine_input == "1":
            engine = "topaz"
            break
        if engine_input == "2":
            engine = "bloom"
            break
        print("Please enter 1 or 2")

    if engine == "topaz":
        # Topaz settings
        print("\nTopaz model:")
        print("  1. Standard V2 - General purpose")
        print("  2. High Fidelity V2 - Maximum detail")
        print("  3. Low Resolution V2 - For very low-res sources")
        print("  4. CGI - For 3D renders")
        print("  5. Text Refine - Preserves text")

        models = ["Standard V2", "High Fidelity V2", "Low Resolution V2", "CGI", "Text Refine"]
        while True:
            model_input = input("\nModel (1-5, default 1): ").strip()
            if not model_input:
                model = "Standard V2"
                break
            try:
                model_idx = int(model_input) - 1
                if 0 <= model_idx < len(models):
                    model = models[model_idx]
                    break
            except ValueError:
                pass
            print("Please enter 1-5")

        # Get numeric settings
        sharpen = float(input("Sharpen (0.0-1.0, default 0.5): ").strip() or "0.5")
        denoise = float(input("Denoise (0.0-1.0, default 0.3): ").strip() or "0.3")
        fix_compression = float(input("Fix compression (0.0-1.0, default 0.5): ").strip() or "0.5")
        face_input = input("Enable face enhancement? (y/N): ").strip().lower()
        face_enhancement = face_input in ("y", "yes")

        return upscale_image(
            image_url,
            scale_factor=scale_factor,
            model=model,
            sharpen=sharpen,
            denoise=denoise,
            fix_compression=fix_compression,
            face_enhancement=face_enhancement,
        )
    else:
        # Bloom settings
        creativity = int(input("Creativity (1-9, default 3): ").strip() or "3")
        face_input = input("Enable face preservation? (y/N): ").strip().lower()
        face_preservation = face_input in ("y", "yes")
        color_input = input("Enable color preservation? (y/N): ").strip().lower()
        color_preservation = color_input in ("y", "yes")
        prompt = input("Optional prompt (press Enter to skip): ").strip()

        return upscale_bloom(
            image_url,
            scale_factor=scale_factor,
            creativity=creativity,
            face_preservation=face_preservation,
            color_preservation=color_preservation,
            prompt=prompt,
        )


def get_last_image_info():
    """Load info about the last generated image."""
    if LAST_IMAGE_FILE.exists():
        return json.loads(LAST_IMAGE_FILE.read_text())
    return None


def main():
    parser = argparse.ArgumentParser(description="Generate images using Krea AI")
    parser.add_argument("prompt", nargs="?", default=None,
                       help="Text prompt for generation/editing (not needed for upscale)")
    parser.add_argument("-m", "--model", default="nano",
                       choices=["nano", "pro"],
                       help="Model: nano ($0.08, default) or pro ($0.30)")
    parser.add_argument("-n", "--num", type=int, default=1,
                       help="Number of images (default: 1)")
    parser.add_argument("-a", "--aspect-ratio", default=None,
                       choices=["1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "5:4", "4:5", "21:9"],
                       help="Aspect ratio (default: 1:1, or inherited from source in edit mode)")
    parser.add_argument("-r", "--resolution", default="1K",
                       choices=["1K", "2K", "4K"],
                       help="Resolution for Pro model (default: 1K)")
    parser.add_argument("-e", "--edit", nargs="?", const="last", default=None,
                       help="Edit mode: use 'last' (default) or provide a Krea image URL")
    parser.add_argument("-s", "--strength", type=float, default=0.8,
                       help="Edit strength: how much to preserve source (0.0-1.0, default: 0.8)")
    parser.add_argument("-u", "--upscale", nargs="?", const="last", default=None,
                       help="Upscale mode: use 'last' (default) or provide a Krea image URL")
    parser.add_argument("-i", "--interactive", action="store_true",
                       help="Interactive upscale mode - asks for image type and settings")
    parser.add_argument("-x", "--scale", type=int, default=2,
                       help="Upscale factor (1-32, default: 2)")
    parser.add_argument("--engine", default="topaz",
                       choices=["topaz", "bloom"],
                       help="Upscale engine: topaz ($0.15, fast) or bloom ($0.75, creative)")
    parser.add_argument("--preset", default=None,
                       choices=["portrait", "photo", "artwork", "cgi", "lowres", "text", "creative"],
                       help="Use preset settings for image type")
    # Topaz-specific options
    parser.add_argument("--upscale-model", default="Standard V2",
                       choices=["Standard V2", "Low Resolution V2", "CGI", "High Fidelity V2", "Text Refine"],
                       help="Topaz model (default: Standard V2)")
    parser.add_argument("--sharpen", type=float, default=0.5,
                       help="Topaz sharpening (0.0-1.0, default: 0.5)")
    parser.add_argument("--denoise", type=float, default=0.3,
                       help="Topaz denoising (0.0-1.0, default: 0.3)")
    parser.add_argument("--fix-compression", type=float, default=0.5,
                       help="Topaz compression fix (0.0-1.0, default: 0.5)")
    parser.add_argument("--face-enhancement", action="store_true",
                       help="Topaz face enhancement")
    # Bloom-specific options
    parser.add_argument("--creativity", type=int, default=3,
                       help="Bloom creativity level (1-9, default: 3)")
    parser.add_argument("--face-preservation", action="store_true",
                       help="Bloom face preservation (keeps faces accurate)")
    parser.add_argument("--color-preservation", action="store_true",
                       help="Bloom color preservation (keeps original colors)")
    parser.add_argument("--upscale-prompt", default="",
                       help="Optional prompt to guide Bloom enhancement")

    args = parser.parse_args()
    num_images = args.num

    # Handle upscale mode (separate from generate/edit)
    if args.upscale:
        try:
            if args.upscale == "last":
                last_info = get_last_image_info()
                if not last_info:
                    print("Error: No previous image found. Generate an image first or provide a URL.", file=sys.stderr)
                    sys.exit(1)
                upscale_url = last_info.get("krea_url")
                print(f"Upscaling last image: {last_info.get('local_path', 'unknown')}")
            else:
                # Resolve path to URL (uploads local files to FTP if needed)
                upscale_url = resolve_image_url(args.upscale)
                if is_local_file(args.upscale):
                    print(f"Upscaling local image: {args.upscale}")
                else:
                    print("Upscaling image from URL")

            # Interactive mode
            if args.interactive:
                output_path, output_folder, krea_url = interactive_upscale(upscale_url)
            # Preset mode
            elif args.preset:
                preset = UPSCALE_PRESETS[args.preset]
                engine = args.engine if args.engine != "topaz" else preset["engine"]
                settings = preset[engine]
                print(f"Using {args.preset} preset with {engine} engine...")

                if engine == "topaz":
                    output_path, output_folder, krea_url = upscale_image(
                        upscale_url,
                        scale_factor=args.scale,
                        model=settings["model"],
                        sharpen=settings["sharpen"],
                        denoise=settings["denoise"],
                        fix_compression=settings["fix_compression"],
                        face_enhancement=settings["face_enhancement"],
                    )
                else:
                    output_path, output_folder, krea_url = upscale_bloom(
                        upscale_url,
                        scale_factor=args.scale,
                        creativity=settings["creativity"],
                        face_preservation=settings["face_preservation"],
                        color_preservation=settings["color_preservation"],
                    )
            # Direct engine selection
            elif args.engine == "bloom":
                output_path, output_folder, krea_url = upscale_bloom(
                    upscale_url,
                    scale_factor=args.scale,
                    creativity=args.creativity,
                    face_preservation=args.face_preservation,
                    color_preservation=args.color_preservation,
                    prompt=args.upscale_prompt,
                )
            # Default: Topaz
            else:
                output_path, output_folder, krea_url = upscale_image(
                    upscale_url,
                    scale_factor=args.scale,
                    model=args.upscale_model,
                    sharpen=args.sharpen,
                    denoise=args.denoise,
                    fix_compression=args.fix_compression,
                    face_enhancement=args.face_enhancement,
                )

            cost = BLOOM_COST if args.engine == "bloom" else TOPAZ_COST
            print(f"\nSuccess! Upscaled image saved to: {output_path}")

            if output_folder:
                subprocess.run(["open", output_folder], check=True)
                print(f"Opened folder in Finder: {output_folder}")

        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return  # Exit after upscaling

    # Prompt is required for generation/editing
    if not args.prompt:
        print("Error: prompt is required for generation/editing. Use -u for upscaling.", file=sys.stderr)
        sys.exit(1)

    # Handle edit mode
    source_image_url = None
    aspect_ratio = args.aspect_ratio or "1:1"

    if args.edit:
        if args.edit == "last":
            last_info = get_last_image_info()
            if not last_info:
                print("Error: No previous image found. Generate an image first or provide a URL.", file=sys.stderr)
                sys.exit(1)
            source_image_url = last_info["krea_url"]
            # Inherit aspect ratio from source if not specified
            if args.aspect_ratio is None:
                aspect_ratio = last_info.get("aspect_ratio", "1:1")
            print(f"Editing last image: {last_info['local_path']}")
        else:
            source_image_url = args.edit
            print(f"Editing image from URL")

    # Safety check for Pro model
    if args.model == "pro" and num_images > 1:
        print(f"Warning: Nano Banana Pro costs $0.30/image. Generating {num_images} images = ${num_images * 0.30:.2f}")

    try:
        output_paths = []
        total_cost = 0.0
        output_folder = None

        for i in range(num_images):
            if num_images > 1:
                print(f"--- Variation {i + 1}/{num_images} ---")
            output_path, output_folder, krea_url = generate_image(
                args.prompt,
                model=args.model,
                aspect_ratio=aspect_ratio,
                resolution=args.resolution,
                source_image_url=source_image_url,
                edit_strength=args.strength,
            )
            output_paths.append(output_path)
            total_cost += MODELS[args.model]["cost"]
            print()

        print(f"Success! {'Edited' if source_image_url else 'Generated'} {len(output_paths)} image(s)")
        for path in output_paths:
            print(f"  - {path}")
        print(f"Total estimated cost: ${total_cost:.2f}")

        # Open the day's folder in Finder
        if output_folder:
            subprocess.run(["open", output_folder], check=True)
            print(f"Opened folder in Finder: {output_folder}")

        # Suggest next steps
        if args.model == "nano":
            print("\nWant higher quality? Ask for a Nano Banana Pro version (-m pro, $0.30)")
        if not source_image_url:
            print("Want to edit this image? Use -e flag with your edit instructions")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
