from sqlmodel import Session

from app.db.session import engine
from app.services.indexing_service import IndexingService
from app.services.retrieval_service import RetrievalService


if __name__ == '__main__':
    retrieval = RetrievalService()
    service = IndexingService(retrieval_service=retrieval)
    with Session(engine) as session:
        result = service.rebuild(db=session)
    print(result.model_dump_json(indent=2, ensure_ascii=False))
