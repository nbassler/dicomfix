from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("dicomfix")
except PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback version if package metadata is unavailable
