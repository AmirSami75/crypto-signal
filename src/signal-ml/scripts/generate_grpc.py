from __future__ import annotations

from pathlib import Path
import sys

from grpc_tools import protoc
import grpc_tools


def main() -> int:
    ml_root = Path(__file__).resolve().parents[1]
    repository_root = ml_root.parents[1]
    contracts_root = repository_root / "contracts"
    source_root = ml_root / "src"
    protobuf_include = Path(grpc_tools.__file__).resolve().parent / "_proto"
    contract = (
        contracts_root
        / "crypto_signal_engine"
        / "contracts"
        / "v1"
        / "ml_engine.proto"
    )
    arguments = [
        "grpc_tools.protoc",
        f"--proto_path={contracts_root}",
        f"--proto_path={protobuf_include}",
        f"--python_out={source_root}",
        f"--pyi_out={source_root}",
        f"--grpc_python_out={source_root}",
        str(contract),
    ]
    return protoc.main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
