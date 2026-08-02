import pytest
import os
from pathlib import Path
from app.kernel.data_processing.generative_crystals import run_dynamic_crystal_gauntlet

# This test should be run from the root of the project.
# It's a temporary test to verify the dynamic gauntlet.

def test_dynamic_gauntlet_non_breaking_change():
    """
    Tests the dynamic gauntlet with a non-breaking change.
    """
    file_to_change = "app/kernel/deployment/beast_context.py"
    
    # Read the original content
    original_content = Path(file_to_change).read_text()

    # Make a non-breaking change (add a comment)
    new_content = original_content.replace(
        'def validate(self) -> None:',
        'def validate(self) -> None:\\n        # This is a test comment'
    )

    # Run the gauntlet
    result = run_dynamic_crystal_gauntlet(file_to_change, new_content)

    assert result["status"] == "passed"

def test_dynamic_gauntlet_breaking_change():
    """
    Tests the dynamic gauntlet with a breaking change.
    """
    file_to_change = "app/kernel/deployment/beast_context.py"
    
    # Read the original content
    original_content = Path(file_to_change).read_text()

    # Make a breaking change (change TypeError to ValueError)
    new_content = original_content.replace(
        'raise TypeError("BEAST context dependencies violate protocols: " + ", ".join(missing))',
        'raise ValueError("BEAST context dependencies violate protocols: " + ", ".join(missing))'
    )

    # Run the gauntlet
    result = run_dynamic_crystal_gauntlet(file_to_change, new_content)

    assert result["status"] == "failed"

if __name__ == "__main__":
    # A way to run this standalone
    print("Running non-breaking change test...")
    test_dynamic_gauntlet_non_breaking_change()
    print("\\nRunning breaking change test...")
    test_dynamic_gauntlet_breaking_change()
    print("\\nAll tests finished.")
