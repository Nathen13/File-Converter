"""Abstract base class for all converters."""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Optional


class ConversionError(Exception):
    """Raised when a conversion fails. Wraps the underlying library error."""


class ConversionCancelled(ConversionError):
    """Raised when the user cancelled mid-conversion.

    Subclasses ConversionError so existing error-handling paths still
    catch it, but the GUI distinguishes by type to show "Cancelled"
    rather than an error dialog.
    """


# Progress callback: callback(current: int, total: int)
# Where current/total are page counts (or step counts).
ProgressCallback = Callable[[int, int], None]

# Cancel-check callback: returns True if the user has requested cancel.
# Converters that support cancellation poll this between work units
# (e.g. between PDF pages) and raise ConversionCancelled when it's True.
CancelCheck = Callable[[], bool]


class BaseConverter(ABC):
    """One subclass per (input_ext, output_ext) pair.

    Subclasses MUST set `input_ext` and `output_ext` (lowercase, no dot)
    and implement `convert`.
    """

    input_ext: str = ""
    output_ext: str = ""

    # True if the converter calls progress_callback as it works.
    # The GUI uses this to pick determinate vs indeterminate progress.
    supports_progress: bool = False

    # True if the converter polls cancel_check and can stop cleanly
    # mid-work. The GUI uses this to decide whether to show the
    # Cancel button -- showing it for non-cancellable conversions
    # would be misleading.
    supports_cancel: bool = False

    @abstractmethod
    def convert(
        self,
        input_path: Path,
        output_path: Path,
        progress_callback: Optional[ProgressCallback] = None,
        cancel_check: Optional[CancelCheck] = None,
    ) -> None:
        """Convert input_path to output_path.

        Raise ConversionError on failure. Raise ConversionCancelled if
        cancel_check returns True at a checkpoint. Call progress_callback
        (if provided) with (current, total) as work proceeds.
        """

    @property
    def display_name(self) -> str:
        return f"{self.input_ext.upper()} \u2192 {self.output_ext.upper()}"
