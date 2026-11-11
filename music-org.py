#!/usr/bin/env python3
"""Build a reviewable manifest for organizing music files.

Rules applied (in order):
- Prefer ID3 tags (artist, title)
- Fallback to filename pattern 'Artist - Title'
- Fallback to parent folder for artist and filename for title
- Remove trailing numeric counters like ' (1)' or repeated ' (1) (1)'
- Strip common trailing suffixes like '(Official Music Video)', '[Official Video]', 'Official Audio'
- Normalize artist casing using heuristics and a small exceptions map
- Sanitize filesystem-unfriendly characters (no '/', no control chars)
- Avoid overwrites by appending ' (n)'

The `plan` command writes a CSV manifest at <root>/plan.csv and does not change
audio files. File operations are intentionally left for a later reviewed-copy step.
"""
from pathlib import Path
import argparse
import re
import csv
from typing import Tuple, Optional

try:
    from mutagen import File as MutagenFile
except Exception:
    MutagenFile = None


EXTENSIONS = ['.mp3', '.flac', '.m4a', '.wav', '.ogg', '.wma', '.aac']
PLAN_FILENAME = 'plan.csv'
CATEGORIES = ('hard', 'rock', 'pop', 'polskie', '80s')
QUALITY_RANK = {'unknown': 0, 'poor': 1, 'good': 2, 'very good': 3, 'excellent': 4}

COUNTER_RE = re.compile(r"(\s*\(\d+\))+$")

# Small exceptions map for artist stylings (filename-safe values)
EXCEPTIONS = {
}


def read_tags(path: Path) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Return (artist, title, date) using mutagen easy tags when available."""
    if MutagenFile is None:
        return None, None, None
    try:
        f = MutagenFile(str(path), easy=True)
        if not f:
            return None, None, None
        artist = None
        title = None
        date = None
        if 'artist' in f and f['artist']:
            artist = f['artist'][0]
        if 'title' in f and f['title']:
            title = f['title'][0]
        # common date keys
        if 'date' in f and f['date']:
            date = f['date'][0]
        elif 'originaldate' in f and f['originaldate']:
            date = f['originaldate'][0]
        elif 'year' in f and f['year']:
            date = f['year'][0]
        elif 'releasedate' in f and f['releasedate']:
            date = f['releasedate'][0]
        # normalize to 4-digit year when possible
        date = normalize_year(date)
        return artist, title, date
    except Exception:
        return None, None, None


def remove_counters(s: str) -> str:
    return COUNTER_RE.sub('', s).strip()


# patterns to strip from the end of titles (case-insensitive)
SUFFIX_PATTERNS = [
    'official music video',
    'official video',
    'official audio',
    'official',
    'music video',
    'video',
    'audio',
]


def strip_common_suffixes(s: str) -> str:
    """Remove common trailing suffixes like '(Official Music Video)', '[Official Video]', ' - Official Audio', etc.

    This strips repeated/various bracket and separator forms at the end of the string.
    """
    orig = s
    changed = True
    while changed:
        changed = False
        for pat in SUFFIX_PATTERNS:
            # match optional separators, optional opening bracket, the pattern, optional closing bracket, optional punctuation/whitespace at end
            regex = re.compile(rf"(?i)\s*[-–—_:]*\s*(?:\(|\[)?\s*{re.escape(pat)}\s*(?:\)|\])?\s*\.?$")
            new = regex.sub('', s).strip()
            if new != s:
                s = new
                changed = True
    # trim leftover trailing separators
    s = re.sub(r"[\-–—_:\s]+$", '', s).strip()
    return s if s else orig


def title_case_artist(s: str) -> str:
    # Better title-casing that handles apostrophes and keeps short all-caps (e.g. "AC/DC")
    def cap_word(w: str) -> str:
        if w.isupper() and len(w) <= 3:
            return w
        # handle contractions like "it's" -> "It's"
        if "'" in w:
            parts = w.split("'")
            if len(parts) == 2:
                return parts[0].capitalize() + "'" + parts[1].lower()
        return w.capitalize()

    parts = re.split(r"(\s+|,|-|:)", s)
    out = []
    for part in parts:
        if re.match(r"\s+|,|-|:", part):
            out.append(part)
        else:
            out.append(cap_word(part))
    return ''.join(out)


def normalize_artist(artist: str) -> str:
    a = artist.strip()
    low = a.lower()
    if low in EXCEPTIONS:
        return EXCEPTIONS[low]
    if a.isupper() and len(a) <= 3:
        return a
    return title_case_artist(a)


def title_case_title(s: str) -> str:
    # Similar to artist casing but preserve known stylings inside titles
    def cap_token(t: str) -> str:
        # keep existing capitalization for mixed-case tokens (e.g., McDonald's)
        if any(ch.isupper() for ch in t[1:]):
            return t
        if "'" in t:
            parts = t.split("'")
            if len(parts) == 2:
                return parts[0].capitalize() + "'" + parts[1].lower()
        return t.capitalize()

    parts = re.split(r"(\s+|\-|\.|,|:|/)", s)
    out = []
    for part in parts:
        if re.match(r"\s+|\-|\.|,|:|/", part):
            out.append(part)
        else:
            out.append(cap_token(part))
    return ''.join(out)


def sanitize_for_filename(s: str) -> str:
    # Replace problematic filesystem characters
    s = s.replace('/', ' ')
    s = s.replace('\\', ' ')
    s = re.sub(r'[\x00-\x1f]', '', s)
    s = s.replace(':', ' -')
    s = s.strip()
    s = re.sub(r'\s+', ' ', s)
    return s


def normalize_year(date_str: Optional[str]) -> Optional[str]:
    """Return a 4-digit year string (1900-2099) extracted from date_str, or None if not found."""
    if not date_str:
        return None
    s = str(date_str)
    m = re.search(r"(19|20)\d{2}", s)
    if m:
        return m.group(0)
    return None


def read_extra_tags(path: Path):
    """Read compact manifest metadata not needed by the filename parser."""
    result = {'artist': '', 'song': '', 'album': '', 'genre': '', 'year': ''}
    if MutagenFile is None:
        return result
    try:
        audio = MutagenFile(str(path), easy=True)
        if not audio:
            return result
        for field, tag_name in (
            ('artist', 'artist'),
            ('song', 'title'),
            ('album', 'album'),
            ('genre', 'genre'),
        ):
            values = audio.get(tag_name)
            if values:
                result[field] = str(values[0]).strip()
        for field in ('date', 'originaldate', 'year', 'releasedate'):
            values = audio.get(field)
            if values:
                result['year'] = normalize_year(values[0]) or ''
                if result['year']:
                    break
    except Exception:
        pass
    return result


def has_cover_art(path: Path) -> bool:
    if MutagenFile is None:
        return False
    try:
        audio = MutagenFile(str(path))
        if audio is None:
            return False
        tags = getattr(audio, 'tags', None)
        if tags is None:
            return bool(getattr(audio, 'pictures', None))
        if hasattr(tags, 'getall') and tags.getall('APIC'):
            return True
        if tags.get('covr') or tags.get('metadata_block_picture'):
            return True
        return bool(getattr(audio, 'pictures', None))
    except Exception:
        return False


def quality_label(path: Path, bitrate: Optional[int]) -> str:
    if path.suffix.lower() in ('.flac', '.wav'):
        return 'excellent'
    if not bitrate:
        return 'unknown'
    if bitrate >= 256_000:
        return 'excellent'
    if bitrate >= 192_000:
        return 'very good'
    if bitrate >= 128_000:
        return 'good'
    return 'poor'


def existing_category(path: Path, root: Path) -> str:
    try:
        parts = path.parent.relative_to(root).parts
    except ValueError:
        parts = path.parent.parts
    for part in parts:
        category = part.strip().lower()
        if category in CATEGORIES:
            return category
    if root.name.strip().lower() in CATEGORIES:
        return root.name.strip().lower()
    return ''


def same_filename_ignoring_counters(path_a: Path, path_b: Path) -> bool:
    """Return True if the filenames (stems + suffix) are equal ignoring trailing numeric counters and case.

    Examples: 'Song (1).mp3' == 'Song.mp3'
    """
    try:
        # remove numeric counters and normalize internal whitespace, but keep original case
        a = re.sub(r"\s+", ' ', COUNTER_RE.sub('', Path(path_a).stem)).strip()
        b = re.sub(r"\s+", ' ', COUNTER_RE.sub('', Path(path_b).stem)).strip()
        # compare stems case-sensitively so casing changes count as updates
        # compare suffixes case-insensitively
        return a == b and Path(path_a).suffix.lower() == Path(path_b).suffix.lower()
    except Exception:
        return False


def choose_artist_title(path: Path) -> Tuple[str, str, str, Optional[str]]:
    """Return (artist, title, reason, release_date)"""
    # try tags
    artist_tag, title_tag, date_tag = read_tags(path)
    # If we have any tag data, prefer it for that field and try to parse the other from filename
    if artist_tag or title_tag or date_tag:
        artist = artist_tag.strip() if artist_tag else None
        title = title_tag.strip() if title_tag else None
        # read_tags already normalizes to a 4-digit year when possible; fall back to 'N/A'
        release_date = date_tag if date_tag else 'N/A'
        name = path.stem.strip()
        # try to parse missing pieces from filename if possible
        if (not artist or not title) and ' - ' in name:
            a, t = name.split(' - ', 1)
            if not artist:
                artist = a.strip()
            if not title:
                # handle nested hyphen case
                left_lower = a.strip().lower()
                parent_lower = path.parent.name.strip().lower()
                if left_lower in ('_new', '__new', 'new') or left_lower == parent_lower:
                    if '-' in t:
                        cand_a, cand_t = t.split('-', 1)
                        if not artist:
                            artist = cand_a.strip()
                        if not title:
                            title = cand_t.strip()
                else:
                    title = t.strip()
        # also handle simple hyphen without spaces
        if (not artist or not title) and '-' in name:
            left, right = name.split('-', 1)
            if not artist:
                artist = left.strip()
            if not title:
                title = right.strip()
        # fallback to parent or name
        if not artist:
            artist = path.parent.name.strip() or 'Unknown Artist'
        if not title:
            title = name or 'Unknown Title'
        reason = 'tag'
        if artist_tag and not title_tag:
            reason = 'tag_artist'
        elif title_tag and not artist_tag:
            reason = 'tag_title'
        elif artist_tag and title_tag:
            reason = 'tag'
        else:
            reason = 'tag_parsed'
        return artist, title, reason, release_date

    name = path.stem.strip()
    # if filename contains ' - ' parse it
    if ' - ' in name:
        a, t = name.split(' - ', 1)
        # If the left side is a generic folder marker (e.g. '_new') or equals the parent folder,
        # the right side may itself contain the real 'Artist-Title' without spaces (e.g. 'Wet Wet Wet-Love...').
        left_lower = a.strip().lower()
        parent_lower = path.parent.name.strip().lower()
        if left_lower in ('_new', '__new', 'new') or left_lower == parent_lower:
            if '-' in t:
                cand_a, cand_t = t.split('-', 1)
                return cand_a.strip(), cand_t.strip(), 'parsed_filename_nested', 'N/A'
        return a.strip(), t.strip(), 'parsed_filename', 'N/A'

    # handle filenames using hyphen as separator but without spaces (e.g. 'Wet Wet Wet-Love is all around')
    if '-' in name:
        left, right = name.split('-', 1)
        if left.strip() and right.strip():
            return left.strip(), right.strip(), 'parsed_filename_no_space', 'N/A'

    # fallback: parent folder as artist, filename as title
    parent = path.parent.name
    if parent:
        return parent.strip(), name, 'fallback_parent', 'N/A'

    return 'Unknown Artist', name or 'Unknown Title', 'fallback_unknown', 'N/A'


def find_unique_target(target: Path) -> Path:
    if not target.exists():
        return target
    base = target.stem
    ext = target.suffix
    parent = target.parent
    i = 1
    while True:
        candidate = parent / f"{base} ({i}){ext}"
        if not candidate.exists():
            return candidate
        i += 1


def build_plan(root: Path, exts=EXTENSIONS, show_progress: bool = True):
    files = [p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in exts]
    plan = []
    total = len(files)
    for idx, p in enumerate(files, start=1):
        # print progress to stderr so stdout remains machine-readable
        if show_progress:
            try:
                print(f"Processing {idx}/{total}: {p}", end='\r')
            except Exception:
                pass
        raw_artist, raw_title, reason, release_date = choose_artist_title(p)

        # remove counters from title and artist
        raw_artist = remove_counters(raw_artist)
        raw_title = remove_counters(raw_title)

        # strip common video/audio suffixes from titles (e.g. '(Official Music Video)')
        raw_title = strip_common_suffixes(raw_title)

        # normalize artist casing and sanitize for filenames
        norm_artist = normalize_artist(raw_artist)
        safe_artist = sanitize_for_filename(norm_artist)

        # sanitize title
        # apply title-casing to titles (prefer tag-provided casing)
        try:
            norm_title = title_case_title(raw_title)
        except Exception:
            norm_title = raw_title.strip()
        safe_title = sanitize_for_filename(norm_title)

        # final filename
        new_name = f"{safe_artist} - {safe_title}{p.suffix}"
        new_path = p.with_name(new_name)
        # ensure uniqueness
        final_path = p if new_path == p else find_unique_target(new_path)
        # collect extra metadata for duplicate detection
        # ensure release_date is a string (year) or 'N/A'
        rd = release_date if release_date else 'N/A'
        # consider only the filename when determining if the original filename was updated
        upd = 'no' if same_filename_ignoring_counters(final_path, p) else 'yes'

        meta = {
            'old': str(p),
            'new': str(final_path),
            'updated': upd,
            'reason': reason,
            'size': p.stat().st_size,
            'release_date': rd,
            'bitrate': None,
            'duration': None,
            'artist': '',
            'song': '',
            'album': '',
            'genre': '',
            'year': '',
            'quality': 'unknown',
            'has_cover': 'no',
            'tag_count': 0,
            'category': existing_category(p, root),
            'safe_artist': safe_artist.lower(),
            'safe_title': safe_title.lower(),
        }
        extra_tags = read_extra_tags(p)
        meta['artist'] = extra_tags['artist'] or raw_artist
        meta['song'] = extra_tags['song'] or raw_title
        meta['album'] = extra_tags['album']
        meta['genre'] = extra_tags['genre']
        meta['year'] = rd if rd != 'N/A' else extra_tags['year']
        meta['tag_count'] = sum(bool(extra_tags[field]) for field in ('artist', 'song', 'album', 'genre', 'year'))
        meta['has_cover'] = 'yes' if has_cover_art(p) else 'no'
        # try to read bitrate/duration from tags/info
        try:
            if MutagenFile is not None:
                m = MutagenFile(str(p))
                if m is not None and hasattr(m, 'info') and m.info is not None:
                    info = m.info
                    # some formats expose bitrate in bits/sec
                    bitrate = getattr(info, 'bitrate', None)
                    if bitrate:
                        meta['bitrate'] = int(bitrate)
                    # length in seconds
                    length = getattr(info, 'length', None)
                    if length:
                        meta['duration'] = float(length)
        except Exception:
            pass
        meta['quality'] = quality_label(p, meta['bitrate'])

        plan.append(meta)
    # clear last progress line
    if show_progress:
        try:
            if total:
                print(' ' * 80, end='\r')
        except Exception:
            pass
    return plan


def annotate_duplicates(plan):
    # group by artist/title and approximate duration (or size if duration missing)
    groups = {}
    for i, e in enumerate(plan):
        key = (e['safe_artist'], e['safe_title'])
        # use rounded duration as a tolerant key if available
        dur = e.get('duration')
        if dur:
            key = key + (round(dur),)
        groups.setdefault(key, []).append((i, e))

    # annotate each group
    for gid, items in enumerate(groups.values(), start=1):
        if len(items) <= 1:
            idx, e = items[0]
            e['dup_group'] = ''
            e['dup_action'] = ''
            e['copy_action'] = 'keep'
            e['decision_reason'] = 'No likely duplicate in this scan'
            continue
        ranked = sorted(
            items,
            key=lambda item: (
                QUALITY_RANK.get(item[1].get('quality', 'unknown'), 0),
                item[1].get('tag_count', 0),
                item[1].get('has_cover') == 'yes',
                item[1].get('bitrate') or 0,
                item[1].get('size') or 0,
                item[1].get('updated') == 'no',
                bool(item[1].get('category')),
                item[1]['old'],
            ),
            reverse=True,
        )
        preserve_idx = ranked[0][0]
        for idx, e in items:
            e['dup_group'] = f'dup-{gid}'
            if idx == preserve_idx:
                e['dup_action'] = 'preserve'
                e['copy_action'] = 'keep'
                e['decision_reason'] = 'Highest quality, tag completeness, and artwork score in group'
            else:
                e['dup_action'] = 'skip_duplicate'
                e['copy_action'] = 'skip_duplicate'
                e['decision_reason'] = 'Lower-ranked likely duplicate; review before skipping'

    return plan


def write_plan(root: Path, plan, overwrite: bool = False):
    out = root / PLAN_FILENAME
    if out.exists() and not overwrite:
        raise FileExistsError(f"Manifest already exists: {out}. Pass overwrite=True to replace it.")
    with out.open('w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow([
            'old', 'new', 'reason', 'dup_group', 'dup_action', 'updated',
            'release_date', 'category', 'artist', 'song', 'album', 'genre',
            'quality', 'has_cover', 'tag_count', 'copy_action', 'decision_reason',
        ])
        for e in plan:
            # dup_group and dup_action may be set later (or empty)
            dg = e.get('dup_group', '')
            da = e.get('dup_action', '')
            # recompute updated by comparing filenames (ignore counters) using current values
            try:
                oldp = Path(e.get('old',''))
                newp = Path(e.get('new',''))
                current_updated = 'no' if same_filename_ignoring_counters(newp, oldp) else 'yes'
            except Exception:
                current_updated = e.get('updated','no')
            e['updated'] = current_updated
            w.writerow([
                e['old'], e['new'], e.get('reason', ''), dg, da,
                e.get('updated', 'no'), e.get('release_date', ''),
                e.get('category', ''), e.get('artist', ''), e.get('song', ''),
                e.get('album', ''), e.get('genre', ''), e.get('quality', 'unknown'),
                e.get('has_cover', 'no'), e.get('tag_count', 0),
                e.get('copy_action', 'keep'), e.get('decision_reason', ''),
            ])
    return out


def read_plan_from_csv(plan_path: Path):
    """Read a previously written plan.csv and return a list of plan entries.

    Expects columns: old,new,reason,dup_group,dup_action (but will tolerate extra columns).
    """
    if not plan_path.exists():
        return None
    out = []
    with plan_path.open('r', newline='') as fh:
        r = csv.reader(fh)
        try:
            header = next(r)
        except StopIteration:
            return out
        for row in r:
            # use header mapping for robust column handling
            header_map = {h: i for i, h in enumerate(header)}
            def val(name, default=''):
                idx = header_map.get(name)
                if idx is None or idx >= len(row):
                    return default
                return row[idx]

            old = val('old', '')
            new = val('new', '')
            updated = val('updated', 'no')
            reason = val('reason', '')
            release_date = normalize_year(val('release_date', '')) or ''
            dup_group = val('dup_group', '')
            dup_action = val('dup_action', '')
            out.append({
                'old': old,
                'new': new,
                'updated': updated,
                'reason': reason,
                'release_date': release_date,
                'dup_group': dup_group,
                'dup_action': dup_action,
                'copy_action': val('copy_action', 'keep'),
                'category': val('category', ''),
                'artist': val('artist', ''),
                'song': val('song', ''),
                'album': val('album', ''),
                'genre': val('genre', ''),
                'quality': val('quality', 'unknown'),
                'has_cover': val('has_cover', 'no'),
                'tag_count': int(val('tag_count', '0') or 0),
                'decision_reason': val('decision_reason', ''),
            })
    return out


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest='command', required=True)
    plan_parser = commands.add_parser('plan', help='Prepare a reviewable CSV manifest')
    plan_parser.add_argument('--root', required=True)
    plan_parser.add_argument('--no-progress', action='store_true', help='Disable per-file progress output')
    plan_parser.add_argument('--extensions', default=','.join(EXTENSIONS))
    plan_parser.add_argument('--overwrite-manifest', action='store_true', help='Replace an existing plan.csv')
    args = parser.parse_args()

    root = Path(args.root)
    manifest_path = root / PLAN_FILENAME
    if manifest_path.exists() and not args.overwrite_manifest:
        parser.error(f"{manifest_path} already exists; review it or rerun with --overwrite-manifest")
    exts = [e if e.startswith('.') else '.'+e for e in args.extensions.split(',')]

    plan = build_plan(root, exts, show_progress=not args.no_progress)
    plan = annotate_duplicates(plan)

    print(f"Manifest entries: {len(plan)}")
    for e in plan:
        dup = ''
        if e.get('dup_group'):
            dup = f" {e.get('dup_group')}:{e.get('dup_action')}"
        category = f" category={e.get('category')}" if e.get('category') else ' category=REVIEW'
        copy_action = e.get('copy_action', 'keep')
        rd = ''
        if e.get('release_date'):
            rd = f" release_date={e.get('release_date')}"
        upd = ''
        if e.get('updated'):
            upd = f" updated={e.get('updated')}"
        print(f"{e['old']} -> {e.get('new','')} [{e.get('reason','')}]" + category + f" copy_action={copy_action}" + rd + upd + dup)

    plan_file = write_plan(root, plan, overwrite=args.overwrite_manifest)
    print(f"Manifest written to: {plan_file}")
    print('Manifest only: no audio files were changed.')


if __name__ == '__main__':
    main()
