# api/index.py - Vercel API Proxy
import os
import sys
from pathlib import Path

# Add the parent directory to sys.path
sys.path.append(str(Path(__file__).parent.parent))

# Import the Flask app
from backend.app import app as flask_app

# Vercel expects a callable named 'app'
app = flask_app

# For Vercel, we need to handle static files differently
# The app will serve templates and static files from the correct locations