# Harness² attribution and local boundary

CampusPilot optionally uses Google Research Harness², fixed at
[`1cfe254e8d25b15f37048c3730134686abe60335`](https://github.com/google-research/harness2/tree/1cfe254e8d25b15f37048c3730134686abe60335).
The upstream Apache-2.0 license is preserved in [UPSTREAM_LICENSE](UPSTREAM_LICENSE).
The upstream repository is downloaded into an ignored cache; it is not vendored here.

`patch_surface.py` registers a CampusPilot text surface with the upstream prompt registry.
It does not replace the original recursion, selection or experience library. The adapter,
two-runtime bridge, restricted profiles, metered gateway, public lab and independent
evaluation workflow are CampusPilot integration work, not new Harness² algorithms.

The upstream OpenCode dependency is pinned to
`23fb5e0516c99ac04a1aa46c193efda2e1b9bb24`, with the compatibility patch distributed by
the pinned Harness² checkout. Its own upstream license remains in that dependency checkout.
No external model credentials are included in this directory or in public experiment records.
