## Smart Allocation Utility

`smart_allocation.py` generates a discipline-balanced project allocation workbook from an input Excel sheet.

### Usage

```bash
python smart_allocation.py \
  --input-file PETROCAF_Final_Allocation_v2.xlsx \
  --output-file PETROCAF_SMART_ALLOCATION.xlsx \
  --sheet MASTER_ALL \
  --projects NEAG_1_EPF DAHSHOUR_16IN_PIPELINE ALEX_FIRE_FIGHTING GAMSA_CHEMICAL
```

### Output sheets

- `Management`: personnel classified as Management.
- `Project_Allocation`: discipline-distributed engineering personnel with `Assigned Project`.
- `Balance_Check`: project-level discipline counts for validation.
