from datetime import datetime, timezone


def create_configured_user(client):
    return client.post(
        "/users/",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "base_currency": "COP",
            "timezone": "UTC",
        },
    )


def test_import_capabilities_expose_supported_headers(client):
    created_user = create_configured_user(client)
    assert created_user.status_code == 200

    response = client.get("/ingestion/import-capabilities")
    assert response.status_code == 200

    data = response.json()
    assert data["max_rows"] == 1000
    assert "date" in data["required_fields"]
    assert "fecha" in data["required_fields"]["date"]
    assert "amount" in data["required_fields"]["amount"]
    assert "description" in data["optional_fields"]
    assert "category" in data["optional_fields"]
    assert "ingreso" in data["type_aliases"]
    assert "gasto" in data["type_aliases"]


def test_create_csv_import_session_classifies_rows_and_reconciles_duplicates(client):
    created_user = create_configured_user(client)
    assert created_user.status_code == 200

    income_category = client.post(
        "/categories/",
        json={"name": "Salary", "direction": "income", "parent_id": None},
    )
    assert income_category.status_code == 200

    expense_category = client.post(
        "/categories/",
        json={"name": "Food", "direction": "expense", "parent_id": None},
    )
    assert expense_category.status_code == 200

    existing_transaction = client.post(
        "/transactions/",
        json={
            "category_id": expense_category.json()["id"],
            "amount": "12.50",
            "currency": "COP",
            "description": "Lunch",
            "occurred_at": "2026-03-05T12:00:00Z",
        },
    )
    assert existing_transaction.status_code == 200

    preview = client.post(
        "/ingestion/imports/csv",
        json={
            "file_name": "bank.csv",
            "csv_content": (
                "fecha;descripcion;debito;credito;categoria\n"
                "05/03/2026;Lunch;12,50;;Food\n"
                "06/03/2026;Payroll;;1500,00;\n"
                "07/03/2026;Coffee;5,00;;Food\n"
                "07/03/2026;Coffee;5,00;;Food\n"
                "08/03/2026;Mystery;8,00;;Unknown\n"
            ),
            "default_income_category_id": income_category.json()["id"],
            "default_expense_category_id": expense_category.json()["id"],
        },
    )
    assert preview.status_code == 200

    data = preview.json()
    assert data["file_name"] == "bank.csv"
    assert data["analysis"] == {
        "source_headers": [
            "fecha",
            "descripcion",
            "debito",
            "credito",
            "categoria",
        ],
        "detected_columns": {
            "date": "fecha",
            "description": "descripcion",
            "debit": "debito",
            "credit": "credito",
            "category": "categoria",
        },
    }
    assert data["summary"] == {
        "total_rows": 5,
        "ready_count": 2,
        "needs_review_count": 1,
        "duplicate_count": 2,
        "ignored_count": 0,
        "imported_count": 0,
    }

    row_by_index = {item["row_index"]: item for item in data["items"]}
    assert row_by_index[1]["status"] == "duplicate"
    assert row_by_index[1]["duplicate_transaction"]["id"] == existing_transaction.json()["id"]
    assert row_by_index[2]["status"] == "ready"
    assert row_by_index[2]["category_id"] == income_category.json()["id"]
    assert row_by_index[3]["status"] == "ready"
    assert row_by_index[3]["category_id"] == expense_category.json()["id"]
    assert row_by_index[4]["status"] == "duplicate"
    assert row_by_index[4]["duplicate_transaction"] is None
    assert row_by_index[5]["status"] == "needs_review"
    assert row_by_index[5]["status_reason"] == 'Category "Unknown" was not found'


def test_import_items_can_be_reviewed_ignored_and_committed_to_ledger(client):
    created_user = create_configured_user(client)
    assert created_user.status_code == 200

    income_category = client.post(
        "/categories/",
        json={"name": "Salary", "direction": "income", "parent_id": None},
    )
    assert income_category.status_code == 200

    expense_category = client.post(
        "/categories/",
        json={"name": "Food", "direction": "expense", "parent_id": None},
    )
    assert expense_category.status_code == 200

    preview = client.post(
        "/ingestion/imports/csv",
        json={
            "file_name": "statement.csv",
            "csv_content": (
                "date,description,amount\n"
                "2026-03-10,Consulting,+500.00\n"
                "2026-03-11,Snacks,-10.00\n"
                "2026-03-12,Taxi,-15.00\n"
            ),
            "default_income_category_id": income_category.json()["id"],
        },
    )
    assert preview.status_code == 200

    session = preview.json()
    session_id = session["id"]
    assert session["analysis"] == {
        "source_headers": ["date", "description", "amount"],
        "detected_columns": {
            "date": "date",
            "amount": "amount",
            "description": "description",
        },
    }
    row_by_index = {item["row_index"]: item for item in session["items"]}

    assert row_by_index[1]["status"] == "ready"
    assert row_by_index[2]["status"] == "needs_review"
    assert row_by_index[3]["status"] == "needs_review"

    reviewed = client.patch(
        f"/ingestion/imports/{session_id}/items/{row_by_index[2]['id']}",
        json={"category_id": expense_category.json()["id"]},
    )
    assert reviewed.status_code == 200
    reviewed_rows = {item["row_index"]: item for item in reviewed.json()["items"]}
    assert reviewed_rows[2]["status"] == "ready"

    ignored = client.patch(
        f"/ingestion/imports/{session_id}/items/{row_by_index[3]['id']}",
        json={"ignored": True},
    )
    assert ignored.status_code == 200
    ignored_rows = {item["row_index"]: item for item in ignored.json()["items"]}
    assert ignored_rows[3]["status"] == "ignored"

    committed = client.post(f"/ingestion/imports/{session_id}/commit")
    assert committed.status_code == 200
    committed_data = committed.json()
    committed_rows = {item["row_index"]: item for item in committed_data["items"]}

    assert committed_data["summary"] == {
        "total_rows": 3,
        "ready_count": 0,
        "needs_review_count": 0,
        "duplicate_count": 0,
        "ignored_count": 1,
        "imported_count": 2,
    }
    assert committed_rows[1]["status"] == "imported"
    assert committed_rows[1]["imported_transaction"] is not None
    assert committed_rows[2]["status"] == "imported"
    assert committed_rows[2]["category_id"] == expense_category.json()["id"]
    assert committed_rows[3]["status"] == "ignored"

    transactions = client.get("/transactions/")
    assert transactions.status_code == 200
    assert transactions.json()["total_count"] == 2
    descriptions = {item["description"] for item in transactions.json()["items"]}
    assert descriptions == {"Consulting", "Snacks"}
