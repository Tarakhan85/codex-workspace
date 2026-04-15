"""PETROCAF smart resource allocation utility.

This script reads an input workbook, classifies personnel by discipline based on
job title text, keeps management separate, and distributes non-management staff
across target projects in a round-robin way per discipline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

import pandas as pd


@dataclass(frozen=True)
class AllocationConfig:
    """Runtime configuration for the allocation workflow."""

    input_file: Path = Path("PETROCAF_Final_Allocation_v2.xlsx")
    output_file: Path = Path("PETROCAF_SMART_ALLOCATION.xlsx")
    source_sheet: str = "MASTER_ALL"
    projects: tuple[str, ...] = (
        "NEAG_1_EPF",
        "DAHSHOUR_16IN_PIPELINE",
        "ALEX_FIRE_FIGHTING",
        "GAMSA_CHEMICAL",
    )


DISCIPLINE_ORDER: tuple[str, ...] = (
    "Mechanical",
    "Civil",
    "Electrical",
    "I&C",
    "HSE",
    "Other",
)


def classify_discipline(job_title: object) -> str:
    """Map free-text job title to a normalized discipline bucket."""
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


def validate_input_columns(df: pd.DataFrame, required_columns: Iterable[str]) -> None:
    """Fail fast when required columns are missing."""
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")


def load_source_data(config: AllocationConfig) -> pd.DataFrame:
    """Load and normalize source workbook rows."""
    df = pd.read_excel(config.input_file, sheet_name=config.source_sheet)
    validate_input_columns(df, required_columns=("Name", "Job Title"))
    return df.drop_duplicates(subset=["Name"]).copy()


def split_population(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Add discipline column and separate management from engineers."""
    typed = df.copy()
    typed["Discipline"] = typed["Job Title"].apply(classify_discipline)
    management = typed[typed["Discipline"] == "Management"].copy()
    engineers = typed[typed["Discipline"] != "Management"].copy()
    return management, engineers


def build_allocation(engineers: pd.DataFrame, projects: Iterable[str]) -> Dict[str, List[dict]]:
    """Distribute each discipline in round-robin order across projects."""
    project_list = list(projects)
    allocation: Dict[str, List[dict]] = {project: [] for project in project_list}

    for discipline in DISCIPLINE_ORDER:
        subset = engineers[engineers["Discipline"] == discipline]
        for index, (_, row) in enumerate(subset.iterrows()):
            project = project_list[index % len(project_list)]
            record = row.to_dict()
            record["Assigned Project"] = project
            allocation[project].append(record)

    return allocation


def build_project_allocation_frame(allocation: Dict[str, List[dict]]) -> pd.DataFrame:
    """Convert allocation dictionary to a flat dataframe."""
    rows: List[dict] = []
    for people in allocation.values():
        rows.extend(people)
    return pd.DataFrame(rows)


def build_balance_check(df_allocation: pd.DataFrame, projects: Iterable[str]) -> pd.DataFrame:
    """Build count matrix by project and discipline for QA."""
    checks: List[dict] = []

    for project in projects:
        subset = df_allocation[df_allocation["Assigned Project"] == project]
        disciplines = subset["Discipline"].value_counts().to_dict()

        checks.append(
            {
                "Project": project,
                "Mechanical": disciplines.get("Mechanical", 0),
                "Civil": disciplines.get("Civil", 0),
                "Electrical": disciplines.get("Electrical", 0),
                "I&C": disciplines.get("I&C", 0),
                "HSE": disciplines.get("HSE", 0),
                "Other": disciplines.get("Other", 0),
                "Total": len(subset),
            }
        )

    return pd.DataFrame(checks)


def save_output(
    management: pd.DataFrame,
    project_allocation: pd.DataFrame,
    balance_check: pd.DataFrame,
    output_file: Path,
) -> None:
    """Write workbook outputs to dedicated sheets."""
    with pd.ExcelWriter(output_file) as writer:
        management.to_excel(writer, sheet_name="Management", index=False)
        project_allocation.to_excel(writer, sheet_name="Project_Allocation", index=False)
        balance_check.to_excel(writer, sheet_name="Balance_Check", index=False)


def run_allocation(config: AllocationConfig) -> None:
    """Execute end-to-end smart allocation process."""
    source = load_source_data(config)
    management, engineers = split_population(source)
    allocation_map = build_allocation(engineers, config.projects)
    project_allocation = build_project_allocation_frame(allocation_map)
    balance_check = build_balance_check(project_allocation, config.projects)
    save_output(management, project_allocation, balance_check, config.output_file)

    print("✅ DONE: SMART ALLOCATION GENERATED")
    print(f"Output file: {config.output_file.resolve()}")


if __name__ == "__main__":
    run_allocation(AllocationConfig())
