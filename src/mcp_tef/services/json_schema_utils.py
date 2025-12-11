"""Utilities for working with JSON Schema, including $ref resolution."""

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class CircularReferenceError(ValueError):
    """Raised when a circular reference is detected in JSON Schema $refs."""


def resolve_refs(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively resolve $ref references in a JSON Schema.

    Only handles internal references within the same schema document
    (references starting with #/).

    Args:
        schema: JSON Schema with potential $ref references

    Returns:
        Schema with all $ref references resolved inline

    Raises:
        CircularReferenceError: If a circular reference is detected
    """
    if not isinstance(schema, dict):
        return schema

    # Get definitions from the schema
    # (handles both $defs and definitions for JSON Schema draft compatibility)
    defs = schema.get("$defs", schema.get("definitions", {}))

    def resolve_value(value: Any, visited: set[str] | None = None) -> Any:
        """Recursively resolve $ref in any value.

        Args:
            value: Value to resolve
            visited: Set of already visited $ref paths to detect circular references

        Returns:
            Resolved value

        Raises:
            CircularReferenceError: If a circular reference is detected
        """
        if visited is None:
            visited = set()

        if isinstance(value, dict):
            # If this is a $ref, resolve it
            if "$ref" in value:
                ref = value["$ref"]
                if ref.startswith(("#/$defs/", "#/definitions/")):
                    # Check for circular reference
                    if ref in visited:
                        msg = f"Circular reference detected: {ref}"
                        logger.error(msg)
                        raise CircularReferenceError(msg)

                    # Extract definition name
                    def_name = ref.replace("#/$defs/", "").replace("#/definitions/", "")

                    if def_name in defs:
                        # Add to visited set before recursion
                        new_visited = visited | {ref}

                        # Recursively resolve the definition
                        resolved_def = resolve_value(defs[def_name].copy(), new_visited)

                        # Preserve any additional properties from the original $ref
                        # (like description, title, etc.)
                        for key, val in value.items():
                            if key != "$ref" and key not in resolved_def:
                                resolved_def[key] = val
                        return resolved_def

                    msg = f"Reference not found in $defs: {ref}"
                    logger.warning(msg)
                    # Return unresolved reference rather than failing silently
                    # Downstream code should handle missing types gracefully
                    return value

                # Keep non-internal references as-is
                return value

            # Recursively process all dict values
            return {k: resolve_value(v, visited) for k, v in value.items()}

        if isinstance(value, list):
            # Recursively process list items
            return [resolve_value(item, visited) for item in value]

        return value

    # Create a copy and resolve all references
    resolved = schema.copy()
    if "properties" in resolved:
        resolved["properties"] = resolve_value(resolved["properties"])

    return resolved


# Simple in-memory cache for resolved schemas
# Key: JSON string of schema, Value: Resolved schema
_schema_cache: dict[str, dict[str, Any]] = {}


def resolve_refs_cached(schema: dict[str, Any]) -> dict[str, Any]:
    """Resolve $ref references with caching to avoid redundant resolution.

    Uses JSON serialization for cache keys. This is more reliable than trying to
    hash complex nested structures.

    Args:
        schema: JSON Schema with potential $ref references

    Returns:
        Schema with all $ref references resolved inline
    """
    import json

    # Create cache key from JSON representation
    try:
        # Sort keys for consistent cache keys
        cache_key = json.dumps(schema, sort_keys=True)

        # Check cache first
        if cache_key in _schema_cache:
            return _schema_cache[cache_key]

        # Resolve and cache
        resolved = resolve_refs(schema)
        _schema_cache[cache_key] = resolved

        # Limit cache size to prevent memory issues (simple FIFO eviction)
        if len(_schema_cache) > 1000:
            # Remove oldest entries (first 200)
            keys_to_remove = list(_schema_cache.keys())[:200]
            for key in keys_to_remove:
                del _schema_cache[key]

        return resolved

    except (TypeError, ValueError):
        # If schema can't be serialized, fall back to uncached version
        return resolve_refs(schema)


def extract_parameter_descriptions(schema: dict[str, Any]) -> dict[str, str]:
    """Extract parameter names and descriptions from a JSON Schema.

    Handles schemas with $ref by resolving them first.
    For nested object parameters, creates flattened keys like "address.street".

    Args:
        schema: JSON Schema (may contain $ref references)

    Returns:
        Dictionary mapping parameter names to descriptions
    """
    # First resolve any $ref references
    resolved_schema = resolve_refs(schema)

    params: dict[str, str] = {}

    def extract_from_properties(properties: dict[str, Any], prefix: str = "") -> None:
        """Recursively extract descriptions from properties."""
        for prop_name, prop_schema in properties.items():
            full_name = f"{prefix}{prop_name}" if prefix else prop_name

            if not isinstance(prop_schema, dict):
                continue

            # Get description for this property
            description = prop_schema.get("description", "")

            # If it's an object with nested properties, recurse
            if prop_schema.get("type") == "object" and "properties" in prop_schema:
                # Add the parent object description
                if description:
                    params[full_name] = description

                # Recurse into nested properties
                extract_from_properties(prop_schema["properties"], prefix=f"{full_name}.")
            else:
                # Leaf property - add description
                params[full_name] = description

    # Extract from top-level properties
    properties = resolved_schema.get("properties", {})
    if properties:
        extract_from_properties(properties)

    return params


def get_required_parameters(schema: dict[str, Any]) -> list[str]:
    """Get list of required parameter names from JSON Schema.

    Args:
        schema: JSON Schema

    Returns:
        List of required parameter names
    """
    return schema.get("required", [])


def get_parameter_type(schema: dict[str, Any], parameter_name: str) -> str | None:
    """Get the type of a specific parameter from JSON Schema.

    Resolves $ref if needed.

    Args:
        schema: JSON Schema
        parameter_name: Name of the parameter

    Returns:
        Type string (e.g., "string", "integer", "object") or None if not found
    """
    resolved_schema = resolve_refs(schema)
    properties = resolved_schema.get("properties", {})

    if parameter_name not in properties:
        return None

    param_schema = properties[parameter_name]
    if isinstance(param_schema, dict):
        return param_schema.get("type")

    return None
