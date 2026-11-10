"""Demo only: rewrite the fake Cursor state DB the way users reported after installing Cursor on iOS
(legacy no-storage -> no-training)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "examples"))
try:
    import make_demo_home
except ImportError:  # copied into the demo sandbox
    sys.path.insert(0, "/workspace/apps/optout/examples")
    import make_demo_home

make_demo_home.cursor_db(os.environ["OPTOUT_HOME"], "PRIVACY_MODE_NO_TRAINING")
print("cursor privacy mode is now PRIVACY_MODE_NO_TRAINING (as reported after the iOS install)")
