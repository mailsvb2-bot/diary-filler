"""Stable entrypoint for the combined smoke suite.

Regression contract kept here for release_check:
Number popup must not open from the sick-leave Yes button.
"""

from __future__ import annotations

from smoke_combined_runner import run


if __name__ == "__main__":
    run()
