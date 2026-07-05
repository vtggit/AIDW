#!/usr/bin/env python3
"""Export the current FastAPI OpenAPI schema to a committed contract artifact.

Usage:
    python scripts/export_openapi.py [--output backend/openapi.json]

This script should be run whenever API routes or request/response models change.
The exported file is tracked in version control and validated by CI to prevent
silent API drift.
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure the backend package is importable regardless of working directory
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.main import app  # noqa: E402


def export_openapi(output_path: str) -> None:
    """Generate and write the OpenAPI schema to the specified path."""
    schema = app.openapi()
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(schema, indent=2) + "\n")
    print(f"OpenAPI schema exported to {output}")


def main():
    parser = argparse.ArgumentParser(description="Export OpenAPI schema to JSON")
    parser.add_argument(
        "--output",
        default=str(backend_dir / "openapi.json"),
        help="Output path for the OpenAPI JSON file (default: backend/openapi.json)",
    )
    args = parser.parse_args()
    export_openapi(args.output)


if __name__ == "__main__":
    main()
