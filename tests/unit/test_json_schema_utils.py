"""Tests for JSON Schema utilities."""

import pytest

from mcp_tef.services.json_schema_utils import (
    CircularReferenceError,
    extract_parameter_descriptions,
    get_parameter_type,
    get_required_parameters,
    resolve_refs,
    resolve_refs_cached,
)


class TestResolveRefs:
    """Tests for resolve_refs function."""

    def test_resolve_simple_ref(self):
        """Test resolving a simple $ref to a definition."""
        schema = {
            "$defs": {
                "Address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string", "description": "Street name"},
                        "city": {"type": "string", "description": "City name"},
                    },
                }
            },
            "properties": {
                "name": {"type": "string", "description": "Person name"},
                "address": {"$ref": "#/$defs/Address"},
            },
        }

        resolved = resolve_refs(schema)

        # Original should be unchanged
        assert "$ref" in schema["properties"]["address"]

        # Resolved should have definition inlined
        assert "$ref" not in resolved["properties"]["address"]
        assert resolved["properties"]["address"]["type"] == "object"
        assert "street" in resolved["properties"]["address"]["properties"]
        assert "city" in resolved["properties"]["address"]["properties"]

    def test_resolve_nested_refs(self):
        """Test resolving nested $refs."""
        schema = {
            "$defs": {
                "City": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "City name"},
                    },
                },
                "Address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                        "city": {"$ref": "#/$defs/City"},
                    },
                },
            },
            "properties": {
                "address": {"$ref": "#/$defs/Address"},
            },
        }

        resolved = resolve_refs(schema)

        # Check nested resolution
        address_prop = resolved["properties"]["address"]
        assert "street" in address_prop["properties"]
        city_prop = address_prop["properties"]["city"]
        assert city_prop["type"] == "object"
        assert "name" in city_prop["properties"]

    def test_resolve_without_refs(self):
        """Test schema without $ref remains unchanged."""
        schema = {
            "properties": {
                "name": {"type": "string", "description": "Name"},
                "age": {"type": "integer", "description": "Age"},
            }
        }

        resolved = resolve_refs(schema)

        assert resolved == schema

    def test_resolve_missing_ref(self):
        """Test handling of missing $ref target."""
        schema = {
            "$defs": {},
            "properties": {
                "missing": {"$ref": "#/$defs/NonExistent"},
            },
        }

        resolved = resolve_refs(schema)

        # Should keep the $ref if it can't be resolved
        assert "$ref" in resolved["properties"]["missing"]

    def test_resolve_circular_ref(self):
        """Test detection of circular references."""
        schema = {
            "$defs": {
                "Node": {
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "next": {"$ref": "#/$defs/Node"},
                    },
                }
            },
            "properties": {
                "root": {"$ref": "#/$defs/Node"},
            },
        }

        # Should raise CircularReferenceError
        with pytest.raises(CircularReferenceError, match="Circular reference detected"):
            resolve_refs(schema)

    def test_resolve_definitions_key(self):
        """Test resolving with 'definitions' vs '$defs' (older JSON Schema draft)."""
        schema = {
            "definitions": {
                "Address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string", "description": "Street name"},
                    },
                }
            },
            "properties": {
                "address": {"$ref": "#/definitions/Address"},
            },
        }

        resolved = resolve_refs(schema)

        # Should resolve using 'definitions' key
        assert "$ref" not in resolved["properties"]["address"]
        assert resolved["properties"]["address"]["type"] == "object"
        assert "street" in resolved["properties"]["address"]["properties"]


class TestExtractParameterDescriptions:
    """Tests for extract_parameter_descriptions function."""

    def test_extract_simple_parameters(self):
        """Test extracting descriptions from simple schema."""
        schema = {
            "properties": {
                "name": {"type": "string", "description": "User name"},
                "age": {"type": "integer", "description": "User age"},
                "email": {"type": "string", "description": "Email address"},
            }
        }

        params = extract_parameter_descriptions(schema)

        assert params == {
            "name": "User name",
            "age": "User age",
            "email": "Email address",
        }

    def test_extract_with_refs(self):
        """Test extracting from schema with $ref."""
        schema = {
            "$defs": {
                "Address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string", "description": "Street name"},
                        "city": {"type": "string", "description": "City name"},
                    },
                }
            },
            "properties": {
                "name": {"type": "string", "description": "Person name"},
                "address": {"$ref": "#/$defs/Address", "description": "Mailing address"},
            },
        }

        params = extract_parameter_descriptions(schema)

        # Should flatten nested properties
        assert "name" in params
        assert params["name"] == "Person name"
        assert "address" in params
        assert params["address"] == "Mailing address"
        assert "address.street" in params
        assert params["address.street"] == "Street name"
        assert "address.city" in params
        assert params["address.city"] == "City name"

    def test_extract_missing_descriptions(self):
        """Test extracting when descriptions are missing."""
        schema = {
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer", "description": "User age"},
            }
        }

        params = extract_parameter_descriptions(schema)

        assert params == {
            "name": "",
            "age": "User age",
        }

    def test_extract_empty_schema(self):
        """Test extracting from empty schema."""
        params = extract_parameter_descriptions({})
        assert params == {}

    def test_extract_nested_objects(self):
        """Test extracting from nested object properties."""
        schema = {
            "properties": {
                "user": {
                    "type": "object",
                    "description": "User information",
                    "properties": {
                        "name": {"type": "string", "description": "Full name"},
                        "contact": {
                            "type": "object",
                            "description": "Contact info",
                            "properties": {
                                "email": {"type": "string", "description": "Email"},
                            },
                        },
                    },
                }
            }
        }

        params = extract_parameter_descriptions(schema)

        assert "user" in params
        assert params["user"] == "User information"
        assert "user.name" in params
        assert params["user.name"] == "Full name"
        assert "user.contact" in params
        assert params["user.contact"] == "Contact info"
        assert "user.contact.email" in params
        assert params["user.contact.email"] == "Email"


class TestGetRequiredParameters:
    """Tests for get_required_parameters function."""

    def test_get_required_fields(self):
        """Test getting required fields from schema."""
        schema = {
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            },
            "required": ["name"],
        }

        required = get_required_parameters(schema)
        assert required == ["name"]

    def test_get_required_empty(self):
        """Test schema with no required fields."""
        schema = {
            "properties": {
                "name": {"type": "string"},
            }
        }

        required = get_required_parameters(schema)
        assert required == []


class TestGetParameterType:
    """Tests for get_parameter_type function."""

    def test_get_simple_type(self):
        """Test getting type for simple parameter."""
        schema = {
            "properties": {
                "name": {"type": "string"},
                "age": {"type": "integer"},
            }
        }

        assert get_parameter_type(schema, "name") == "string"
        assert get_parameter_type(schema, "age") == "integer"

    def test_get_type_with_ref(self):
        """Test getting type when parameter uses $ref."""
        schema = {
            "$defs": {
                "Address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string"},
                    },
                }
            },
            "properties": {
                "address": {"$ref": "#/$defs/Address"},
            },
        }

        assert get_parameter_type(schema, "address") == "object"

    def test_get_type_missing_parameter(self):
        """Test getting type for non-existent parameter."""
        schema = {
            "properties": {
                "name": {"type": "string"},
            }
        }

        assert get_parameter_type(schema, "missing") is None


class TestRealWorldPydanticSchema:
    """Tests with real Pydantic-generated schemas."""

    def test_pydantic_model_with_nested_types(self):
        """Test with a realistic Pydantic schema."""
        schema = {
            "$defs": {
                "Address": {
                    "properties": {
                        "street": {
                            "title": "Street",
                            "type": "string",
                            "description": "Street address",
                        },
                        "city": {
                            "title": "City",
                            "type": "string",
                            "description": "City name",
                        },
                        "zip_code": {
                            "title": "Zip Code",
                            "type": "string",
                            "description": "Postal code",
                        },
                    },
                    "required": ["street", "city"],
                    "title": "Address",
                    "type": "object",
                }
            },
            "properties": {
                "name": {
                    "title": "Name",
                    "type": "string",
                    "description": "Person's full name",
                },
                "age": {
                    "title": "Age",
                    "type": "integer",
                    "description": "Person's age in years",
                },
                "address": {"$ref": "#/$defs/Address"},
            },
            "required": ["name", "age", "address"],
            "title": "Person",
            "type": "object",
        }

        # Test resolution
        resolved = resolve_refs(schema)
        assert "address" in resolved["properties"]
        assert resolved["properties"]["address"]["type"] == "object"
        assert "street" in resolved["properties"]["address"]["properties"]

        # Test parameter extraction
        params = extract_parameter_descriptions(schema)
        assert params["name"] == "Person's full name"
        assert params["age"] == "Person's age in years"
        assert params["address.street"] == "Street address"
        assert params["address.city"] == "City name"
        assert params["address.zip_code"] == "Postal code"

        # Test required fields
        required = get_required_parameters(schema)
        assert set(required) == {"name", "age", "address"}

        # Test type extraction
        assert get_parameter_type(schema, "name") == "string"
        assert get_parameter_type(schema, "age") == "integer"
        assert get_parameter_type(schema, "address") == "object"


class TestCachedResolveRefs:
    """Tests for resolve_refs_cached function."""

    def test_cached_resolution(self):
        """Test that caching works for repeated calls."""
        schema = {
            "$defs": {
                "Address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string", "description": "Street name"},
                    },
                }
            },
            "properties": {
                "address": {"$ref": "#/$defs/Address"},
            },
        }

        # First call should cache result
        resolved1 = resolve_refs_cached(schema)
        # Second call should return cached result
        resolved2 = resolve_refs_cached(schema)

        # Both should be resolved correctly
        assert "$ref" not in resolved1["properties"]["address"]
        assert "$ref" not in resolved2["properties"]["address"]
        assert resolved1 == resolved2

    def test_uncacheable_schema_fallback(self):
        """Test that uncacheable schemas fall back to uncached resolution."""
        schema = {
            "$defs": {
                "Address": {
                    "type": "object",
                    "properties": {
                        "street": {"type": "string", "description": "Street name"},
                    },
                }
            },
            "properties": {
                "address": {"$ref": "#/$defs/Address"},
                "tags": ["tag1", "tag2"],  # List makes it unhashable
            },
        }

        # Should handle uncacheable schema gracefully
        resolved = resolve_refs_cached(schema)
        assert "$ref" not in resolved["properties"]["address"]
