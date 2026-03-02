# This file writes a record of every decision to audit_log.json.
# This is the permanent audit trail — every action the system takes is logged here.

import json

def log_decision(audit_entry):
    """
    Takes a completed audit_entry dictionary.
    Appends it as a new line in audit_log.json.
    Creates the file if it doesn't exist yet.
    """

    with open("audit_log.json", "a") as log_file:
        log_file.write(json.dumps(audit_entry) + "\n")

    print("\n--- AUDIT LOG ENTRY WRITTEN ---")
    print(json.dumps(audit_entry, indent=2))
    print("--------------------------------\n")