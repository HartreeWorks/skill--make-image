---
name: make-image
description: This skill should be used when the user asks to generate, edit, or upscale images. Triggers: "make an image", "draw", "edit this image", "upscale". Uses Krea AI.
---

# Generate, Edit & Upscale Image Skill

Generate new images, edit existing ones, or upscale to higher resolution using Krea AI.

**Models:**
- **Nano Banana** - Good quality (~$0.08/image) - default for generation
- **Nano Banana Pro** - Higher quality (~$0.30/image) - only when explicitly requested
- **Topaz Upscale** - Fast, precise enhancement (~$0.15/image, ~19s) - use `-u` flag
- **Bloom Upscale** - Creative enhancement (~$0.75/image, ~2min) - use `-u --engine bloom`

**Three modes:**
1. **Generate**: Create new images from text prompts
2. **Edit**: Modify existing images while preserving composition (`-e` flag)
3. **Upscale**: Increase resolution with AI enhancement (`-u` flag, or `-u -i` for interactive)

**Default behavior**: Generate 1 image with Nano Banana, then ask user if they want edits, upscaling, or Pro version.

**IMPORTANT**: Never use Nano Banana Pro unless the user explicitly requests it. It costs $0.30 per image!

## Prerequisites

1. **API Key**: Get a Krea API key from https://krea.ai (Settings > API)

2. **Configure the key**: Add your API key to `~/.claude/skills/make-image/.env`:
   ```
   KREA_API_KEY=your_actual_key_here
   ```

3. **Install dependencies** (first time only):
   ```bash
   pip install requests python-dotenv
   ```

4. **(Optional) FTP for local image uploads**: To upscale local images, configure FTP in `.env`:
   ```
   FTP_HOST=your.ftp.server
   FTP_PORT=21
   FTP_USER=username
   FTP_PASS=password
   FTP_REMOTE_PATH=/path/to/upload/
   FTP_PUBLIC_URL=https://your.domain/path/to/upload/
   ```
   This allows upscaling local files by automatically uploading them to your server.

## Usage

Run the Python script:

```bash
python3 ~/.claude/skills/make-image/generate_image.py "your prompt here"
```

### Output Location

Images are automatically saved to:
```
~/.claude/skills/make-image/images/YYYY-MM-DD/HH-MM-SS-MODEL-prompt-slug.ext
```

After generation, the day's folder is automatically opened in **Finder** for easy browsing.

### Options

| Option | Description |
|--------|-------------|
| `-m`, `--model` | Model: `nano` ($0.08, default) or `pro` ($0.30) |
| `-n`, `--num` | Number of images (default: 1) |
| `-a`, `--aspect-ratio` | Aspect ratio: 1:1, 16:9, 9:16, 4:3, 3:4, etc. (default: 1:1) |
| `-r`, `--resolution` | Resolution for Pro model: 1K, 2K, or 4K (default: 1K) |
| `-e`, `--edit` | Edit mode: use alone for last image, or provide a Krea URL |
| `-s`, `--strength` | Edit strength: how much to preserve source (0.0-1.0, default: 0.8) |
| `-u`, `--upscale` | Upscale mode: use alone for last image, or provide a URL |
| `-i`, `--interactive` | Interactive upscale: asks for image type and settings |
| `-x`, `--scale` | Upscale factor: 1-32 (default: 2) |
| `--engine` | Upscale engine: `topaz` ($0.15, fast) or `bloom` ($0.75, creative) |
| `--preset` | Image type preset: portrait, photo, artwork, cgi, lowres, text, creative |
| `--upscale-model` | Topaz model: Standard V2, Low Resolution V2, CGI, High Fidelity V2, Text Refine |
| `--sharpen` | Topaz sharpening: 0.0-1.0 (default: 0.5) |
| `--denoise` | Topaz denoising: 0.0-1.0 (default: 0.3) |
| `--fix-compression` | Topaz compression fix: 0.0-1.0 (default: 0.5) |
| `--face-enhancement` | Topaz face enhancement |
| `--creativity` | Bloom creativity: 1-9 (default: 3) |
| `--face-preservation` | Bloom face preservation (keeps faces accurate) |
| `--color-preservation` | Bloom color preservation |
| `--upscale-prompt` | Optional prompt to guide Bloom enhancement |

### Examples

```bash
# Default: 1 Nano Banana image ($0.08)
python3 ~/.claude/skills/make-image/generate_image.py "A serene mountain landscape at sunset"

# Edit the last generated image
python3 ~/.claude/skills/make-image/generate_image.py "Make it nighttime with stars" -e

# Edit with lower strength (more creative freedom)
python3 ~/.claude/skills/make-image/generate_image.py "Add a red hat" -e -s 0.6

# Upscale the last image 2x ($0.15)
python3 ~/.claude/skills/make-image/generate_image.py -u

# Upscale 4x
python3 ~/.claude/skills/make-image/generate_image.py -u -x 4

# Nano Banana Pro (only if explicitly requested, $0.30)
python3 ~/.claude/skills/make-image/generate_image.py "Detailed botanical illustration" -m pro

# Pro at 4K resolution
python3 ~/.claude/skills/make-image/generate_image.py "Detailed botanical illustration" -m pro -r 4K

# Widescreen format
python3 ~/.claude/skills/make-image/generate_image.py "Panoramic beach scene" -a 16:9

# Multiple images
python3 ~/.claude/skills/make-image/generate_image.py "A cute cat" -n 3
```

## Editing Images

The skill supports editing images using the `-e` flag:

1. **Edit last generated image**: Use `-e` alone
2. **Edit by Krea URL**: Use `-e <krea_url>` for any image generated with this skill
3. **Edit external image**: Use `-e <any_public_url>` for images hosted elsewhere

**Edit strength** (`-s`): Controls how much of the original image to preserve:
- `0.9` - Very close to original, subtle changes
- `0.8` - Default, balanced editing
- `0.6` - More creative freedom
- `0.4` - Significant changes while keeping composition

**Editing external images:**
To edit an image not generated by this skill, you need a public URL. Options:
- Upload to imgur, imgbb, or similar service
- Use a publicly accessible URL
- Check `generation_log.jsonl` for Krea URLs of previous generations

The Krea URL for each image is saved and printed after generation, making it easy to reference specific images for editing.

## Upscaling Images

Two upscale engines are available:
- **Topaz** - Fast (~19s), precise, $0.15 - Best for most images
- **Bloom** - Slower (~2min), creative, $0.75 - Best for low-res sources or artistic enhancement

### Interactive Mode (Recommended)

Use `-i` to get an interactive menu that asks about your image type and recommends settings:

```bash
python3 ~/.claude/skills/make-image/generate_image.py -u -i
```

This will:
1. Ask what type of image (portrait, photo, artwork, etc.)
2. Ask for scale factor
3. Recommend the best engine and apply optimized settings

### Upscaling Local Files

With FTP configured (see Prerequisites), you can upscale local image files directly:

```bash
# Upscale a local file (auto-uploads to FTP server)
python3 ~/.claude/skills/make-image/generate_image.py -u "/path/to/image.jpg" --preset portrait

# Interactive mode with local file
python3 ~/.claude/skills/make-image/generate_image.py -u "/path/to/image.jpg" -i

# Works with any local path
python3 ~/.claude/skills/make-image/generate_image.py -u ~/Downloads/photo.png --preset photo
```

The script automatically:
1. Detects if the path is a local file
2. Uploads it to your FTP server
3. Uses the public URL for upscaling
4. Returns the upscaled result

### Presets

Use `--preset` for quick optimized settings without interaction:

```bash
# Portrait photograph (face preservation enabled)
python3 ~/.claude/skills/make-image/generate_image.py -u --preset portrait

# General photograph
python3 ~/.claude/skills/make-image/generate_image.py -u --preset photo

# Digital art or AI-generated image
python3 ~/.claude/skills/make-image/generate_image.py -u --preset artwork

# 3D render or CGI
python3 ~/.claude/skills/make-image/generate_image.py -u --preset cgi

# Low resolution or compressed source (uses Bloom)
python3 ~/.claude/skills/make-image/generate_image.py -u --preset lowres

# Image with text/typography
python3 ~/.claude/skills/make-image/generate_image.py -u --preset text

# Creative reimagining (uses Bloom, adds details)
python3 ~/.claude/skills/make-image/generate_image.py -u --preset creative
```

### Topaz Engine (Default)

Fast and precise upscaling. Best for high-quality sources.

```bash
# Basic 2x upscale with Topaz
python3 ~/.claude/skills/make-image/generate_image.py -u

# 4x upscale with face enhancement (for portraits)
python3 ~/.claude/skills/make-image/generate_image.py -u -x 4 --face-enhancement

# Maximum quality for photos
python3 ~/.claude/skills/make-image/generate_image.py -u --upscale-model "High Fidelity V2"

# For heavily compressed images
python3 ~/.claude/skills/make-image/generate_image.py -u --upscale-model "Low Resolution V2" --denoise 0.7 --fix-compression 0.8

# For 3D renders
python3 ~/.claude/skills/make-image/generate_image.py -u --upscale-model "CGI"

# Preserve text clarity
python3 ~/.claude/skills/make-image/generate_image.py -u --upscale-model "Text Refine"
```

**Topaz models**:
| Model | Best for |
|-------|----------|
| Standard V2 | General purpose (default) |
| High Fidelity V2 | Maximum detail preservation |
| Low Resolution V2 | Very low-res or compressed sources |
| CGI | 3D renders and CGI content |
| Text Refine | Images with text/typography |

**Topaz options**:
- `--sharpen` (0.0-1.0): Edge sharpness
- `--denoise` (0.0-1.0): Noise/grain removal
- `--fix-compression` (0.0-1.0): JPEG artifact fix
- `--face-enhancement`: AI face enhancement

### Bloom Engine

Creative upscaler that adds details while scaling. Better for low-res sources or artistic results.

```bash
# Basic Bloom upscale
python3 ~/.claude/skills/make-image/generate_image.py -u --engine bloom

# Bloom with face preservation (for portraits)
python3 ~/.claude/skills/make-image/generate_image.py -u --engine bloom --face-preservation

# Bloom with color preservation
python3 ~/.claude/skills/make-image/generate_image.py -u --engine bloom --color-preservation

# Bloom with high creativity (more artistic)
python3 ~/.claude/skills/make-image/generate_image.py -u --engine bloom --creativity 7

# Bloom with prompt guidance
python3 ~/.claude/skills/make-image/generate_image.py -u --engine bloom --upscale-prompt "detailed skin texture, sharp eyes"
```

**Bloom options**:
- `--creativity` (1-9): How creative the enhancement (1=conservative, 9=very creative)
- `--face-preservation`: Keep faces accurate (important for portraits!)
- `--color-preservation`: Keep original colors
- `--upscale-prompt`: Guide the enhancement with a prompt

### Scale Factors

`-x` or `--scale`: 1-32 (default: 2)
- `2` - Double resolution (1024→2048)
- `4` - Quadruple resolution (1024→4096)
- Higher values for large prints (Topaz up to 22K, Bloom up to 10K)

### Cost Comparison

| Engine | Cost | Time | Max Resolution | Best For |
|--------|------|------|----------------|----------|
| Topaz | $0.15 | ~19s | 22K | Most images, fast results |
| Bloom | $0.75 | ~2min | 10K | Low-res sources, artistic enhancement |

## Generation Log

All generations are logged to `~/.claude/skills/make-image/generation_log.jsonl` (JSON Lines format).

Each entry includes:
- `timestamp` - When the image was generated
- `local_path` - Path to the saved image file
- `krea_url` - Krea-hosted URL (for editing)
- `prompt` - The prompt used
- `model` / `model_name` - Which model was used
- `aspect_ratio` - Image dimensions
- `cost` - Estimated cost
- `is_edit` - Whether this was an edit
- `source_image_url` / `edit_strength` - Edit details (if applicable)

**View recent generations:**
```bash
tail -5 ~/.claude/skills/make-image/generation_log.jsonl | python3 -m json.tool
```

**Search by prompt:**
```bash
grep "robot" ~/.claude/skills/make-image/generation_log.jsonl
```

## Workflow

1. **Ask for the prompt**: If the user hasn't provided a detailed prompt, ask what they'd like to generate
2. **Ask about format** (optional): For specific use cases, ask about aspect ratio (social media, wallpaper, etc.)
3. **Generate with Nano Banana**: Run the script (default: 1 image)
4. **View the image**: Use the Read tool to look at the generated image
5. **Analyze and suggest**: Provide feedback on the image and suggest prompt improvements (see Post-Generation below)

## When User Requests Changes

**IMPORTANT**: When the user asks for changes to a recently generated image (e.g., "make it more photorealistic", "change the background", "less cartoony"), you MUST ask which approach they prefer:

1. **Edit the existing image** (`-e` flag) - Preserves composition/layout, transforms the style or adds/removes elements
2. **Generate from scratch** - Creates a completely new image with a revised prompt

Use the AskUserQuestion tool with options like:
- "Edit the current image (keeps composition, changes style)"
- "Generate fresh (new image from scratch)"

**When to default to editing**:
- Adding/removing elements while keeping style (add a hat, remove background)
- Lighting changes within the same style (make it darker, add shadows)
- Minor compositional tweaks (move element, change colors)

**When to default to fresh generation**:
- **Style transformations** (cartoon → photorealistic, illustration → photo) - edit mode preserves too much of the original style even at low strength
- Completely different composition, pose, or subject matter
- Major mood/aesthetic overhauls

When in doubt, ask.

### Intelligent Edit Strength Selection

When editing, automatically select the appropriate strength based on the type of change requested. **Do not ask the user about strength** - just pick the right value based on these heuristics:

| Change Type | Strength | Examples |
|-------------|----------|----------|
| **Lighting/mood changes** | `0.5` | "make it nighttime", "add dramatic lighting", "warmer colors", "make it spooky" |
| **Add/remove elements** | `0.6` | "add a hat", "remove the background", "add more books" |
| **Minor tweaks** | `0.7` | "change the text", "adjust the colors slightly", "fix the glasses" |
| **Subtle refinements** | `0.8` | "sharpen details", "small touch-ups" |

**Note**: Style transformations (cartoon → photorealistic) should use fresh generation, not edit mode.

**Rule of thumb**: The more dramatic the requested change, the lower the strength should be.

### Post-Edit Suggestions

After an edit, if the result doesn't match expectations, suggest:
- **Too similar to original**: "The edit preserved too much of the original. I can try again with lower strength (more creative freedom)."
- **Too different from original**: "The edit changed too much. I can try again with higher strength (preserves more of the original)."

Include the specific strength value you'd try next so the user understands the tradeoff.

## Post-Generation

After generating an image, **always use the Read tool to view the generated image**, then provide:

### 1. Image Analysis
Look at the generated image and consider:
- What is the user likely trying to achieve? (context from conversation, project, etc.)
- What works well in the generated image?
- What might the user want to improve?

### 2. Prompt Improvement Suggestions
Based on your analysis, suggest 1-2 specific prompt refinements. Consider:
- **Composition**: "Try adding 'close-up' or 'wide shot' to control framing"
- **Style**: "Adding 'digital art', 'photorealistic', or 'watercolor' could help"
- **Lighting**: "Specify 'golden hour', 'dramatic lighting', or 'soft diffused light'"
- **Details**: "Be more specific about [X] - e.g., 'a tabby cat' instead of 'a cat'"
- **What's missing**: If something seems off, suggest how to fix it

### 3. Offer Next Steps
After your analysis, offer:
- **Edit the image**: Keep most of it, change specific details (use `-e` flag)
- **Refined prompt**: Try again with improved prompt
- **Pro version**: Higher quality with Nano Banana Pro ($0.30)

**Example response:**
> Looking at your image, the composition is nice but the lighting feels flat. Since this seems to be for [context], you might want more dramatic lighting.
>
> I can:
> 1. **Edit this image** - "Add dramatic side lighting" (keeps the composition)
> 2. **New generation** with refined prompt: "A cheerful robot, dramatic side lighting, metallic reflections"
> 3. **Pro version** of this image ($0.30)
>
> Which would you prefer?

## Tips for Better Results

- Be specific and descriptive in prompts
- Include style references (e.g., "in the style of watercolor", "photorealistic")
- Specify composition details (e.g., "close-up", "wide angle", "aerial view")
- Add lighting and mood descriptors (e.g., "golden hour", "dramatic lighting")

## Pricing

Estimated costs:
- **Nano Banana**: ~$0.08/image (default for generation)
- **Nano Banana Pro**: ~$0.30/image (only when explicitly requested)
- **Topaz Upscale**: ~$0.15/image

Check your balance at krea.ai.

## Troubleshooting

If generation fails:
1. Check that KREA_API_KEY is set in `.env`
2. Verify you have sufficient credits at krea.ai
3. Some prompts may be rejected by content filters - try rephrasing


## Update check

This is a shared skill. Before executing, check `~/.claude/skills/.update-config.json`.
If `auto_check_enabled` is true and `last_checked_timestamp` is older than `check_frequency_days`,
mention: "It's been a while since skill updates were checked. Run `/update-skills` to see available updates."
Do NOT perform network operations - just check the local timestamp.

