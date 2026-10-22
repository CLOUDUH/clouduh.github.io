#!/usr/bin/env python3
import collections
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

SOURCE = Path('/Volumes/photo/170408_妈妈手机照片')
IMAGE_EXTS = {'.jpg', '.jpeg', '.heic', '.png', '.gif'}
VIDEO_EXTS = {'.mp4', '.mov'}
FIELDS = [
    'DateTimeOriginal', 'CreateDate', 'MediaCreateDate', 'TrackCreateDate',
    'FileModifyDate', 'FileName', 'Directory', 'FileTypeExtension',
    'Make', 'Model', 'Software',
]


def parse_date(value):
    if not value or str(value).startswith('0000:00:00'):
        return None
    match = re.match(r'^(\d{4})[:\-](\d{2})[:\-](\d{2})[ T](\d{2}):(\d{2}):(\d{2})', str(value))
    if not match:
        return None
    try:
        return dt.datetime(*map(int, match.groups()))
    except ValueError:
        return None


def filename_date(name):
    patterns = [
        r'(?<!\d)(20\d{2})[-_]?([01]\d)[-_]?([0-3]\d)[_\- ]?([0-2]\d)[.\-:]?([0-5]\d)[.\-:]?([0-5]\d)',
        r'(?<!\d)(\d{2})([01]\d)([0-3]\d)[_\- ]([0-2]\d)([0-5]\d)([0-5]\d)',
    ]
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, name)
        if not match:
            continue
        parts = list(map(int, match.groups()))
        if index == 1:
            parts[0] += 2000
        try:
            return dt.datetime(*parts)
        except ValueError:
            pass
    return None


command = ['exiftool', '-json', '-r']
for ext in sorted(IMAGE_EXTS | VIDEO_EXTS):
    command += ['-ext', ext.lstrip('.')]
for field in FIELDS:
    command.append('-' + field)
command.append(str(SOURCE))
rows = json.loads(subprocess.check_output(command, text=True))

summary = collections.Counter()
months = collections.Counter()
years = collections.Counter()
uncertain = []
disagreements = []
chosen_rows = []
for row in rows:
    path = Path(row['SourceFile'])
    suffix = path.suffix.lower()
    is_video = suffix in VIDEO_EXTS
    dto = parse_date(row.get('DateTimeOriginal'))
    create = parse_date(row.get('CreateDate'))
    media = parse_date(row.get('MediaCreateDate'))
    track = parse_date(row.get('TrackCreateDate'))
    fmod = parse_date(row.get('FileModifyDate'))
    fname = filename_date(path.name)
    if is_video:
        candidates = [('MediaCreateDate', media), ('TrackCreateDate', track), ('CreateDate', create), ('filename', fname), ('FileModifyDate', fmod)]
    else:
        candidates = [('DateTimeOriginal', dto), ('CreateDate', create), ('filename', fname), ('FileModifyDate', fmod)]
    source, chosen = next(((name, value) for name, value in candidates if value), ('none', None))
    kind = 'video' if is_video else 'image'
    summary[(kind, source)] += 1
    if chosen:
        months[chosen.strftime('%Y-%m')] += 1
        years[str(chosen.year)] += 1
    if source == 'FileModifyDate' or chosen is None:
        uncertain.append({'file': str(path.relative_to(SOURCE)), 'kind': kind, 'source': source, 'date': chosen.isoformat(' ') if chosen else None})
    authoritative = [x for x in [dto, create, media, track, fname] if x]
    if len(authoritative) >= 2:
        spread = (max(authoritative) - min(authoritative)).total_seconds()
        if spread > 3 * 86400:
            disagreements.append({'file': str(path.relative_to(SOURCE)), 'spreadDays': round(spread / 86400, 1), 'values': [x.isoformat(' ') for x in authoritative]})
    chosen_rows.append({'file': str(path.relative_to(SOURCE)), 'kind': kind, 'source': source, 'date': chosen.isoformat(' ') if chosen else None})

output = {
    'total': len(rows),
    'sourceCounts': {f'{kind}:{source}': count for (kind, source), count in sorted(summary.items())},
    'years': dict(sorted(years.items())),
    'months': dict(sorted(months.items())),
    'uncertainCount': len(uncertain),
    'uncertain': uncertain,
    'disagreementCount': len(disagreements),
    'disagreements': disagreements[:50],
    'chosen2026': [row for row in chosen_rows if row['date'] and row['date'].startswith('2026-')],
}
print(json.dumps(output, ensure_ascii=False, indent=2))
