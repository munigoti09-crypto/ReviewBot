"""Quick demonstration of Work 3 with live Gemini API."""

import json
from reviewbot.ai_agent.agent import generate_fix

def main():
    issues = [
        {
            "file": "calculator.py",
            "line": 3,
            "tool": "ruff",
            "code": "F821",
            "message": "Undefined name 'result'",
            "severity": "error",
        }
    ]

    source_files = {
        "calculator.py": "def calculate(a, b):\n    total = a + b\n    return result\n"
    }

    print("--- 1. Input Issue ---")
    print(json.dumps(issues, indent=2))
    print("\n--- 2. Original Source Code ---")
    print(source_files["calculator.py"])

    print("--- 3. Calling Gemini ReviewBot Agent ---")
    fixes = generate_fix(issues=issues, source_files=source_files)

    print("\n--- 4. Fix Result Output ---")
    for fix in fixes:
        print(f"File: {fix['file']}")
        print(f"Status: {fix['status']}")
        print(f"Explanation: {fix['explanation']}")
        print("\nGenerated Patch:")
        print(fix["patch"])
        print("Fixed Code:")
        print(fix["fixed_code"])

if __name__ == "__main__":
    main()
