.PHONY: setup proto proto-go install server run test clean

# ── Bootstrap ────────────────────────────────────────────────────────────────

setup:
	bash setup.sh

install:
	pip install -r requirements.txt

# Generate Python gRPC stubs (reads from source_of_truth/, outputs to agent/grpc_stubs/)
proto:
	mkdir -p agent/grpc_stubs
	@[ -f agent/grpc_stubs/__init__.py ] || touch agent/grpc_stubs/__init__.py
	python -m grpc_tools.protoc \
		-I source_of_truth \
		--python_out=agent/grpc_stubs \
		--grpc_python_out=agent/grpc_stubs \
		source_of_truth/account.proto
	@sed -i.bak 's/^import account_pb2 as/from agent.grpc_stubs import account_pb2 as/' \
		agent/grpc_stubs/account_pb2_grpc.py && rm -f agent/grpc_stubs/account_pb2_grpc.py.bak
	@echo "Python stubs generated in agent/grpc_stubs/"

# Generate Go gRPC stubs (reads from source_of_truth/, outputs to server/proto/account/)
proto-go:
	mkdir -p server/proto/account
	protoc \
		-I source_of_truth \
		--go_out=server/proto/account \
		--go_opt=paths=source_relative \
		--go-grpc_out=server/proto/account \
		--go-grpc_opt=paths=source_relative \
		source_of_truth/account.proto
	@echo "Go stubs regenerated in server/proto/account/"

# ── Server ────────────────────────────────────────────────────────────────────

server:
	cd server && go run .

# ── Agent ─────────────────────────────────────────────────────────────────────

run:
	python -m agent.main

run-service:
	python -m agent.main --service $(SERVICE) --scenario "$(SCENARIO)"

# Example: make run-service SERVICE=account SCENARIO="edge cases"

# ── Cleanup ───────────────────────────────────────────────────────────────────

clean:
	rm -rf reports/ __pycache__ agent/__pycache__ \
		agent/tools/__pycache__ agent/parsers/__pycache__ \
		agent/executor/__pycache__ agent/report/__pycache__ \
		agent/grpc_stubs/__pycache__
