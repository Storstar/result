from __future__ import annotations

import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

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
        stderr = self._probe_streams(video_path)
        duration_seconds = self._parse_duration(stderr)
        fps = self._parse_fps(stderr)
        width, height = self._parse_dimensions(stderr)
        frame_count = int(duration_seconds * fps) if duration_seconds > 0 and fps > 0 else 0
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
        duration = metadata.duration_seconds or 0.0
        if duration <= 0:
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
            frame_path = output_dir / f"frame_{index:02d}_{str(timestamp).replace('.', '_')}s.jpg"
            if self._extract_single_frame(video_path, timestamp, frame_path):
                sampled.append((timestamp, frame_path))
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
        stderr = self._probe_streams(video_path).lower()
        return "audio:" in stderr

    def _probe_streams(self, video_path: Path) -> str:
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        result = subprocess.run(
            [ffmpeg_path, "-i", str(video_path)],
            capture_output=True,
            text=True,
        )
        return result.stderr

    def _extract_single_frame(self, video_path: Path, timestamp: float, output_path: Path) -> bool:
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        result = subprocess.run(
            [
                ffmpeg_path,
                "-y",
                "-ss",
                f"{max(timestamp, 0.0):.2f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                str(output_path),
            ],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and output_path.exists()

    def _parse_duration(self, stderr: str) -> float:
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", stderr)
        if not match:
            return 0.0
        hours, minutes, seconds = match.groups()
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    def _parse_fps(self, stderr: str) -> float:
        match = re.search(r"(\d+(?:\.\d+)?)\s*fps", stderr)
        if not match:
            return 0.0
        return float(match.group(1))

    def _parse_dimensions(self, stderr: str) -> tuple[int, int]:
        match = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", stderr, re.DOTALL)
        if not match:
            return 0, 0
        return int(match.group(1)), int(match.group(2))
