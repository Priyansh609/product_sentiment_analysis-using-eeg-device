"""
MindWave Visualizer — Engagement / EEG Processor
==================================================
Computes the neuromarketing engagement score and manages per-product
experiment sessions.

Engagement formula
~~~~~~~~~~~~~~~~~~
    engagement = w_att × attention
               + w_beta × beta_ratio
               + w_blink × blink_score

    beta_ratio  = (low_beta + high_beta) / max(low_alpha + high_alpha, 1) × 100
    blink_score = max(0, 100 − recent_blink_rate × 10)

Lower blink rate → higher engagement (people blink less when focused).
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from config import (
    ENGAGEMENT_WEIGHT_ATTENTION,
    ENGAGEMENT_WEIGHT_BETA,
    ENGAGEMENT_WEIGHT_BLINK,
)
from logger import setup_logger

log = setup_logger("processor")


@dataclass
class SessionStats:
    """Accumulated statistics for one product experiment session."""
    product_name: str
    start_time: float = 0.0
    end_time: float = 0.0
    attention_values: list = field(default_factory=list)
    meditation_values: list = field(default_factory=list)
    engagement_values: list = field(default_factory=list)
    blink_count: int = 0
    data_points: int = 0

    @property
    def duration(self) -> float:
        return max(0.0, self.end_time - self.start_time)

    @property
    def avg_attention(self) -> float:
        return sum(self.attention_values) / max(len(self.attention_values), 1)

    @property
    def max_attention(self) -> float:
        return max(self.attention_values) if self.attention_values else 0

    @property
    def avg_meditation(self) -> float:
        return sum(self.meditation_values) / max(len(self.meditation_values), 1)

    @property
    def avg_engagement(self) -> float:
        return sum(self.engagement_values) / max(len(self.engagement_values), 1)

    @property
    def peak_engagement(self) -> float:
        return max(self.engagement_values) if self.engagement_values else 0

    def summary(self) -> dict:
        return {
            "product_name":     self.product_name,
            "duration_s":       round(self.duration, 1),
            "data_points":      self.data_points,
            "avg_attention":    round(self.avg_attention, 1),
            "max_attention":    round(self.max_attention, 1),
            "avg_meditation":   round(self.avg_meditation, 1),
            "avg_engagement":   round(self.avg_engagement, 1),
            "peak_engagement":  round(self.peak_engagement, 1),
            "blink_count":      self.blink_count,
        }


class EngagementEngine:
    """
    Calculates real-time engagement scores and tracks per-product sessions.
    """

    def __init__(self) -> None:
        self.w_att   = ENGAGEMENT_WEIGHT_ATTENTION
        self.w_beta  = ENGAGEMENT_WEIGHT_BETA
        self.w_blink = ENGAGEMENT_WEIGHT_BLINK

        # Blink-rate tracker (recent blinks in last 60 s)
        self._recent_blinks: deque = deque(maxlen=200)

        # Session management
        self._sessions: Dict[str, SessionStats] = {}
        self._current_session: Optional[SessionStats] = None

        # Latest computed engagement
        self.last_engagement: float = 0.0

    # ── Engagement calculation ─────────────────────────────────────────

    def calculate(self, data: dict) -> float:
        """
        Compute engagement score (0 – 100) from a decoded packet.
        Only meaningful when attention > 0 (i.e. when eSense data is present).
        """
        # NOTE: these keys always exist in the decoded dict, but hold None
        # until the first ASIC/eSense packet arrives (see packet_decoder's
        # forward-fill fix) — `.get(key, 0)` does NOT catch that, since the
        # key is present. `or 0` correctly treats None the same as missing.
        attention  = data.get("attention") or 0
        low_beta   = data.get("low_beta") or 0
        high_beta  = data.get("high_beta") or 0
        low_alpha  = data.get("low_alpha") or 0
        high_alpha = data.get("high_alpha") or 0
        blink      = data.get("blink_strength") or 0

        # Beta / Alpha ratio (clamped to 0-100)
        alpha_sum = max(low_alpha + high_alpha, 1)
        beta_ratio = min((low_beta + high_beta) / alpha_sum * 100, 100)

        # Blink rate (blinks per minute)
        now = time.monotonic()
        if blink > 0:
            self._recent_blinks.append(now)
        # Count blinks in last 60 seconds
        cutoff = now - 60
        while self._recent_blinks and self._recent_blinks[0] < cutoff:
            self._recent_blinks.popleft()
        blink_rate = len(self._recent_blinks)  # per minute
        blink_score = max(0, 100 - blink_rate * 10)

        engagement = (
            self.w_att   * attention
            + self.w_beta  * beta_ratio
            + self.w_blink * blink_score
        )
        engagement = round(max(0, min(100, engagement)), 1)
        self.last_engagement = engagement

        # Update active session
        if self._current_session is not None and attention > 0:
            s = self._current_session
            s.attention_values.append(attention)
            s.meditation_values.append(data.get("meditation") or 0)
            s.engagement_values.append(engagement)
            s.data_points += 1
            if blink > 0:
                s.blink_count += 1

        return engagement

    # ── Session management ─────────────────────────────────────────────

    def start_session(self, product_name: str) -> None:
        """Begin a new experiment session for the given product."""
        session = SessionStats(
            product_name=product_name,
            start_time=time.monotonic(),
        )
        self._current_session = session
        self._sessions[product_name] = session
        log.info("Session started for '%s'", product_name)

    def end_session(self) -> Optional[SessionStats]:
        """End the current session and return its stats."""
        if self._current_session is None:
            return None
        self._current_session.end_time = time.monotonic()
        session = self._current_session
        self._current_session = None
        log.info(
            "Session ended for '%s' — %d data points, avg engagement %.1f",
            session.product_name, session.data_points, session.avg_engagement,
        )
        return session

    @property
    def current_session(self) -> Optional[SessionStats]:
        return self._current_session

    @property
    def is_active(self) -> bool:
        return self._current_session is not None

    def get_session(self, product_name: str) -> Optional[SessionStats]:
        return self._sessions.get(product_name)

    def all_sessions(self) -> Dict[str, SessionStats]:
        return dict(self._sessions)

    def get_rankings(self) -> List[dict]:
        """Return sessions ranked by average engagement (descending)."""
        ranked = sorted(
            self._sessions.values(),
            key=lambda s: s.avg_engagement,
            reverse=True,
        )
        results = []
        for rank, session in enumerate(ranked, 1):
            s = session.summary()
            s["rank"] = rank
            results.append(s)
        return results

    def clear_sessions(self) -> None:
        """Remove all stored sessions."""
        self._sessions.clear()
        self._current_session = None