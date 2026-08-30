"""Project entry point.

Run the bot with:  python run.py
"""

from __future__ import annotations

from app.main import main

if __name__ == "__main__":
    import asyncio

    try:
        asyncio.run(main())
    except KeyboardInterrupt:  # pragma: no cover
        pass
