"""Sample Python module for testing autoredocs parser.

This module contains a variety of code structures to ensure
the parser correctly extracts functions, classes, decorators,
type hints, and docstrings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


def greet(name: str, excited: bool = False) -> str:
    """Return a greeting message.

    Args:
        name: The person's name.
        excited: If True, add an exclamation mark.

    Returns:
        A greeting string.
    """
    suffix = "!" if excited else "."
    return f"Hello, {name}{suffix}"


def add(a: int, b: int) -> int:
    """Add two numbers together."""
    return a + b


def no_docs(x):
    return x * 2


async def fetch_data(url: str, timeout: int = 30) -> dict:
    """Fetch data from a remote URL asynchronously.

    Args:
        url: The URL to fetch.
        timeout: Request timeout in seconds.

    Returns:
        Parsed response data.
    """
    return {"url": url, "timeout": timeout}


@dataclass
class User:
    """Represents a user in the system.

    Attributes:
        name: The user's display name.
        email: The user's email address.
        age: Optional age of the user.
    """

    name: str
    email: str
    age: Optional[int] = None

    def full_info(self) -> str:
        """Return a formatted string with all user info."""
        parts = [f"{self.name} <{self.email}>"]
        if self.age is not None:
            parts.append(f"(age {self.age})")
        return " ".join(parts)

    def is_adult(self) -> bool:
        """Check if the user is 18 or older."""
        return self.age is not None and self.age >= 18


class Calculator:
    """A simple calculator class.

    Supports basic arithmetic operations.
    """

    def __init__(self, precision: int = 2):
        """Initialize with a given decimal precision."""
        self.precision = precision

    def add(self, a: float, b: float) -> float:
        """Add two numbers."""
        return round(a + b, self.precision)

    def divide(self, a: float, b: float) -> float:
        """Divide a by b.

        Raises:
            ZeroDivisionError: If b is zero.
        """
        if b == 0:
            raise ZeroDivisionError("Cannot divide by zero")
        return round(a / b, self.precision)

    @staticmethod
    def is_positive(n: float) -> bool:
        """Check if a number is positive."""
        return n > 0

    @classmethod
    def from_config(cls, config: dict) -> "Calculator":
        """Create a Calculator from a config dict."""
        return cls(precision=config.get("precision", 2))


class _PrivateHelper:
    """This is a private helper class — may be excluded."""

    def _internal(self) -> None:
        """Internal method."""
        pass


def old_function() -> None:
    """Deprecated: Use new_function() instead.

    This function is deprecated and will be removed in v2.0.
    """
    pass


class LegacyProcessor:
    """A legacy processor class.

    .. deprecated:: 1.5
        Use NewProcessor instead.
    """

    def process(self) -> None:
        """Process data using legacy algorithm."""
        pass
