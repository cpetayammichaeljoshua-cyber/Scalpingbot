"""
MiroFish Bot - Swarm Intelligence Prediction Engine
Source: https://github.com/666ghj/MiroFish.git

This script launches the MiroFish backend Flask server.
MiroFish is a multi-agent AI prediction engine that builds high-fidelity
parallel digital worlds to simulate and predict future outcomes.

Required environment variables:
  LLM_API_KEY   - Your LLM API key (OpenAI-compatible)
  ZEP_API_KEY   - Your Zep Cloud API key for agent memory

Optional environment variables:
  LLM_BASE_URL     - LLM API base URL (default: https://api.openai.com/v1)
  LLM_MODEL_NAME   - Model name to use (default: gpt-4o-mini)
  FLASK_HOST       - Host to bind (default: 0.0.0.0)
  FLASK_PORT       - Port to bind (default: 5001)
  FLASK_DEBUG      - Enable debug mode (default: True)
"""

import os
import sys

# Ensure UTF-8 encoding on all platforms
os.environ.setdefault('PYTHONIOENCODING', 'utf-8')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Add the MiroFish backend to the Python path
BACKEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'mirofish_backend')
sys.path.insert(0, BACKEND_DIR)

from app import create_app
from app.config import Config


def main():
    print("=" * 60)
    print("  MiroFish - Swarm Intelligence Prediction Engine")
    print("  https://github.com/666ghj/MiroFish")
    print("=" * 60)

    # Validate required configuration
    errors = Config.validate()
    if errors:
        print("\n[ERROR] Configuration issues detected:")
        for err in errors:
            print(f"  - {err}")
        print("\nPlease set the required environment variables:")
        print("  LLM_API_KEY  - Your LLM API key (OpenAI-compatible)")
        print("  ZEP_API_KEY  - Your Zep Cloud API key")
        sys.exit(1)

    # Create and run the Flask application
    app = create_app()

    host = os.environ.get('FLASK_HOST', '0.0.0.0')
    port = int(os.environ.get('FLASK_PORT', 5001))
    debug = Config.DEBUG

    print(f"\n[INFO] Starting MiroFish backend on http://{host}:{port}")
    print(f"[INFO] Debug mode: {debug}")
    print(f"[INFO] LLM model: {Config.LLM_MODEL_NAME}")
    print(f"[INFO] LLM base URL: {Config.LLM_BASE_URL}")
    print("\n[INFO] API Endpoints:")
    print(f"  GET  http://{host}:{port}/health")
    print(f"  *    http://{host}:{port}/api/graph/...")
    print(f"  *    http://{host}:{port}/api/simulation/...")
    print(f"  *    http://{host}:{port}/api/report/...")
    print("\n" + "=" * 60)

    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    main()
