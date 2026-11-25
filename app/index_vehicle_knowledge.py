from dotenv import load_dotenv

from app.repositories.chroma_vehicle_knowledge import ChromaKnowledgeError, ChromaVehicleKnowledge
from app.repositories.vehicle_knowledge import VehicleKnowledge
from app.services.embedding_service import EmbeddingError


def main():
    load_dotenv()
    try:
        knowledge = ChromaVehicleKnowledge(VehicleKnowledge().all_entries())
        count = knowledge.build()
    except (ChromaKnowledgeError, EmbeddingError, OSError, ValueError) as exc:
        raise SystemExit(f"Vehicle evidence indexing failed. {exc}") from None
    print(f"Indexed {count} records in {knowledge.collection_name}.")


if __name__ == "__main__":
    main()
