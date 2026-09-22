# Roadmap: Später (nach 1.4, nicht 1.0)

## Wissen/RAG (nach 1.4)

1. Hybrid-Suche auf knowledge_chunks: BM25 (exakte Wörter, z. B. Artikelnummern) + Embeddings (Bedeutung), zusammengeführt per Reciprocal Rank Fusion.
2. Suchleiter mit Beleg-Pflicht: ohne Beleg antwortet die KI "nicht gefunden", nichts erfinden (fail-closed). Keine Fremd-Plugins.
3. Geschäftsdaten (Rechnungen, Kunden, Artikel) per fester DB-Abfrage beantworten, nicht per RAG. RAG nur für Texte.
4. Rechte (Mandant, Sichtbarkeit, Ablauf) vor der Suche in der Abfrage prüfen, nicht danach filtern.
5. Qualitätsmessung: ca. 30 Testfragen mit richtigen Antworten, jede Suchänderung muss sie bestehen.
6. Reranker (lokal), Schneiden nach Abschnitten mit Kontextsatz, Quellenangabe Pflicht.
7. Keine zweite Datenbank: SQLite FTS5 + sqlite-vec, PostgreSQL tsvector + pgvector.
