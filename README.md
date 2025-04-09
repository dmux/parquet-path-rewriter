# Parquet Path Rewriter

[![PyPI version](https://badge.fury.io/py/parquet-path-rewriter.svg)](https://badge.fury.io/py/parquet-path-rewriter)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python library to automatically rewrite relative Parquet file paths within Python code strings. It uses Abstract Syntax Tree (AST) manipulation to find calls like `spark.read.parquet('relative/path')` or `df.write.parquet(path='other/path')` and prepends a specified base directory path, making them absolute _within that base context_.

This is useful in scenarios where code needs to be adapted to run in different environments (e.g., local vs. cluster) where data root directories differ, without modifying the original relative path logic directly in the source code strings _before_ execution or analysis.

## Features

- Identifies `.parquet()` method calls (heuristic based on common Spark/Pandas patterns like `read.parquet` and `write.parquet`).
- Rewrites relative string literal paths passed as the first positional argument or using the `path=` keyword argument.
- Prepends a specified `base_path` (string or `pathlib.Path`).
- Ignores absolute paths.
- Ignores paths that are not string literals (e.g., variables, f-strings).
- Keeps track of which paths were rewritten (original -> new mapping).
- Identifies original paths used in likely _read_ operations.
- Uses Python's `ast` module for safe code transformation.

## Installation

```bash
pip install parquet-path-rewriter
```


## Usage

The primary way to use the library is through the rewrite_parquet_paths_in_code function.

```python
from pathlib import Path
from parquet_path_rewriter import rewrite_parquet_paths_in_code

original_python_code = """
import pyspark.sql

# Assume spark session is created elsewhere
# spark = SparkSession.builder.appName("ETLExample").getOrCreate()

print("Starting ETL process...")

# Read input data
customers_df = spark.read.parquet("raw_data/customers")
orders_df = spark.read.parquet(path="raw_data/orders_2023")

# Some transformations (placeholder)
processed_df = customers_df.join(orders_df, "customer_id")

# Write intermediate results
processed_df.write.mode("overwrite").parquet("staging/customer_orders")

# Read another input for final step
products_df = spark.read.parquet('reference_data/products.parquet')

# Final join and write output
final_df = processed_df.join(products_df, "product_id")
output_path = "final_output/report_data" # Not a literal in call
final_df.write.mode("overwrite").parquet(path="final_output/report_data") # Uses keyword

# Example with an absolute path (should not be changed)
logs_df = spark.read.parquet("/mnt/shared/logs/app_logs.parquet")

print("ETL process finished.")
"""

data_root_directory = Path("/user/project/data").resolve()

print("-" * 30)
print(f"Base Path: {data_root_directory}")
print("-" * 30)
print("Original Code:")
print(original_python_code)
print("-" * 30)

try:
    modified_code, rewritten_map, identified_inputs = rewrite_parquet_paths_in_code(
        code_string=original_python_code, base_path=data_root_directory
    )

    print("Modified Code:")
    print(modified_code)
    print("-" * 30)

    print("Rewritten Paths (Original -> New):")
    if rewritten_map:
        for original, new in rewritten_map.items():
            print(f"  '{original}' -> '{new}'")
    else:
        print("  No paths were rewritten.")
    print("-" * 30)

    print("Identified Input Paths (Original):")
    if identified_inputs:
        for path in identified_inputs:
            print(f"  '{path}'")
    else:
        print("  No input paths were identified.")
    print("-" * 30)

except SyntaxError as e:
    print(f"\nError: Invalid Python syntax in the input code.\n{e}")
except TypeError as e:
    print(f"\nError: Invalid base_path provided.\n{e}")
except Exception as e:
    print(f"\nAn unexpected error occurred: {e}")

```


## How it Works
The library parses the input Python code string into an Abstract Syntax Tree (AST) using Python's built-in ast module. It then walks through this tree using a custom ast.NodeTransformer. When it encounters a function call node:

1. It checks if the called attribute is named parquet.

2. It analyzes the call chain (e.g., spark.read.parquet) to guess if it's a read or write operation.

3. It looks for a string literal path in the arguments (first positional or path=...).

4. If a relative path string is found, it constructs a new path by joining the provided base_path with the relative path.

5. It replaces the original path node in the AST with a new node containing the modified path string.

6. Finally, it converts the modified AST back into Python code string.

## Limitations
- **Call Pattern Specificity:** It currently only identifies calls where the final method name is exactly parquet. It won't recognize patterns like spark.read.format("parquet").load("path"). Extending this would require more complex AST analysis.

- **String Literals Only:** Only rewrites paths that are provided as direct string literals (e.g., 'path/to/file', "other/path"). It ignores paths stored in variables, constructed via f-strings, or returned by function calls.

- **Heuristic Read/Write Detection:** The identification of 'read' vs 'write' operations is based on checking for read or write in the attribute chain leading to the .parquet call. This covers common Spark/Pandas usage but might not be universally accurate for all libraries or custom code structures.

- **AST Unparsing:** Relies on ast.unparse (Python 3.9+) or potentially a backport like astunparse for older versions to generate the output code. Minor formatting differences compared to the original code might occur.

## Contributing
Contributions are welcome! Please open an issue or submit a pull request on GitHub.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
