# TLS Configuration Guide

This document explains how to configure TLS/HTTPS for the mcp-tef server.

## Overview

mcp-tef supports two operation modes:
1. **Secure Mode (Default)**: HTTPS with TLS encryption
2. **Insecure Mode**: HTTP without encryption (development/testing only)

## Secure Mode (HTTPS) - Default

By default, the server runs with TLS enabled using auto-generated self-signed certificates.

### Basic Usage

```bash
# Start with default TLS (auto-generates certificate)
uv run python -m mcp_tef

# Explicitly enable TLS
uv run python -m mcp_tef --tls-enabled=true
```

### Custom Certificates

You can provide your own TLS certificates:

```bash
uv run python -m mcp_tef \
  --tls-cert-file=/path/to/cert.pem \
  --tls-key-file=/path/to/key.pem
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `--tls-enabled` | `true` | Enable/disable TLS |
| `--tls-cert-file` | `None` | Path to TLS certificate (PEM format) |
| `--tls-key-file` | `None` | Path to TLS private key (PEM format) |
| `--tls-auto-generate` | `true` | Auto-generate self-signed certificate if not provided |
| `--tls-cert-dir` | `.certs` | Directory for storing auto-generated certificates |

### Environment Variables

You can also configure TLS via environment variables:

```bash
export TLS_ENABLED=true
export TLS_CERT_FILE=/path/to/cert.pem
export TLS_KEY_FILE=/path/to/key.pem
export TLS_AUTO_GENERATE=true
export TLS_CERT_DIR=.certs
```

## Insecure Mode (HTTP) - Development Only

For development and testing, you can disable TLS to run the server over plain HTTP.

⚠️ **WARNING**: Insecure mode should NEVER be used in production environments!

### Usage

```bash
# Disable TLS for development/testing
uv run python -m mcp_tef --tls-enabled=false
```

When running in insecure mode, you'll see a prominent warning:

```
WARNING: ================================================================================
WARNING: ⚠️  TLS DISABLED - Running in INSECURE HTTP mode
WARNING:    This should only be used for development/testing
WARNING:    Enable TLS with: --tls-enabled
WARNING: ================================================================================
INFO: Starting server at http://0.0.0.0:8000
```

### When to Use Insecure Mode

Insecure mode is appropriate for:
- Local development and testing
- Debugging TLS-related issues
- Running behind a TLS-terminating reverse proxy (e.g., nginx, Cloudflare)
- Containerized environments where TLS is handled at the infrastructure level

### Testing Insecure Mode

The project includes comprehensive tests for insecure mode:

```bash
# Run insecure mode tests
uv run pytest tests/integration/test_tls_configuration.py::TestInsecureMode -v

# Run all TLS configuration tests
uv run pytest tests/integration/test_tls_configuration.py -v
```

## Self-Signed Certificates

When TLS is enabled without custom certificates, mcp-tef automatically generates a self-signed certificate with:

- **Validity**: 365 days
- **Subject**: localhost
- **SANs** (Subject Alternative Names):
  - `localhost`
  - `*.localhost`
  - `127.0.0.1`
  - `::1`

### Certificate Information

When a certificate is auto-generated, you'll see details in the logs:

```
INFO: ================================================================================
INFO: 🔒 Self-signed TLS certificate generated
INFO:    Certificate: /path/to/mcp-tef/.certs/cert.pem
INFO:    Private Key: /path/to/mcp-tef/.certs/key.pem
INFO:    Subject: localhost
INFO:    Fingerprint (SHA256): a3:41:cd:b2:bb:98:fa:b3:59:18:76:d3:0f:e5:3a:16:...
INFO:    Valid Until: 2026-11-06T15:11:32+00:00
WARNING: ⚠️  This is a SELF-SIGNED certificate - browsers will show warnings
INFO: ================================================================================
```

### Browser Warnings

Self-signed certificates will trigger browser security warnings. This is expected behavior. To use the server:

1. Accept the security exception in your browser
2. Or use `curl` with `--insecure` / `-k` flag:
   ```bash
   curl -k https://localhost:8000/health
   ```
3. Or provide a proper CA-signed certificate using `--tls-cert-file` and `--tls-key-file`

## Production Deployment

For production deployments, you should:

1. **Use a proper CA-signed certificate** (e.g., Let's Encrypt)
2. **Never disable TLS** in production
3. Consider using a reverse proxy (nginx, Traefik, Caddy) for TLS termination
4. Implement proper certificate rotation and monitoring

### Example with Let's Encrypt

```bash
# Using certbot certificates
uv run python -m mcp_tef \
  --tls-cert-file=/etc/letsencrypt/live/yourdomain.com/fullchain.pem \
  --tls-key-file=/etc/letsencrypt/live/yourdomain.com/privkey.pem \
  --port=443
```

## Troubleshooting

### Certificate Validation Errors

If you encounter certificate validation errors:

1. Check that both `--tls-cert-file` and `--tls-key-file` are provided
2. Verify files exist and are readable
3. Ensure files are in PEM format
4. Check certificate expiration date

### Port Permission Issues

Port 443 (HTTPS) requires root/admin privileges:

```bash
# Option 1: Use a higher port number
uv run python -m mcp_tef --port=8443

# Option 2: Use sudo (not recommended)
sudo uv run python -m mcp_tef --port=443
```

## API Endpoints

The server provides these endpoints in both modes:

- `/health` - Health check endpoint
- `/mcp-servers` - MCP server management
- `/tools` - Tool definitions
- `/test-cases` - Test case management
- `/metrics` - Metrics and analytics
- `/similarity` - Similarity analysis

All endpoints work identically in both secure and insecure modes.

## Testing

The TLS configuration is thoroughly tested:

```bash
# Run all TLS tests
uv run pytest tests/integration/test_tls_configuration.py -v

# Test certificate generation
uv run pytest tests/integration/test_tls_configuration.py::TestTLSCertificateGeneration -v

# Test TLS settings
uv run pytest tests/integration/test_tls_configuration.py::TestTLSSettings -v

# Test insecure mode
uv run pytest tests/integration/test_tls_configuration.py::TestInsecureMode -v
```

Current test coverage for `tls_service.py`: **100%**

## Summary

- **Default**: TLS enabled with auto-generated self-signed certificate
- **Development**: Use `--tls-enabled=false` for plain HTTP
- **Production**: Use CA-signed certificates with `--tls-cert-file` and `--tls-key-file`
- **Never** disable TLS in production environments

