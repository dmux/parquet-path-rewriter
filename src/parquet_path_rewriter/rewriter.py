# src/parquet_path_rewriter/rewriter.py

"""
Core implementation for rewriting Parquet paths in Python code using AST.

This module defines the `ParquetPathRewriter` class, an `ast.NodeTransformer`
that traverses Python code's Abstract Syntax Tree (AST) to find and modify
string literals used as paths in '.parquet()' method calls. It also provides
a helper function `rewrite_parquet_paths_in_code` for easier usage.
"""

import ast
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union

# Define a specific type for AST string constants for clarity
AstStringConstant = (
    ast.Constant
)  # In Python 3.8+, ast.Constant replaces ast.Str, ast.Num etc.
# For Python 3.7 compatibility, you might need:
# AstStringConstant = getattr(ast, "Constant", ast.Str) # Check if Constant exists, fallback to Str


class ParquetPathRewriter(ast.NodeTransformer):
    """
    Traverses a Python Abstract Syntax Tree (AST) and rewrites string literal
    arguments in calls to '.parquet()' methods.

    It modifies relative paths to be rooted within a specified base directory,
    preserving the original file/directory name component. It also tracks
    which paths were rewritten and identifies original paths used in likely
    read operations.

    Attributes:
        base_path: The directory path to prepend to relative parquet paths.
        rewritten_paths: A dictionary mapping original path strings to their
                         newly constructed full path strings.
        identified_inputs: A list of original path strings identified in
                           likely read operations (e.g., spark.read.parquet).
    """

    def __init__(self, base_path: Path):
        if not isinstance(base_path, Path):
            raise TypeError("base_path must be a pathlib.Path object")
        self.base_path = base_path.resolve()  # Ensure base_path is absolute
        self.rewritten_paths: Dict[str, str] = {}
        self.identified_inputs: List[str] = []

    def _is_parquet_call(self, node: ast.Call) -> bool:
        """Checks if the node represents a method call named 'parquet'."""
        return isinstance(node.func, ast.Attribute) and node.func.attr == "parquet"

    def _analyze_call_chain(self, node: ast.Call) -> Tuple[bool, bool]:
        """
        Determines if the call chain likely represents a read or write operation.
        Searches for 'read' or 'write' attributes preceding the '.parquet' call.
        """
        is_read = False
        is_write = False
        current_expr = node.func
        call_chain_parts: List[str] = []

        # Traverse up the attribute access chain (e.g., df.write.parquet)
        while isinstance(current_expr, ast.Attribute):
            call_chain_parts.insert(0, current_expr.attr)
            current_expr = current_expr.value
        # Add the base object name if it's a simple name (e.g., 'spark' in spark.read...)
        if isinstance(current_expr, ast.Name):
            call_chain_parts.insert(0, current_expr.id)

        # Heuristic check for read/write patterns
        if "read" in call_chain_parts:
            is_read = True
        if "write" in call_chain_parts:
            is_write = True

        return is_read, is_write

    def _find_path_argument(
        self, node: ast.Call
    ) -> Tuple[Optional[AstStringConstant], Optional[int], bool]:
        """
        Finds the path argument within the call node.

        Looks for the first positional argument or a keyword argument named 'path',
        expecting a string literal.

        Returns:
            A tuple containing:
            - The AST Constant node for the path string (or None if not found/not string).
            - The index of the argument (in args or keywords list) (or None).
            - A boolean indicating if it was found as a keyword argument.
        """
        path_arg_node: Optional[AstStringConstant] = None
        arg_index: Optional[int] = None
        is_keyword = False

        # 1. Check first positional argument
        if (
            node.args
            and isinstance(node.args[0], AstStringConstant)
            and isinstance(node.args[0].value, str)
        ):
            path_arg_node = node.args[0]
            arg_index = 0
            is_keyword = False
        # 2. Check keyword arguments for 'path'
        else:
            for i, kw in enumerate(node.keywords):
                if (
                    kw.arg == "path"
                    and isinstance(kw.value, AstStringConstant)
                    and isinstance(kw.value.value, str)
                ):
                    path_arg_node = kw.value
                    arg_index = i
                    is_keyword = True
                    break  # Found it

        return path_arg_node, arg_index, is_keyword

    def visit_Call(self, node: ast.Call) -> ast.AST:
        """Visits function/method call nodes in the AST."""
        # Only proceed if it's a '.parquet()' call
        if not self._is_parquet_call(node):
            return self.generic_visit(node)  # Continue traversal for other nodes

        is_read, _is_write = self._analyze_call_chain(node)
        path_arg_node, arg_index, is_keyword = self._find_path_argument(node)

        # Proceed only if a valid string path argument was found
        if path_arg_node is not None and arg_index is not None:
            original_path_str: str = path_arg_node.value
            original_path = Path(original_path_str)

            # Rewrite only relative paths that don't already start with the base path
            # (prevents double-rewriting and respects absolute paths)
            should_rewrite = (
                not original_path.is_absolute()
                and not original_path_str.startswith(str(self.base_path))
                and original_path_str  # Ensure not an empty string
            )

            if should_rewrite:
                try:
                    # Construct the new path relative to the base path
                    new_path = self.base_path / original_path
                    new_path_str = str(new_path)

                    # Track the changes
                    self.rewritten_paths[original_path_str] = new_path_str
                    if is_read:
                        self.identified_inputs.append(original_path_str)

                    # Create the new AST node for the modified path string
                    new_const_node = ast.Constant(value=new_path_str)
                    ast.copy_location(
                        new_const_node, path_arg_node
                    )  # Preserve line/col info

                    # Replace the old path node in the AST
                    if is_keyword:
                        node.keywords[arg_index].value = new_const_node
                    else:
                        # Ensure args list is mutable before modification
                        if not isinstance(node.args, list):
                            node.args = list(node.args)
                        node.args[arg_index] = new_const_node

                    # Print debug info (optional)
                    # print(f"Rewritten: '{original_path_str}' -> '{new_path_str}'")

                except (TypeError, ValueError) as e:
                    # Handle potential issues with Path operations\
                    #  (though unlikely with basic strings)
                    print(
                        f"Warning: Could not process path '{original_path_str}'. Error: {e}"
                    )
                    # Decide if you want to skip rewriting or raise an error
                    # For now, we just print a warning and don't rewrite

        # Crucial: Continue visiting child nodes of the current call node
        # (e.g., arguments within the .parquet() call might contain other calls)
        return self.generic_visit(node)


# --- Helper Function for Easier Library Usage ---


def rewrite_parquet_paths_in_code(
    code_string: str,
    base_path: Union[str, Path],
    *,
    filename: str = "<string>",  # Filename for potential AST errors
) -> Tuple[str, Dict[str, str], List[str]]:
    """
    Parses Python code, rewrites relative parquet paths, and returns the modified code.

    Args:
        code_string: The Python code as a string.
        base_path: The base directory (as a string or Path object) to prepend
                   to relative parquet paths.
        filename: The filename to report in case of parsing errors.

    Returns:
        A tuple containing:
        - The modified Python code string.
        - A dictionary mapping original paths to rewritten paths.
        - A list of original paths identified as inputs.

    Raises:
        SyntaxError: If the input code_string is not valid Python code.
        TypeError: If base_path is not a string or Path object.
    """
    if isinstance(base_path, str):
        base_path_obj = Path(base_path)
    elif isinstance(base_path, Path):
        base_path_obj = base_path
    else:
        raise TypeError("base_path must be a string or pathlib.Path object")

    try:
        tree = ast.parse(code_string, filename=filename)
    except SyntaxError as e:
        print(f"Error parsing Python code: {e}")
        raise

    rewriter = ParquetPathRewriter(base_path=base_path_obj)
    modified_tree = rewriter.visit(tree)
    ast.fix_missing_locations(modified_tree)  # Important after transformations

    try:
        # ast.unparse requires Python 3.9+
        # For older versions (3.7, 3.8), you might need a backport like 'astunparse'
        # import astunparse # pip install astunparse
        # modified_code = astunparse.unparse(modified_tree)
        modified_code = ast.unparse(modified_tree)
    except AttributeError:
        # Fallback or error for Python < 3.9 if astunparse is not installed
        raise RuntimeError(
            "ast.unparse is not available (requires Python 3.9+). "
            "Install 'astunparse' for older versions."
        ) from e
    except Exception as e:
        print(f"Error unparsing modified AST: {e}")
        # Depending on the error, you might return original code or re-raise
        raise RuntimeError(f"Failed to generate code from modified AST: {e}") from e

    return modified_code, rewriter.rewritten_paths, rewriter.identified_inputs
