from flask import Flask, request, render_template, send_file, redirect, url_for
from moviepy.editor import VideoFileClip
import tempfile, os, shutil, zipfile, io, uuid, threading, time

app = Flask(__name__)
UPLOAD_DIR = os.path.join(tempfile.gettempdir(), "video_cutter_sessions")
os.makedirs(UPLOAD_DIR, exist_ok=True)
SESSIONS = {}

# Cleanup thread
def cleanup_old_sessions():
    while True:
        now = time.time()
        for session_id in list(SESSIONS):
            folder = SESSIONS[session_id]['folder']
            if now - os.path.getmtime(folder) > 3600:  # 1 hour
                shutil.rmtree(folder, ignore_errors=True)
                del SESSIONS[session_id]
        time.sleep(600)  # Check every 10 minutes

threading.Thread(target=cleanup_old_sessions, daemon=True).start()

def cut_video_background(session_id, input_path, session_folder):
    clip = VideoFileClip(input_path)
    duration = int(clip.duration)
    segment_duration = 60
    part_files = []
    total_parts = (duration + segment_duration - 1) // segment_duration

    for i, start in enumerate(range(0, duration, segment_duration), start=1):
        end = min(start + segment_duration, duration)
        potongan = clip.subclip(start, end)
        part_path = os.path.join(session_folder, f"cut{i}.mp4")
        potongan.write_videofile(part_path, codec="libx264", audio_codec="aac", logger=None)
        part_files.append(f"cut{i}.mp4")
        SESSIONS[session_id]["progress"] = int(i / total_parts * 100)

    SESSIONS[session_id]["parts"] = part_files
    SESSIONS[session_id]["progress"] = 100

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        video_file = request.files["video"]
        if not video_file:
            return "No video uploaded", 400

        session_id = str(uuid.uuid4())
        session_folder = os.path.join(UPLOAD_DIR, session_id)
        os.makedirs(session_folder)

        input_path = os.path.join(session_folder, "input.mp4")
        video_file.save(input_path)

        # Inisialisasi progress
        SESSIONS[session_id] = {
            "folder": session_folder,
            "parts": [],
            "progress": 0
        }

        # Jalankan proses cutting di thread terpisah
        threading.Thread(
            target=cut_video_background,
            args=(session_id, input_path, session_folder),
            daemon=True
        ).start()

        # Langsung balas session_id agar client bisa polling progress
        return {"session_id": session_id}

    return render_template("index.html", year=time.strftime("%Y"))

@app.route("/progress/<session_id>")
def progress(session_id):
    session = SESSIONS.get(session_id)
    if not session:
        return {"progress": 0}
    return {"progress": session.get("progress", 0)}

@app.route("/result/<session_id>")
def result(session_id):
    session = SESSIONS.get(session_id)
    if not session:
        return "Session not found", 404
    return render_template("result.html", session_id=session_id, files=session['parts'])

@app.route("/download/<session_id>/<filename>")
def download_part(session_id, filename):
    session = SESSIONS.get(session_id)
    if not session:
        return "Session not found", 404
    path = os.path.join(session["folder"], filename)
    return send_file(path, as_attachment=True)

@app.route("/download_zip/<session_id>")
def download_zip(session_id):
    session = SESSIONS.get(session_id)
    if not session:
        return "Session not found", 404

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zipf:
        for filename in session["parts"]:
            filepath = os.path.join(session["folder"], filename)
            zipf.write(filepath, arcname=filename)

    zip_buffer.seek(0)
    return send_file(zip_buffer, mimetype="application/zip", as_attachment=True, download_name="video_potongan.zip")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
