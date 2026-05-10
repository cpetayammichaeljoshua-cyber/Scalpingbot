"""
MiroFish Backend — Production Flask Application Factory
"""

from __future__ import annotations

import os
import time
import uuid
import warnings

# Suppress noisy third-party resource tracker warnings before any other imports
warnings.filterwarnings("ignore", message=".*resource_tracker.*")
warnings.filterwarnings("ignore", category=DeprecationWarning)

from flask import Flask, request, jsonify, g
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .utils.logger import setup_logger, get_logger


def create_app(config_class: type = Config) -> Flask:
    """Flask application factory — production-hardened."""
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── Production JSON encoding (no ASCII escaping for Unicode/CJK chars) ──
    if hasattr(app, "json") and hasattr(app.json, "ensure_ascii"):
        app.json.ensure_ascii = False

    # ── Proxy fix (Replit, nginx, etc.) ──
    # Handles X-Forwarded-For, X-Forwarded-Proto, X-Forwarded-Host
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    # ── Logging ──
    logger = setup_logger("mirofish")

    _is_reloader = os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    _debug_mode  = app.config.get("DEBUG", False)
    _log_startup = not _debug_mode or _is_reloader

    if _log_startup:
        logger.info("=" * 50)
        logger.info("MiroFish Backend 启动中...")
        logger.info("=" * 50)

    # ── CORS — allow all origins on /api/* ──
    CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=False)

    # ── Request lifecycle hooks ──
    @app.before_request
    def _before_request() -> None:
        g.request_id = str(uuid.uuid4())[:8]
        g.start_time = time.monotonic()
        req_logger = get_logger("mirofish.request")
        req_logger.debug(
            f"[{g.request_id}] ▶ {request.method} {request.path}"
            + (f" body={request.get_json(silent=True)}" if request.is_json else "")
        )

    @app.after_request
    def _after_request(response):
        rid  = getattr(g, "request_id", "-")
        dur  = time.monotonic() - getattr(g, "start_time", time.monotonic())
        code = response.status_code
        get_logger("mirofish.request").debug(
            f"[{rid}] ◀ {code} ({dur*1000:.1f}ms)"
        )
        # ── Security headers ──
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers["X-Request-ID"] = rid
        return response

    # ── Simulation cleanup ──
    from .services.simulation_runner import SimulationRunner
    SimulationRunner.register_cleanup()
    if _log_startup:
        logger.info("已注册模拟进程清理函数")

    # ── Blueprints ──
    from .api import graph_bp, simulation_bp, report_bp
    app.register_blueprint(graph_bp,    url_prefix="/api/graph")
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    app.register_blueprint(report_bp,   url_prefix="/api/report")

    # ── Health check ──
    @app.route("/health")
    def health():
        return jsonify({
            "status":  "ok",
            "service": "MiroFish Backend",
            "version": "2.0.0",
            "llm_configured": bool(Config.LLM_API_KEY),
            "zep_configured": bool(Config.ZEP_API_KEY),
        })

    # ── Error handlers ──
    @app.errorhandler(400)
    def bad_request(exc):
        logger.debug(f"400 Bad Request: {exc}")
        return jsonify({"success": False, "error": "Bad request", "detail": str(exc)}), 400

    @app.errorhandler(404)
    def not_found(exc):
        return jsonify({"success": False, "error": "Endpoint not found", "path": request.path}), 404

    @app.errorhandler(405)
    def method_not_allowed(exc):
        return jsonify({"success": False, "error": "Method not allowed", "method": request.method}), 405

    @app.errorhandler(413)
    def request_too_large(exc):
        return jsonify({"success": False, "error": "Request entity too large"}), 413

    @app.errorhandler(429)
    def rate_limited(exc):
        return jsonify({"success": False, "error": "Too many requests — slow down"}), 429

    @app.errorhandler(500)
    def internal_error(exc):
        logger.exception(f"500 Internal Server Error: {exc}")
        return jsonify({"success": False, "error": "Internal server error"}), 500

    @app.errorhandler(503)
    def service_unavailable(exc):
        return jsonify({"success": False, "error": "Service temporarily unavailable"}), 503

    @app.errorhandler(Exception)
    def handle_unhandled(exc):
        logger.exception(f"Unhandled exception: {type(exc).__name__}: {exc}")
        return jsonify({
            "success": False,
            "error":   "Unexpected server error",
            "type":    type(exc).__name__,
        }), 500

    if _log_startup:
        logger.info("MiroFish Backend 启动完成")

    return app
