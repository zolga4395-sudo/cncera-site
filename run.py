#!/usr/bin/env python3
"""
CNCera - 3D Analysis & G-code Generation
Startup script for the Flask application
"""

import os
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_dir = Path(__file__).parent / "backend"
sys.path.insert(0, str(backend_dir))

# Change to backend directory
os.chdir(backend_dir)

# Import and run the Flask app
from app import app

if __name__ == "__main__":
    print("Starting CNCera server...")
    print("Open your browser and navigate to: http://127.0.0.1:5000")
    print("Press Ctrl+C to stop the server")
    app.run(host="127.0.0.1", port=5000, debug=True, use_reloader=False)