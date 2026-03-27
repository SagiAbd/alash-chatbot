from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class KnowledgeBaseBase(BaseModel):
    name: str
    description: Optional[str] = None


class KnowledgeBaseCreate(KnowledgeBaseBase):
    pass


class KnowledgeBaseUpdate(KnowledgeBaseBase):
    pass


class DocumentBase(BaseModel):
    file_name: str
    file_path: str
    file_hash: str
    file_size: int
    content_type: str


class DocumentCreate(DocumentBase):
    knowledge_base_id: int


class DocumentUploadBase(BaseModel):
    file_name: str
    file_hash: str
    file_size: int
    content_type: str
    temp_path: str
    status: str = "pending"
    error_message: Optional[str] = None


class DocumentUploadCreate(DocumentUploadBase):
    knowledge_base_id: int


class DocumentUploadResponse(DocumentUploadBase):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True


class ProcessingTaskBase(BaseModel):
    status: str
    error_message: Optional[str] = None


class ProcessingTaskCreate(ProcessingTaskBase):
    document_id: int
    knowledge_base_id: int


class ProcessingTask(ProcessingTaskBase):
    id: int
    document_id: int
    knowledge_base_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DocumentResponse(DocumentBase):
    id: int
    knowledge_base_id: int
    created_at: datetime
    updated_at: datetime
    processing_tasks: List[ProcessingTask] = []
    analysis: Optional[dict] = None

    class Config:
        from_attributes = True


class KnowledgeBaseResponse(KnowledgeBaseBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime
    documents: List[DocumentResponse] = []

    class Config:
        from_attributes = True
