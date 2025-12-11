"""Main entry point for the MCP Tool Evaluation System.

This module allows the package to be run as: python -m mcp_tef
"""

import sys

import structlog
import uvicorn

from mcp_tef.config.logging_config import setup_logging
from mcp_tef.config.settings import get_settings
from mcp_tef.services.tls_service import TLSCertificateService

logger = structlog.get_logger(__name__)


def main():
    """Run the FastAPI application with CLI-configured settings.

    CLI arguments automatically override environment variables and defaults.
    """
    settings = get_settings()

    # Setup logging early so TLS service logs are visible
    setup_logging(
        log_level=settings.log_level,
        rich_tracebacks=settings.rich_tracebacks,
        colored_logs=settings.colored_logs,
    )

    # TLS Configuration
    ssl_keyfile = None
    ssl_certfile = None

    if settings.tls_enabled:
        # Check if custom cert/key provided
        if settings.tls_cert_file and settings.tls_key_file:
            # Validate provided certificates
            if TLSCertificateService.validate_cert_files(
                settings.tls_cert_file, settings.tls_key_file
            ):
                ssl_certfile = settings.tls_cert_file
                ssl_keyfile = settings.tls_key_file
                logger.info(f"Using provided TLS certificate: {ssl_certfile}")
            else:
                logger.error("Invalid certificate files provided. Exiting.")
                sys.exit(1)
        elif settings.tls_auto_generate:
            # Auto-generate self-signed certificate
            logger.info("No TLS certificate provided. Generating self-signed certificate...")
            ssl_certfile, ssl_keyfile = TLSCertificateService.generate_self_signed_cert(
                cert_dir=settings.tls_cert_dir,
                hostname="localhost",
                validity_days=365,
            )
        else:
            logger.error(
                "TLS enabled but no certificates provided and auto-generation disabled. "
                "Use --tls-cert-file and --tls-key-file or enable --tls-auto-generate"
            )
            sys.exit(1)

        protocol = "https"
    else:
        protocol = "http"
        logger.warning("=" * 80)
        logger.warning("⚠️  TLS DISABLED - Running in INSECURE HTTP mode")
        logger.warning("   This should only be used for development/testing")
        logger.warning("   Enable TLS with: --tls-enabled")
        logger.warning("=" * 80)

    # Log server startup
    logger.info(f"Starting server at {protocol}://{settings.host}:{settings.port}")
    if settings.reload_server:
        logger.info("Auto-reload enabled (development mode)")

    # Run server with settings from CLI/env/defaults
    uvicorn.run(
        "mcp_tef.api.app:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
        reload=settings.reload_server,
        ssl_keyfile=ssl_keyfile,
        ssl_certfile=ssl_certfile,
    )


if __name__ == "__main__":
    main()
