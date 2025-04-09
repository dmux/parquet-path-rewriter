"""
This module contains unit tests for the Parquet path rewriter.
"""

import ast
from pathlib import Path
import pytest


# Make sure the src directory is in the path for tests
# (Alternatively, install the package in editable mode: pip install -e .)
# sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Now import from the package
from src.parquet_path_rewriter import rewrite_parquet_paths_in_code

# Define a base path for testing (use Path objects)
# Use a POSIX-like path for consistency in tests across platforms
BASE_TEST_PATH = Path("/test/data/base").resolve()  # Make it absolute


# Helper to normalize code string for comparison (removes extra whitespace/newlines)
def normalize_code(code: str) -> str:
    """Normalize code string by removing extra whitespace and newlines."""
    try:
        # Parse and unparse to get a canonical representation
        # Requires Python 3.9+ for ast.unparse
        return ast.unparse(ast.parse(code))
    except AttributeError:
        # Basic normalization for older Python versions if astunparse isn't used/available
        return "\n".join(
            line.strip() for line in code.strip().splitlines() if line.strip()
        )
    except SyntaxError:
        # Fallback if parsing fails (shouldn't happen for valid test code)
        return code.strip()


def test_simple_read_rewrite():
    """Test rewriting a simple spark.read.parquet call."""
    code = """
import pyspark.sql
spark = pyspark.sql.SparkSession.builder.getOrCreate()
df = spark.read.parquet('input/my_data.parquet')
print(df.count())
"""
    expected_rewritten_path = str(BASE_TEST_PATH / "input/my_data.parquet")
    expected_code = f"""
import pyspark.sql
spark = pyspark.sql.SparkSession.builder.getOrCreate()
df = spark.read.parquet('{expected_rewritten_path}')
print(df.count())
"""
    modified_code, rewritten, inputs = rewrite_parquet_paths_in_code(
        code, BASE_TEST_PATH
    )

    assert normalize_code(modified_code) == normalize_code(expected_code)
    assert rewritten == {"input/my_data.parquet": expected_rewritten_path}
    assert inputs == ["input/my_data.parquet"]


def test_simple_write_rewrite():
    """Test rewriting a simple df.write.parquet call."""
    code = """
df.write.mode('overwrite').parquet("output/final_table")
"""
    expected_rewritten_path = str(BASE_TEST_PATH / "output/final_table")
    expected_code = f"""
df.write.mode('overwrite').parquet('{expected_rewritten_path}')
"""
    modified_code, rewritten, inputs = rewrite_parquet_paths_in_code(
        code, BASE_TEST_PATH
    )

    assert normalize_code(modified_code) == normalize_code(expected_code)
    assert rewritten == {"output/final_table": expected_rewritten_path}
    assert not inputs  # No inputs in this case


def test_keyword_argument_rewrite():
    """Test rewriting using the 'path=' keyword argument."""
    code = """
df_result = spark.read.parquet(path = "staging/data_v1")
"""
    expected_rewritten_path = str(BASE_TEST_PATH / "staging/data_v1")
    expected_code = f"""
df_result = spark.read.parquet(path='{expected_rewritten_path}')
"""
    modified_code, rewritten, inputs = rewrite_parquet_paths_in_code(
        code, BASE_TEST_PATH
    )

    assert normalize_code(modified_code) == normalize_code(expected_code)
    assert rewritten == {"staging/data_v1": expected_rewritten_path}
    assert inputs == ["staging/data_v1"]


def test_absolute_path_no_rewrite():
    """Test that absolute paths are not rewritten."""
    absolute_path = "/var/log/data.parquet"
    code = f"""
df = spark.read.parquet('{absolute_path}')
"""
    modified_code, rewritten, inputs = rewrite_parquet_paths_in_code(
        code, BASE_TEST_PATH
    )

    assert normalize_code(modified_code) == normalize_code(
        code
    )  # Code should be unchanged
    assert not rewritten  # No paths to rewrite
    assert not inputs  # No parquet paths to rewrite


def test_path_already_based_no_rewrite():
    """Test that paths already starting with the base path are not rewritten."""
    path_already_based = str(BASE_TEST_PATH / "subdir/file.parquet")
    code = f"""
df.write.parquet('{path_already_based}')
"""
    modified_code, rewritten, inputs = rewrite_parquet_paths_in_code(
        code, BASE_TEST_PATH
    )

    assert normalize_code(modified_code) == normalize_code(
        code
    )  # Code should be unchanged
    assert not rewritten  # No paths to rewrite
    assert not inputs  # No parquet paths to rewrite


def test_non_parquet_call_no_rewrite():
    """Test that calls other than '.parquet' are ignored."""
    code = """
df = spark.read.csv('input/my_data.csv')
df.write.json('output/my_data.json')
some_object.some_method('path/to/something')
"""
    modified_code, rewritten, inputs = rewrite_parquet_paths_in_code(
        code, BASE_TEST_PATH
    )

    assert normalize_code(modified_code) == normalize_code(
        code
    )  # Code should be unchanged
    assert not rewritten  # No paths to rewrite
    assert not inputs  # No parquet paths to rewrite


def test_non_string_literal_path_no_rewrite():
    """Test that non-string-literal paths are ignored."""
    code = """
path_var = 'dynamic/path.parquet'
df = spark.read.parquet(path_var)
df2 = spark.read.parquet(f"formatted/{path_var}")
df3 = spark.read.parquet('literal/path.parquet') # This one should be rewritten
"""
    expected_rewritten_path = str(BASE_TEST_PATH / "literal/path.parquet")
    _expected_code = f"""
path_var = 'dynamic/path.parquet'
df = spark.read.parquet(path_var)
df2 = spark.read.parquet(f'formatted/{{path_var}}')
df3 = spark.read.parquet('{expected_rewritten_path}')
"""
    modified_code, rewritten, inputs = rewrite_parquet_paths_in_code(
        code, BASE_TEST_PATH
    )

    # Check the parts that should change/not change
    assert "spark.read.parquet(path_var)" in modified_code
    # F-string representation can be tricky, check presence of key part
    assert f"spark.read.parquet(f'formatted/{{path_var}}')" in normalize_code(
        modified_code
    )
    assert f"spark.read.parquet('{expected_rewritten_path}')" in modified_code

    assert rewritten == {"literal/path.parquet": expected_rewritten_path}
    assert inputs == ["literal/path.parquet"]


def test_multiple_calls():
    """Test code with multiple parquet calls."""
    code = """
df1 = spark.read.parquet('source1/data')
df2 = spark.read.parquet(path='source2/more_data')
df1.write.parquet('intermediate/step1')
df_final = df1.join(df2)
df_final.write.parquet(path="results/final_output.parquet")
"""
    expected_rewritten = {
        "source1/data": str(BASE_TEST_PATH / "source1/data"),
        "source2/more_data": str(BASE_TEST_PATH / "source2/more_data"),
        "intermediate/step1": str(BASE_TEST_PATH / "intermediate/step1"),
        "results/final_output.parquet": str(
            BASE_TEST_PATH / "results/final_output.parquet"
        ),
    }
    expected_inputs = ["source1/data", "source2/more_data"]

    modified_code, rewritten, inputs = rewrite_parquet_paths_in_code(
        code, BASE_TEST_PATH
    )

    # Check a few key rewrites in the output code
    assert (
        f"spark.read.parquet('{expected_rewritten['source1/data']}')" in modified_code
    )
    assert (
        f"write.parquet(path='{expected_rewritten['results/final_output.parquet']}')"
        in modified_code
    )

    assert rewritten == expected_rewritten
    # Sort inputs for consistent comparison
    assert sorted(inputs) == sorted(expected_inputs)


def test_invalid_base_path_type():
    """Test that providing an invalid type for base_path raises TypeError."""
    code = "spark.read.parquet('data')"
    with pytest.raises(
        TypeError, match="base_path must be a string or pathlib.Path object"
    ):
        rewrite_parquet_paths_in_code(code, base_path=123)


def test_invalid_python_code():
    """Test that invalid Python syntax raises SyntaxError."""
    code = "spark.read.parquet('data' blah"
    with pytest.raises(SyntaxError):
        rewrite_parquet_paths_in_code(code, BASE_TEST_PATH)
