from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

import pandas as pd


@dataclass(frozen=True)
class AllocationConfig:
    """Configuration for project allocation workflow."""

    input_file: Path
    output_file: Path
    source_sheet: str
    projects: Sequence[str]


DISCIPLINE_ORDER: Sequence[str] = (
    "Mechanical",
    "Civil",
    "Electrical",
    "I&C",
    "HSE",
    "Other",
)


REQUIRED_COLUMNS: Sequence[str] = (
    "Name",
    "Job Title",
)


def classify_discipline(job_title: str) -> str:
    """Map a job title to a discipline bucket."""
    job = str(job_title).strip().lower()

    if "mechanical" in job or "piping" in job:
        return "Mechanical"
    if "civil" in job:
        return "Civil"
    if "electrical" in job:
        return "Electrical"
    if "instrument" in job or "control" in job:
        return "I&C"
    if "hse" in job or "safety" in job:
        return "HSE"
    if "manager" in job or "director" in job:
        return "Management"
    return "Other"


def validate_columns(df: pd.DataFrame, required_columns: Iterable[str]) -> None:
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")


def load_and_prepare_data(config: AllocationConfig) -> pd.DataFrame:
    if not config.input_file.exists():
        raise FileNotFoundError(f"Input file not found: {config.input_file}")

    df = pd.read_excel(config.input_file, sheet_name=config.source_sheet)
    validate_columns(df, REQUIRED_COLUMNS)

    deduplicated = df.drop_duplicates(subset=["Name"]).copy()
    deduplicated["Discipline"] = deduplicated["Job Title"].apply(classify_discipline)
    return deduplicated


def allocate_engineers(engineers: pd.DataFrame, projects: Sequence[str]) -> Dict[str, List[pd.Series]]:
    if not projects:
        raise ValueError("Projects list cannot be empty.")

    allocation: Dict[str, List[pd.Series]] = {project: [] for project in projects}

    for discipline in DISCIPLINE_ORDER:
        subset = engineers[engineers["Discipline"] == discipline]
        for index, (_, row) in enumerate(subset.iterrows()):
            target_project = projects[index % len(projects)]
            allocation[target_project].append(row)

    return allocation


def build_project_allocation_table(allocation: Dict[str, List[pd.Series]]) -> pd.DataFrame:
    final_rows: List[dict] = []
    for project, people in allocation.items():
        for person in people:
            record = person.to_dict()
            record["Assigned Project"] = project
            final_rows.append(record)

    return pd.DataFrame(final_rows)


def build_balance_check(df_allocated: pd.DataFrame, projects: Sequence[str]) -> pd.DataFrame:
    checks: List[dict] = []

    for project in projects:
        subset = df_allocated[df_allocated["Assigned Project"] == project]
        counts = subset["Discipline"].value_counts().to_dict()

        checks.append(
            {
                "Project": project,
                "Mechanical": counts.get("Mechanical", 0),
                "Civil": counts.get("Civil", 0),
                "Electrical": counts.get("Electrical", 0),
                "I&C": counts.get("I&C", 0),
                "HSE": counts.get("HSE", 0),
                "Other": counts.get("Other", 0),
                "Total": len(subset),
            }
        )

    return pd.DataFrame(checks)


def write_output(
    output_file: Path,
    management_df: pd.DataFrame,
    allocation_df: pd.DataFrame,
    balance_df: pd.DataFrame,
) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_file) as writer:
        management_df.to_excel(writer, sheet_name="Management", index=False)
        allocation_df.to_excel(writer, sheet_name="Project_Allocation", index=False)
        balance_df.to_excel(writer, sheet_name="Balance_Check", index=False)


def run_allocation(config: AllocationConfig) -> None:
    prepared_df = load_and_prepare_data(config)
    management = prepared_df[prepared_df["Discipline"] == "Management"].copy()
    engineers = prepared_df[prepared_df["Discipline"] != "Management"].copy()

    allocation_map = allocate_engineers(engineers, config.projects)
    allocation_df = build_project_allocation_table(allocation_map)
    balance_df = build_balance_check(allocation_df, config.projects)

    write_output(config.output_file, management, allocation_df, balance_df)


def parse_args() -> AllocationConfig:
    parser = argparse.ArgumentParser(description="Generate balanced project allocations from an Excel file.")
    parser.add_argument("--input", default="PETROCAF_Final_Allocation_v2.xlsx", help="Input Excel file path")
    parser.add_argument("--output", default="PETROCAF_SMART_ALLOCATION.xlsx", help="Output Excel file path")
    parser.add_argument("--sheet", default="MASTER_ALL", help="Input sheet name")
    parser.add_argument(
        "--projects",
        nargs="+",
        default=[
            "NEAG_1_EPF",
            "DAHSHOUR_16IN_PIPELINE",
            "ALEX_FIRE_FIGHTING",
            "GAMSA_CHEMICAL",
        ],
        help="Projects to distribute staff across",
    )

    args = parser.parse_args()
    return AllocationConfig(
        input_file=Path(args.input),
        output_file=Path(args.output),
        source_sheet=args.sheet,
        projects=args.projects,
    )


def main() -> None:
    config = parse_args()
    run_allocation(config)
    print(f"✅ DONE: SMART ALLOCATION GENERATED -> {config.output_file}")


if __name__ == "__main__":
    main()
