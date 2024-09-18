try:
    from importlib.metadata import version as get_version
except ImportError:
    # For older Python versions (pre 3.8)
    from importlib_metadata import version as get_version

__version__ = get_version("dicomfix")
