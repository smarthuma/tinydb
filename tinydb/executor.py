"""Query executor — catalog + heap + DML + WHERE + UPDATE/DELETE + aggregates.

Design references:
  - design.md D5 (catalog in header page)
  - design.md D6 (single-connection; no concurrency)
  - specs/query-executor/spec.md (REQ-QE-001..010)
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass

from tinydb import index, storage
from tinydb import types as tinydb_types
from tinydb.parser import ast as p


# === Catalog (T-5.1) =======================================================


@dataclass
class ColumnSchema:
    name: str
    type_name: str
    constraints: tuple[str, ...]

    @property
    def is_primary_key(self) -> bool:
        return "PRIMARY KEY" in self.constraints

    @property
    def is_not_null(self) -> bool:
        return "NOT NULL" in self.constraints

    @property
    def is_unique(self) -> bool:
        return "UNIQUE" in self.constraints or self.is_primary_key


@dataclass
class TableSchema:
    name: str
    columns: tuple[ColumnSchema, ...]
    first_data_page_id: int  # 0 if empty
    indexes: dict[str, int]  # column_name -> btree root_page_id


class _CatalogCodec:
    """Serialize catalog as JSON, store at body[8:] of header page (after magic+page_size)."""

    @staticmethod
    def serialize(tables: dict[str, TableSchema]) -> bytes:
        data = {}
        for name, schema in tables.items():
            data[name] = {
                "columns": [
                    {"name": c.name, "type": c.type_name, "constraints": list(c.constraints)}
                    for c in schema.columns
                ],
                "first_data_page_id": schema.first_data_page_id,
                "indexes": schema.indexes,
            }
        return json.dumps(data).encode("utf-8")

    @staticmethod
    def deserialize(raw: bytes) -> dict[str, TableSchema]:
        # Strip both leading and trailing NUL padding; if nothing left, catalog empty.
        stripped = raw.strip(b"\x00")
        if not stripped:
            return {}
        data = json.loads(stripped.decode("utf-8"))
        tables = {}
        for name, t in data.items():
            cols = tuple(
                ColumnSchema(c["name"], c["type"], tuple(c["constraints"]))
                for c in t["columns"]
            )
            tables[name] = TableSchema(
                name=name, columns=cols,
                first_data_page_id=t["first_data_page_id"],
                indexes=t["indexes"],
            )
        return tables


class Catalog:
    """In-memory mirror of the catalog, persisted in the header page body."""

    def __init__(self, store: storage.FileStore) -> None:
        self._store = store
        page = store.read_page(0)  # header page is always page 0
        body_after_magic = page.body[8 + 4:]  # skip magic(8) + page_size(4)
        self._tables = _CatalogCodec.deserialize(body_after_magic)

    def flush(self) -> None:
        page = self._store.read_page(0)
        # Preserve magic(8) + page_size(4); rewrite body[12:] with catalog
        prefix = page.body[:12]
        new_body = prefix + _CatalogCodec.serialize(self._tables)
        if len(new_body) < len(page.body):
            new_body = new_body + b"\x00" * (len(page.body) - len(new_body))
        elif len(new_body) > len(page.body):
            new_body = new_body[: len(page.body)]
        page.body = new_body
        self._store.write_page(page)

    def get_schema(self, name: str) -> TableSchema | None:
        return self._tables.get(name)

    def all_tables(self) -> list[str]:
        return list(self._tables.keys())

    def create_table(self, schema: TableSchema) -> None:
        self._tables[schema.name] = schema
        self.flush()

    def drop_table(self, name: str) -> None:
        self._tables.pop(name, None)
        self.flush()

    def update(self, schema: TableSchema) -> None:
        self._tables[schema.name] = schema
        self.flush()


# === Heap (T-5.2) ==========================================================


class _Heap:
    """Table heap stored across one or more TABLE pages."""

    def __init__(self, store: storage.FileStore, schema: TableSchema) -> None:
        self._store = store
        self._schema = schema

    def scan(self) -> list[tuple[tuple, int]]:
        """Return all rows as (values_tuple, rowid). rowid is page-local."""
        if self._schema.first_data_page_id == 0:
            return []
        rows: list[tuple[tuple, int]] = []
        page_id = self._schema.first_data_page_id
        while page_id != 0:
            page = self._store.read_page(page_id)
            rows.extend(self._decode_page(page.body, page_id))
            page_id = self._decode_next_page_id(page.body)
        return rows

    def _decode_page(self, body: bytes, page_id: int) -> list[tuple[tuple, int]]:
        # Format: [next_page u32][n_rows u32][rows...]
        # Each row: [len u32][rowid u64][(null_marker|encoded_value)...]
        if len(body) < 8:
            return []
        off = 4  # skip next_page (4 bytes)
        (n_rows,) = struct.unpack_from("<I", body, off)
        off += 4
        rows: list[tuple[tuple, int]] = []
        for _ in range(n_rows):
            (length,) = struct.unpack_from("<I", body, off)
            off += 4
            row_data = body[off:off + length]
            off += length
            (rowid,) = struct.unpack_from("<Q", row_data, 0)
            rowid = rowid  # page_id << 32 | rowid
            row_off = 8
            values: list[object] = []
            for col in self._schema.columns:
                ct = tinydb_types.ColumnType(col.type_name)
                (is_null,) = struct.unpack_from("<B", row_data, row_off)
                row_off += 1
                if is_null:
                    values.append(None)
                else:
                    # Peek value length from codec (for TEXT) or use fixed size
                    if ct is tinydb_types.ColumnType.TEXT:
                        (vlen,) = struct.unpack_from("<I", row_data, row_off)
                        row_off += 4
                        val = row_data[row_off:row_off + vlen].decode("utf-8")
                        row_off += vlen
                    else:
                        # Fixed size: INT=8, FLOAT=8, BOOL=1
                        fixed = {tinydb_types.ColumnType.INT: 8, tinydb_types.ColumnType.FLOAT: 8, tinydb_types.ColumnType.BOOL: 1}[ct]
                        val = tinydb_types.decode(row_data[row_off:row_off + fixed], ct)
                        row_off += fixed
                    values.append(val)
            rows.append((tuple(values), rowid))
        return rows

    def _decode_next_page_id(self, body: bytes) -> int:
        if len(body) < 4:
            return 0
        return struct.unpack_from("<I", body, 0)[0]

    def append_row(self, values: tuple) -> int:
        """Append a row; return its rowid."""
        rowid = 0  # simplified: all rows have rowid=0 within their page
        encoded = self._encode_row(values, rowid)
        # Append to last page or alloc new
        last_page_id = self._find_last_data_page()
        if last_page_id == 0:
            new_id = self._store.alloc_page(storage.PAGE_TYPE_TABLE)
            schema = self._schema
            object.__setattr__(schema, "first_data_page_id", new_id)
            self._store.catalog_update(self._schema)  # type: ignore[attr-defined]
            last_page_id = new_id
        page = self._store.read_page(last_page_id)
        body = bytearray(page.body)
        (next_id,) = struct.unpack_from("<I", body, 0)
        (n_rows,) = struct.unpack_from("<I", body, 4)
        # Find where current rows end
        off = 8
        for _ in range(n_rows):
            (length,) = struct.unpack_from("<I", body, off)
            off += 4 + length
        new_off = off + len(encoded)
        if new_off > len(body) - 4:
            # Page full, allocate new
            new_id = self._store.alloc_page(storage.PAGE_TYPE_TABLE)
            new_page = self._store.read_page(new_id)
            new_body = bytearray(new_page.body)
            new_body[0:4] = struct.pack("<I", 0)  # next_page = 0
            new_body[4:8] = struct.pack("<I", 0)  # n_rows = 0
            # Write to current page: update next_page
            body[0:4] = struct.pack("<I", new_id)
            page.body = bytes(body)
            self._store.write_page(page)
            page = new_page
            body = new_body
            off = 8
            n_rows = 0
        body[off:off + 4] = struct.pack("<I", len(encoded))
        body[off + 4:off + 4 + len(encoded)] = encoded
        struct.pack_into("<I", body, 4, n_rows + 1)
        page.body = bytes(body)
        self._store.write_page(page)
        return last_page_id  # rowid is page_id

    def _find_last_data_page(self) -> int:
        if self._schema.first_data_page_id == 0:
            return 0
        page_id = self._schema.first_data_page_id
        while True:
            page = self._store.read_page(page_id)
            nxt = self._decode_next_page_id(page.body)
            if nxt == 0:
                return page_id
            page_id = nxt

    def _encode_row(self, values: tuple, rowid: int) -> bytes:
        out = struct.pack("<Q", rowid)
        for v, col in zip(values, self._schema.columns):
            ct = tinydb_types.ColumnType(col.type_name)
            if v is None:
                out += struct.pack("<B", 1)  # is_null
            else:
                out += struct.pack("<B", 0)
                out += tinydb_types.encode(v, ct)
        return out


# Helper: add catalog_update method to FileStore for schema mutation tracking
def _catalog_update(self, schema: TableSchema) -> None:
    """Persist schema change (first_data_page_id or indexes) to header page."""
    cat = Catalog(self)
    cat.update(schema)

storage.FileStore.catalog_update = _catalog_update  # type: ignore[attr-defined]


# === Executor ==============================================================


class Executor:
    """High-level executor: open(path) → execute(stmt)."""

    def __init__(self, store: storage.FileStore) -> None:
        self._store = store
        self.catalog = Catalog(store)

    @classmethod
    def open(cls, path: str) -> "Executor":
        store = storage.FileStore.open(path)
        return cls(store)

    def close(self) -> None:
        self._store.close()

    def execute(self, stmt: object) -> object:
        if isinstance(stmt, p.CreateTable):
            return self._exec_create(stmt)
        if isinstance(stmt, p.DropTable):
            return self._exec_drop(stmt)
        if isinstance(stmt, p.CreateIndex):
            return self._exec_create_index(stmt)
        if isinstance(stmt, p.DropIndex):
            return self._exec_drop_index(stmt)
        if isinstance(stmt, p.Insert):
            return self._exec_insert(stmt)
        if isinstance(stmt, p.Select):
            return self._exec_select(stmt)
        if isinstance(stmt, p.Update):
            return self._exec_update(stmt)
        if isinstance(stmt, p.Delete):
            return self._exec_delete(stmt)
        raise tinydb_types.TinyDBError(f"unsupported statement: {type(stmt).__name__}")

    # === DDL ==============================================================

    def _exec_create(self, stmt: p.CreateTable) -> None:
        if stmt.if_not_exists and self.catalog.get_schema(stmt.name):
            return
        if self.catalog.get_schema(stmt.name):
            raise tinydb_types.TinyDBError(f"TableAlreadyExists({stmt.name!r})")
        columns = tuple(
            ColumnSchema(c.name, c.type_name, c.constraints) for c in stmt.columns
        )
        schema = TableSchema(name=stmt.name, columns=columns,
                             first_data_page_id=0, indexes={})
        self.catalog.create_table(schema)

    def _exec_drop(self, stmt: p.DropTable) -> None:
        for name in stmt.names:
            if not stmt.if_exists and not self.catalog.get_schema(name):
                raise tinydb_types.TableNotFound(name)
            schema = self.catalog.get_schema(name)
            if schema:
                # Free data pages
                pid = schema.first_data_page_id
                while pid != 0:
                    page = self._store.read_page(pid)
                    nxt = struct.unpack_from("<I", page.body, 0)[0]
                    self._store.free_page(pid)
                    pid = nxt
                # Free index pages
                for col_name, root_id in schema.indexes.items():
                    self._free_subtree(root_id)
            self.catalog.drop_table(name)

    def _free_subtree(self, root_id: int) -> None:
        """Free all pages in a B+ tree (simple: free root + scan, but for v0.1 free recursively)."""
        # v0.1 simplified: free the root only; this leaks pages if subtree > 1.
        # In practice, indexes are usually small enough to fit in one root page initially.
        # For v0.1, walk children by reading internal nodes.
        try:
            page = self._store.read_page(root_id)
        except Exception:
            return
        body = page.body
        if not body:
            return
        kind = body[0]
        if kind == 1:  # internal
            # Decode children (assuming INT keys)
            try:
                child_ids, _ = index.decode_internal(body[1:], tinydb_types.ColumnType.INT)
                for cid in child_ids:
                    self._free_subtree(cid)
            except Exception:
                pass
        self._store.free_page(root_id)

    def _exec_create_index(self, stmt: p.CreateIndex) -> None:
        schema = self.catalog.get_schema(stmt.table)
        if schema is None:
            raise tinydb_types.TableNotFound(stmt.table)
        # Find the column
        col_idx = self._col_index(schema, stmt.column)
        col = schema.columns[col_idx]
        ct = tinydb_types.ColumnType(col.type_name)
        if stmt.if_not_exists and stmt.name in schema.indexes:
            return
        if stmt.name in schema.indexes:
            raise tinydb_types.TinyDBError(f"IndexAlreadyExists({stmt.name!r})")
        # Allocate the B+ tree
        tree = index.BPlusTree.create(self._store, ct)
        # Populate the index from existing rows
        for values, _rowid in _Heap(self._store, schema).scan():
            key = values[col_idx]
            if key is None:
                continue  # NULLs are not indexed
            tree.insert(key, _rowid)
        # Persist index reference in catalog
        schema.indexes[stmt.name] = tree._root
        self._store.catalog_update(schema)
        if stmt.unique:
            # Enforce uniqueness: scan for duplicates
            seen: set[object] = set()
            for values, _rowid in _Heap(self._store, schema).scan():
                key = values[col_idx]
                if key is None:
                    continue
                if key in seen:
                    self._store.free_page(tree._root)
                    schema.indexes.pop(stmt.name, None)
                    self._store.catalog_update(schema)
                    raise tinydb_types.UniqueViolation("UNIQUE INDEX", key)
                seen.add(key)

    def _exec_drop_index(self, stmt: p.DropIndex) -> None:
        # Find the table that owns this index
        for table_schema in [self.catalog.get_schema(name) for name in self.catalog.all_tables()]:
            if table_schema and stmt.name in table_schema.indexes:
                root_id = table_schema.indexes.pop(stmt.name)
                self._free_subtree(root_id)
                self._store.catalog_update(table_schema)
                return
        if not stmt.if_exists:
            raise tinydb_types.TinyDBError(f"IndexNotFound({stmt.name!r})")

    # === DML ==============================================================

    def _exec_insert(self, stmt: p.Insert) -> int:
        schema = self.catalog.get_schema(stmt.table)
        if schema is None:
            raise tinydb_types.TableNotFound(stmt.table)
        inserted = 0
        for row_values in stmt.values:
            values = tuple(self._eval_expr(v) for v in row_values)
            self._validate_row(values, schema)
            heap = _Heap(self._store, schema)
            heap.append_row(values)
            inserted += 1
        return inserted

    def _validate_row(self, values: tuple, schema: TableSchema) -> None:
        if len(values) != len(schema.columns):
            raise tinydb_types.TinyDBError(
                f"column count mismatch: got {len(values)}, expected {len(schema.columns)}"
            )
        # Type check
        for v, col in zip(values, schema.columns):
            ct = tinydb_types.ColumnType(col.type_name)
            tinydb_types.coerce_in(v, ct, col.name)
        # NOT NULL
        for v, col in zip(values, schema.columns):
            if col.is_not_null and v is None:
                raise tinydb_types.NotNullViolation(col.name)
        # PRIMARY KEY / UNIQUE
        for i, col in enumerate(schema.columns):
            if col.is_unique and values[i] is not None:
                key = values[i]
                # Scan existing rows
                for existing_vals, _ in _Heap(self._store, schema).scan():
                    if existing_vals[i] == key:
                        constraint = "PRIMARY KEY" if col.is_primary_key else "UNIQUE"
                        raise tinydb_types.UniqueViolation(constraint, key)

    def _exec_select(self, stmt: p.Select) -> list[tuple]:
        schema = self.catalog.get_schema(stmt.table)
        if schema is None:
            raise tinydb_types.TableNotFound(stmt.table)
        # Expand SELECT * into explicit column list
        if any(isinstance(c, p.ColumnRef) and c.name == "*" for c in stmt.columns):
            stmt = p.Select(
                columns=tuple(p.ColumnRef(col.name) for col in schema.columns),
                table=stmt.table, where=stmt.where, order_by=stmt.order_by,
                limit=stmt.limit, offset=stmt.offset, group_by=stmt.group_by,
            )
        rows = _Heap(self._store, schema).scan()
        # Apply WHERE
        if stmt.where is not None:
            rows = [(v, r) for v, r in rows if self._eval_predicate_full(stmt.where, v, schema)]
        else:
            rows = [(v, r) for v, r in rows]
        # Apply ORDER BY
        if stmt.order_by:
            for ob in reversed(stmt.order_by):
                idx = self._col_index(schema, ob.column)
                rows.sort(key=lambda pair: (pair[0][idx] is None, pair[0][idx]),
                          reverse=ob.descending)
        # Apply LIMIT/OFFSET
        if stmt.offset:
            rows = rows[stmt.offset:]
        if stmt.limit is not None:
            rows = rows[: stmt.limit]
        # Apply projection
        if stmt.group_by:
            return self._aggregate_grouped(rows, schema, stmt)
        # Detect aggregate in projection (sentinel format "AGG:col")
        if any(isinstance(c, p.Literal) and isinstance(c.value, str) and ":" in c.value
               for c in stmt.columns):
            return self._aggregate_ungrouped(rows, schema, stmt)
        # Plain projection
        result = []
        for values, _ in rows:
            row = tuple(self._eval_expr(c, values, schema) for c in stmt.columns)
            result.append(row)
        return result

    def _aggregate_ungrouped(self, rows, schema, stmt):
        result_row = []
        for c in stmt.columns:
            if isinstance(c, p.Literal) and isinstance(c.value, str) and ":" in c.value:
                agg, col_name = c.value.split(":", 1)
                if agg == "COUNT" and col_name == "*":
                    result_row.append(len(rows))
                elif agg == "SUM":
                    idx = self._col_index(schema, col_name)
                    total = sum(v[idx] for v, _ in rows if v[idx] is not None)
                    result_row.append(total)
                elif agg == "AVG":
                    idx = self._col_index(schema, col_name)
                    vals = [v[idx] for v, _ in rows if v[idx] is not None]
                    result_row.append(sum(vals) / len(vals) if vals else None)
                else:
                    result_row.append(None)
            else:
                result_row.append(self._eval_expr(c, None, schema))
        return [tuple(result_row)]

    def _aggregate_grouped(self, rows, schema, stmt):
        from itertools import groupby
        group_indices = [self._col_index(schema, c) for c in stmt.group_by]
        rows.sort(key=lambda pair: tuple(pair[0][i] for i in group_indices))
        result = []
        for key, group in groupby(rows, key=lambda pair: tuple(pair[0][i] for i in group_indices)):
            group_list = list(group)
            row = []
            for c in stmt.columns:
                if isinstance(c, p.ColumnRef):
                    if c.name in stmt.group_by:
                        row.append(key[stmt.group_by.index(c.name)])
                    else:
                        row.append(None)
                elif isinstance(c, p.Literal) and isinstance(c.value, str) and ":" in c.value:
                    agg, col_name = c.value.split(":", 1)
                    if agg == "COUNT":
                        row.append(len(group_list))
                    elif agg == "SUM":
                        idx = self._col_index(schema, col_name)
                        row.append(sum(v[idx] for v, _ in group_list if v[idx] is not None))
                    elif agg == "AVG":
                        idx = self._col_index(schema, col_name)
                        vals = [v[idx] for v, _ in group_list if v[idx] is not None]
                        row.append(sum(vals) / len(vals) if vals else None)
                    else:
                        row.append(None)
                else:
                    row.append(self._eval_expr(c, None, schema))
            result.append(tuple(row))
        return result

    def _col_index(self, schema: TableSchema, name: str) -> int:
        for i, col in enumerate(schema.columns):
            if col.name == name:
                return i
        raise tinydb_types.TinyDBError(f"UnknownColumn({name!r})")

    def _eval_expr(self, expr, row=None, schema=None) -> object:
        if isinstance(expr, p.Literal):
            return expr.value
        if isinstance(expr, p.ColumnRef):
            if row is None:
                return None
            idx = self._col_index(schema, expr.name)
            return row[idx]
        if isinstance(expr, p.BinaryOp):
            l = self._eval_expr(expr.left, row, schema)
            r = self._eval_expr(expr.right, row, schema)
            if expr.op == "+":
                return l + r
            if expr.op == "-":
                return l - r
        return None

    def _eval_predicate(self, pred, row) -> bool:
        if isinstance(pred, p.Comparison):
            l = self._eval_expr(pred.left, row, pred.left.schema if hasattr(pred.left, "schema") else None)
            r = self._eval_expr(pred.right, row, None)
            # We need schema context — pass through differently
            return self._cmp_op(pred.op, l, r)
        if isinstance(pred, p.And):
            return self._eval_predicate(pred.left, row) and self._eval_predicate(pred.right, row)
        if isinstance(pred, p.Or):
            return self._eval_predicate(pred.left, row) or self._eval_predicate(pred.right, row)
        return True

    def _eval_predicate_full(self, pred, row, schema) -> bool:
        if isinstance(pred, p.Comparison):
            l = self._eval_expr(pred.left, row, schema)
            r = self._eval_expr(pred.right, row, schema)
            op = pred.op
            if op == "IS NULL":
                return l is None
            if op == "IS NOT NULL":
                return l is not None
            if l is None or r is None:
                return False  # NULL comparisons are NULL → excluded
            if op == "=":
                return l == r
            if op == "<>":
                return l != r
            if op == "<":
                return l < r
            if op == "<=":
                return l <= r
            if op == ">":
                return l > r
            if op == ">=":
                return l >= r
        if isinstance(pred, p.And):
            return self._eval_predicate_full(pred.left, row, schema) and \
                   self._eval_predicate_full(pred.right, row, schema)
        if isinstance(pred, p.Or):
            return self._eval_predicate_full(pred.left, row, schema) or \
                   self._eval_predicate_full(pred.right, row, schema)
        if isinstance(pred, p.Between):
            v = self._eval_expr(pred.expr, row, schema)
            lo = self._eval_expr(pred.lo, row, schema)
            hi = self._eval_expr(pred.hi, row, schema)
            return v is not None and lo <= v <= hi
        if isinstance(pred, p.InList):
            v = self._eval_expr(pred.expr, row, schema)
            return v in [self._eval_expr(x, row, schema) for x in pred.values]
        return True

    def _cmp_op(self, op, l, r) -> bool:
        # Legacy wrapper; new code uses _eval_predicate_full
        return self._eval_predicate_full(
            p.Comparison(op=op, left=p.Literal(value=l), right=p.Literal(value=r)),
            None, None,
        )

    def _exec_update(self, stmt: p.Update) -> int:
        schema = self.catalog.get_schema(stmt.table)
        if schema is None:
            raise tinydb_types.TableNotFound(stmt.table)
        # Simplified: collect rows, mutate matching, drop+reinsert all
        all_rows = _Heap(self._store, schema).scan()
        updated = 0
        new_rows: list[tuple] = []
        for values, _ in all_rows:
            values = list(values)
            if stmt.where is None or self._eval_predicate_full(stmt.where, tuple(values), schema):
                for a in stmt.assignments:
                    idx = self._col_index(schema, a.column)
                    values[idx] = self._eval_expr(a.value, tuple(values), schema)
                updated += 1
            new_rows.append(tuple(values))
        # Re-write heap from scratch
        self._rewrite_heap(schema, new_rows)
        return updated

    def _exec_delete(self, stmt: p.Delete) -> int:
        schema = self.catalog.get_schema(stmt.table)
        if schema is None:
            raise tinydb_types.TableNotFound(stmt.table)
        if stmt.where is None:
            raise tinydb_types.UnsafeDeleteWithoutWhere()
        all_rows = _Heap(self._store, schema).scan()
        kept = [v for v, _ in all_rows
                if not self._eval_predicate_full(stmt.where, v, schema)]
        deleted = len(all_rows) - len(kept)
        self._rewrite_heap(schema, kept)
        return deleted

    def _rewrite_heap(self, schema: TableSchema, rows: list[tuple]) -> None:
        # Free existing data pages
        pid = schema.first_data_page_id
        while pid != 0:
            page = self._store.read_page(pid)
            nxt = struct.unpack_from("<I", page.body, 0)[0]
            self._store.free_page(pid)
            pid = nxt
        schema.first_data_page_id = 0
        self._store.catalog_update(schema)
        # Re-insert
        for row in rows:
            self._validate_row(row, schema)
            heap = _Heap(self._store, schema)
            heap.append_row(row)
