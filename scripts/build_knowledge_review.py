"""Create a joint structured/RAG review artifact, reusing unchanged vectors for free."""

import argparse
import json
from pathlib import Path

from campuspilot.knowledge_review import prepare_candidate, review_archive


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--vector-donor", type=Path,
                        help="Verified indexed version when the compiled base has no index")
    args = parser.parse_args()
    try:
        result = prepare_candidate(args.base, args.directory, args.output,
                                   vector_donor=args.vector_donor)
        if args.archive:
            result["archive"] = review_archive(args.output, args.archive)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(2, "Review build failed; active versions unchanged.\n")


if __name__ == "__main__":
    main()
