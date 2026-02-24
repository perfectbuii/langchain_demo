#!/usr/bin/env bash
# setup.sh — one-time project bootstrap

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "==> Creating virtualenv..."
python3 -m venv .venv
source .venv/bin/activate

echo "==> Installing Python dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "==> Generating Python gRPC stubs from source_of_truth/account.proto..."
mkdir -p agent/grpc_stubs
[ -f agent/grpc_stubs/__init__.py ] || touch agent/grpc_stubs/__init__.py
python -m grpc_tools.protoc \
  -I source_of_truth \
  --python_out=agent/grpc_stubs \
  --grpc_python_out=agent/grpc_stubs \
  source_of_truth/account.proto

echo "==> Fixing relative import in generated grpc stub..."
sed -i.bak 's/^import account_pb2 as/from agent.grpc_stubs import account_pb2 as/' \
  agent/grpc_stubs/account_pb2_grpc.py && rm -f agent/grpc_stubs/account_pb2_grpc.py.bak

echo ""
echo "Setup complete. Before running the agent:"
echo "  1. Copy .env.example → .env and add your OPENAI_API_KEY"
echo "  2. Start the Go server:   cd server && go run ."
echo "  3. Activate env:          source .venv/bin/activate"
echo "  4. Run the agent:         python -m agent.main"
