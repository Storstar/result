from __future__ import annotations

import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import imageio_ffmpeg


@dataclass
class VideoMetadata:
    duration_seconds: float
    fps: float
    frame_count: int
    width: int
    height: int
    has_audio: bool


class VideoService:
    def inspect(self, video_path: Path) -> VideoMetadata:
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            raise RuntimeError(f"Could not open video: {video_path}")

        fps = capture.get(cv2.CAP_PROP_FPS) or 0.0
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        capture.release()

        duration_seconds = frame_count / fps if fps and frame_count else 0.0
        has_audio = self._probe_audio_stream(video_path)
        return VideoMetadata(
            duration_seconds=duration_seconds,
            fps=fps,
            frame_count=frame_count,
            width=width,
            height=height,
            has_audio=has_audio,
        )

    def sample_frames(self, video_path: Path, output_dir: Path, interval_seconds: float, max_frames: int) -> list[tuple[float, Path]]:
        metadata = self.inspect(video_path)
        output_dir.mkdir(parents=True, exist_ok=True)
        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            return []

        duration = metadata.duration_seconds or 0.0
        if duration <= 0:
            capture.release()
            return []

        timestamps: list[float] = []
        current = 0.0
        while current < duration and len(timestamps) < max_frames:
            timestamps.append(round(current, 2))
            current += max(interval_seconds, 0.5)
        if timestamps and timestamps[-1] < duration - 0.5 and len(timestamps) < max_frames:
            timestamps.append(round(duration - 0.25, 2))

        sampled: list[tuple[float, Path]] = []
        for index, timestamp in enumerate(timestamps):
            frame_number = min(
                int(math.floor(timestamp * metadata.fps)),
                max(metadata.frame_count - 1, 0),
            )
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_number)
            success, frame = capture.read()
            if not success:
                continue
            frame_path = output_dir / f"frame_{index:02d}_{str(timestamp).replace('.', '_')}s.jpg"
            cv2.imwrite(str(frame_path), frame)
            sampled.append((timestamp, frame_path))

        capture.release()
        return sampled

    def extract_audio(self, video_path: Path, output_path: Path) -> Optional[Path]:
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-i",
                str(video_path),
                "-vn",
                "-acodec",
                "mp3",
                str(output_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not output_path.exists():
            return None
        return output_path

    def _probe_audio_stream(self, video_path: Path) -> bool:
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        result = subprocess.run(
            [ffmpeg_path, "-i", str(video_path)],
            capture_output=True,
            text=True,
        )
        stderr = result.stderr.lower()
        return "audio:" in stderr
