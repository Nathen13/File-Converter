"""Abstract base class for all converters."""
from abc import ABC, abstractmethod
from pathlib import Path


class ConversionError(Exception):
    """Raised when a conversion fails. Wraps the underlying library error."""


class BaseConverter(ABC):
    """One subclass per (input_ext, output_ext) pair.

    Subclasses MUST set `input_ext` and `output_ext` (lowercase, no dot)
    and implement `convert`.
    """

    input_ext: str = ""
    output_ext: str = ""

    @abstractmethod
    def convert(self, input_path: Path, output_path: Path) -> None:
        """Convert input_path to output_path. Raise ConversionError on failure."""

    @property
    def display_name(self) -> str:
        return f"{self.input_ext.upper()} \u2192 {self.output_ext.upper()}"
