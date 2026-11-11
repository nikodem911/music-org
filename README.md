Music collection manifest

The script scans audio files recursively and writes a review manifest to `<root>/plan.csv`. It does not move, rename, copy, or delete audio files.

Usage:

- Install requirements: pip install -r requirements.txt
- Generate the manifest: python3 music-org.py plan --root "/home/nico/tmp/music/sd"
- Replace an existing manifest: add `--overwrite-manifest` after reviewing the existing CSV

The manifest includes source and proposed filename, artist/title/album/genre/year, a heuristic quality label, embedded-cover yes/no, and duplicate recommendations. `copy_action` is `keep` or `skip_duplicate`; every row starts with `review_status=pending`.

`category` is filled when the source path is already under `hard`, `rock`, `pop`, `polskie`, or `80s`. Otherwise it is left blank for review. The quality label is an estimate based on codec/bitrate and cannot verify the recording's original quality. Duplicate groups are candidates for review, not guaranteed identical recordings.

Only the `plan` command is available at this stage. An `apply` command for copying reviewed selections will be added later.