import os
import re
import shutil
import tempfile
from datetime import datetime
from flask import (
    Flask, request, render_template, send_file,
    redirect, url_for, flash
)
from pytubefix import YouTube

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "supersecret")

# --- Tunables ---
MAX_BYTES = 100 * 1024 * 1024   # ~100 MB safeguard
DEFAULT_RES_ORDER = ["720p", "480p", "360p", "240p"]
ALLOWED_RES = ["best"] + DEFAULT_RES_ORDER


def safe_filename(name: str, default: str = "download"):
    """Sanitize filename for filesystem."""
    name = name or default
    name = re.sub(r"[^\w\-\.\s\(\)\[\]]+", "", name).strip()
    return name or default


def pick_progressive_stream(yt: YouTube, target_res: str):
    streams = yt.streams.filter(progressive=True, file_extension="mp4")
    if not streams:
        return None
    if target_res == "best":
        return streams.order_by("resolution").desc().first()
    try:
        start_idx = DEFAULT_RES_ORDER.index(target_res)
    except ValueError:
        start_idx = 0
    for res in DEFAULT_RES_ORDER[start_idx:]:
        s = streams.filter(res=res).order_by("fps").desc().first()
        if s:
            return s
    return streams.order_by("resolution").desc().first()


def pick_audio_stream(yt: YouTube):
    return yt.streams.filter(only_audio=True).order_by("abr").desc().first()


def estimate_size_bytes(stream):
    return getattr(stream, "filesize", None) or getattr(stream, "filesize_approx", None)


def get_youtube_obj(url: str) -> YouTube:
    """Return YouTube object, trying env PO_TOKEN first, fallback to Node.js po_token."""
    po_token = os.environ.get("PO_TOKEN")
    if po_token:
        return YouTube(url, po_token=po_token)
    return YouTube(url, use_po_token=True)


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = (request.form.get("url") or "").strip()
        mode = (request.form.get("mode") or "video").lower()
        target_res = (request.form.get("resolution") or "best").lower()

        if not url:
            flash("Please enter a YouTube URL.")
            return redirect(url_for("index"))

        if not (url.startswith("http://") or url.startswith("https://")):
            flash("Invalid URL. Please include http(s)://")
            return redirect(url_for("index"))

        try:
            yt = get_youtube_obj(url)
        except Exception as e:
            flash(f"Failed to initialize YouTube object: {e}")
            return redirect(url_for("index"))

        try:
            if mode == "audio":
                stream = pick_audio_stream(yt)
            else:
                if target_res not in ALLOWED_RES:
                    target_res = "best"
                stream = pick_progressive_stream(yt, target_res)

            if not stream:
                flash("No suitable stream found. Try audio-only.")
                return redirect(url_for("index"))

            est = estimate_size_bytes(stream)
            if est and est > MAX_BYTES:
                mb = round(est / (1024 * 1024), 1)
                flash(f"Stream too large (~{mb} MB). Try a lower resolution or audio-only.")
                return redirect(url_for("index"))

            tmpdir = tempfile.mkdtemp(prefix="yt_")
            title = safe_filename(yt.title, default="video")
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

            if mode == "audio":
                mime = (stream.mime_type or "audio/webm").lower()
                ext = ".webm" if "webm" in mime else ".m4a"
                fname = f"{title}_{timestamp}{ext}"
            else:
                fname = f"{title}_{timestamp}.mp4"

            filepath = stream.download(output_path=tmpdir, filename=fname)

            response = send_file(filepath, as_attachment=True, download_name=fname)

            @response.call_on_close
            def cleanup():
                shutil.rmtree(tmpdir, ignore_errors=True)

            return response

        except Exception as e:
            flash(f"Download failed: {e}")
            return redirect(url_for("index"))

    return render_template("index.html", allowed_res=ALLOWED_RES)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)