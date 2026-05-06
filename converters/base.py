"""Abstract base class for all converters."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional


class ConversionError(Exception):
    """Raised when a conversion fails. Wraps the underlying library error."""


# Progress callback signature:
#   callback(current: int, total: int)
# Where current/total are page counts (or step counts). Converters that
# can't report fine-grained progress should pass None and the GUI will
# show indeterminate progress instead.
ProgressCallback = Callable[[int, int], None]


class BaseConverter(ABC):
    """One subclass per (input_ext, output_ext) pair.

    Subclasses MUST set `input_ext` and `output_ext` (lowercase, no dot)
    and implement `convert`.

    The `progress_callback` parameter is optional. Converters that can
    report progress (e.g. per-page) should call it as work proceeds.
    Converters that work in one indivisible step can ignore it.
    """

    input_ext: str = ""
    output_ext: str = ""

    # Set this to True in subclasses that call progress_callback.
    # The GUI uses this hint to choose between determinate (real %) and
    # indeterminate (spinner) progress display upfront.
    supports_progress: bool = False

    @abstractmethod
    def convert(
        self,
        input_path: Path,
        output_path: Path,
        progress_callback: Optional[ProgressCallback] = None,
    ) -> None:
        """Convert input_path to output_path.

        Raise ConversionError on failure. Call progress_callback (if
        provided and if the converter supports it) with (current, total)
        as work proceeds.
        """

    @property
    def display_name(self) -> str:
        return f"{self.input_ext.upper()} \u2192 {self.output_ext.upper()}"
