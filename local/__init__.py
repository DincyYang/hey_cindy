# Auto-load .env into the environment on import, so entry points don't need a
# manual `source .env`. Existing env vars win (load_dotenv override=False), so an
# explicit `export FOO=...` still overrides the .env value.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
