from pathlib import Path

# Make sure src is in path if running directly without installation
# sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'src'))

from parquet_path_rewriter import rewrite_parquet_paths_in_code

# --- Example Code ---
# Simulate a Python script that uses Spark or Pandas to read/write Parquet
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

# --- Library Usage ---

# Define the base directory where the relative paths should point
# This would typically be determined by your execution environment or configuration
# Use absolute paths for clarity
data_root_directory = Path("/user/project/data").resolve()

print("-" * 30)
print(f"Base Path: {data_root_directory}")
print("-" * 30)
print("Original Code:")
print(original_python_code)
print("-" * 30)

try:
    # Call the library function to rewrite the code
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
