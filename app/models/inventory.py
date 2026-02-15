from pydantic import BaseModel, Field


class InventoryItem(BaseModel):
    name: str = Field(min_length=1, description="상품명")
    quantity: float = Field(gt=0, description="수량")
    unit: str = Field(min_length=1, description="단위")


class InventoryExtraction(BaseModel):
    items: list[InventoryItem]
