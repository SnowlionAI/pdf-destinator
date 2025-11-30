"""PDF Destinator - Add named destinations and links to PDFs without expensive tools."""

__version__ = "0.1.1"
__author__ = "Claude & friends"

from .picker import PDFDestinationPicker, main

__all__ = ["PDFDestinationPicker", "main"]
