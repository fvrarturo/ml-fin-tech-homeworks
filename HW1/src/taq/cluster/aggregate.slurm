#!/usr/bin/env bash
#SBATCH --job-name=taq_agg
#SBATCH --partition=mit_normal
#SBATCH --array=2016-2025
#SBATCH --cpus-per-task=4
#SBATCH --mem=64G
#SBATCH --time=06:00:00
#SBATCH --output=logs/taq_agg_%A_%a.out
#SBATCH --error=logs/taq_agg_%A_%a.err
# --------------------------------------------------------------------------- #
# SLURM array job: aggregate TAQ{YEAR}.csv.gz → partitioned 30-min bar parquet
#
# One task per calendar year (array index = year). Task 2025 is the heaviest
# (17 GB gzipped). 4 cores is enough because gzip decompression is the
# bottleneck and is single-threaded; giving more cores doesn't help and wastes
# partition slots.
#
# Launch:
#     sbatch src/taq/cluster/aggregate.slurm
#
# For a quick smoke test, override the array to a single cheap year:
#     sbatch --array=2016 --partition=mit_quicktest --time=00:15:00 \
#            src/taq/cluster/aggregate.slurm
# --------------------------------------------------------------------------- #
set -euo pipefail

ROOT="${HOME}/Fin_Tech/HW1"
cd "${ROOT}"
mkdir -p logs out/bars

YEAR="${SLURM_ARRAY_TASK_ID}"
INPUT="data/TAQ/TAQ${YEAR}.csv.gz"
OUT_DIR="out/bars"
META="out/meta_${YEAR}.json"

echo "[$(date -Is)] task=${YEAR} node=$(hostname) job=${SLURM_JOB_ID}.${SLURM_ARRAY_TASK_ID}"
echo "  input:  ${INPUT}  ($(du -h "${INPUT}" | cut -f1))"
echo "  output: ${OUT_DIR}/year=${YEAR}/"
echo

# Activate project venv (built by src/taq/cluster/setup_venv.sh).
module load miniforge/25.11.0-0 2>/dev/null || true
# shellcheck source=/dev/null
source venv/bin/activate
python -c "import sys, pandas, pyarrow; print(f'  python {sys.version.split()[0]}, pandas {pandas.__version__}, pyarrow {pyarrow.__version__}')"
echo

# Chunksize: 5M rows keeps per-chunk memory <1.5 GB on mixed string+numeric.
# Early-close dates is small (21 rows); we pass the CSV path.
python -m src.taq.aggregate_bars \
    --input        "${INPUT}" \
    --year         "${YEAR}" \
    --output-dir   "${OUT_DIR}" \
    --tickers      "data/reference/dj30_tenure.csv" \
    --early-closes "data/reference/nyse_early_closes.csv" \
    --chunksize    5000000 \
    --meta         "${META}"

echo
echo "[$(date -Is)] task=${YEAR} DONE"
cat "${META}"
