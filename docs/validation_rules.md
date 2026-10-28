# Declarative Validation Rules Reference

OpenDataGuard enables data engineers to define and version-control validation rules as declarative **JSON** or **YAML** files.

---

## 1. File Structure

Every rules file must contain a root object with `version` and a `rules` list:

```json
{
  "version": "1.0",
  "description": "Optional human-readable description",
  "rules": [
    { ... }
  ]
}
```

---

## 2. Supported Rule Types

### `required`
Asserts that a column contains non-null values.
```json
{
  "rule": "required",
  "column": "customer_id",
  "threshold_percent": 0.0,
  "treat_empty_as_missing": false
}
```
- `threshold_percent` (optional, default `0.0`): Permissible percentage of missing rows (0.0 to 100.0).
- `treat_empty_as_missing` (optional, default `false`): If `true`, also treats empty strings `""` and whitespace-only strings `"   "` as missing values.

### `unique`
Asserts that values across one or more columns are unique and non-null.
```json
{
  "rule": "unique",
  "columns": ["customer_id"]
}
```

### `duplicate_rows`
Asserts that there are no duplicate rows across the entire dataset or a column subset.
```json
{
  "rule": "duplicate_rows",
  "columns": ["customer_id", "email"]
}
```

### `data_type`
Validates that values conform to expected data types (`int`, `float`, `datetime`, `bool`, `string`).
```json
{
  "rule": "data_type",
  "column": "age",
  "type": "int"
}
```

### `range` / `min_value` / `max_value`
Restricts numeric values within specified bounds.
```json
{
  "rule": "range",
  "column": "age",
  "min": 18,
  "max": 120
}
```

### `allowed_values`
Restricts categorical values to a defined set.
```json
{
  "rule": "allowed_values",
  "column": "status",
  "values": ["ACTIVE", "INACTIVE", "PENDING"],
  "case_sensitive": true
}
```

### `min_length` / `max_length` / `length_range`
Validates string character count bounds.
```json
{
  "rule": "length_range",
  "column": "username",
  "min": 3,
  "max": 30
}
```

### `date_format` / `date_range`
Validates parseability, bounds, and optionally ascending chronological sequence.
```json
{
  "rule": "date_range",
  "column": "signup_date",
  "format": "%Y-%m-%d",
  "min_date": "2020-01-01",
  "max_date": "2030-12-31",
  "chronological": true
}
```
- `chronological` (optional, default `false`): Asserts valid dates appear in ascending chronological order.

### `regex`
Matches text values against a regular expression pattern.
```json
{
  "rule": "regex",
  "column": "username",
  "pattern": "^[a-zA-Z0-9_]{3,30}$"
}
```

### `email`
Validates that text values conform to standard email syntax.
```json
{
  "rule": "email",
  "column": "email"
}
```
- `pattern` (optional): Override the default RFC-compliant email regex pattern.

### `schema`
Asserts required column presence and flags unexpected columns if `strict: true`.
```json
{
  "rule": "schema",
  "expected_columns": ["customer_id", "email", "age", "status"],
  "strict": false
}
```
