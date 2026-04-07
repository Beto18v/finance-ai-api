import importlib.util
from pathlib import Path

import pytest


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "a1b2c3d4e5f6_add_balance_direction_for_ledger.py"
)

spec = importlib.util.spec_from_file_location(
    "ledger_balance_direction_migration",
    MIGRATION_PATH,
)
assert spec is not None
assert spec.loader is not None
migration = importlib.util.module_from_spec(spec)
spec.loader.exec_module(migration)


def test_detected_legacy_rows_raise_clear_error():
    with pytest.raises(
        RuntimeError,
        match="legacy transfer/adjustment rows created before M1",
    ):
        migration._raise_for_detected_legacy_ledger_rows(
            [
                {
                    "id": "tx-transfer",
                    "transaction_type": "transfer",
                    "transfer_group_id": "group-1",
                },
                {
                    "id": "tx-adjustment",
                    "transaction_type": "adjustment",
                    "transfer_group_id": None,
                },
            ]
        )


def test_detected_legacy_rows_error_lists_examples():
    with pytest.raises(RuntimeError) as error:
        migration._raise_for_detected_legacy_ledger_rows(
            [
                {
                    "id": "tx-transfer",
                    "transaction_type": "transfer",
                    "transfer_group_id": "group-1",
                },
                {
                    "id": "tx-adjustment",
                    "transaction_type": "adjustment",
                    "transfer_group_id": None,
                },
            ]
        )

    assert "tx-transfer (transfer group group-1)" in str(error.value)
    assert "tx-adjustment (adjustment)" in str(error.value)


def test_detected_legacy_rows_allows_empty_input():
    migration._raise_for_detected_legacy_ledger_rows([])
