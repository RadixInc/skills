# Contributing

Skills are added and changed through pull requests. The `main` branch requires an approving review.

1. Read [docs/VISION.md](docs/VISION.md), especially the Security Model. This repository is public.
2. Follow [docs/authoring.md](docs/authoring.md) to add or change a skill.
3. Run `python3 scripts/validate_skills.py` and `python3 scripts/build_skill_zips.py --out dist` before opening the PR. The second command checks that every skill packages.
4. Fill in the pull request template. Leave versions alone; see [docs/releasing.md](docs/releasing.md).

Contributions are accepted under the Apache License 2.0, the same license as the rest of the repository.
