# Auto-load .env on import (see local/__init__.py for rationale).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # pragma: no cover - dotenv is a hard dependency
    pass
