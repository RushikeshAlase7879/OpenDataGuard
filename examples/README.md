# OpenDataGuard Synthetic Datasets

This directory contains synthetic datasets crafted for testing and demonstrating data quality validation and reconciliation features.

## Files

1. `sample_source.csv`:
   A customer profile dataset containing deliberate quality issues:
   - **Row 1 & 11**: Duplicate record (`customer_id: 1001`) to test duplicate row & unique key detection.
   - **Row 2**: Null email for `bob_jones` to test missing value checks.
   - **Row 4**: 
     - `age: 250` (violates upper bound 120 in range check).
     - `status: INVALID_STATUS` (violates categorical allowed values).
     - `signup_date: invalid-date-format` (violates date parsing check).
   - **Row 12**: Source-only customer (`customer_id: 1011`).

2. `sample_source_deduped.csv`:
   Same as `sample_source.csv` without the duplicate row (1001), suitable for direct one-to-one reconciliation without triggering duplicate key warnings.

3. `sample_target.csv`:
   The target reconciliation dataset (e.g. data warehouse downstream):
   - **Matching rows**: `1001`, `1002`, `1003`, `1006`, `1008`, `1009`, `1010`.
   - **Target-only row**: `customer_id: 1099` (absent from source).
   - **Source-only row**: `customer_id: 1011` (absent from target) and `customer_id: 1004` (absent from target).
   - **Cell value mismatch**: `customer_id: 1005` has `status: SUSPENDED` (Source had `INACTIVE`) and `balance: 150.00` (Source had `0.00`).
   - **Floating-point tolerance**: `customer_id: 1007` has `balance: 450.00001` vs Source `450.00` (matches within default absolute tolerance `1e-4`).

All data is strictly synthetic and contains no personal or corporate information.
