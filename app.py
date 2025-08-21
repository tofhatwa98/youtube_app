import os
import re
import shutil
import tempfile
from datetime import datetime
from flask import (
    Flask, request, render_template, send_file,
    redirect, url_for, flash, abort
)
from pytubefix import YouTube

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecret")  # for flash()

# --- Tunables ---
MAX_BYTES = 100 * 1024 * 1024   # ~100 MB safeguard for free-tier limits on some hosts
DEFAULT_RES_ORDER = ["720p", "480p", "360p", "240p"]
ALLOWED_RES = ["best"] + DEFAULT_RES_ORDER  # options exposed to users


def safe_filename(name: str, default: str = "download"):
    """Sanitize filename (no path traversal, keep basic characters)."""
    name = name or default
    name = re.sub(r"[^\w\-\.\s\(\)\[\]]+", "", name).strip()
    return name or default


def pick_progressive_stream(yt: YouTube, target_res: str):
    """
    Pick a progressive MP4 stream (video+audio).
    If target_res == 'best', pick highest under our order; otherwise try that or next lower.
    """
    streams = yt.streams.filter(progressive=True, file_extension="mp4")
    if not streams:
        return None

    if target_res == "best":
        ordered = streams.order_by("resolution").desc()
        return ordered.first()

    # Try requested resolution or next lower in DEFAULT_RES_ORDER
    order = DEFAULT_RES_ORDER
    # start from selected resolution index
    try:
        start_idx = order.index(target_res)
    except ValueError:
        start_idx = 0

    for res in order[start_idx:]:
        s = streams.filter(res=res).order_by("fps").desc().first()
        if s:
            return s

    # Fallback: best available
    return streams.order_by("resolution").desc().first()


def pick_audio_stream(yt: YouTube):
    """Pick the first audio-only stream (usually webm or m4a)."""
    s = yt.streams.filter(only_audio=True).order_by("abr").desc().first()
    return s


def estimate_size_bytes(stream):
    """Return precise or approximate filesize in bytes if available; else None."""
    size = getattr(stream, "filesize", None)
    if size:
        return size
    size_approx = getattr(stream, "filesize_approx", None)
    return size_approx


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = (request.form.get("url") or "").strip()
        mode = (request.form.get("mode") or "video").lower()  # 'video' or 'audio'
        target_res = (request.form.get("resolution") or "best").lower()

        if not url:
            flash("Please enter a YouTube URL.")
            return redirect(url_for("index"))

        # Basic URL sanity check
        if not (url.startswith("http://") or url.startswith("https://")):
            flash("Invalid URL. Please include http(s)://")
            return redirect(url_for("index"))

        try:
            # Use anti-bot token
            yt = YouTube(url, use_po_token=True)
        except Exception as e:
            flash(f"Failed to initialize YouTube object: {e}")
            return redirect(url_for("index"))

        try:
            if mode == "audio":
                stream = pick_audio_stream(yt)
                if not stream:
                    flash("No audio-only stream was found for this video.")
                    return redirect(url_for("index"))
            else:
                # default to video
                if target_res not in ALLOWED_RES:
                    target_res = "best"
                stream = pick_progressive_stream(yt, target_res)
                if not stream:
                    flash("No progressive MP4 stream found. Try audio-only.")
                    return redirect(url_for("index"))

            # Size checks (best-effort)
            est = estimate_size_bytes(stream)
            if est and est > MAX_BYTES:
                mb = round(est / (1024 * 1024), 1)
                flash(
                    f"This stream is about {mb} MB, which may exceed free hosting limits. "
                    f"Try a lower resolution or audio-only."
                )
                return redirect(url_for("index"))

            # Prepare temp dir and filename
            tmpdir = tempfile.mkdtemp(prefix="yt_")
            title = safe_filename(yt.title, default="video")
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

            if mode == "audio":
                # Derive container/extension from mime_type (e.g., 'audio/webm' or 'audio/mp4')
                mime = (stream.mime_type or "audio/webm").lower()
                ext = ".webm" if "webm" in mime else ".m4a" if "mp4" in mime else ".audio"
                fname = f"{title}_{timestamp}{ext}"
            else:
                # Video mode: MP4 progressive
                fname = f"{title}_{timestamp}.mp4"

            # Download
            filepath = stream.download(output_path=tmpdir, filename=fname)

            # Send and cleanup temp dir after sending completes
            # NOTE: send_file needs an absolute path; we also set a nice filename for the browser
            response = send_file(
                filepath,
                as_attachment=True,
                download_name=fname
            )

            # Clean up temp directory after request finishes
            @response.call_on_close
            def cleanup():
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass

            return response

        except Exception as e:
            flash(f"Download failed: {e}")
            return redirect(url_for("index"))

    # GET
    return render_template("index.html", allowed_res=ALLOWED_RES)
