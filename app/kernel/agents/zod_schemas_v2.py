"""
Enhanced Zod-style Schema System for BEAST - Phase 2.
Extends Pydantic with Zod-like patterns and TypeScript generation.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import (
    Any, Dict, List, Optional, Type, Union, Callable, get_type_hints,
    get_origin, get_args, Annotated, Literal
)
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic.json_schema import GenerateJsonSchema
from pydantic_core import core_schema
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import BaseModel as PydanticBaseModel


# =============================================================================
# Enhanced Type System (Zod-like patterns)
# =============================================================================

class ExecutionTarget(str, Enum):
    LOCAL = "local"
    SSH = "ssh"
    CONTAINER = "container"


class ToolEffect(str, Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    PROMOTION = "promotion"


class ToolRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DecisionType(str, Enum):
    TOOL = "tool"
    COMPLETE = "complete"
    BLOCKED = "blocked"


# =============================================================================
# Zod-like Schema Primitives (extends Pydantic)
# =============================================================================

class ZodString(str):
    """String with Zod-like refinements."""
    
    @classmethod
    def __get_pydantic_json_schema__(cls, core_schema, handler):
        schema = handler(str)
        schema.update({
            "type": "string",
            "description": cls.__doc__ or "String value"
        })
        return schema
    
    @classmethod
    def email(cls) -> Type["ZodString"]:
        class EmailString(cls):
            @classmethod
            def __get_pydantic_json_schema__(cls, core_schema, handler):
                schema = handler(str)
                schema.update({"format": "email"})
                return schema
            
            @field_validator("value")
            @classmethod
            def validate_email(cls, v: str) -> str:
                if "@" not in v:
                    raise ValueError("Invalid email format")
                return v
        return EmailString
    
    @classmethod
    def url(cls) -> Type["ZodString"]:
        class UrlString(cls):
            @classmethod
            def __get_pydantic_json_schema__(cls, core_schema, handler):
                schema = handler(str)
                schema.update({"format": "uri"})
                return schema
            
            @field_validator("value")
            @classmethod
            def validate_url(cls, v: str) -> str:
                if not (v.startswith("http://") or v.startswith("https://")):
                    raise ValueError("Invalid URL format")
                return v
        return UrlString
    
    @classmethod
    def uuid(cls) -> Type["ZodString"]:
        class UuidString(cls):
            @classmethod
            def __get_pydantic_json_schema__(cls, core_schema, handler):
                schema = handler(str)
                schema.update({"format": "uuid"})
                return schema
        return UuidString
    
    @classmethod
    def min(cls, length: int) -> Type["ZodString"]:
        class MinString(cls):
            min_length = length
            
            @classmethod
            def __get_pydantic_json_schema__(cls, core_schema, handler):
                schema = handler(str)
                schema.update({"minLength": length})
                return schema
            
            @field_validator("value")
            @classmethod
            def validate_min(cls, v: str) -> str:
                if len(v) < length:
                    raise ValueError(f"String must be at least {length} characters")
                return v
        return MinString
    
    @classmethod
    def max(cls, length: int) -> Type["ZodString"]:
        class MaxString(cls):
            max_length = length
            
            @classmethod
            def __get_pydantic_json_schema__(cls, core_schema, handler):
                schema = handler(str)
                schema.update({"maxLength": length})
                return schema
            
            @field_validator("value")
            @classmethod
            def validate_max(cls, v: str) -> str:
                if len(v) > length:
                    raise ValueError(f"String must be at most {length} characters")
                return v
        return MaxString
    
    @classmethod
    def regex(cls, pattern: str) -> Type["ZodString"]:
        class RegexString(cls):
            regex_pattern = pattern
            
            @classmethod
            def __get_pydantic_json_schema__(cls, core_schema, handler):
                schema = handler(str)
                schema.update({"pattern": pattern})
                return schema
            
            @field_validator("value")
            @classmethod
            def validate_regex(cls, v: str) -> str:
                if not re.match(pattern, v):
                    raise ValueError(f"String does not match pattern: {pattern}")
                return v
        return RegexString


class ZodNumber(int):
    """Number with Zod-like refinements."""
    
    @classmethod
    def min(cls, value: int) -> Type["ZodNumber"]:
        class MinNumber(cls):
            min_value = value
            
            @classmethod
            def __get_pydantic_json_schema__(cls, core_schema, handler):
                schema = handler(int)
                schema.update({"minimum": value})
                return schema
        return MinNumber
    
    @classmethod
    def max(cls, value: int) -> Type["ZodNumber"]:
        class MaxNumber(cls):
            max_value = value
            
            @classmethod
            def __get_pydantic_json_schema__(cls, core_schema, handler):
                schema = handler(int)
                schema.update({"maximum": value})
                return schema
        return MaxNumber
    
    @classmethod
    def positive(cls) -> Type["ZodNumber"]:
        class PositiveNumber(cls):
            @classmethod
            def __get_pydantic_json_schema__(cls, core_schema, handler):
                schema = handler(int)
                schema.update({"exclusiveMinimum": 0})
                return schema
            
            @field_validator("value")
            @classmethod
            def validate_positive(cls, v: int) -> int:
                if v <= 0:
                    raise ValueError("Number must be positive")
                return v
        return PositiveNumber


class ZodArray(list):
    """Array with Zod-like refinements."""
    
    @classmethod
    def min(cls, length: int) -> Type["ZodArray"]:
        class MinArray(cls):
            min_items = length
            
            @classmethod
            def __get_pydantic_json_schema__(cls, core_schema, handler):
                schema = handler(list)
                schema.update({"minItems": length})
                return schema
        return MinArray
    
    @classmethod
    def max(cls, length: int) -> Type["ZodArray"]:
        class MaxArray(cls):
            max_items = length
            
            @classmethod
            def __get_pydantic_json_schema__(cls, core_schema, handler):
                schema = handler(list)
                schema.update({"maxItems": length})
                return schema
        return MaxArray
    
    @classmethod
    def nonempty(cls) -> Type["ZodArray"]:
        class NonEmptyArray(cls):
            @classmethod
            def __get_pydantic_json_schema__(cls, core_schema, handler):
                schema = handler(list)
                schema.update({"minItems": 1})
                return schema
        return NonEmptyArray


# =============================================================================
# Schema Builder (Zod-like fluent API)
# =============================================================================

class SchemaBuilder:
    """Fluent schema builder for creating Zod-like schemas."""
    
    def __init__(self):
        self._fields: Dict[str, Any] = {}
        self._required: List[str] = []
        self._description: str = ""
    
    def field(self, name: str, type_: Type, **kwargs) -> "SchemaBuilder":
        """Add a field to the schema."""
        self._fields[name] = {"type": type_, "kwargs": kwargs}
        return self
    
    def required(self, *names: str) -> "SchemaBuilder":
        """Mark fields as required."""
        self._required.extend(names)
        return self
    
    def optional(self, *names: str) -> "SchemaBuilder":
        """Mark fields as optional."""
        for name in names:
            if name in self._fields:
                self._fields[name]["kwargs"]["default"] = None
        return self
    
    def description(self, desc: str) -> "SchemaBuilder":
        self._description = desc
        return self
    
    def build(self) -> Type[BaseModel]:
        """Build the Pydantic model."""
        annotations = {}
        defaults = {}
        
        for name, field_info in self._fields.items():
            type_ = field_info["type"]
            kwargs = field_info["kwargs"]
            
            if name not in self._required:
                annotations[name] = Optional[type_]
                defaults[name] = kwargs.get("default", None)
            else:
                annotations[name] = type_
        
        # Create model
        model = type(
            self._description.replace(" ", "") or "DynamicModel",
            (BaseModel,),
            {"__annotations__": annotations, **defaults}
        )
        
        if self._description:
            model.__doc__ = self._description
        
        return model


def schema() -> SchemaBuilder:
    """Create a new schema builder (Zod.object equivalent)."""
    return SchemaBuilder()


def string() -> Type[ZodString]:
    return ZodString


def number() -> Type[ZodNumber]:
    return ZodNumber


def array() -> Type[ZodArray]:
    return ZodArray


def boolean() -> Type[bool]:
    return bool


def literal(*values: Any) -> Type:
    """Create literal type (Zod.literal)."""
    return Literal[values]


def union(*types: Type) -> Type:
    """Create union type (Zod.union)."""
    return Union[types]


def optional(type_: Type) -> Type:
    """Create optional type (Zod.optional)."""
    return Optional[type_]


# =============================================================================
# Enhanced Tool Spec with Zod-like Features
# =============================================================================

class EnhancedToolSpec(BaseModel):
    """Enhanced tool specification with Zod-like features."""
    
    tool_id: str
    version: str = "1.0"
    title: str
    description: str
    category: str
    risk: ToolRisk = ToolRisk.MEDIUM
    effect: ToolEffect = ToolEffect.READ
    input_schema: Dict[str, Any]
    output_schema: Optional[Dict[str, Any]] = None
    targets: List[ExecutionTarget] = Field(default_factory=lambda: [ExecutionTarget.LOCAL])
    requires_approval: bool = False
    requires_worktree: bool = False
    timeout_seconds: int = 30
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Zod-specific enhancements
    input_transforms: List[str] = Field(default_factory=list)  # Transform functions
    input_refinements: List[str] = Field(default_factory=list)  # Refinement functions
    output_transforms: List[str] = Field(default_factory=list)
    
    def to_zod_schema(self) -> Dict[str, Any]:
        """Export as Zod-compatible JSON schema."""
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            "title": self.title,
            "description": self.description,
            "type": "object",
            "properties": self.input_schema.get("properties", {}),
            "required": self.input_schema.get("required", []),
            "additionalProperties": False,
            "x-bast-tool": {
                "tool_id": self.tool_id,
                "version": self.version,
                "risk": self.risk.value,
                "effect": self.effect.value,
                "category": self.category,
                "targets": [t.value for t in self.targets],
                "requires_approval": self.requires_approval,
                "requires_worktree": self.requires_worktree,
                "timeout_seconds": self.timeout_seconds,
            }
        }


# =============================================================================
# TypeScript Type Generator
# =============================================================================

class TypeScriptGenerator:
    """Generate TypeScript type definitions from Pydantic models."""
    
    TYPE_MAP = {
        "str": "string",
        "int": "number",
        "float": "number",
        "bool": "boolean",
        "list": "Array",
        "dict": "Record<string, any>",
        "datetime": "string",  # ISO 8601
        "UUID": "string",
        "Path": "string",
    }
    
    def __init__(self):
        self._generated: Dict[str, str] = {}
    
    def generate_type(self, model: Type[BaseModel]) -> str:
        """Generate TypeScript interface from Pydantic model."""
        model_name = model.__name__
        
        if model_name in self._generated:
            return self._generated[model_name]
        
        lines = [
            f"/**",
            f" * Auto-generated from {model.__module__}.{model_name}",
            f" * Generated at {datetime.now().isoformat()}",
            f" */",
            f"export interface {model_name} {{"
        ]
        
        for field_name, field_info in model.model_fields.items():
            ts_type = self._field_to_ts(field_info)
            required = field_info.is_required()
            optional = "" if required else "?"
            description = field_info.description or ""
            
            if description:
                lines.append(f"  /** {description} */")
            
            lines.append(f"  {field_name}{optional}: {ts_type};")
        
        lines.append("}")
        lines.append("")
        
        result = "\n".join(lines)
        self._generated[model_name] = result
        return result
    
    def _field_to_ts(self, field_info) -> str:
        """Convert Pydantic field to TypeScript type."""
        annotation = field_info.annotation
        
        if annotation is None:
            return "any"
        
        origin = get_origin(annotation)
        args = get_args(annotation)
        
        # Handle Optional
        if origin is Union and type(None) in args:
            non_none = [a for a in args if a is not type(None)]
            if len(non_none) == 1:
                return self._field_to_ts(type("temp", (), {"annotation": non_none[0]})) + " | null"
        
        # Handle Literal
        if origin is Literal:
            values = " | ".join(json.dumps(value) for value in args)
            return values
        
        # Handle List/Array
        if origin in (list, List):
            if args:
                inner_type = self._field_to_ts(type('Temp', (), {'annotation': args[0]}))
                return f"Array<{inner_type}>"
            return "Array<any>"
        
        # Handle Dict
        if origin in (dict, Dict):
            if len(args) >= 2:
                key_type = self._field_to_ts(type('Temp', (), {'annotation': args[0]}))
                value_type = self._field_to_ts(type('Temp', (), {'annotation': args[1]}))
                return f"Record<{key_type}, {value_type}>"
            return "Record<string, any>"
        
        # Handle base types
        if annotation is str:
            return "string"
        if annotation is int:
            return "number"
        if annotation is float:
            return "number"
        if annotation is bool:
            return "boolean"
        if annotation is dict:
            return "Record<string, any>"
        
        # Handle enums
        if isinstance(annotation, type) and issubclass(annotation, Enum):
            values = [f'"{e.value}"' for e in annotation]
            return " | ".join(values)
        
        # Handle nested models
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            nested_ts = self.generate_type(annotation)
            return annotation.__name__
        
        return "any"
    
    def write_to_file(self, models: List[Type[BaseModel]], output_path: Path) -> None:
        """Write all generated types to a TypeScript file."""
        lines = [
            "// Auto-generated TypeScript types for BEAST",
            "// DO NOT EDIT MANUALLY",
            f"// Generated at {datetime.now().isoformat()}",
            "",
        ]
        
        for model in models:
            lines.append(self.generate_type(model))
        
        output_path.write_text("\n".join(lines))
        print(f"Generated TypeScript types at {output_path}")


# =============================================================================
# Schema Registry with Validation
# =============================================================================

class SchemaRegistry:
    """Registry for managing schemas with validation."""
    
    def __init__(self):
        self._schemas: Dict[str, Type[BaseModel]] = {}
        self._tool_schemas: Dict[str, EnhancedToolSpec] = {}
        self._ts_generator = TypeScriptGenerator()
    
    def register(self, model: Type[BaseModel]) -> None:
        """Register a schema model."""
        self._schemas[model.__name__] = model
    
    def register_tool(self, spec: EnhancedToolSpec) -> None:
        """Register a tool specification."""
        self._tool_schemas[spec.tool_id] = spec
    
    def get_schema(self, name: str) -> Optional[Type[BaseModel]]:
        return self._schemas.get(name)
    
    def get_tool_spec(self, tool_id: str) -> Optional[EnhancedToolSpec]:
        return self._tool_schemas.get(tool_id)
    
    def validate_input(self, tool_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tool input against schema."""
        spec = self._tool_schemas.get(tool_id)
        if not spec:
            raise ValueError(f"Unknown tool: {tool_id}")
        
        # Use Pydantic for validation
        model = self._create_model_from_schema(spec.input_schema)
        validated = model(**data)
        return validated.model_dump()
    
    def validate_output(self, tool_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate tool output against schema."""
        spec = self._tool_schemas.get(tool_id)
        if not spec or not spec.output_schema:
            return data
        
        model = self._create_model_from_schema(spec.output_schema)
        validated = model(**data)
        return validated.model_dump()
    
    def _create_model_from_schema(self, schema: Dict[str, Any]) -> Type[BaseModel]:
        """Create Pydantic model from JSON schema."""
        # Simplified - in production use pydantic.create_model_from_json_schema
        return type("DynamicModel", (BaseModel,), {})
    
    def export_typescript(self, output_path: Path) -> None:
        """Export all registered schemas as TypeScript types."""
        models = list(self._schemas.values())
        self._ts_generator.write_to_file(models, output_path)
    
    def export_tool_typescript(self, output_path: Path) -> None:
        """Export tool schemas as TypeScript types."""
        lines = [
            "// Auto-generated TypeScript types for BEAST Tools",
            "// DO NOT EDIT MANUALLY",
            f"// Generated at {datetime.now().isoformat()}",
            "",
        ]
        
        for spec in self._tool_schemas.values():
            # Generate input type
            lines.append(f"export interface {spec.tool_id.replace('.', '_')}Input {{")
            # Would generate from schema properties
            lines.append("}")
            lines.append("")
            
            # Generate output type
            if spec.output_schema:
                lines.append(f"export interface {spec.tool_id.replace('.', '_')}Output {{")
                lines.append("}")
                lines.append("")
        
        output_path.write_text("\n".join(lines))


# =============================================================================
# Global Registry Instance
# =============================================================================

_schema_registry = SchemaRegistry()


def get_schema_registry() -> SchemaRegistry:
    return _schema_registry


# =============================================================================
# Example Usage
# =============================================================================

if __name__ == "__main__":
    # Example: Build schema with fluent API
    UserSchema = schema() \
        .field("name", str, description="User's full name") \
        .field("email", str, description="User's email") \
        .field("age", int, ge=0, le=150, description="User's age") \
        .required("name", "email") \
        .optional("age") \
        .description("User information") \
        .build()
    
    print("Generated UserSchema:")
    print(UserSchema.model_json_schema())
    
    # Generate TypeScript
    ts_gen = TypeScriptGenerator()
    print("\nGenerated TypeScript:")
    print(ts_gen.generate_type(UserSchema))