import re

def test_regex():
    print("--- Testing Regex Patterns ---")
    
    # 1. Original Pattern
    pattern_1 = r"^(\+|入款|下发)"
    
    # 2. Fallback Pattern (Added recently)
    pattern_2 = r"^(\+|-)?\d+"
    
    test_cases = [
        "+1000",
        "1000",
        "-100",
        "入款100",
        "下发500",
        "下发100u",
        " + 1000" # Leading space
    ]
    
    for text in test_cases:
        match1 = re.search(pattern_1, text)
        match2 = re.search(pattern_2, text)
        
        print(f"Text: '{text}'")
        print(f"  Pattern 1 (^(\\+|入款|下发)): {'✅ Match' if match1 else '❌ No Match'}")
        print(f"  Pattern 2 (^(\\+|-)?\\d+):   {'✅ Match' if match2 else '❌ No Match'}")
        
        if not match1 and not match2:
            print("  ⚠️  WARNING: No pattern matched!")
        else:
            print("  OK: Caught by at least one.")
            
if __name__ == "__main__":
    test_regex()