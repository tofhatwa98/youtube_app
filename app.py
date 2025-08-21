from flask import Flask, request, jsonify, send_file
from pytubefix import YouTube
import os
import tempfile

app = Flask(__name__)

@app.route("/download", methods=["GET"])
def download_video():
    url = request.args.get("url")
    if not url:
        return jsonify({"error": "Missing 'url' parameter"}), 400

    try:
        yt = YouTube(url)
        stream = yt.streams.get_highest_resolution()

        # Create a temp file
        temp_dir = tempfile.mkdtemp()
        filepath = stream.download(output_path=temp_dir)

        return send_file(filepath, as_attachment=True)

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/")
def home():
    return jsonify({"message": "YouTube API is running!"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)