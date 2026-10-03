"""Protect forecast and outcome rows against update or deletion.

Database administrators can still alter triggers; this is append-only application
storage, not a cryptographically tamper-proof external archive.
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for table in ("forecasts", "forecast_outcomes"):
            for action in ("UPDATE", "DELETE"):
                op.execute(
                    f"CREATE TRIGGER protect_{table}_{action.lower()} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT, 'Forecast ledger is append-only'); END"
                )
    elif dialect == "postgresql":
        op.execute(
            "CREATE FUNCTION trendforge_immutable_ledger() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'Forecast ledger is append-only'; END; $$ LANGUAGE plpgsql"
        )
        for table in ("forecasts", "forecast_outcomes"):
            op.execute(
                f"CREATE TRIGGER protect_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION trendforge_immutable_ledger()"
            )


def downgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        for table in ("forecasts", "forecast_outcomes"):
            for action in ("update", "delete"):
                op.execute(f"DROP TRIGGER protect_{table}_{action}")
    elif dialect == "postgresql":
        for table in ("forecasts", "forecast_outcomes"):
            op.execute(f"DROP TRIGGER protect_{table} ON {table}")
        op.execute("DROP FUNCTION trendforge_immutable_ledger()")
