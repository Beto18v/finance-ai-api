from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user_id
from app.database.session import get_db
from app.schemas.ingestion import (
    CsvImportCreate,
    ImportCapabilitiesRead,
    ImportItemUpdate,
    ImportSessionListItemRead,
    ImportSessionRead,
)
from app.services.ingestion_service import (
    commit_import_session,
    create_csv_import_session,
    get_import_capabilities,
    get_import_session,
    list_import_sessions,
    update_import_item,
)
from app.services.user_service import ensure_active_user

router = APIRouter(prefix="/ingestion", tags=["Ingestion"])


@router.get("/import-capabilities", response_model=ImportCapabilitiesRead)
def get_import_capabilities_endpoint(
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return get_import_capabilities()


@router.get("/imports", response_model=list[ImportSessionListItemRead])
def list_import_sessions_endpoint(
    user_id=Depends(get_current_user_id),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return list_import_sessions(db, user_id, limit=limit)


@router.get("/imports/{import_session_id}", response_model=ImportSessionRead)
def get_import_session_endpoint(
    import_session_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return get_import_session(db, user_id, import_session_id)


@router.post("/imports/csv", response_model=ImportSessionRead)
def create_csv_import_session_endpoint(
    payload: CsvImportCreate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return create_csv_import_session(db, user_id, payload)


@router.patch(
    "/imports/{import_session_id}/items/{item_id}",
    response_model=ImportSessionRead,
)
def update_import_item_endpoint(
    import_session_id: UUID,
    item_id: UUID,
    payload: ImportItemUpdate,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return update_import_item(
        db,
        user_id,
        import_session_id,
        item_id,
        payload,
    )


@router.post("/imports/{import_session_id}/commit", response_model=ImportSessionRead)
def commit_import_session_endpoint(
    import_session_id: UUID,
    user_id=Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    ensure_active_user(db, user_id)
    return commit_import_session(db, user_id, import_session_id)
