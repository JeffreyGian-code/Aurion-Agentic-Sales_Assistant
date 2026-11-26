`app/RAG` takes a buyer’s preferences, finds relevant vehicle evidence, checks it against the inventory, and gives the assistant a ranked shortlist. It has two flows: **indexing** prepares the evidence in Chroma, and **recommendation** searches that evidence when a buyer asks a question.

## 1. `documents/` — Source material

| File | Responsibility |
|---|---|
| [vehicle_knowledge.md](/D:/workspace/playground/Agentic-Vehicle-Sales-Assistant-/app/RAG/documents/vehicle_knowledge.md) | Contains the guide to 200 seeded variants and the manufacturer feature comparisons. The indexer reads the **16 rows in the recommendation evidence table** at the bottom. Each row has a vehicle ID, trim identity, topic, evidence strength, reason, and source. |
| [vehicles.json](/D:/workspace/playground/Agentic-Vehicle-Sales-Assistant-/app/RAG/documents/vehicles.json) | Contains five sample vehicle records. The current RAG pipeline has no reader for this file. Vehicle IDs, prices, and inventory filters come from PostgreSQL. |

This distinction matters when editing the knowledge base. Adding a sunroof comparison to the guide makes it visible to someone reading the Markdown. It becomes searchable through RAG when it is represented in the evidence table and the index is rebuilt. A firm requirement such as “must have a sunroof” also needs `confirmed` evidence for the exact variant.

## 2. `ingestion/` — Read and validate the evidence

| File | Responsibility |
|---|---|
| [vehicle_knowledge.py](/D:/workspace/playground/Agentic-Vehicle-Sales-Assistant-/app/RAG/ingestion/vehicle_knowledge.py) | `VehicleKnowledge` reads the Markdown and turns table rows into `KnowledgeEntry` objects. It rejects conflicting IDs and duplicate topics for the same vehicle. It also defines `KnowledgeIndex`, the interface the recommendation service uses, and `verified_evidence()`, which checks that evidence matches the vehicle’s ID, brand, model, trim, and body type. |
| [index_vehicle_knowledge.py](/D:/workspace/playground/Agentic-Vehicle-Sales-Assistant-/app/RAG/ingestion/index_vehicle_knowledge.py) | The entry point for `python -m app.RAG.ingestion.index_vehicle_knowledge`. It loads configuration, reads the parsed entries, calls Chroma’s `build()` method, and reports how many records were indexed. |

## 3. `embeddings/` — Turn text into vectors

| File | Responsibility |
|---|---|
| [embedding_service.py](/D:/workspace/playground/Agentic-Vehicle-Sales-Assistant-/app/RAG/embeddings/embedding_service.py) | `OpenRouterEmbeddings` sends text to the configured embedding model and returns a vector of 2,048 numbers for each input. It checks the response order, vector size, and values. Indexing uses `passage` mode for evidence reasons. Retrieval uses `query` mode for buyer preferences. |

The embedding client generates vectors. Chroma handles storage and search.

## 4. `retrieval/` — Store and search the evidence

| File | Responsibility |
|---|---|
| [chroma_vehicle_knowledge.py](/D:/workspace/playground/Agentic-Vehicle-Sales-Assistant-/app/RAG/retrieval/chroma_vehicle_knowledge.py) | `build()` creates or reuses a collection for the current evidence revision. It stores each reason, its vector, and its metadata under an ID such as `41:parking`. `semantic_matches()` embeds a preference and searches by cosine similarity, optionally restricted to eligible vehicle IDs. `requirement_entries()` looks up exact topics marked `confirmed`. The retriever checks that the collection is complete before searching. |

Chroma persists the evidence vectors in the Docker volume `aurion_chroma_data`. PostgreSQL holds the vehicle inventory in a separate database. [Docker Compose](/D:/workspace/playground/Agentic-Vehicle-Sales-Assistant-/docker-compose.yml)

## 5. `recommendations/` — Decide what to show

| File | Responsibility |
|---|---|
| [recommendation_service.py](/D:/workspace/playground/Agentic-Vehicle-Sales-Assistant-/app/RAG/recommendations/recommendation_service.py) | `RecommendationService` applies inventory filters and firm requirements, asks the retriever for evidence, drops weak matches, and checks the vehicle identity against PostgreSQL. It ranks up to three vehicles by preference match, then price and ID, and returns the supporting reasons and sources. |

The root `app/RAG/__init__.py` and each code folder’s `__init__.py` mark Python packages and describe their purpose. They contain no pipeline logic. Outside `app/RAG`, [agent_tools.py](/D:/workspace/playground/Agentic-Vehicle-Sales-Assistant-/app/tools/agent_tools.py:32) connects the recommendation service to the assistant’s `recommend_vehicles` tool.

## How a request flows through the layers

For **“Show me a hatchback under ₹9 lakh that’s easy to park,”** the service first gets eligible hatchback IDs from PostgreSQL. It then embeds “easy to park” and asks Chroma for similar evidence tied to those IDs. When Chroma returns a match, the service checks that the evidence still belongs to that exact variant, ranks the candidates, and passes the shortlist and reasons back to the assistant.