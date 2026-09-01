# AILIZA — Schema-Konfliktbericht

Stand: 30.08.2026

## Ergebnis

Der frühere Konflikt zwischen Laufzeit-Schema und Migrationen ist technisch
abgesichert. Für den aktuellen Code gilt:

1. `apps/backend/db_schema.py` enthält das lebende SQLAlchemy-Metadatenmodell.
2. `apps/backend/alembic/versions/` enthält die nachvollziehbare
   Migrationshistorie für Deployments.
3. `apps/backend/alembic/env.py` verwendet dasselbe `metadata_obj` als
   Vergleichsziel.
4. `apps/backend/alembic_adopt.py` prüft bestehende Datenbanken zunächst gegen
   die unveränderliche Baseline und anschließend gegen das lebende Metadatenmodell.
5. Der Drift-Guard erkennt fehlende Tabellen, Spalten, Indizes und
   Unique-Constraints; PR #111 ergänzte insbesondere die Constraint-Prüfung.

## Arbeitsregel

- Neue Schemaänderungen beginnen in `db_schema.py` und erhalten eine passende
  Alembic-Migration sowie Drift-/Migrations-Tests.
- `metadata_obj.create_all()` ist kein Ersatz für eine Produktionsmigration.
- Bestehende Produktionsdatenbanken werden vor `alembic upgrade head` mit dem
  dokumentierten Adopt-/Drift-Verfahren geprüft.
- Eine Migration darf ihre Baseline nicht dynamisch aus dem neuesten
  Metadatenmodell ableiten.

## Noch offen

Dieser Bericht entscheidet nicht, ob Root-Dokumente oder `docs/` künftig die
fachliche Regelquelle bilden. Das ist weiterhin eine Owner-Entscheidung. Der
technische Schema-Ist-Stand ist davon unabhängig durch Code und Tests belegt.
