from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from pytubefix import YouTube
from pytubefix.cli import on_progress
import tempfile
import os

app = Flask(__name__)
app.secret_key = "your_secret_key_here"  # needed for flash messages

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        url = request.form.get("url")
        download_type = request.form.get("type")
        min_resolution = request.form.get("resolution", type=int)

        if not url:
            flash("Please enter a YouTube URL.")
            return redirect(url_for("index"))

        try:
            yt = YouTube(url, on_progress_callback=on_progress)
        except Exception as e:
            flash(f"Error loading video: {e}")
            return redirect(url_for("index"))

        # Temporary directory to store the download
        temp_dir = tempfile.mkdtemp()
        
        try:
            if download_type == "audio":
                streams = yt.streams.filter(only_audio=True).order_by('abr').desc()
                if not streams:
                    flash("No audio streams available.")
                    return redirect(url_for("index"))
                stream = streams.first()
                filename = f"{yt.title}.mp3"
            else:
                # Video download with minimum resolution
                streams = [
                    s for s in yt.streams.filter(progressive=True, file_extension="mp4")
                    if s.resolution and int(s.resolution[:-1]) >= (min_resolution or 480)
                ]
                if not streams:
                    flash(f"No video streams available with at least {min_resolution}p resolution.")
                    return redirect(url_for("index"))
                # Pick highest available resolution
                stream = max(streams, key=lambda s: int(s.resolution[:-1]))
                filename = f"{yt.title}.mp4"

            file_path = stream.download(output_path=temp_dir, filename=filename)
            return send_file(file_path, as_attachment=True)

        except Exception as e:
            flash(f"Error downloading: {e}")
            return redirect(url_for("index"))

    return render_template("index.html")


if __name__ == "__main__":
    app.run(debug=True)
