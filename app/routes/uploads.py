"""/api/v1 下的分片上传接口（无 /api/v1 前缀）。"""

from typing import Optional

from fastapi import APIRouter, Body, Request, Response
from fastapi.responses import JSONResponse
from starlette import status

from app.constants.uploads import UPLOAD_STATUS_COMPLETED
from app.models.common import ApiResponse
from app.models.fs_entry import FsEntry
from app.models.upload_session import UploadSession
from app.routes.schemas.request import CompleteUploadRequest, InitUploadRequest
from app.routes.schemas.response import (
    ChunkUploadResponse,
    UploadSessionResponse,
    build_upload_session_response,
)
from app.utils.uploads import manager

router = APIRouter(tags=["uploads"])


@router.post("/files/uploads", status_code=status.HTTP_201_CREATED)
def initialize_upload(body: InitUploadRequest) -> ApiResponse[UploadSessionResponse]:
    """初始化分片上传会话。"""
    session: UploadSession = manager.create_upload_session(
        virtual_path=body.path,
        size=body.size,
        chunk_size=body.chunk_size,
        overwrite=body.overwrite,
        checksum_algorithm=_checksum_algorithm(body),
        checksum_value=_checksum_value(body),
    )
    return ApiResponse[UploadSessionResponse](data=build_upload_session_response(session))


@router.get("/files/uploads/{upload_id}", status_code=status.HTTP_200_OK)
def fetch_upload_status(upload_id: str) -> ApiResponse[UploadSessionResponse]:
    """查询上传状态，用于断点续传。"""
    session: UploadSession = manager.query_upload_session(upload_id)
    final_entry: Optional[FsEntry] = None
    if session.status == UPLOAD_STATUS_COMPLETED:
        final_entry = manager.build_final_entry(session.path)
    return ApiResponse[UploadSessionResponse](
        data=build_upload_session_response(session, final_entry)
    )


@router.put(
    "/files/uploads/{upload_id}/chunks/{chunk_number}",
    status_code=status.HTTP_200_OK,
)
def upload_chunk(
    upload_id: str,
    chunk_number: int,
    request: Request,
    content: bytes = Body(..., media_type="application/octet-stream"),
) -> ApiResponse[ChunkUploadResponse]:
    """上传单个分片（application/octet-stream）。"""
    content_md5: Optional[str] = request.headers.get("content-md5")
    chunk_sha256: Optional[str] = request.headers.get("x-chunk-sha256")

    session: UploadSession = manager.upload_chunk(
        upload_id=upload_id,
        chunk_number=chunk_number,
        content=content,
        content_md5=content_md5,
        chunk_sha256=chunk_sha256,
    )
    return ApiResponse[ChunkUploadResponse](
        data=ChunkUploadResponse(
            upload_id=session.upload_id,
            chunk_number=chunk_number,
            received_size=len(content),
            uploaded_chunks=len(session.uploaded_chunks),
            total_chunks=session.total_chunks,
            uploaded_bytes=session.uploaded_bytes,
            status=session.status,
        )
    )


@router.post(
    "/files/uploads/{upload_id}/complete",
    status_code=status.HTTP_201_CREATED,
)
def complete_upload(
    upload_id: str,
    body: Optional[CompleteUploadRequest] = Body(default=None),
) -> JSONResponse:
    """完成上传并合并分片；已完成会话重试返回 200。"""
    checksum_algorithm: Optional[str] = None
    checksum_value: Optional[str] = None
    if body is not None and body.checksum is not None:
        checksum_algorithm = body.checksum.algorithm
        checksum_value = body.checksum.value

    session, entry, already_completed = manager.complete_upload(
        upload_id=upload_id,
        checksum_algorithm=checksum_algorithm,
        checksum_value=checksum_value,
    )
    payload: dict = ApiResponse[FsEntry](data=entry).model_dump(by_alias=True)
    if already_completed:
        return JSONResponse(status_code=status.HTTP_200_OK, content=payload)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=payload)


@router.delete(
    "/files/uploads/{upload_id}", status_code=status.HTTP_204_NO_CONTENT
)
def cancel_upload(upload_id: str) -> Response:
    """取消上传并清理临时数据，操作幂等。"""
    manager.cancel_upload(upload_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _checksum_algorithm(body: InitUploadRequest) -> Optional[str]:
    """提取请求中的校验算法。"""
    if body.checksum is None:
        return None
    return body.checksum.algorithm


def _checksum_value(body: InitUploadRequest) -> Optional[str]:
    """提取请求中的校验值。"""
    if body.checksum is None:
        return None
    return body.checksum.value
