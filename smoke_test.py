"""Stable compatibility entrypoint for the combined smoke suite.

Run with: python smoke_test.py
"""

from __future__ import annotations

from smoke_combined_runner import run


if __name__ == "__main__":
    run()
