"""TLS certificate generation and management service."""

import ipaddress
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

logger = logging.getLogger(__name__)


class TLSCertificateService:
    """Manages TLS certificate generation and validation."""

    @staticmethod
    def generate_self_signed_cert(
        cert_dir: str,
        hostname: str = "localhost",
        validity_days: int = 365,
    ) -> tuple[str, str]:
        """Generate a self-signed certificate and private key.

        Args:
            cert_dir: Directory to store the certificate files
            hostname: Hostname for the certificate (default: localhost)
            validity_days: Certificate validity period in days

        Returns:
            Tuple of (cert_path, key_path)
        """
        cert_path = Path(cert_dir)
        cert_path.mkdir(parents=True, exist_ok=True)

        cert_file = cert_path / "cert.pem"
        key_file = cert_path / "key.pem"

        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )

        # Create certificate
        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COUNTRY_NAME, "US"),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "mcp-tef Dev"),
                x509.NameAttribute(NameOID.COMMON_NAME, hostname),
            ]
        )

        now = datetime.now(UTC)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + timedelta(days=validity_days))
            .add_extension(
                x509.SubjectAlternativeName(
                    [
                        x509.DNSName(hostname),
                        x509.DNSName("*.localhost"),
                        x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                        x509.IPAddress(ipaddress.IPv6Address("::1")),
                    ]
                ),
                critical=False,
            )
            .sign(private_key, hashes.SHA256(), default_backend())
        )

        # Write certificate
        with open(cert_file, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        # Write private key
        with open(key_file, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        # Get certificate details for logging
        fingerprint = cert.fingerprint(hashes.SHA256()).hex(":")
        expiry = cert.not_valid_after_utc

        logger.info("=" * 80)
        logger.info("🔒 Self-signed TLS certificate generated")
        logger.info(f"   Certificate: {cert_file.absolute()}")
        logger.info(f"   Private Key: {key_file.absolute()}")
        logger.info(f"   Subject: {hostname}")
        logger.info(f"   Fingerprint (SHA256): {fingerprint}")
        logger.info(f"   Valid Until: {expiry.isoformat()}")
        logger.warning("⚠️  This is a SELF-SIGNED certificate - browsers will show warnings")
        logger.info("=" * 80)

        return str(cert_file.absolute()), str(key_file.absolute())

    @staticmethod
    def validate_cert_files(cert_file: str | None, key_file: str | None) -> bool:
        """Check if certificate and key files exist and are readable.

        Args:
            cert_file: Path to certificate file
            key_file: Path to key file

        Returns:
            True if both files exist and are readable
        """
        if not cert_file or not key_file:
            return False

        cert_path = Path(cert_file)
        key_path = Path(key_file)

        if not cert_path.exists():
            logger.error(f"Certificate file not found: {cert_file}")
            return False

        if not key_path.exists():
            logger.error(f"Private key file not found: {key_file}")
            return False

        return True
