"""Retention for closed recording segments and concurrent save operations.

This module does not capture video or assemble MP4s. Capture must register a
segment only after it is closed and must use one time base for every segment.
"""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from threading import RLock


@dataclass(frozen=True)
class Segment:
    path: Path
    start: float
    end: float


class ReplayBuffer:
    def __init__(self, duration: float):
        if duration <= 0:
            raise ValueError("duration must be positive")
        self.duration = duration
        self._lock = RLock()
        self._segments: list[Segment] = []
        self._paths: set[Path] = set()
        self._pins: dict[Path, int] = {}
        self._reservations: dict[object, tuple[float, float]] = {}

    def add_closed(self, segment: Segment):
        if segment.end <= segment.start:
            raise ValueError("segment must have a positive duration")
        if not segment.path.is_file():
            raise FileNotFoundError(segment.path)
        with self._lock:
            if self._segments:
                previous = self._segments[-1]
                if segment.path in self._paths:
                    raise ValueError("segments must have unique paths")
                if segment.start < previous.end:
                    # Container timestamps are rounded to milliseconds. A
                    # 1–2 ms rounding overlap is not a duplicated segment.
                    if previous.end - segment.start > 0.005 or segment.end <= previous.end:
                        raise ValueError("segments must have non-overlapping time ranges")
                    segment = Segment(segment.path, previous.end, segment.end)
            self._segments.append(segment)
            self._paths.add(segment.path)

    @contextmanager
    def snapshot(self, end: float):
        """Protect the interval, including segments that close while waiting."""
        reservation = object()
        with self._lock:
            self._reservations[reservation] = (end - self.duration, end)
            selected = tuple(s for s in self._segments if s.end > end - self.duration and s.start < end)
            for segment in selected:
                self._pins[segment.path] = self._pins.get(segment.path, 0) + 1
        try:
            yield selected
        finally:
            with self._lock:
                del self._reservations[reservation]
                for segment in selected:
                    remaining = self._pins[segment.path] - 1
                    if remaining:
                        self._pins[segment.path] = remaining
                    else:
                        del self._pins[segment.path]

    def reserve_from(self, start: float):
        """Keep all closed segments from a recording start until released."""
        reservation = object()
        with self._lock:
            self._reservations[reservation] = (start, float("inf"))
        return reservation

    def reserved_segments(self, reservation, end: float):
        with self._lock:
            start, _ = self._reservations[reservation]
            return tuple(s for s in self._segments if s.end > start and s.start < end)

    def release(self, reservation):
        with self._lock:
            del self._reservations[reservation]

    def limit(self, reservation, end):
        with self._lock:
            start, _ = self._reservations[reservation]
            self._reservations[reservation] = (start, end)

    def cleanup(self, now: float):
        """Remove expired, unpinned closed segments; return deletion failures."""
        failures = []
        with self._lock:
            keep = []
            for segment in self._segments:
                reserved = any(segment.end > start and segment.start < end
                               for start, end in self._reservations.values())
                if segment.end > now - self.duration or self._pins.get(segment.path) or reserved:
                    keep.append(segment)
                    continue
                try:
                    segment.path.unlink(missing_ok=True)
                except OSError:
                    keep.append(segment)
                    failures.append(segment.path)
            self._segments = keep
            self._paths = {segment.path for segment in keep}
        return failures
