"""Runtime-declared lexical identity, not a member or business authority."""
import json
from backend.app.powerbi.fabric_iq_contract import fail

PREFIX = 'PBIAGENT_MEMBER_IDENTITY_V1:'
RULE = 'TRAILING_SPACE_UPPER_INVARIANT_ASCII_V1'


def declaration(column):
    text = column.description or ''
    if not text.startswith(PREFIX):
        return None
    def unique(pairs):
        result = dict(pairs)
        if len(result) != len(pairs):
            raise ValueError()
        return result
    try:
        value = json.loads(text[len(PREFIX):], object_pairs_hook=unique)
        if value == {'role':'provenance_only'}:
            return value
        if (not isinstance(value, dict) or set(value) != {'role','rule','source_field','input_name'}
                or value['role'] != 'canonical' or value['rule'] != RULE
                or any(not isinstance(value[k], str) or not value[k] or len(value[k]) > 100
                       for k in ('source_field','input_name'))):
            raise ValueError()
        return value
    except (ValueError, TypeError):
        raise fail('CONTRACT_DRIFT') from None


def canonical_literal(value):
    # ASCII makes Python and Power Query invariant uppercase identical without
    # locale-dependent Unicode expansion. Other scripts fail closed.
    if not isinstance(value, str) or not value or len(value) > 200 or not value.isascii():
        raise fail('CONTRACT_DRIFT')
    result = value.rstrip(' ').upper()
    if not result or any(ord(c) < 32 or ord(c) == 127 for c in result):
        raise fail('CONTRACT_DRIFT')
    return result


def normalize_declared_columns(schema):
    for table in schema.tables:
        for column in table.columns:
            contract = declaration(column)
            if contract is None:
                continue
            if column.data_type.lower() not in {'text','string'}:
                raise fail('CONTRACT_DRIFT')
            if contract['role'] == 'provenance_only':
                # Product eligibility exclusion, never a Microsoft OLS claim.
                column.is_hidden = True
            else:
                sources = [c for c in table.columns if c.name == contract['source_field']]
                if len(sources) != 1 or declaration(sources[0]) != {'role':'provenance_only'}:
                    raise fail('CONTRACT_DRIFT')
                if any(c.name == contract['input_name'] and c is not column and
                       declaration(c) != {'role':'provenance_only'} for c in table.columns):
                    raise fail('CONTRACT_DRIFT')
                column.display_name = contract['input_name']
    return schema
