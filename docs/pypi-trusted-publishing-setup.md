# PyPI Trusted Publishing Setup for mcp-tef-cli

This document describes how to configure PyPI trusted publishing for the `mcp-tef-cli` package.

## Overview

Trusted publishing allows GitHub Actions to publish to PyPI without storing API tokens. It uses OpenID Connect (OIDC) to establish trust between GitHub and PyPI.

## Prerequisites

- Admin access to the [StacklokLabs/mcp-tef](https://github.com/StacklokLabs/mcp-tef) repository
- PyPI account with permissions to manage `mcp-tef-cli` project

## Setup Steps

### 1. Create GitHub Environment

1. Go to **Repository Settings** → **Environments** → **New environment**
2. Name: `pypi` (must match exactly)
3. (Optional) Configure protection rules:
   - Required reviewers for production releases
   - Limit to specific branches/tags

### 2. Create PyPI Project (First Release Only)

If the `mcp-tef-cli` project doesn't exist on PyPI yet:

**Option A: Create manually first**
1. Go to https://pypi.org/manage/projects/
2. Click "Create project"
3. Name: `mcp-tef-cli`

**Option B: Use pending publisher (recommended)**
1. Go to https://pypi.org/manage/account/publishing/
2. Add a "pending publisher" before the first release
3. This allows the first release to create the project automatically

### 3. Configure Trusted Publisher on PyPI

1. Go to https://pypi.org/manage/project/mcp-tef-cli/settings/publishing/
   - Or if using pending publisher: https://pypi.org/manage/account/publishing/

2. Add a new publisher with these values:

   | Field | Value |
   |-------|-------|
   | **Owner** | `StacklokLabs` |
   | **Repository name** | `mcp-tef` |
   | **Workflow name** | `release-cli.yml` |
   | **Environment name** | `pypi` |

3. Click "Add"

## How It Works

The release workflow (`.github/workflows/release-cli.yml`) uses:

```yaml
permissions:
  id-token: write  # Required for OIDC token

jobs:
  build-and-publish:
    environment:
      name: pypi  # Must match PyPI configuration
    steps:
      - uses: pypa/gh-action-pypi-publish@v1
        # No password/token needed - uses OIDC
```

When the workflow runs:
1. GitHub generates an OIDC token identifying the workflow
2. PyPI verifies the token matches the trusted publisher configuration
3. If valid, the package is published without any stored secrets

## Testing the Setup

1. Create a test tag:
   ```bash
   git tag cli-v0.0.1-test.1
   git push origin cli-v0.0.1-test.1
   ```

2. Monitor the workflow at:
   https://github.com/StacklokLabs/mcp-tef/actions/workflows/release-cli.yml

3. Check PyPI for the published package:
   https://pypi.org/project/mcp-tef-cli/

4. Delete the test release if needed:
   - PyPI: Delete via project settings (only within 24 hours for new projects)
   - GitHub: Delete the tag and release

## Troubleshooting

### "Trusted publisher not found"

- Verify environment name matches exactly (`pypi`)
- Check workflow filename matches (`release-cli.yml`)
- Ensure owner and repo are correct (`StacklokLabs`, `mcp-tef`)

### "Environment not found"

- Create the `pypi` environment in GitHub repository settings
- Ensure the workflow references `environment: name: pypi`

### First release fails

- If the project doesn't exist, you need either:
  - A pending publisher configured on your PyPI account
  - Manual project creation on PyPI first

## References

- [PyPI Trusted Publishing Documentation](https://docs.pypi.org/trusted-publishers/)
- [GitHub OIDC for PyPI](https://docs.github.com/en/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-pypi)
- [pypa/gh-action-pypi-publish](https://github.com/pypa/gh-action-pypi-publish)
