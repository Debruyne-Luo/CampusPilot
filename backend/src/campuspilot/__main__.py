import argparse
import io
import sys
from pathlib import Path

from pydantic import ValidationError

from campuspilot.contracts import Contract, ExecutionContext, ToolCall, ToolResult, TraceEvent
from campuspilot.demo import run_demo
from campuspilot.directory.repository import DirectoryRepository
from campuspilot.directory.tools import directory_tools
from campuspilot.state import InMemoryExecutionJournal
from campuspilot.tools import ReadOnlyPermissionPolicy, ToolExecutor


class DirectoryOutput(Contract):
    notice: str = (
        "CDUT public source inventory; all records need human review. No action performed."
    )
    result: ToolResult
    trace: tuple[TraceEvent, ...]


def query_directory(
    directory: Path, tool_id: str, query: str, academic_year: str | None = None
) -> DirectoryOutput:
    repository = DirectoryRepository.load(directory)
    journal = InMemoryExecutionJournal()
    executor = ToolExecutor(directory_tools(repository), ReadOnlyPermissionPolicy(), journal)
    context = ExecutionContext(
        session_id="directory-session",
        task_id="directory-query",
        run_id="directory-run",
        allowed_tools=executor.tool_ids,
    )
    call = ToolCall(
        call_id="directory-call",
        tool_id=tool_id,
        arguments={"query": query, "academic_year": academic_year}
        if tool_id == "search_service"
        else {"office_id": query},
    )
    result = executor.execute(call, context)
    return DirectoryOutput(result=result, trace=journal.events(context.session_id))


def main() -> None:
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="CampusPilot offline demo and public directory")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo", help="Run the isolated synthetic demo")
    for name in ("search-service", "find-office"):
        command = commands.add_parser(name)
        command.add_argument("query", help="Service name/alias or exact office ID")
        command.add_argument("--data-dir", type=Path, default=Path("data/cdut"))
        if name == "search-service":
            command.add_argument("--academic-year", default=None)
    args = parser.parse_args()
    if args.command == "demo":
        print(run_demo().model_dump_json(indent=2))
        return
    try:
        output = query_directory(
            args.data_dir,
            args.command.replace("-", "_"),
            args.query,
            getattr(args, "academic_year", None),
        )
    except OSError, ValidationError, ValueError:
        parser.exit(2, "Directory data unavailable or invalid; no synthetic fallback.\n")
    print(output.model_dump_json(indent=2))
    if output.result.status not in {"success", "empty"}:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
