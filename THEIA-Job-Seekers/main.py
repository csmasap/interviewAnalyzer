"""
THEIA Interview Prep System — Main Entrypoint (Router to full API)

Purpose: Ensure Cloud Run buildpacks that look for `main:app` will serve the
complete application (including voice token endpoints) by re-exporting the
fully featured FastAPI app from `backend.simple_main`.
"""

from backend.simple_main import app  # re-export full application for buildpacks

__all__ = ["app"]

