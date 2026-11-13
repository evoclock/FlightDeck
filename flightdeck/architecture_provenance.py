"""Check provenance on rendered Architecture HTML without blocking legacy publishes."""
import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

SHA = re.compile(r"[0-9a-f]{40}\Z")
VERSION = re.compile(r"bowerbird\s+(\S+)\Z")


@dataclass(frozen=True)
class Result:
    missing: tuple[str, ...]
    legacy: bool = False

    @property
    def ok(self):
        return not self.missing


class _Markers(HTMLParser):
    def __init__(self):
        super().__init__()
        self.generators = []
        self.shas = []
        self.versions = []
        self.new_contract = False

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag in ('html', 'body'):
            self.new_contract |= 'data-bowerbird-version' in values or 'data-bowerbird-input-sha' in values
            self.versions.append(values.get('data-bowerbird-version', ''))
            self.shas.append(values.get('data-bowerbird-input-sha', ''))
        if tag == 'meta':
            if values.get('name', '').lower() == 'generator':
                self.generators.append(values.get('content', ''))
            if values.get('name', '').lower() == 'bowerbird-input-sha':
                self.new_contract = True
                self.shas.append(values.get('content', ''))


def check_html(html):
    markers = _Markers()
    markers.feed(html)
    official = any(value == 'bowerbird' or VERSION.fullmatch(value) for value in markers.generators)
    version = any(VERSION.fullmatch(value) for value in markers.generators) or any(
        value and not any(c.isspace() for c in value) for value in markers.versions)
    sha = any(SHA.fullmatch(value) for value in markers.shas)
    if not official and not (any(markers.versions) or any(markers.shas)):
        return Result(('not a bowerbird page',))
    missing = tuple(label for label, present in (('version', version), ('input SHA', sha)) if not present)
    legacy = official and 'bowerbird' in markers.generators and not markers.new_contract and not version
    return Result(missing, legacy)


def check_file(path):
    return check_html(Path(path).read_text(encoding='utf-8'))


def check_directory(path):
    return {file: result for file in sorted(Path(path).rglob('*.html'))
            if not (result := check_file(file)).ok}


def publishable(path):
    result = check_file(path)
    if result.missing:
        action = 'publishing legacy output; provenance markers are not yet present' if result.legacy else 'excluding diagram'
        print(f'WARNING: {path}: {action} ({", ".join(result.missing)})', file=sys.stderr)
    return result.ok or result.legacy


def copy_assets(source, destination):
    source, destination = Path(source), Path(destination)
    if destination.exists():
        shutil.rmtree(destination)

    def exclude(directory, names):
        if Path(directory).parent.name != 'rendered':
            return []
        return [name for name in names if name.endswith('.html') and
                not publishable(Path(directory) / name)]

    shutil.copytree(source, destination, ignore=exclude)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', type=Path, help='rendered HTML file or directory')
    args = parser.parse_args()
    findings = check_directory(args.path) if args.path.is_dir() else {args.path: check_file(args.path)}
    for file, result in findings.items():
        if result.missing:
            print(f'{file}: {", ".join(result.missing)}')
    return int(any(result.missing for result in findings.values()))


if __name__ == '__main__':
    raise SystemExit(main())
