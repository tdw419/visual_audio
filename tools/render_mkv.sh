#!/usr/bin/env bash
# render_mkv.sh — Assembly wrapper: frames → MKV with audio
#
# Usage:
#   ./tools/render_mkv.sh <input.wav> [--json metadata.json] -o <output.mkv>
#
# Requires:
#   - ffmpeg (with libx264 or ffv1 support)
#   - tools/audio_to_frames.py
#
# Pipeline:
#   audio_to_frames.py --raw input.wav | ffmpeg ... -i pipe: -i input.wav -acodec copy output.mkv

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRAME_GEN="$SCRIPT_DIR/audio_to_frames.py"
WAV_INPUT=""
JSON_INPUT=""
OUTPUT_MKV=""
CODEC="libx264"
BITRATE="10M"
FPS=60

usage() {
    cat <<EOF
Usage: $(basename "$0") <input.wav> [options] -o <output.mkv>

Options:
  -j, --json FILE    UPIC JSON metadata for phoneme annotations
  -o, --output FILE  Output MKV file (required)
  -c, --codec NAME   Video codec: libx264 (default, good for preview) or ffv1 (lossless)
  -b, --bitrate RATE Video bitrate (default: 10M)
  -h, --help         Show this help

Examples:
  # Basic: audio to MKV with h264 preview
  $0 speech.wav -o speech.mkv

  # With UPIC metadata for phoneme visualization
  $0 speech.wav -j speech.upic.json -o speech_visual.mkv

  # Lossless archival (FFV1)
  $0 speech.wav -o speech_archival.mkv -c ffv1
EOF
    exit 0
}

# Parse arguments
if [[ $# -eq 0 ]]; then
    usage
fi

# First positional arg is the WAV
WAV_INPUT="${1:-}"
shift 2>/dev/null || true

while [[ $# -gt 0 ]]; do
    case "$1" in
        -j|--json)   JSON_INPUT="$2"; shift 2 ;;
        -o|--output) OUTPUT_MKV="$2"; shift 2 ;;
        -c|--codec)  CODEC="$2"; shift 2 ;;
        -b|--bitrate) BITRATE="$2"; shift 2 ;;
        -h|--help)   usage ;;
        *)           echo "Unknown option: $1"; usage ;;
    esac
done

if [[ -z "$WAV_INPUT" ]]; then
    echo "ERROR: No WAV input specified."
    usage
fi

if [[ ! -f "$WAV_INPUT" ]]; then
    echo "ERROR: WAV file not found: $WAV_INPUT"
    exit 1
fi

if [[ -z "$OUTPUT_MKV" ]]; then
    echo "ERROR: No output file specified. Use -o <output.mkv>"
    exit 1
fi

if [[ ! -x "$FRAME_GEN" ]]; then
    echo "ERROR: Frame generator not found or not executable: $FRAME_GEN"
    echo "  Make sure tools/audio_to_frames.py exists and is executable."
    exit 1
fi

if [[ -n "$JSON_INPUT" && ! -f "$JSON_INPUT" ]]; then
    echo "WARNING: JSON metadata file not found: $JSON_INPUT (proceeding without)"
    JSON_INPUT=""
fi

echo "=== Audio-to-Video Renderer ==="
echo "Input WAV:   $WAV_INPUT"
[[ -n "$JSON_INPUT" ]] && echo "JSON meta:   $JSON_INPUT"
echo "Output MKV:  $OUTPUT_MKV"
echo "Codec:       $CODEC"
echo "Bitrate:     $BITRATE"
echo "FPS:         $FPS"
echo ""

# Determine codec parameters
CODEC_ARGS="-c:v $CODEC"
if [[ "$CODEC" == "libx264" ]]; then
    CODEC_ARGS="-c:v libx264 -preset medium -b:v $BITRATE -pix_fmt yuv420p"
elif [[ "$CODEC" == "ffv1" ]]; then
    CODEC_ARGS="-c:v ffv1 -level 3 -coder 1 -context 1 -g 1 -pix_fmt yuv420p"
else
    CODEC_ARGS="-c:v $CODEC -b:v $BITRATE"
fi

# Build ffmpeg command
# Pipeline: audio_to_frames.py --raw -> rawvideo pipe -> ffmpeg -> mux with audio
echo "Rendering frames..."

FFMPEG_CMD=(
    ffmpeg -y
    -f rawvideo
    -pix_fmt rgb24
    -s 1920x1080
    -r "$FPS"
    -i -
    -i "$WAV_INPUT"
    -c:a copy
    $CODEC_ARGS
    -map 0:v:0
    -map 1:a:0
    -shortest
    "$OUTPUT_MKV"
)

JSON_ARGS=()
if [[ -n "$JSON_INPUT" ]]; then
    JSON_ARGS=(-j "$JSON_INPUT")
fi

# Run the pipeline
python3 "$FRAME_GEN" --raw "$WAV_INPUT" "${JSON_ARGS[@]}" | "${FFMPEG_CMD[@]}"

# Check result
FFMPEG_EXIT=$?
if [[ $FFMPEG_EXIT -eq 0 ]]; then
    # Get file size
    SIZE=$(du -h "$OUTPUT_MKV" 2>/dev/null | cut -f1)
    DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUTPUT_MKV" 2>/dev/null)
    echo ""
    echo "✓ Video rendered successfully!"
    echo "  File:   $OUTPUT_MKV"
    echo "  Size:   $SIZE"
    echo "  Length: ${DURATION%.*}s"
else
    echo ""
    echo "✗ Rendering failed (ffmpeg exit code $FFMPEG_EXIT)"
    exit $FFMPEG_EXIT
fi
