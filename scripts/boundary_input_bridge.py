"""Reversible, content-bound event-table correction; no implicit hash exemption."""
from __future__ import annotations
import hashlib
import ast
import polars as pl


def parse_dtype(name):
    """Parse Polars' schema repr without evaluating executable source."""
    allowed={str(t):t for t in (pl.String,pl.Boolean,pl.Null,pl.Int8,pl.Int16,pl.Int32,pl.Int64,pl.UInt8,pl.UInt16,pl.UInt32,pl.UInt64,pl.Float32,pl.Float64,pl.Date)}
    constructors={'List':pl.List,'Struct':pl.Struct,'Datetime':pl.Datetime,'Duration':pl.Duration,'Array':pl.Array}
    def visit(node):
        if isinstance(node,ast.Name) and node.id in allowed:return allowed[node.id]
        if isinstance(node,ast.Constant) and isinstance(node.value,(str,int,type(None))):return node.value
        if isinstance(node,ast.Dict):return {visit(k):visit(v) for k,v in zip(node.keys,node.values)}
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in constructors:
            return constructors[node.func.id](*[visit(x) for x in node.args],**{x.arg:visit(x.value) for x in node.keywords if x.arg is not None})
        raise AssertionError(('unsupported source dtype',name))
    return visit(ast.parse(name,mode='eval').body)


def content_hash(table):
    return hashlib.sha256(table.sort('event_id').select(sorted(table.columns)).write_json().encode()).hexdigest()


def make_record(path, before, after):
    assert before['event_id'].n_unique()==before.height
    assert after['event_id'].n_unique()==after.height
    assert before['event_id'].to_list()==after['event_id'].to_list(), 'event population/order changed'
    assert set(before.columns)<=set(after.columns), 'removed source columns'
    added=sorted(set(after.columns)-set(before.columns))
    assert all(c.startswith('measurement_predecessor_') for c in added), ('unexpected added columns',added)
    old=before.to_dicts();new=after.select(before.columns).to_dicts()
    changes=[{'event_id':a['event_id'],'before':a,'after':b} for a,b in zip(old,new) if a!=b]
    return {'path':path,'before_content_sha256':content_hash(before),'after_content_sha256':content_hash(after),
            'before_columns':before.columns,'before_schema':{c:str(t) for c,t in before.schema.items()},'added_columns':added,'rows':before.height,'changed_rows':changes}


def restore_table(after, record):
    assert content_hash(after)==record['after_content_sha256'], 'boundary after content mismatch'
    assert after.height==record['rows'] and after['event_id'].n_unique()==after.height
    assert set(after.columns)==set(record['before_columns'])|set(record['added_columns'])
    assert all(c.startswith('measurement_predecessor_') for c in record['added_columns'])
    table=after.select(record['before_columns'])
    changes={r['event_id']:r for r in record['changed_rows']}
    assert len(changes)==len(record['changed_rows'])
    rows=table.to_dicts()
    for i,row in enumerate(rows):
        if row['event_id'] in changes:
            change=changes.pop(row['event_id'])
            assert row==change['after'], ('boundary changed-row mismatch',row['event_id'])
            assert change['before']['event_id']==row['event_id']
            rows[i]=change['before']
    assert not changes, 'unknown changed event'
    schema={c:parse_dtype(t) for c,t in record.get('before_schema',{c:str(t) for c,t in table.schema.items()}).items()}
    before=pl.DataFrame(rows,schema=schema)
    assert content_hash(before)==record['before_content_sha256'], 'boundary reconstructed content mismatch'
    return before


def restore_floor(after, record):
    assert content_hash(after)==record['after_content_sha256'], 'revised prefix floor content mismatch'
    assert set(after.columns)==set(record['before_columns']) and after.height==record['after_rows']
    removed=pl.DataFrame(record['removed_rows'],schema=after.schema)
    assert not set(removed['event_id'])&set(after['event_id'])
    before=pl.concat([after,removed]).select(record['before_columns'])
    assert before.height==record['before_rows'] and before['event_id'].n_unique()==before.height
    assert content_hash(before)==record['before_content_sha256'], 'reconstructed prefix floor mismatch'
    return before
