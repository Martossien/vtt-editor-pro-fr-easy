#!/usr/bin/env python3
"""
SRT Editor Pro — Flask server
Auto-hosted subtitle correction tool
Usage: python server.py --port 7861 --debug
"""

import argparse
import json
import logging
import os
import re
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from collections import deque

from flask import Flask, request, jsonify, send_file, send_from_directory, abort

# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────
app = Flask(__name__, static_folder=None)

BASE_DIR = Path(__file__).parent.resolve()
UPLOADS_DIR = BASE_DIR / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)

DEBUG_MODE = True
MAX_LOG_LINES = 200
MAX_UPLOAD_MB = 1024
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

# ──────────────────────────────────────────────
# Logging system
# ──────────────────────────────────────────────
class InMemoryLogHandler(logging.Handler):
    """Stores log records in a deque for the debug panel."""
    def __init__(self, maxlen=MAX_LOG_LINES):
        super().__init__()
        self.buffer = deque(maxlen=maxlen)

    def emit(self, record):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        level = record.levelname
        module = record.name
        msg = self.format(record)
        self.buffer.append(f"[{ts}] [{level}] [{module}] {msg}")

    def get_logs(self):
        return list(self.buffer)


log_handler = InMemoryLogHandler()
log_handler.setFormatter(logging.Formatter("%(message)s"))

logger = logging.getLogger("srt-editor")
logger.setLevel(logging.DEBUG)
logger.addHandler(log_handler)

# Also log to console
console = logging.StreamHandler()
console.setFormatter(logging.Formatter("[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"))
logger.addHandler(console)

# Flask werkzeug logs to our handler too
werkzeug_logger = logging.getLogger("werkzeug")
werkzeug_logger.setLevel(logging.DEBUG)
werkzeug_logger.addHandler(log_handler)

logger.info("SRT Editor Pro server starting")

# ──────────────────────────────────────────────
# CORS
# ──────────────────────────────────────────────
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/<path:path>", methods=["OPTIONS"])
@app.route("/uploads/<path:path>", methods=["OPTIONS"])
def handle_options(path):
    return "", 204


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

ALLOWED_AUDIO_EXT = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"}
ALLOWED_VIDEO_EXT = {".mp4", ".mkv", ".webm"}
ALLOWED_MEDIA_EXT = ALLOWED_AUDIO_EXT | ALLOWED_VIDEO_EXT

ALLOWED_SUBTITLE_EXT = {".srt", ".vtt", ".ass", ".ssa", ".sbv"}


def sanitize_filename(name: str) -> str:
    """Remove problematic characters and prevent path traversal."""
    cleaned = Path(name).name
    cleaned = re.sub(r"[^\w\-.]", "_", cleaned)
    cleaned = cleaned.lstrip(".")
    return cleaned or "untitled"


def validate_cues(cues_raw):
    """Validate and sanitize cue data from client. Returns (clean_cues, skipped)."""
    import math
    if not isinstance(cues_raw, list):
        return [], len(cues_raw) if cues_raw else 0
    clean = []
    skipped = 0
    for cue in cues_raw:
        if not isinstance(cue, dict):
            skipped += 1
            continue
        start = cue.get("start")
        end = cue.get("end")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            skipped += 1
            continue
        if math.isnan(start) or math.isnan(end) or math.isinf(start) or math.isinf(end):
            skipped += 1
            continue
        if start > end:
            skipped += 1
            continue
        text = cue.get("text", "")
        if not isinstance(text, str):
            text = str(text)
        clean.append({
            "id": cue.get("id", ""),
            "start": round(start, 3),
            "end": round(end, 3),
            "text": text,
            "color": cue.get("color", ""),
        })
    return clean, skipped


def create_project_dir(base_name: str) -> tuple:
    """Create a project directory with timestamp. Returns (dir_name, Path)."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = sanitize_filename(Path(base_name).stem)
    dir_name = f"{safe_name}_{ts}"

    # If exists, append microseconds
    target = UPLOADS_DIR / dir_name
    if target.exists():
        dir_name = f"{safe_name}_{ts}_{int(time.time() * 1000) % 1000000}"
        target = UPLOADS_DIR / dir_name

    target.mkdir(parents=True, exist_ok=True)
    logger.info(f"Project created: {dir_name}")
    return dir_name, target


def find_latest_project() -> dict | None:
    """Find the most recent project with a session.json."""
    if not UPLOADS_DIR.exists():
        return None
    projects = sorted(
        [d for d in UPLOADS_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    for proj in projects:
        session_file = proj / "session.json"
        if session_file.exists():
            return {"project_id": proj.name, "path": str(proj)}
    return None


# ──────────────────────────────────────────────
# SRT Parsing (Python side)
# ──────────────────────────────────────────────

def parse_srt_time(time_str: str) -> float | None:
    """Parse SRT time (HH:MM:SS,mmm or MM:SS,mmm)."""
    time_str = time_str.replace(",", ".").strip()
    parts = time_str.split(":")
    try:
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = int(parts[0]), float(parts[1])
            return m * 60 + s
    except (ValueError, IndexError):
        return None
    return None


def parse_vtt_time(time_str: str) -> float | None:
    """Parse VTT time (HH:MM:SS.mmm or MM:SS.mmm)."""
    parts = time_str.strip().split(":")
    try:
        if len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = int(parts[0]), float(parts[1])
            return m * 60 + s
    except (ValueError, IndexError):
        return None
    return None


def parse_srt_content(content: str) -> dict:
    """Parse SRT content and return cues, speakers, warnings, stats."""
    raw_lines = content.split("\n")
    # Filter header comment lines
    lines = [l for l in raw_lines if not l.strip().startswith("#")]
    
    cues = []
    warnings = []
    speakers_found = set()
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        if "-->" in line:
            time_parts = line.split("-->")
            start = parse_srt_time(time_parts[0].strip())
            end = parse_srt_time(time_parts[1].strip())

            i += 1
            text_parts = []
            while i < len(lines) and lines[i].strip() != "":
                text_parts.append(lines[i].strip())
                i += 1

            text = " ".join(text_parts)
            # Clean inline timecodes
            text = re.sub(
                r"\d+\s+\d{2}:\d{2}:\d{2}[,.]\d{3}\s+-->\s+\d{2}:\d{2}:\d{2}[,.]\d{3}\s*",
                "",
                text,
            ).strip()

            if start is None or end is None:
                warnings.append({
                    "type": "invalid_timecode",
                    "message": f"Timecode invalide ligne {i}",
                    "cue_index": len(cues),
                })

            # Detect speaker
            speaker_match = re.match(r"^(SPEAKER_\w+):\s*", text)
            speaker_key = speaker_match.group(1) if speaker_match else None
            if speaker_key:
                speakers_found.add(speaker_key)

            if start is not None and end is not None:
                cues.append({
                    "id": f"cue-{int(time.time() * 1000)}-{len(cues):04d}",
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": text,
                    "color": "",
                })
        i += 1

    # Validation warnings
    for idx, cue in enumerate(cues):
        dur = cue["end"] - cue["start"]
        if dur < 0.5:
            warnings.append({
                "type": "min_duration",
                "message": f"Segment {idx + 1} : duree courte ({dur:.1f}s)",
                "cue_index": idx,
                "severity": "error",
            })
        if dur > 10:
            warnings.append({
                "type": "max_duration",
                "message": f"Segment {idx + 1} : duree longue ({dur:.1f}s)",
                "cue_index": idx,
                "severity": "warning",
            })
        if not cue["text"].strip():
            warnings.append({
                "type": "empty_text",
                "message": f"Segment {idx + 1} : texte vide",
                "cue_index": idx,
                "severity": "error",
            })

    # Check for gaps > 5s
    for idx in range(1, len(cues)):
        gap = cues[idx]["start"] - cues[idx - 1]["end"]
        if gap > 5:
            warnings.append({
                "type": "large_gap",
                "message": f"Trou de {gap:.1f}s entre segments {idx} et {idx + 1}",
                "cue_index": idx,
                "severity": "warning",
            })

    # Check overlaps
    for idx in range(len(cues) - 1):
        if cues[idx]["end"] > cues[idx + 1]["start"]:
            overlap = cues[idx]["end"] - cues[idx + 1]["start"]
            if overlap > 0.1:
                warnings.append({
                    "type": "overlap",
                    "message": f"Chevauchement de {overlap:.1f}s entre segments {idx + 1} et {idx + 2}",
                    "cue_index": idx,
                    "severity": "warning",
                })

    total_duration = cues[-1]["end"] - cues[0]["start"] if cues else 0
    error_count = sum(1 for w in warnings if w.get("severity") == "error")
    warning_count = sum(1 for w in warnings if w.get("severity") == "warning")
    quality_score = max(0, 100 - error_count * 10 - warning_count * 3)

    stats = {
        "total_cues": len(cues),
        "total_duration": round(total_duration, 1),
        "total_speakers": len(speakers_found),
        "errors": error_count,
        "warnings": warning_count,
        "quality_score": quality_score,
    }

    return {
        "cues": cues,
        "speakers": sorted(speakers_found),
        "warnings": warnings,
        "stats": stats,
    }


def parse_vtt_content(content: str) -> dict:
    """Parse VTT content."""
    lines = content.split("\n")
    cues = []
    warnings = []
    i = 0
    
    # Skip WEBVTT header
    if lines and lines[0].strip().startswith("WEBVTT"):
        i = 1
    
    while i < len(lines):
        line = lines[i].strip()
        if "-->" in line:
            time_parts = line.split("-->")
            start = parse_vtt_time(time_parts[0].strip())
            end = parse_vtt_time(time_parts[1].strip())
            
            # Check previous line for color metadata
            color = ""
            if i > 0:
                prev = lines[i - 1].strip()
                cm = re.match(r"\[color:\s*(#[0-9A-Fa-f]{6})\]", prev)
                if cm:
                    color = cm.group(1)
            
            i += 1
            text_parts = []
            while i < len(lines) and lines[i].strip() != "":
                text_parts.append(lines[i].strip())
                i += 1
            
            text = " ".join(text_parts)
            if start is not None and end is not None:
                cues.append({
                    "id": f"cue-{int(time.time() * 1000)}-{len(cues):04d}",
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "text": text,
                    "color": color,
                })
            else:
                warnings.append({
                    "type": "invalid_timecode",
                    "message": f"Timecode invalide ligne {i}",
                    "cue_index": len(cues),
                })
        i += 1
    
    return {"cues": cues, "speakers": [], "warnings": warnings, "stats": {"total_cues": len(cues)}}


# ──────────────────────────────────────────────
# Routes — Frontend
# ──────────────────────────────────────────────

@app.route("/")
def serve_frontend():
    """Serve the main application HTML file."""
    logger.debug("GET / — serving srt-editor-pro.html")
    return send_file(BASE_DIR / "srt-editor-pro.html")


# ──────────────────────────────────────────────
# Routes — Static files (uploads)
# ──────────────────────────────────────────────

@app.route("/uploads/<project>/<filename>")
def serve_upload(project, filename):
    """Serve files from project directories."""
    # Security: prevent path traversal
    safe_project = sanitize_filename(project)
    safe_filename = sanitize_filename(filename)
    filepath = UPLOADS_DIR / safe_project / safe_filename
    if not filepath.exists():
        logger.warning(f"File not found: {filepath}")
        abort(404)
    logger.debug(f"Serving static file: {filepath}")
    return send_from_directory(UPLOADS_DIR / safe_project, safe_filename)


# ──────────────────────────────────────────────
# Routes — API
# ──────────────────────────────────────────────

@app.route("/api/upload/audio", methods=["POST"])
def upload_audio():
    """Upload audio/video file and create project directory."""
    logger.info("POST /api/upload/audio")
    
    if "file" not in request.files:
        logger.error("No file in request")
        return jsonify({"error": "Aucun fichier envoye"}), 400
    
    file = request.files["file"]
    if not file.filename:
        return jsonify({"error": "Nom de fichier vide"}), 400
    
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_MEDIA_EXT:
        logger.warning(f"Rejected file type: {ext}")
        return jsonify({"error": f"Format non supporte : {ext}"}), 400
    
    # Create project directory
    project_id, project_dir = create_project_dir(file.filename)
    audio_path = project_dir / f"audio{ext}"
    file.save(str(audio_path))
    
    file_size = audio_path.stat().st_size
    logger.info(
        f"Audio upload: {file.filename} -> {project_id} "
        f"(size={file_size}B, ext={ext})"
    )
    
    # Try to get audio duration (requires mutagen or ffprobe — optional)
    duration = 0.0
    sample_rate = 0
    channels = 0
    try:
        import subprocess
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "format=duration:stream=sample_rate,channels",
             "-of", "json", str(audio_path)],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            info = json.loads(result.stdout)
            if "format" in info:
                duration = float(info["format"].get("duration", 0))
            if "streams" in info:
                for s in info["streams"]:
                    if s.get("codec_type") == "audio":
                        sample_rate = int(s.get("sample_rate", 0))
                        channels = int(s.get("channels", 0))
                        break
            logger.debug(
                f"Audio probe: duration={duration:.1f}s, "
                f"sr={sample_rate}, ch={channels}"
            )
    except Exception as e:
        logger.warning(f"Could not probe audio: {e}")
    
    if duration <= 0 and file_size > 0:
        logger.warning("Audio duration unknown, setting to 0")
    
    audio_format = ext.lstrip(".")
    if ext in ALLOWED_VIDEO_EXT:
        audio_format = f"video/{audio_format}"
    
    return jsonify({
        "project_id": project_id,
        "duration": round(duration, 3),
        "format": audio_format,
        "sample_rate": sample_rate,
        "channels": channels,
        "file_size": file_size,
    })


@app.route("/api/upload/srt", methods=["POST"])
def upload_srt():
    """Upload SRT/VTT/ASS/SBV file, parse it, save original."""
    logger.info("POST /api/upload/srt")
    
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Payload JSON requis"}), 400
    
    project_id = data.get("project_id")
    content = data.get("content")
    format_type = data.get("format", "srt")
    
    if not project_id or not content:
        return jsonify({"error": "project_id et content requis"}), 400
    
    project_dir = UPLOADS_DIR / sanitize_filename(project_id)
    if not project_dir.exists():
        return jsonify({"error": "Projet introuvable"}), 404
    
    # Save original
    original_path = project_dir / f"original.{format_type}"
    original_path.write_text(content, encoding="utf-8")
    logger.info(f"Original {format_type} saved: {original_path}")
    
    # Parse
    if format_type == "srt":
        result = parse_srt_content(content)
    elif format_type == "vtt":
        result = parse_vtt_content(content)
    else:
        # For ASS, SBV — return the content as-is for client-side parsing
        result = {"cues": [], "speakers": [], "warnings": [], "stats": {"total_cues": 0}}
        result["_raw_content"] = content
        result["_format"] = format_type
    
    logger.info(
        f"Parsing result: {result['stats']['total_cues']} cues, "
        f"{len(result['speakers'])} speakers, "
        f"{len(result['warnings'])} warnings"
    )
    
    # Build initial speakers map
    SPEAKER_COLORS = [
        "#ff6b6b", "#4ecdc4", "#45b7d1", "#f9ca24",
        "#ff9ff3", "#54a0ff", "#feca57", "#1dd1a1",
        "#ff6348", "#a29bfe", "#fd79a8", "#00b894",
    ]
    speakers_map = {}
    for idx, sp in enumerate(result.get("speakers", [])):
        speakers_map[sp] = {
            "label": sp,
            "color": SPEAKER_COLORS[idx % len(SPEAKER_COLORS)],
        }
    
    # Save initial session
    session_data = {
        "cues": result["cues"],
        "markers": [],
        "tracks": [{"id": "default", "name": "Main Track", "cues": [], "color": "#1db954"}],
        "currentTrackId": "default",
        "timestamp": int(time.time() * 1000),
    }
    session_path = project_dir / "session.json"
    session_path.write_text(json.dumps(session_data, indent=2, ensure_ascii=False))
    
    # Save speakers
    speakers_path = project_dir / "speakers.json"
    speakers_path.write_text(json.dumps(speakers_map, indent=2, ensure_ascii=False))
    
    return jsonify({
        "cues": result["cues"],
        "speakers_map": speakers_map,
        "warnings": result["warnings"],
        "stats": result["stats"],
        "raw_content": result.get("_raw_content", ""),
        "raw_format": result.get("_format", ""),
    })


@app.route("/api/save", methods=["POST"])
def save_session():
    """Auto-save session.json and speakers.json."""
    logger.debug("POST /api/save")
    
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Payload JSON requis"}), 400
    
    project_id = data.get("project_id")
    if not project_id:
        return jsonify({"error": "project_id requis"}), 400
    
    project_dir = UPLOADS_DIR / sanitize_filename(project_id)
    if not project_dir.exists():
        return jsonify({"error": "Projet introuvable"}), 404
    
    cues, skipped = validate_cues(data.get("cues", []))
    if skipped:
        logger.warning(f"Save validation: skipped {skipped} invalid cue(s)")
    
    session_data = {
        "cues": cues,
        "markers": data.get("markers", []),
        "tracks": data.get("tracks", [{"id": "default", "name": "Main Track", "cues": [], "color": "#1db954"}]),
        "currentTrackId": data.get("currentTrackId", "default"),
        "timestamp": int(time.time() * 1000),
    }
    
    session_path = project_dir / "session.json"
    session_path.write_text(json.dumps(session_data, indent=2, ensure_ascii=False))
    logger.debug(f"Session saved: {len(session_data['cues'])} cues")
    
    # Also save speakers map if provided
    speakers_map = data.get("speakersMap")
    if speakers_map:
        speakers_path = project_dir / "speakers.json"
        speakers_path.write_text(json.dumps(speakers_map, indent=2, ensure_ascii=False))
        logger.debug(f"Speakers saved with session: {len(speakers_map)} entries")
    
    return jsonify({"status": "ok", "timestamp": session_data["timestamp"], "skipped": skipped})


@app.route("/api/speakers", methods=["POST"])
def save_speakers():
    """Save speakers.json."""
    logger.debug("POST /api/speakers")
    
    data = request.get_json(silent=True)
    project_id = data.get("project_id")
    speakers_map = data.get("speakersMap", {})
    
    if not project_id:
        return jsonify({"error": "project_id requis"}), 400
    
    project_dir = UPLOADS_DIR / sanitize_filename(project_id)
    if not project_dir.exists():
        return jsonify({"error": "Projet introuvable"}), 404
    
    speakers_path = project_dir / "speakers.json"
    speakers_path.write_text(json.dumps(speakers_map, indent=2, ensure_ascii=False))
    logger.info(f"Speakers saved: {len(speakers_map)} entries")
    
    return jsonify({"status": "ok"})


@app.route("/api/session", methods=["GET"])
def load_session():
    """Load the most recent project session."""
    logger.debug("GET /api/session")
    
    project = find_latest_project()
    if not project:
        return jsonify({"project_id": None, "cues": [], "message": "Aucun projet trouve"})
    
    project_dir = UPLOADS_DIR / project["project_id"]
    session_path = project_dir / "session.json"
    speakers_path = project_dir / "speakers.json"
    
    session_data = {}
    if session_path.exists():
        session_data = json.loads(session_path.read_text())
    
    speakers_map = {}
    if speakers_path.exists():
        speakers_map = json.loads(speakers_path.read_text())
    
    # Find audio file
    audio_url = None
    for ext in ALLOWED_MEDIA_EXT:
        audio_file = project_dir / f"audio{ext}"
        if audio_file.exists():
            audio_url = f"/uploads/{project['project_id']}/audio{ext}"
            break
    
    logger.info(
        f"Session loaded: {project['project_id']} — "
        f"{len(session_data.get('cues', []))} cues, "
        f"audio={'yes' if audio_url else 'no'}"
    )
    
    return jsonify({
        "project_id": project["project_id"],
        "cues": session_data.get("cues", []),
        "speakersMap": speakers_map,
        "markers": session_data.get("markers", []),
        "tracks": session_data.get("tracks", [{"id": "default", "name": "Main Track", "cues": [], "color": "#1db954"}]),
        "currentTrackId": session_data.get("currentTrackId", "default"),
        "audio_url": audio_url,
    })


@app.route("/api/export/srt", methods=["POST"])
def export_srt():
    """Generate and return SRT file."""
    logger.info("POST /api/export/srt")
    
    data = request.get_json(silent=True)
    cues_raw = data.get("cues", [])
    speakers_map = data.get("speakersMap", {})
    project_id = data.get("project_id")
    
    cues, skipped = validate_cues(cues_raw)
    if skipped:
        logger.warning(f"Export SRT: skipped {skipped} invalid cue(s)")
    
    if not cues:
        return jsonify({"error": "Aucun cue a exporter"}), 400
    
    lines = []
    for i, cue in enumerate(cues, 1):
        start_str = format_srt_time(cue["start"])
        end_str = format_srt_time(cue["end"])
        text = cue.get("text", "")
        lines.append(str(i))
        lines.append(f"{start_str} --> {end_str}")
        lines.append(text)
        lines.append("")
    
    srt_content = "\n".join(lines)
    
    # Save to project directory
    if project_id:
        project_dir = UPLOADS_DIR / sanitize_filename(project_id)
        if project_dir.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = project_dir / f"export_{ts}.srt"
            export_path.write_text(srt_content, encoding="utf-8")
            logger.info(f"Exported SRT saved: {export_path}")
    
    return jsonify({"content": srt_content, "filename": "subtitles.srt", "skipped": skipped})


@app.route("/api/export/vtt", methods=["POST"])
def export_vtt():
    """Generate and return VTT file."""
    logger.info("POST /api/export/vtt")
    
    data = request.get_json(silent=True)
    cues_raw = data.get("cues", [])
    project_id = data.get("project_id")
    
    cues, skipped = validate_cues(cues_raw)
    if skipped:
        logger.warning(f"Export VTT: skipped {skipped} invalid cue(s)")
    
    lines = ["WEBVTT", ""]
    for i, cue in enumerate(cues):
        start_str = format_vtt_time(cue["start"])
        end_str = format_vtt_time(cue["end"])
        text = cue.get("text", "")
        # Color metadata
        color = cue.get("color", "")
        if color:
            lines.append(f"[color: {color}]")
        lines.append(f"cue-{i + 1}")
        lines.append(f"{start_str} --> {end_str}")
        lines.append(text)
        lines.append("")
    
    vtt_content = "\n".join(lines)
    
    if project_id:
        project_dir = UPLOADS_DIR / sanitize_filename(project_id)
        if project_dir.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_path = project_dir / f"export_{ts}.vtt"
            export_path.write_text(vtt_content, encoding="utf-8")
            logger.info(f"Exported VTT saved: {export_path}")
    
    return jsonify({"content": vtt_content, "filename": "subtitles.vtt", "skipped": skipped})


@app.route("/api/debug/logs", methods=["GET"])
def debug_logs():
    """Return recent server logs."""
    limit = request.args.get("limit", 100, type=int)
    logs = log_handler.get_logs()
    return jsonify({"logs": logs[-limit:]})


# ──────────────────────────────────────────────
# Time formatting
# ──────────────────────────────────────────────

def format_srt_time(seconds: float) -> str:
    """Format as HH:MM:SS,mmm (SRT format)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def format_vtt_time(seconds: float) -> str:
    """Format as HH:MM:SS.mmm (VTT format)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


# ──────────────────────────────────────────────
# Error handlers
# ──────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    logger.warning(f"404: {request.path}")
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(413)
def too_large(e):
    max_mb = app.config.get("MAX_CONTENT_LENGTH", 0) / (1024 * 1024)
    logger.warning(f"413: Payload too large (max {max_mb:.0f} MB)")
    return jsonify({"error": f"Fichier trop volumineux (max {max_mb:.0f} MB)"}), 413


@app.errorhandler(500)
def server_error(e):
    logger.error(f"500: {traceback.format_exc()}")
    return jsonify({"error": "Internal server error"}), 500


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SRT Editor Pro Server")
    parser.add_argument("--port", type=int, default=7861, help="Server port")
    parser.add_argument("--debug", action="store_true", default=True, help="Debug mode")
    args = parser.parse_args()
    
    logger.info(f"Starting server on 0.0.0.0:{args.port} (debug={args.debug})")
    app.run(
        host="0.0.0.0",
        port=args.port,
        debug=args.debug,
        threaded=True,
    )
