from typing import Generic, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = Field(default=0, description="响应码，0 表示成功，非 0 表示失败")
    message: str = Field(default="success", description="响应信息")
    data: Optional[T] = Field(default=None, description="响应数据")


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1, description="页码，从 1 开始")
    page_size: int = Field(default=10, ge=1, le=100, description="每页条数")


class PageData(BaseModel, Generic[T]):
    items: List[T] = Field(description="当前页数据列表")
    total: int = Field(description="总条数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页条数")
    total_pages: int = Field(description="总页数")


def ok(data: Optional[T] = None, message: str = "success") -> ApiResponse[T]:
    return ApiResponse[T](code=0, message=message, data=data)


def fail(code: int = 400, message: str = "Bad Request") -> ApiResponse[None]:
    return ApiResponse[None](code=code, message=message, data=None)


def page_data(
    items: List[T],
    total: int,
    page: int,
    page_size: int,
) -> PageData[T]:
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return PageData[T](
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
