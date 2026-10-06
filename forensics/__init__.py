"""Sada — Role 5: forgery and manipulation.

- fingerprint.py / library.py   fingerprints of the ORIGINAL recordings (raw/, data/originals/) and fast search
- compare.py   compare_with_original: where the clip sits in its original, internal cuts, joins, missing context
- artifact.py  artifact_score: does it sound generated (TTS)?
- splice.py    detect_splice_points: blind join search when the original is not in the library
- verdict.py   Analyzer.analyze(): the four questions (role 4 identity + role 5)

Built on role 1's data (data/manifest.csv, data/manipulation_log.csv, raw/) like role 4.
"""
