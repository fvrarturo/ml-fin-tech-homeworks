#!/usr/bin/env bash
#SBATCH --job-name=taq_panel
#SBATCH --partition=mit_normal
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=10:00:00
#SBATCH --output=logs/taq_panel_%j.out
#SBATCH --error=logs/taq_panel_%j.err
# --------------------------------------------------------------------------- #
# Build the H1 signal panel from partitioned bars. Cheap (single machine) but
# separated into its own job so dependencies are explicit.
#
# Launch after aggregate.slurm finishes:
#     sbatch --dependency=afterok:<AGG_JOB_ID> src/taq/cluster/build_panel.slurm
#
# Or, since the aggregate job is an array, use afterok:$JOB_ID to chain on the
# whole array's success.
# --------------------------------------------------------------------------- #
set -euo pipefail

ROOT="${HOME}/Fin_Tech/HW1"
cd "${ROOT}"
mkdir -p logs out/taq_summaries

module load miniforge/25.11.0-0 2>/dev/null || true
# shellcheck source=/dev/null
source venv/bin/activate

echo "[$(date -Is)] building H1 panel ..."
python -m src.taq.build_h1_panel \
    --bars-dir  out/bars \
    --members   data/reference/dj30_membership_long.csv \
    --out       out/taq_summaries/h1_panel.parquet \
    --meta      out/taq_summaries/h1_panel_meta.json

echo
echo "[$(date -Is)] auditing bars ..."
python -m src.taq.validate_bars \
    --bars-dir     out/bars \
    --early-closes data/reference/nyse_early_closes.csv \
    --crsp         data/interim/daily.parquet \
    --out-dir      out/taq_summaries

echo
echo "[$(date -Is)] DONE. Outputs:"
ls -la out/taq_summaries/
