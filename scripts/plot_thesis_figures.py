import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import os
plt.rcParams['figure.dpi'] = 150
FIG_DIR = Path('reports/figures')
FIG_DIR.mkdir(parents=True, exist_ok=True)
TABLE = Path('reports/tables_for_thesis_20260225.csv')
df = pd.read_csv(TABLE)

# helper
def safe_save(fig, name):
    fig.savefig(FIG_DIR / f"{name}.png", bbox_inches='tight')
    fig.savefig(FIG_DIR / f"{name}.svg", bbox_inches='tight')
    plt.close(fig)

# E1 ESR by dataset
try:
    e1 = df[df['experiment_id'].str.contains('E1')]
    e1_ds = e1.copy()
    fig, ax = plt.subplots()
    ax.bar(e1_ds['dataset'], e1_ds['ESR'])
    ax.set_ylabel('ESR')
    ax.set_title('E1 ESR by Dataset')
    safe_save(fig, 'fig_e1_esr_by_dataset')
except Exception as e:
    print('skip fig_e1_esr_by_dataset', e)

# E1 cost latency
try:
    fig, axes = plt.subplots(1,2, figsize=(7,3))
    axes[0].bar(e1_ds['dataset'], e1_ds['avg_tokens'])
    axes[0].set_title('Avg Tokens')
    axes[1].bar(e1_ds['dataset'], e1_ds['avg_latency_ms'])
    axes[1].set_title('Avg Latency (ms)')
    safe_save(fig, 'fig_e1_cost_latency_by_dataset')
except Exception as e:
    print('skip fig_e1_cost_latency', e)

# E2 guard ablation llmsql
try:
    e2 = df[df['experiment_id'].str.contains('llmsql') & df['experiment_id'].str.contains('E2')]
    e2_sorted = e2.sort_values('experiment_id')
    fig, ax = plt.subplots()
    ax.bar(e2_sorted['experiment_id'], e2_sorted['ESR'])
    ax.set_xticklabels(e2_sorted['experiment_id'], rotation=30, ha='right')
    ax.set_ylabel('ESR')
    ax.set_title('E2 Guard Ablation (LLMSQL)')
    safe_save(fig, 'fig_e2_guard_ablation_llmsql')
except Exception as e:
    print('skip fig_e2_guard', e)

# E3 write matrix (use ESR as placeholder)
try:
    e3 = df[df['experiment_id'].str.contains('write_eval')]
    pivot = e3.pivot(index='experiment_id', columns='variant_id', values='ESR')
    fig, ax = plt.subplots()
    im = ax.imshow(pivot.values, cmap='viridis')
    ax.set_xticks(range(pivot.shape[1])); ax.set_xticklabels(pivot.columns, rotation=30, ha='right')
    ax.set_yticks(range(pivot.shape[0])); ax.set_yticklabels(pivot.index)
    ax.set_title('E3 Write Policy Matrix (ESR proxy)')
    fig.colorbar(im, ax=ax)
    safe_save(fig, 'fig_e3_write_policy_matrix')
except Exception as e:
    print('skip fig_e3', e)

# E5 schema tradeoff (LLMSQL)
try:
    e5 = df[df['experiment_id'].str.contains('llmsql') & df['experiment_id'].str.contains('E5')]
    fig, ax = plt.subplots()
    ax.scatter(e5['avg_tokens'], e5['ESR'])
    for _, row in e5.iterrows():
        ax.annotate(row['experiment_id'], (row['avg_tokens'], row['ESR']))
    ax.set_xlabel('Avg Tokens')
    ax.set_ylabel('ESR')
    ax.set_title('E5 Schema Cost-Performance (LLMSQL)')
    safe_save(fig, 'fig_e5_schema_tradeoff')
except Exception as e:
    print('skip fig_e5', e)

# Error code distribution E1
try:
    e1_codes = []
    for _, row in e1_ds.iterrows():
        e1_codes.append((row['dataset'], row['error_top1_code'], row['error_top1_count']))
    if e1_codes:
        fig, ax = plt.subplots()
        labels = [r[0] for r in e1_codes]
        vals = [r[2] for r in e1_codes]
        ax.bar(labels, vals)
        ax.set_title('E1 Top Error Count')
        safe_save(fig, 'fig_error_code_distribution_e1')
except Exception as e:
    print('skip fig_error_code', e)

print('figures written to', FIG_DIR)
