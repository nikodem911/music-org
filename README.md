Music collection manifest

The script scans audio files recursively and writes a review manifest to `<root>/plan.csv`. It can preview an apply step or perform the reviewed file operations directly with `--inplace`.

Usage:

- Install requirements: pip install -r requirements.txt
- Generate the manifest: python3 music-org.py plan --root "/home/nico/tmp/music/sd"
- Replace an existing manifest: add `--overwrite-manifest` after reviewing the existing CSV
- Preview changes from the manifest without touching files: python3 music-org.py apply --root "/home/nico/tmp/music/sd"
- Apply the manifest in place (rename/delete files directly): python3 music-org.py apply --root "/home/nico/tmp/music/sd" --inplace

The manifest includes source and proposed filename, artist/title/album/genre/year, a heuristic quality label, embedded-cover yes/no, and duplicate recommendations. `copy_action` is `keep` or `skip_duplicate`.

`category` is filled when the source path is already under `hard`, `rock`, `pop`, `polskie`, or `80s`. Otherwise it is left blank for review. The quality label is an estimate based on codec/bitrate and cannot verify the recording's original quality. Duplicate groups are candidates for review, not guaranteed identical recordings.

The `apply` command reads the CSV and either previews the actions or, with `--inplace`, renames the files in the source directory and deletes duplicate entries marked as `skip_duplicate`.