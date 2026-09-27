import argparse

from campuspilot.demo import run_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="CampusPilot synthetic offline skeleton")
    parser.add_argument("command", choices=["demo"])
    parser.parse_args()
    print(run_demo().model_dump_json(indent=2))


if __name__ == "__main__":
    main()
