"""Schema introspection via the system catalogs."""

from dataclasses import dataclass, field

import psycopg

# Types whose values are interpretable. Skips identifiers and raw measurements.
_SAMPLEABLE = {"text", "character varying", "character", "date", "boolean"}

# Past this, the column is essentially an identifier — three random values
# teach nothing useful.
_MAX_DISTINCT = 50


@dataclass
class Column:
    name: str
    data_type: str
    nullable: bool
    is_primary_key: bool = False
    sample_values: list[str] = field(default_factory=list)


@dataclass
class ForeignKey:
    column: str
    references_table: str
    references_column: str


@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)
    row_estimate: int = 0

    @property
    def primary_key(self) -> list[str]:
        return [c.name for c in self.columns if c.is_primary_key]


def _fetch_columns(conn: psycopg.Connection, schema: str) -> dict[str, list[Column]]:
    query = """
        SELECT table_name, column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = %s
        ORDER BY table_name, ordinal_position
    """
    columns: dict[str, list[Column]] = {}
    with conn.cursor() as cur:
        cur.execute(query, (schema,))
        for table_name, column_name, data_type, is_nullable in cur.fetchall():
            columns.setdefault(table_name, []).append(
                Column(name=column_name, data_type=data_type, nullable=is_nullable == "YES")
            )
    return columns


def _fetch_primary_keys(conn: psycopg.Connection, schema: str) -> dict[str, set[str]]:
    # pg_index rather than information_schema — fewer joins
    query = """
        SELECT cls.relname, att.attname
        FROM pg_index idx
        JOIN pg_class cls ON cls.oid = idx.indrelid
        JOIN pg_namespace ns ON ns.oid = cls.relnamespace
        JOIN pg_attribute att
             ON att.attrelid = cls.oid AND att.attnum = ANY(idx.indkey)
        WHERE idx.indisprimary AND ns.nspname = %s
    """
    keys: dict[str, set[str]] = {}
    with conn.cursor() as cur:
        cur.execute(query, (schema,))
        for table_name, column_name in cur.fetchall():
            keys.setdefault(table_name, set()).add(column_name)
    return keys


def _fetch_foreign_keys(conn: psycopg.Connection, schema: str) -> dict[str, list[ForeignKey]]:
    # unnest WITH ORDINALITY to handle composite FKs
    query = """
        SELECT
            src_cls.relname, src_att.attname,
            tgt_cls.relname, tgt_att.attname
        FROM pg_constraint con
        JOIN pg_class src_cls ON src_cls.oid = con.conrelid
        JOIN pg_class tgt_cls ON tgt_cls.oid = con.confrelid
        JOIN pg_namespace ns ON ns.oid = src_cls.relnamespace
        JOIN unnest(con.conkey)  WITH ORDINALITY AS sk(attnum, ord) ON true
        JOIN unnest(con.confkey) WITH ORDINALITY AS tk(attnum, ord) ON tk.ord = sk.ord
        JOIN pg_attribute src_att
             ON src_att.attrelid = con.conrelid AND src_att.attnum = sk.attnum
        JOIN pg_attribute tgt_att
             ON tgt_att.attrelid = con.confrelid AND tgt_att.attnum = tk.attnum
        WHERE con.contype = 'f' AND ns.nspname = %s
    """
    fks: dict[str, list[ForeignKey]] = {}
    with conn.cursor() as cur:
        cur.execute(query, (schema,))
        for source_table, source_column, target_table, target_column in cur.fetchall():
            fks.setdefault(source_table, []).append(
                ForeignKey(
                    column=source_column,
                    references_table=target_table,
                    references_column=target_column,
                )
            )
    return fks


def _fetch_row_estimates(conn: psycopg.Connection, schema: str) -> dict[str, int]:
    query = """
        SELECT cls.relname, GREATEST(cls.reltuples, 0)::bigint
        FROM pg_class cls
        JOIN pg_namespace ns ON ns.oid = cls.relnamespace
        WHERE ns.nspname = %s AND cls.relkind = 'r'
    """
    with conn.cursor() as cur:
        cur.execute(query, (schema,))
        return {name: count for name, count in cur.fetchall()}


def _fetch_samples(
    conn: psycopg.Connection,
    schema: str,
    tables: list[Table],
    per_column: int = 3,
) -> None:
    """Fills sample_values on low-cardinality columns."""
    with conn.cursor() as cur:
        for table in tables:
            if table.row_estimate == 0:
                continue
            for column in table.columns:
                if column.data_type not in _SAMPLEABLE or column.is_primary_key:
                    continue

                cur.execute(
                    f"""
                    SELECT count(*) FROM (
                        SELECT DISTINCT "{column.name}"
                        FROM "{schema}"."{table.name}"
                        WHERE "{column.name}" IS NOT NULL
                        LIMIT {_MAX_DISTINCT + 1}
                    ) t
                    """
                )
                row = cur.fetchone()
                if row is None or row[0] > _MAX_DISTINCT:
                    continue

                cur.execute(
                    f"""
                    SELECT DISTINCT left("{column.name}"::text, 40)
                    FROM "{schema}"."{table.name}"
                    WHERE "{column.name}" IS NOT NULL
                    ORDER BY 1
                    LIMIT {per_column}
                    """
                )
                column.sample_values = [r[0] for r in cur.fetchall()]


def introspect(
    conn: psycopg.Connection,
    schema: str = "public",
    with_samples: bool = True,
) -> list[Table]:
    columns = _fetch_columns(conn, schema)
    primary_keys = _fetch_primary_keys(conn, schema)
    foreign_keys = _fetch_foreign_keys(conn, schema)
    row_estimates = _fetch_row_estimates(conn, schema)

    tables: list[Table] = []
    for table_name, table_columns in sorted(columns.items()):
        pk_names = primary_keys.get(table_name, set())
        for column in table_columns:
            column.is_primary_key = column.name in pk_names

        tables.append(
            Table(
                name=table_name,
                columns=table_columns,
                foreign_keys=foreign_keys.get(table_name, []),
                row_estimate=row_estimates.get(table_name, 0),
            )
        )

    if with_samples:
        _fetch_samples(conn, schema, tables)

    return tables
