## Summary

## Evidence contract

- What report schema or metadata is read?
- What remains unknown?
- How is this prevented from being mistaken for whole-game completion?

## Safety checklist

- [ ] Target repositories remain read-only and no target code is executed.
- [ ] Fixtures are synthetic and contain no game files, keys, saves, private paths, or copyrighted artwork.
- [ ] Missing and malformed evidence remains unknown.
- [ ] Python and JavaScript checks pass.
- [ ] The release package passes `verify_package.py`.
