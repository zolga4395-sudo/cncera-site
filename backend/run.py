#!/usr/bin/env python3
"""
CNCera Backend Server Launcher
"""

import os
import sys
from pathlib import Path

# Add app directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

from app import create_app

if __name__ == '__main__':
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        print("python-dotenv not installed, skipping .env file loading")
    
    # Create app
    app = create_app()
    
    # Configuration
    host = os.getenv('BACKEND_HOST', '127.0.0.1')
    port = int(os.getenv('BACKEND_PORT', 5000))
    debug = os.getenv('FLASK_ENV') == 'development'
    
    print(f"🚀 Starting CNCera Backend API")
    print(f"   Server: http://{host}:{port}")
    print(f"   Environment: {os.getenv('FLASK_ENV', 'production')}")
    print(f"   Debug: {debug}")
    
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠️  OpenAI API key not set - AI features will be disabled")
    
    # Run server
    app.run(
        host=host,
        port=port,
        debug=debug,
        use_reloader=False
    )