#!/usr/bin/env bash
# End-to-end orchestration for the H1 TAQ pipeline.
#
# Two modes:
#
#   Local (laptop):
#       bash src/taq/cluster/run_pipeline.sh push
#           → rsync src + reference data to cluster
#       bash src/taq/cluster/run_pipeline.sh submit
#           → ssh in, submit the SLURM chain (aggregate → build_panel)
#       bash src/taq/cluster/run_pipeline.sh status
#           → ssh in, squeue + tail recent logs
#       bash src/taq/cluster/run_pipeline.sh pull
#           → rsync summary files back to data/interim/taq_summaries/
#       bash src/taq/cluster/run_pipeline.sh all
#           → push + submit (you poll status / pull later)
#
#   Cluster (already ssh'd):
#       bash src/taq/cluster/run_pipeline.sh setup
#           → one-shot venv bootstrap (see setup_venv.sh)

set -euo pipefail

# --------------------------------------------------------------------------- #
# Config                                                                      #
# --------------------------------------------------------------------------- #
CLUSTER_USER="${CLUSTER_USER:-favara}"
CLUSTER_HOST="${CLUSTER_HOST:-orcd-login.mit.edu}"
CLUSTER_ROOT="${CLUSTER_ROOT:-~/Fin_Tech/HW1}"
LOCAL_ROOT="${LOCAL_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
SSH="ssh ${CLUSTER_USER}@${CLUSTER_HOST}"

# --------------------------------------------------------------------------- #
# Functions                                                                   #
# --------------------------------------------------------------------------- #

push() {
    echo "[push] rsync code + reference data → ${CLUSTER_USER}@${CLUSTER_HOST}:${CLUSTER_ROOT}"
    cd "${LOCAL_ROOT}"
    # Sync code
    rsync -avz --delete \
        --exclude='__pycache__/' --exclude='*.pyc' --exclude='.pytest_cache/' \
        src/ "${CLUSTER_USER}@${CLUSTER_HOST}:${CLUSTER_ROOT}/src/"
    # Sync reference data (small files; needed for membership PIT + early-closes)
    rsync -avz \
        data/reference/ "${CLUSTER_USER}@${CLUSTER_HOST}:${CLUSTER_ROOT}/data/reference/"
    # Ensure interim daily.parquet is there for VWAP audit
    if [[ -f "${LOCAL_ROOT}/data/interim/daily.parquet" ]]; then
        rsync -avz \
            "${LOCAL_ROOT}/data/interim/daily.parquet" \
            "${CLUSTER_USER}@${CLUSTER_HOST}:${CLUSTER_ROOT}/data/interim/"
    fi
    echo "[push] OK."
}

setup() {
    # Runs on the cluster.
    echo "[setup] bootstrapping venv ..."
    bash "${HOME}/Fin_Tech/HW1/src/taq/cluster/setup_venv.sh"
}

submit() {
    echo "[submit] aggregate.slurm + build_panel.slurm (chained)"
    # Submit array aggregation first and chain panel build on afterok
    # Capture the aggregation job ID for the dependency.
    ${SSH} bash -l << 'EOF'
set -euo pipefail
cd ~/Fin_Tech/HW1
mkdir -p logs

# Submit aggregation array.
agg_out=$(sbatch src/taq/cluster/aggregate.slurm)
echo "  ${agg_out}"
agg_id=$(echo "${agg_out}" | awk '{print $NF}')

# Submit panel build with dependency on the whole array.
panel_out=$(sbatch --dependency=afterok:${agg_id} src/taq/cluster/build_panel.slurm)
echo "  ${panel_out}"

echo
echo "Queue:"
squeue -u $USER -o "%.10i %.20j %.12T %.5D %.10M %.9l %R"
EOF
}

status() {
    echo "[status] queue + recent logs"
    ${SSH} bash -l << 'EOF'
set -e
cd ~/Fin_Tech/HW1
echo "--- squeue ---"
squeue -u $USER -o "%.12i %.20j %.12T %.10M %.9l %R"
echo
echo "--- out/ ---"
ls -la out/ 2>/dev/null || echo "  (no out/ yet)"
echo
echo "--- logs/ (last 30 lines of most recent) ---"
latest=$(ls -t logs/*.out 2>/dev/null | head -1)
if [[ -n "${latest}" ]]; then
    echo "file: ${latest}"
    tail -30 "${latest}"
fi
EOF
}

pull() {
    echo "[pull] rsync summaries back → ${LOCAL_ROOT}/data/interim/taq_summaries/"
    mkdir -p "${LOCAL_ROOT}/data/interim/taq_summaries"
    rsync -avz \
        "${CLUSTER_USER}@${CLUSTER_HOST}:${CLUSTER_ROOT}/out/taq_summaries/" \
        "${LOCAL_ROOT}/data/interim/taq_summaries/"
    echo "[pull] OK. Contents:"
    ls -la "${LOCAL_ROOT}/data/interim/taq_summaries/"
}

all() {
    push
    submit
    echo
    echo "Next steps:"
    echo "  bash src/taq/cluster/run_pipeline.sh status     # check queue"
    echo "  bash src/taq/cluster/run_pipeline.sh pull       # when done"
}

# --------------------------------------------------------------------------- #
# Dispatch                                                                    #
# --------------------------------------------------------------------------- #

cmd="${1:-}"
case "${cmd}" in
    push)   push ;;
    setup)  setup ;;
    submit) submit ;;
    status) status ;;
    pull)   pull ;;
    all)    all ;;
    *)
        echo "usage: bash $0 {push|setup|submit|status|pull|all}"
        echo "  push   : rsync code + reference data up"
        echo "  setup  : (run on cluster) build project venv"
        echo "  submit : launch aggregate+build_panel SLURM chain"
        echo "  status : show queue + tail most recent log"
        echo "  pull   : rsync summaries down"
        echo "  all    : push + submit"
        exit 1
        ;;
esac
