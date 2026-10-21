"""Strict Microsoft browser selectors. URLs are never fetched."""
import re
from urllib.parse import urlsplit, parse_qs
from uuid import UUID


def parse_resource_link(value):
    try:
        if not isinstance(value,str) or len(value)>2048: raise ValueError()
        url=urlsplit(value)
        if (url.scheme!='https' or url.netloc not in {'app.powerbi.com','app.fabric.microsoft.com'}
                or url.fragment or url.username or url.password): raise ValueError()
        query=parse_qs(url.query,keep_blank_values=True,max_num_fields=2,strict_parsing=True)
        if any(key not in {'ctid','experience'} or len(values)!=1 for key,values in query.items()): raise ValueError()
        if 'ctid' in query: UUID(query['ctid'][0])
        if 'experience' in query and query['experience']!=['power-bi']: raise ValueError()
        match=re.fullmatch(r'/groups/([0-9a-fA-F-]{36})/(reports|datasets|semanticmodels)/([0-9a-fA-F-]{36})(?:/(?:details|ReportSection[a-zA-Z0-9]*))?/?',url.path)
        if match is None: raise ValueError()
        return str(UUID(match[1])),str(UUID(match[3])),'Report' if match[2]=='reports' else 'SemanticModel'
    except (ValueError,TypeError,AttributeError):
        raise ValueError('unsupported_cloud_resource_link') from None
