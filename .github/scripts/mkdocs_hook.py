"""MkDocs hook: expand runbook blocks before reading docs."""
import subprocess, sys
from pathlib import Path

def on_pre_build(config, **kw):
    script = Path(__file__).parent / 'expand_handbook_blocks.py'
    subprocess.run([sys.executable, str(script)], check=True)
