"""Keep the original indexing command available for existing deployments."""

from app.RAG.ingestion.index_vehicle_knowledge import main


if __name__ == "__main__":
    main()
