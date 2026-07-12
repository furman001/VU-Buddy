#!/usr/bin/env python
"""Wrapper to run the dashboard on port 5002 (to avoid zombie on 5000)."""
import os, sys
os.environ["VU_BUDDY_PORT"] = "5002"
from frontend.app import app
app.run(host=os.getenv("VU_BUDDY_HOST", "0.0.0.0"), port=5002, debug=True)
