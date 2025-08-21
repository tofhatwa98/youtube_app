from flask import Flask, request, render_template, send_file, redirect, url_for, flash
from pytubefix import YouTube
import tempfile
import os

app = Flask(__name__)
app.secret_key = "supersecret"  # required for flash messages


@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        youtube_url = request.form.get("url")

        if not youtube_url:
            flash("Please enter a YouTube URL.")
            return redirect(url_for("index"))

        try:
            # ✅ pytubefix with anti-bot fix
            yt = YouTube(youtube_url, use_po_token=True)
            stream = yt.streams.get_highest_resolution()

            # Save to a temporary directory
            temp_dir = tempfile.mkdtemp()
            filepath = stream.download(output_path=temp_dir, filename="video.mp4")

            return send_file(filepath, as_attachment=True)

        except Exception as e:
            flash(f"Download failed: {str(e)}")
            return redirect(url_for("index"))

    return render_template("index.html")

