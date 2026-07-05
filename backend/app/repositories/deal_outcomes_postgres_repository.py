"""PostgreSQL repository for deal outcomes (win/loss reason tracking)."""

from datetime import datetime, timezone
from uuid import uuid4

from app.db.connection import get_cursor


def _generate_id() -> str:
    return str(uuid4())


def _row_to_dict(row) -> dict:
    d = dict(row)
    for key in ("created_at", "updated_at"):
        if d.get(key) and isinstance(d[key], datetime):
            d[key] = d[key].isoformat()
    return d


class DealOutcomesPostgresRepository:
    """PostgreSQL repository for deal_outcomes table."""

    def list_all(self) -> list[dict]:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM deal_outcomes ORDER BY created_at DESC")
            return [_row_to_dict(r) for r in cur.fetchall()]

    def get_by_id(self, outcome_id: str) -> dict | None:
        with get_cursor() as cur:
            cur.execute("SELECT * FROM deal_outcomes WHERE id = %s", (outcome_id,))
            row = cur.fetchone()
            return _row_to_dict(row) if row else None

    def get_by_lead_id(self, lead_id: str) -> dict | None:
        """Get the most recent outcome for a lead."""
        with get_cursor() as cur:
            cur.execute(
                "SELECT * FROM deal_outcomes WHERE lead_id = %s ORDER BY created_at DESC LIMIT 1",
                (lead_id,),
            )
            row = cur.fetchone()
            return _row_to_dict(row) if row else None

    def create(self, data: dict) -> dict:
        outcome_id = data.get("id", _generate_id())
        now = datetime.now(timezone.utc)
        with get_cursor() as cur:
            cur.execute(
                """INSERT INTO deal_outcomes
                   (id, lead_id, outcome, reason_category, reason_text, competitor_name, created_at, updated_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    outcome_id,
                    data["lead_id"],
                    data["outcome"],
                    data.get("reason_category", ""),
                    data.get("reason_text"),
                    data.get("competitor_name"),
                    now,
                    now,
                ),
            )
        return self.get_by_id(outcome_id)

    def update(self, outcome_id: str, data: dict) -> dict | None:
        updatable = ("reason_category", "reason_text", "competitor_name")
        fields = [k for k in updatable if k in data]
        if not fields:
            return self.get_by_id(outcome_id)

        set_clauses = [f"{f} = %s" for f in fields]
        set_clauses.append("updated_at = %s")
        values = [data[f] for f in fields]
        values.append(datetime.now(timezone.utc))

        with get_cursor() as cur:
            cur.execute(
                f"UPDATE deal_outcomes SET {', '.join(set_clauses)} WHERE id = %s",
                values + [outcome_id],
            )
        return self.get_by_id(outcome_id)

    def delete(self, outcome_id: str) -> bool:
        with get_cursor() as cur:
            cur.execute("DELETE FROM deal_outcomes WHERE id = %s", (outcome_id,))
            return cur.rowcount > 0

    def get_analytics(self) -> dict:
        """Get win/loss analytics summary."""
        with get_cursor() as cur:
            # Total won/lost
            cur.execute("""SELECT outcome, COUNT(*) as count
                   FROM deal_outcomes GROUP BY outcome""")
            outcome_counts = {row["outcome"]: row["count"] for row in cur.fetchall()}
            total_won = outcome_counts.get("won", 0)
            total_lost = outcome_counts.get("lost", 0)
            total = total_won + total_lost
            win_rate = round((total_won / total * 100), 1) if total > 0 else 0.0

            # Top win reasons
            cur.execute("""SELECT reason_category, COUNT(*) as count
                   FROM deal_outcomes WHERE outcome = 'won'
                   GROUP BY reason_category ORDER BY count DESC LIMIT 3""")
            top_win_reasons = [
                {"reason": r["reason_category"], "count": r["count"]}
                for r in cur.fetchall()
            ]

            # Top loss reasons
            cur.execute("""SELECT reason_category, COUNT(*) as count
                   FROM deal_outcomes WHERE outcome = 'lost'
                   GROUP BY reason_category ORDER BY count DESC LIMIT 3""")
            top_loss_reasons = [
                {"reason": r["reason_category"], "count": r["count"]}
                for r in cur.fetchall()
            ]

            # Competitor mentions
            cur.execute("""SELECT competitor_name, COUNT(*) as count
                   FROM deal_outcomes
                   WHERE competitor_name IS NOT NULL AND competitor_name != ''
                   GROUP BY competitor_name ORDER BY count DESC LIMIT 5""")
            competitor_mentions = [
                {"name": r["competitor_name"], "count": r["count"]}
                for r in cur.fetchall()
            ]

            return {
                "total_won": total_won,
                "total_lost": total_lost,
                "win_rate": win_rate,
                "top_win_reasons": top_win_reasons,
                "top_loss_reasons": top_loss_reasons,
                "competitor_mentions": competitor_mentions,
            }
