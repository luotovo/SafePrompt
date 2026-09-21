import sys


if __name__ == "__main__":
    if "--ui-probe" in sys.argv:
        from release.ui_probe import run
    elif "--rc-probe" in sys.argv:
        from release.rc_probe import run
    else:
        from safeprompt.app import run
    raise SystemExit(run())
