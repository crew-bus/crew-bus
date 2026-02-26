"""
Image generation bridge for Crew Bus agents.

Supports Leonardo.ai (primary) and Ideogram (fallback).
Generated images are saved to /tmp/ and the path is returned so agents
can chain into twitter_bridge.upload_media() or other uses.

Credentials stored in crew_config:
  - leonardo_api_key
  - ideogram_api_key
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

import bus

DEFAULT_DB = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_key(name: str, db_path: Optional[Path] = None) -> str:
    val = bus.get_config(name, "", db_path)
    if not val:
        raise ValueError(f"Missing credential: {name}. Store via /api/config/set.")
    return val


def _http_post(url: str, payload: dict, headers: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:500]
        return {"error": f"HTTP {e.code}", "detail": err}
    except Exception as e:
        return {"error": str(e)}


def _http_get(url: str, headers: dict = None) -> bytes:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _save_image(data: bytes, suffix: str = ".png") -> str:
    """Save image bytes to /tmp/ with a unique name."""
    import tempfile
    fd, path = tempfile.mkstemp(prefix="crewbus_img_", suffix=suffix)
    import os
    os.write(fd, data)
    os.close(fd)
    return path


# ---------------------------------------------------------------------------
# Leonardo.ai
# ---------------------------------------------------------------------------

def generate_image(prompt: str, style: str = "PHOTO",
                   width: int = 1024, height: int = 1024,
                   db_path: Optional[Path] = None) -> str:
    """Generate an image via Leonardo.ai.

    Polls until the generation completes, downloads the first image, saves
    it to /tmp/, and returns the local file path.

    Args:
        prompt: Text description of the desired image.
        style:  Leonardo style preset (PHOTO, ILLUSTRATION, ANIME, etc.).
        width:  Output width in pixels (default 1024).
        height: Output height in pixels (default 1024).

    Returns:
        Local file path (str) of the downloaded PNG, or raises on error.
    """
    api_key = _get_key("leonardo_api_key", db_path)
    headers = {"Authorization": f"Bearer {api_key}"}

    # POST /generations
    payload = {
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_images": 1,
        "presetStyle": style,
        "modelId": "b24e16ff-06e3-43eb-8d33-4416c2d75876",  # Leonardo Phoenix
    }
    resp = _http_post(
        "https://cloud.leonardo.ai/api/rest/v1/generations",
        payload, headers,
    )
    if resp.get("error"):
        raise RuntimeError(f"Leonardo generation failed: {resp}")

    generation_id = resp.get("sdGenerationJob", {}).get("generationId")
    if not generation_id:
        raise RuntimeError(f"No generationId returned: {resp}")

    # Poll until done (max 90s)
    poll_url = f"https://cloud.leonardo.ai/api/rest/v1/generations/{generation_id}"
    for _ in range(30):
        time.sleep(3)
        poll = _http_post(  # GET via helper doesn't fit; use urllib directly
            poll_url, {}, {**headers, "Content-Type": "application/json"}
        )
        # Actually need GET here
        req = urllib.request.Request(poll_url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                poll = json.loads(r.read().decode())
        except Exception as e:
            continue

        gen = poll.get("generations_by_pk", {})
        if gen.get("status") == "COMPLETE":
            images = gen.get("generated_images", [])
            if not images:
                raise RuntimeError("Generation complete but no images returned")
            img_url = images[0]["url"]
            img_bytes = _http_get(img_url)
            return _save_image(img_bytes, ".png")

    raise RuntimeError(f"Leonardo generation timed out: {generation_id}")


# ---------------------------------------------------------------------------
# Ideogram
# ---------------------------------------------------------------------------

def generate_ideogram(prompt: str, aspect_ratio: str = "ASPECT_1_1",
                      db_path: Optional[Path] = None) -> str:
    """Generate an image via Ideogram.

    Returns local file path of downloaded image.

    Args:
        prompt:       Text description of the desired image.
        aspect_ratio: ASPECT_1_1, ASPECT_16_9, ASPECT_9_16, etc.
    """
    api_key = _get_key("ideogram_api_key", db_path)
    headers = {"Api-Key": api_key}

    payload = {
        "image_request": {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "model": "V_2",
            "magic_prompt_option": "AUTO",
        }
    }
    resp = _http_post("https://api.ideogram.ai/generate", payload, headers)
    if resp.get("error"):
        raise RuntimeError(f"Ideogram generation failed: {resp}")

    images = resp.get("data", [])
    if not images:
        raise RuntimeError(f"No images returned from Ideogram: {resp}")

    img_url = images[0].get("url")
    if not img_url:
        raise RuntimeError(f"No image URL in Ideogram response: {images[0]}")

    img_bytes = _http_get(img_url)
    return _save_image(img_bytes, ".png")


# ---------------------------------------------------------------------------
# Smart generate — tries Leonardo first, falls back to Ideogram
# ---------------------------------------------------------------------------

def generate(prompt: str, style: str = "PHOTO",
             db_path: Optional[Path] = None) -> str:
    """Generate an image. Tries Leonardo first; falls back to Ideogram.

    Returns local file path ready for twitter_bridge.upload_media().
    """
    try:
        return generate_image(prompt, style=style, db_path=db_path)
    except Exception as leo_err:
        try:
            return generate_ideogram(prompt, db_path=db_path)
        except Exception as ideo_err:
            raise RuntimeError(
                f"Both generators failed. Leonardo: {leo_err}. Ideogram: {ideo_err}"
            ) from ideo_err


# ---------------------------------------------------------------------------
# Status check
# ---------------------------------------------------------------------------

def status(db_path: Optional[Path] = None) -> dict:
    leo = bool(bus.get_config("leonardo_api_key", "", db_path))
    ideo = bool(bus.get_config("ideogram_api_key", "", db_path))
    return {
        "leonardo": leo,
        "ideogram": ideo,
        "configured": leo or ideo,
    }
