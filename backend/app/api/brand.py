from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from ..db import get_session
from ..models import BrandProfile, Project
from ..schemas import BrandProfileCreate, BrandProfileRead, BrandProfileUpdate

router = APIRouter(prefix="/api/brand-profiles", tags=["brand"])


@router.get("", response_model=list[BrandProfileRead])
def list_brands(session: Session = Depends(get_session)) -> list[BrandProfileRead]:
    brands = session.exec(select(BrandProfile).order_by(BrandProfile.created_at)).all()
    return [BrandProfileRead.model_validate(brand) for brand in brands]


@router.post("", response_model=BrandProfileRead, status_code=201)
def create_brand(
    payload: BrandProfileCreate, session: Session = Depends(get_session)
) -> BrandProfileRead:
    brand = BrandProfile(**payload.model_dump())
    session.add(brand)
    session.commit()
    session.refresh(brand)
    return BrandProfileRead.model_validate(brand)


@router.get("/{brand_id}", response_model=BrandProfileRead)
def get_brand(brand_id: str, session: Session = Depends(get_session)) -> BrandProfileRead:
    brand = session.get(BrandProfile, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand profile not found")
    return BrandProfileRead.model_validate(brand)


@router.patch("/{brand_id}", response_model=BrandProfileRead)
def update_brand(
    brand_id: str,
    payload: BrandProfileUpdate,
    session: Session = Depends(get_session),
) -> BrandProfileRead:
    brand = session.get(BrandProfile, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand profile not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(brand, field, value)
    brand.updated_at = datetime.now(UTC)
    session.add(brand)
    session.commit()
    session.refresh(brand)
    return BrandProfileRead.model_validate(brand)


@router.delete("/{brand_id}")
def delete_brand(brand_id: str, session: Session = Depends(get_session)) -> dict:
    brand = session.get(BrandProfile, brand_id)
    if not brand:
        raise HTTPException(status_code=404, detail="Brand profile not found")
    projects = session.exec(select(Project).where(Project.brand_profile_id == brand_id)).all()
    for project in projects:
        project.brand_profile_id = None
        project.updated_at = datetime.now(UTC)
        session.add(project)
    session.delete(brand)
    session.commit()
    return {"deleted": True, "brand_id": brand_id}
