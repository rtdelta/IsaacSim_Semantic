#!/usr/bin/env python3
"""Cloud operations entry point. No credentials are accepted on the command line."""
from cloud_ops.cli import main

if __name__ == "__main__":
    raise SystemExit(main())

