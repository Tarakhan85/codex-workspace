from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import pandas as pd


DEFAULT_PROJECTS: List[str] = [
    "NEAG_1_EPF",
    "DAHSHOUR_16IN_PIPELINE",
    "ALEX_FIRE_FIGHTING",
    "GAMSA_CHEMICAL",
]

DISCIPLINE_ORDER: List[str] = ["Mechanical", "Civil", "Electrical", "I&C", "HSE", "Other"]


@dataclass(frozen=True)
class AllocationConfig:
    input_file: Path
    output_file: Path
    source_sheet: str = "MASTER_ALL"
    unique_key_column: str = "Name"
    job_title_column: str = "Job Title"
    projects: Sequence[str] = tuple(DEFAULT_PROJECTS)


class AllocationError(Exception):
    """Raised when the allocation workflow cannot continue."""


def classify_discipline(job_title: str) -> str:
    """Return a discipline bucket from a job title string."""
    normalized = str(job_title).strip().lower()

    if "mechanical" in normalized or "piping" in normalized:
        return "Mechanical"
    if "civil" in normalized:
        return "Civil"
    if "electrical" in normalized:
        return "Electrical"
    if "instrument" in normalized or "control" in normalized:
        return "I&C"
    if "hse" in normalized or "safety" in normalized:
        return "HSE"
    if "manager" in normalized or "director" in normalized:
        return "Management"
    return "Other"


def validate_inputs(df: pd.DataFrame, config: AllocationConfig) -> None:
    required_columns = {config.unique_key_column, config.job_title_column}
    missing_columns = sorted(required_columns.difference(df.columns))

    if missing_columns:
        missing = ", ".join(missing_columns)
        raise AllocationError(
            f"Required column(s) missing from '{config.source_sheet}' sheet: {missing}"
        )

    if not config.projects:
        raise AllocationError("At least one project must be provided.")


def load_and_prepare_data(config: AllocationConfig) -> pd.DataFrame:
    """Load source sheet, validate schema, and compute discipline."""
    if not config.input_file.exists():
        raise AllocationError(f"Input file does not exist: {config.input_file}")

    df = pd.read_excel(config.input_file, sheet_name=config.source_sheet)
    validate_inputs(df, config)

    deduplicated = df.drop_duplicates(subset=[config.unique_key_column]).copy()
    deduplicated["Discipline"] = deduplicated[config.job_title_column].apply(classify_discipline)
    return deduplicated


def allocate_engineers(engineers: pd.DataFrame, projects: Sequence[str]) -> pd.DataFrame:
    """Evenly distribute each discipline across projects using round-robin."""
    allocation: Dict[str, List[pd.Series]] = {project: [] for project in projects}

    for discipline in DISCIPLINE_ORDER:
        subset = engineers[engineers["Discipline"] == discipline]
        for index, (_, row) in enumerate(subset.iterrows()):
            project = projects[index % len(projects)]
            allocation[project].append(row)

    assigned_rows: List[dict] = []
    for project, people in allocation.items():
        for person in people:
            record = person.to_dict()
            record["Assigned Project"] = project
            assigned_rows.append(record)

    return pd.DataFrame(assigned_rows)


def build_balance_check(df_allocated: pd.DataFrame, projects: Sequence[str]) -> pd.DataFrame:
    """Create per-project discipline count summary for quick balancing review."""
    check_rows: List[dict] = []

    for project in projects:
        subset = df_allocated[df_allocated["Assigned Project"] == project]
        counts = subset["Discipline"].value_counts().to_dict()

        check_rows.append(
            {
                "Project": project,
                "Mechanical": counts.get("Mechanical", 0),
                "Civil": counts.get("Civil", 0),
                "Electrical": counts.get("Electrical", 0),
                "I&C": counts.get("I&C", 0),
                "HSE": counts.get("HSE", 0),
                "Other": counts.get("Other", 0),
            }
        )

    return pd.DataFrame(check_rows)


def write_output(
    output_file: Path,
    management: pd.DataFrame,
    allocation: pd.DataFrame,
    balance_check: pd.DataFrame,
) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(output_file) as writer:
        management.to_excel(writer, sheet_name="Management", index=False)
        allocation.to_excel(writer, sheet_name="Project_Allocation", index=False)
        balance_check.to_excel(writer, sheet_name="Balance_Check", index=False)


def run_allocation(config: AllocationConfig) -> None:
    """Run full workflow end-to-end."""
    df = load_and_prepare_data(config)

    management = df[df["Discipline"] == "Management"].copy()
    engineers = df[df["Discipline"] != "Management"].copy()

    allocated = allocate_engineers(engineers, config.projects)
    balance_check = build_balance_check(allocated, config.projects)

    write_output(config.output_file, management, allocated, balance_check)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create discipline-balanced engineer allocation workbook."
    )
    parser.add_argument(
        "--input-file",
        default="PETROCAF_Final_Allocation_v2.xlsx",
        help="Path to source Excel file (default: PETROCAF_Final_Allocation_v2.xlsx)",
    )
    parser.add_argument(
        "--output-file",
        default="PETROCAF_SMART_ALLOCATION.xlsx",
        help="Path to output Excel file (default: PETROCAF_SMART_ALLOCATION.xlsx)",
    )
    parser.add_argument(
        "--sheet",
        default="MASTER_ALL",
        help="Source worksheet name (default: MASTER_ALL)",
    )
    parser.add_argument(
        "--projects",
        nargs="+",
        default=DEFAULT_PROJECTS,
        help="Project names for round-robin assignment (space-separated list)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = AllocationConfig(
        input_file=Path(args.input_file),
        output_file=Path(args.output_file),
        source_sheet=args.sheet,
        projects=tuple(args.projects),
    )

    try:
        run_allocation(config)
    except AllocationError as exc:
        print(f"❌ Allocation failed: {exc}")
        return 1

    print(f"✅ DONE: SMART ALLOCATION GENERATED -> {config.output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
