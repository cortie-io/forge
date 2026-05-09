import pandas as pd

df = pd.read_csv("performance_comparison/sample_120_questions.csv", encoding="utf-8-sig")
print(df.columns)
print(df.head())
