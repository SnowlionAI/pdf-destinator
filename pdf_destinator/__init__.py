"""PDF Destinator - Add named destinations and links to PDFs without expensive tools."""

__version__ = "0.1.0"
__author__ = "Claude and friends"

from .picker import PDFDestinationPicker, main

__all__ = ["PDFDestinationPicker", "main"]
