"""Start the Photoshop Menu local application."""
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--apply-update":
        sys.argv.pop(1)
        from backend.update_helper import cli
    elif len(sys.argv) > 1 and sys.argv[1] == "--ps-launch-worker":
        sys.argv.pop(1)
        from backend.photoshop_launch import cli
    elif len(sys.argv) > 1 and sys.argv[1] == "--overlay":
        sys.argv.pop(1)
        from backend.overlay import cli
    else:
        from backend.main import cli
    cli()
