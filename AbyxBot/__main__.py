import asyncio
import os
import sys
from pathlib import Path
os.chdir(Path(__file__).resolve().parent.parent)
sys.path.append(os.getcwd())
from AbyxBot import done, run

async def main():
    try:
        await run()
    except KeyboardInterrupt:
        pass
    finally:
        await done()

try:
    asyncio.run(main())
except KeyboardInterrupt:
    pass
