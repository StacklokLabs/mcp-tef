"""Integration tests for TLS configuration."""

import tempfile
from pathlib import Path

import pytest

from mcp_tef.config.settings import Settings
from mcp_tef.services.tls_service import TLSCertificateService


class TestTLSCertificateGeneration:
    """Test TLS certificate generation service."""

    def test_generate_self_signed_cert(self):
        """Test generating a self-signed certificate."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cert_file, key_file = TLSCertificateService.generate_self_signed_cert(
                cert_dir=tmpdir,
                hostname="test.localhost",
                validity_days=30,
            )

            # Verify files exist
            assert Path(cert_file).exists()
            assert Path(key_file).exists()

            # Verify they're readable
            assert Path(cert_file).read_text().startswith("-----BEGIN CERTIFICATE-----")
            assert Path(key_file).read_text().startswith("-----BEGIN RSA PRIVATE KEY-----")

    def test_generate_cert_with_default_hostname(self):
        """Test generating certificate with default hostname."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cert_file, key_file = TLSCertificateService.generate_self_signed_cert(cert_dir=tmpdir)

            assert Path(cert_file).exists()
            assert Path(key_file).exists()

    def test_generate_cert_creates_directory(self):
        """Test that certificate generation creates the directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cert_dir = Path(tmpdir) / "nested" / "certs"
            cert_file, key_file = TLSCertificateService.generate_self_signed_cert(
                cert_dir=str(cert_dir),
                hostname="test.example.com",
                validity_days=7,
            )

            assert cert_dir.exists()
            assert Path(cert_file).exists()
            assert Path(key_file).exists()

    def test_validate_cert_files_valid(self):
        """Test validation of valid certificate files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cert_file, key_file = TLSCertificateService.generate_self_signed_cert(cert_dir=tmpdir)

            assert TLSCertificateService.validate_cert_files(cert_file, key_file)

    def test_validate_cert_files_missing(self):
        """Test validation fails for missing files."""
        assert not TLSCertificateService.validate_cert_files(
            "/nonexistent/cert.pem", "/nonexistent/key.pem"
        )

    def test_validate_cert_files_none(self):
        """Test validation fails for None values."""
        assert not TLSCertificateService.validate_cert_files(None, None)

    def test_validate_cert_files_partial(self):
        """Test validation fails when only cert or only key is provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cert_file, key_file = TLSCertificateService.generate_self_signed_cert(cert_dir=tmpdir)

            # Only cert, no key
            assert not TLSCertificateService.validate_cert_files(cert_file, None)

            # Only key, no cert
            assert not TLSCertificateService.validate_cert_files(None, key_file)

    def test_validate_cert_files_one_missing(self):
        """Test validation fails when one file is missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            cert_file, key_file = TLSCertificateService.generate_self_signed_cert(cert_dir=tmpdir)

            # Delete key file
            Path(key_file).unlink()
            assert not TLSCertificateService.validate_cert_files(cert_file, key_file)


class TestTLSSettings:
    """Test TLS configuration in Settings."""

    def test_default_tls_enabled(self):
        """Test TLS is enabled by default."""
        settings = Settings()
        assert settings.tls_enabled is True
        assert settings.tls_auto_generate is True
        assert settings.tls_cert_dir == ".certs"

    def test_tls_can_be_disabled(self):
        """Test TLS can be disabled via settings."""
        settings = Settings(tls_enabled=False)
        assert settings.tls_enabled is False

    def test_tls_custom_cert_paths(self):
        """Test custom certificate paths can be configured."""
        settings = Settings(
            tls_cert_file="/custom/path/cert.pem", tls_key_file="/custom/path/key.pem"
        )
        assert settings.tls_cert_file == "/custom/path/cert.pem"
        assert settings.tls_key_file == "/custom/path/key.pem"

    def test_tls_auto_generate_can_be_disabled(self):
        """Test auto-generation can be disabled."""
        settings = Settings(tls_auto_generate=False)
        assert settings.tls_auto_generate is False

    def test_tls_custom_cert_dir(self):
        """Test custom certificate directory can be configured."""
        settings = Settings(tls_cert_dir="/custom/certs")
        assert settings.tls_cert_dir == "/custom/certs"


class TestInsecureMode:
    """Test server operation with TLS disabled (insecure HTTP mode)."""

    @pytest.mark.asyncio
    async def test_server_runs_without_tls(self, test_db):
        """Test that the server can run in insecure HTTP mode."""
        from httpx import ASGITransport, AsyncClient

        from mcp_tef.api.app import app

        # Configure settings with TLS disabled
        settings = Settings(
            tls_enabled=False,
            database_url="sqlite:///:memory:",
            log_level="INFO",
        )

        # Override app state for testing
        app.state.settings = settings
        app.state.db = test_db

        # Create client for HTTP testing (no TLS)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test that API endpoints are accessible
            response = await client.get("/health")
            assert response.status_code == 200

            # Test another endpoint to ensure full functionality
            response = await client.get("/test-cases")
            assert response.status_code == 200
            result = response.json()
            assert "items" in result
            assert isinstance(result["items"], list)

    def test_insecure_mode_settings_validation(self):
        """Test that insecure mode settings are correctly configured."""
        settings = Settings(tls_enabled=False)

        # Verify TLS is disabled
        assert settings.tls_enabled is False

        # Other settings should still work
        assert settings.port > 0
        assert settings.host is not None

    @pytest.mark.asyncio
    async def test_insecure_mode_with_all_endpoints(self, test_db):
        """Test that all main API endpoints work without TLS."""
        from httpx import ASGITransport, AsyncClient

        from mcp_tef.api.app import app

        settings = Settings(tls_enabled=False, database_url="sqlite:///:memory:")
        app.state.settings = settings
        app.state.db = test_db

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Test various endpoints (only those with GET / support)
            endpoints = [
                "/health",
                "/test-cases",
            ]

            for endpoint in endpoints:
                response = await client.get(endpoint)
                assert response.status_code == 200, f"Endpoint {endpoint} failed"

    def test_tls_disabled_takes_precedence(self):
        """Test that when TLS is disabled, cert/key settings are ignored."""
        settings = Settings(
            tls_enabled=False,
            tls_cert_file="/some/cert.pem",
            tls_key_file="/some/key.pem",
        )

        # TLS should still be disabled regardless of cert/key paths
        assert settings.tls_enabled is False
        # Cert/key settings should be preserved but not used
        assert settings.tls_cert_file == "/some/cert.pem"
        assert settings.tls_key_file == "/some/key.pem"
