#!/usr/bin/env python3

import pandas as pd
import json
import sys
import os
import numpy as np

def clean_cell(x):
    if pd.isna(x) or (isinstance(x, (float, np.float64)) and str(x) == "nan"):
        return None
    if isinstance(x, pd.Timestamp):
        return str(x)
    return x

def main():
    try:
        input_path = "/home/nifi/nifi2/HR_Bot/data/CandidateData.xlsx"

        if not os.path.exists(input_path):
            sys.stderr.write(f"Error: File not found - {input_path}\n")
            sys.exit(1)

        df = pd.read_excel(input_path, engine='openpyxl')

        # ✅ Updated to use .map() instead of deprecated .applymap()
        df_clean = df.map(clean_cell)

        records = df_clean.to_dict(orient='records')

        print(json.dumps(records, ensure_ascii=False, indent=2))

    except Exception as e:
        sys.stderr.write(f"Error: {str(e)}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
