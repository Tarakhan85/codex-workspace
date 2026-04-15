from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import pandas as pd


PROJECTS = [
    "NEAG_1_EPF",
    "DAHSHOUR_16IN_PIPELINE",
    "ALEX_FIRE_FIGHTING_WATER_TANK",
    "GAMSA_300M_CHEMICAL_BUND",
]

PROJECT_PRIORITY = {
    "NEAG_1_EPF": {
        "Mechanical": 1.0,
        "Civil": 1.0,
        "Electrical": 1.0,
        "Instrumentation": 1.0,
        "HSE": 1.0,
        "QAQC": 1.0,
        "Planning": 0.8,
        "Workforce_General": 1.0,
        "Other": 0.7,
    },
    "DAHSHOUR_16IN_PIPELINE": {
        "Mechanical": 1.8,
        "Civil": 0.4,
        "Electrical": 0.2,
        "Instrumentation": 0.2,
        "HSE": 1.0,
        "QAQC": 1.2,
        "Planning": 0.8,
        "Workforce_General": 1.5,
        "Other": 0.8,
    },
    "ALEX_FIRE_FIGHTING_WATER_TANK": {
        "Mechanical": 1.0,
        "Civil": 1.0,
        "Electrical": 1.2,
        "Instrumentation": 1.2,
        "HSE": 1.0,
        "QAQC": 1.0,
        "Planning": 0.7,
        "Workforce_General": 1.0,
        "Other": 0.8,
    },
    "GAMSA_300M_CHEMICAL_BUND": {
        "Mechanical": 0.5,
        "Civil": 1.8,
        "Electrical": 0.5,
        "Instrumentation": 0.2,
        "HSE": 1.0,
        "QAQC": 0.8,
        "Planning": 0.6,
        "Workforce_General": 1.3,
        "Other": 0.8,
    },
}

CENTRAL_TITLES = {
    "CEO / Founder",
    "Executive Management",
    "General Manager",
    "Project Director",
    "Construction Director",
    "Planning Manager / Engineer",
    "QA/QC Manager / Engineer / Inspector",
    "HSE Manager / Engineer / Officer",
    "Procurement / Contracts / Store",
    "Admin / HR / Finance / Document Control",
}

CENTRAL_DISCIPLINES = {
    "Management",
    "Finance_Admin",
    "Procurement",
    "Contracts",
    "Stores_Logistics",
}

REQUIRED_COLUMNS = [
    "Full_Name",
    "Normalized_Name",
    "Current_Title",
    "Standardized_Title",
    "Discipline",
    "Seniority_Level",
    "Years_Experience",
]

SENIORITY_ORDER = {
    "L3 Department / Project Management": 1,
    "L4 Lead / Senior Engineer": 2,
    "L5 Engineer / Specialist": 3,
    "L6 Supervisor / Foreman": 4,
    "L7 Technician / Skilled Worker": 5,
    "L8 General Worker / Support": 6,
}

KNOWN_DISCIPLINES = {
    "Mechanical",
    "Civil",
    "Electrical",
    "Instrumentation",
    "HSE",
    "QAQC",
    "Planning",
    "Workforce_General",
}


@dataclass(frozen=True)
class AllocationConfig:
    input_file: Path
    output_file: Path
    input_sheet: str = "MASTER_ALL"


def load_master_sheet(config: AllocationConfig) -> pd.DataFrame:
    df = pd.read_excel(config.input_file, sheet_name=config.input_sheet)
    missing = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns in {config.input_sheet}: {missing}")

    dedup_col = "Normalized_Name" if "Normalized_Name" in df.columns else "Full_Name"
    return df.drop_duplicates(subset=[dedup_col]).copy()


def is_central(row: pd.Series) -> bool:
    title = str(row.get("Standardized_Title", "")).strip()
    discipline = str(row.get("Discipline", "")).strip()
    level = str(row.get("Seniority_Level", "")).strip()
    return (
        title in CENTRAL_TITLES
        or discipline in CENTRAL_DISCIPLINES
        or level in {"L1 Executive", "L2 Senior Management"}
    )


def normalize_discipline(value: object) -> str:
    discipline = str(value).strip()
    return discipline if discipline in KNOWN_DISCIPLINES else "Other"


def prepare_workforce(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    df = df.copy()
    df["Is_Central"] = df.apply(is_central, axis=1)

    management_df = df[df["Is_Central"]].copy()
    site_df = df[~df["Is_Central"]].copy()

    site_df["Discipline_Group"] = site_df["Discipline"].apply(normalize_discipline)
    site_df["Seniority_Rank"] = site_df["Seniority_Level"].map(SENIORITY_ORDER).fillna(99)
    site_df["Years_Experience"] = pd.to_numeric(site_df["Years_Experience"], errors="coerce").fillna(0)

    site_df = site_df.sort_values(
        by=["Discipline_Group", "Seniority_Rank", "Years_Experience"],
        ascending=[True, True, False],
    ).copy()

    return management_df, site_df


def weighted_targets(people_count: int, discipline: str) -> Dict[str, int]:
    weights = {project: PROJECT_PRIORITY[project].get(discipline, 1.0) for project in PROJECTS}
    total_weight = sum(weights.values())

    raw = {project: people_count * (weights[project] / total_weight) for project in PROJECTS}
    base = {project: math.floor(raw[project]) for project in PROJECTS}
    remainder = people_count - sum(base.values())

    fractions = sorted(PROJECTS, key=lambda p: raw[p] - base[p], reverse=True)
    for idx in range(remainder):
        base[fractions[idx]] += 1

    return base


def allocate_site_team(site_df: pd.DataFrame) -> pd.DataFrame:
    allocation_rows: List[dict] = []

    for discipline, group in site_df.groupby("Discipline_Group", sort=False):
        people = group.to_dict("records")
        targets = weighted_targets(len(people), discipline)

        start = 0
        for project in PROJECTS:
            count = targets[project]
            for person in people[start : start + count]:
                person["Assigned_Project"] = project
                person["Allocation_Basis"] = f"{discipline} weighted fit"
                allocation_rows.append(person)
            start += count

    return pd.DataFrame(allocation_rows)


def build_balance_check(df_final: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for project in PROJECTS:
        subset = df_final[df_final["Assigned_Project"] == project]
        counts = subset["Discipline_Group"].value_counts().to_dict()
        rows.append(
            {
                "Project": project,
                "Total": len(subset),
                "Mechanical": counts.get("Mechanical", 0),
                "Civil": counts.get("Civil", 0),
                "Electrical": counts.get("Electrical", 0),
                "Instrumentation": counts.get("Instrumentation", 0),
                "HSE": counts.get("HSE", 0),
                "QAQC": counts.get("QAQC", 0),
                "Planning": counts.get("Planning", 0),
                "Workforce_General": counts.get("Workforce_General", 0),
                "Other": counts.get("Other", 0),
            }
        )

    return pd.DataFrame(rows)


def build_project_sheets(df_final: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    sheets = {}
    for project in PROJECTS:
        subset = df_final[df_final["Assigned_Project"] == project].copy()
        sheets[project] = subset.sort_values(
            by=["Seniority_Rank", "Years_Experience"],
            ascending=[True, False],
        )
    return sheets


def save_allocation(
    output_file: Path,
    management_df: pd.DataFrame,
    df_final: pd.DataFrame,
    df_check: pd.DataFrame,
    project_sheets: Dict[str, pd.DataFrame],
) -> None:
    with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
        management_df.to_excel(writer, sheet_name="Management_Shared", index=False)
        df_final.to_excel(writer, sheet_name="Project_Allocation", index=False)
        df_check.to_excel(writer, sheet_name="Balance_Check", index=False)

        for project_name, data in project_sheets.items():
            data.to_excel(writer, sheet_name=project_name[:31], index=False)


def run_allocation(config: AllocationConfig) -> None:
    master_df = load_master_sheet(config)
    management_df, site_df = prepare_workforce(master_df)
    final_allocation = allocate_site_team(site_df)
    check_df = build_balance_check(final_allocation)
    sheets = build_project_sheets(final_allocation)

    save_allocation(config.output_file, management_df, final_allocation, check_df, sheets)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate weighted project staffing allocation workbook.")
    parser.add_argument(
        "--input",
        default="PETROCAF_Final_Allocation_v2.xlsx",
        help="Input Excel workbook path (default: PETROCAF_Final_Allocation_v2.xlsx)",
    )
    parser.add_argument(
        "--output",
        default="PETROCAF_SMART_ALLOCATION.xlsx",
        help="Output Excel workbook path (default: PETROCAF_SMART_ALLOCATION.xlsx)",
    )
    parser.add_argument(
        "--sheet",
        default="MASTER_ALL",
        help="Input worksheet name (default: MASTER_ALL)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = AllocationConfig(
        input_file=Path(args.input),
        output_file=Path(args.output),
        input_sheet=args.sheet,
    )
    run_allocation(config)
    print(f"✅ DONE: SMART ALLOCATION GENERATED -> {config.output_file}")


if __name__ == "__main__":
    main()
