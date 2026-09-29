import sys


if __name__ == "__main__":
    if "--hybrid-probe" in sys.argv:
        from release.hybrid_probe import run
    elif "--competition-probe" in sys.argv:
        from release.competition_portable_probe import run
    elif "--ui-probe" in sys.argv:
        from release.ui_probe import run
    elif "--competition-v2-probe" in sys.argv:
        from release.competition_v2_probe import run
    elif "--rc-probe" in sys.argv:
        from release.rc_probe import run
    elif "--lite-probe" in sys.argv:
        from release.lite_probe import run
    else:
        from safeprompt.app import run
    raise SystemExit(run())
