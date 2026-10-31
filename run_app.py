import sys

from rocket_league_clips.app import main

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--self-test":
        from rocket_league_clips.self_test import run
        raise SystemExit(run(sys.argv[2]))
    raise SystemExit(main())
