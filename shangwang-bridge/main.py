"""Entry point for 商网 bridge (CDP mode). Run: python main.py"""

import asyncio
import sys

from server import serve


def main() -> None:
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        print("\nBridge stopped.")


if __name__ == "__main__":
    main()
