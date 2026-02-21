"""Data models for extracted documentation."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ArgInfo:
    """Represents a function/method argument."""

    name: str
    type_hint: str = ""
    default: str = ""

    def signature_str(self) -> str:
        """Return the argument as it would appear in a signature."""
        parts = [self.name]
        if self.type_hint:
            parts.append(f": {self.type_hint}")
        if self.default:
            parts.append(f" = {self.default}")
        return "".join(parts)


@dataclass
class FunctionDoc:
    """Documentation extracted from a function or method."""

    name: str
    args: list[ArgInfo] = field(default_factory=list)
    return_type: str = ""
    docstring: str = ""
    decorators: list[str] = field(default_factory=list)
    is_method: bool = False
    is_async: bool = False
    is_deprecated: bool = False
    line_number: int = 0

    @property
    def signature(self) -> str:
        """Build a readable function signature string."""
        prefix = "async def" if self.is_async else "def"
        args_str = ", ".join(arg.signature_str() for arg in self.args)
        ret = f" -> {self.return_type}" if self.return_type else ""
        return f"{prefix} {self.name}({args_str}){ret}"


@dataclass
class ClassDoc:
    """Documentation extracted from a class."""

    name: str
    bases: list[str] = field(default_factory=list)
    docstring: str = ""
    methods: list[FunctionDoc] = field(default_factory=list)
    decorators: list[str] = field(default_factory=list)
    is_deprecated: bool = False
    line_number: int = 0

    @property
    def signature(self) -> str:
        """Build a readable class signature string."""
        bases_str = f"({', '.join(self.bases)})" if self.bases else ""
        return f"class {self.name}{bases_str}"


@dataclass
class ModuleDoc:
    """Documentation extracted from a single Python module (file)."""

    filepath: str
    module_name: str
    docstring: str = ""
    functions: list[FunctionDoc] = field(default_factory=list)
    classes: list[ClassDoc] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Check if the module has any documented items."""
        return not self.functions and not self.classes and not self.docstring


@dataclass
class ProjectDoc:
    """Aggregated documentation for an entire project."""

    title: str = "Project Documentation"
    modules: list[ModuleDoc] = field(default_factory=list)

    @property
    def module_count(self) -> int:
        return len(self.modules)

    @property
    def function_count(self) -> int:
        return sum(len(m.functions) for m in self.modules)

    @property
    def class_count(self) -> int:
        return sum(len(m.classes) for m in self.modules)
