"""Encrypted per-college read-only data source adapters and schema discovery."""
import base64,hashlib,ipaddress,json,socket
from urllib.parse import urlsplit
from cryptography.fernet import Fernet,InvalidToken
from sqlalchemy import create_engine,inspect
from sqlalchemy.engine import make_url
from .connectors import fetch_sql,fetch_mongo,fetch_api,ConnectorError
from .db import SCHEMAS

def fernet(secret):
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(('pulseiq3:integration:'+secret).encode()).digest()))

def encrypt(secret,details):
    return fernet(secret).encrypt(json.dumps(details).encode()).decode()

def decrypt(secret,value):
    try:return json.loads(fernet(secret).decrypt(value.encode()).decode())
    except (InvalidToken,ValueError): raise ConnectorError('Credentials cannot be decrypted. Check APP_SECRET.')

def validate_config(kind,details,mapping):
    if kind not in ('sql','mongodb','api'):raise ConnectorError('Select SQL, MongoDB, or HTTPS API.')
    if not isinstance(mapping,dict) or 'students' not in mapping:raise ConnectorError('Mapping requires a students entity.')
    for source,description in mapping.items():
        if source not in SCHEMAS or not isinstance(description,dict):raise ConnectorError('Invalid source mapping entity.')
        if kind!='api' and (not isinstance(description.get('table'),str) or not description.get('table')):raise ConnectorError(f'Missing table or collection for {source}.')
        col=description.get('columns',{})
        if not isinstance(col,dict) or any(k not in SCHEMAS[source] or not isinstance(v,str) for k,v in col.items()):raise ConnectorError('Column mapping must contain supported canonical fields.')
    if kind=='sql':
        url=details.get('url','')
        try:
            u=make_url(url)
            if not u.host or not u.database or u.drivername.split('+')[0] not in ('postgresql','mysql','mariadb','mssql','oracle'):
                raise ValueError()
        except Exception: raise ConnectorError('Use a valid PostgreSQL/MySQL/MariaDB/SQL Server/Oracle SQLAlchemy connection URL.')
    if kind=='mongodb':
        if not details.get('url','').startswith(('mongodb://','mongodb+srv://')) or not details.get('database'):raise ConnectorError('MongoDB URI and database are required.')
    if kind=='api':
        safe_api(details.get('url',''))
    return True

def safe_api(url):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:raise ConnectorError('API must be a public HTTPS address without embedded credentials.')
    hostname=parsed.hostname.rstrip('.').lower()
    if hostname=='localhost' or hostname.endswith(('.local','.internal')):raise ConnectorError('Private API hostnames are not supported.')
    try:
        addresses=socket.getaddrinfo(hostname,parsed.port or 443,type=socket.SOCK_STREAM)
        for a in addresses:
            ip=ipaddress.ip_address(a[4][0]);
            if not ip.is_global:raise ConnectorError('API host resolves to a private or reserved address.')
    except socket.gaierror:raise ConnectorError('API hostname could not be resolved.')

def discover(kind,details):
    if kind=='sql':
        engine=create_engine(details['url'],pool_pre_ping=True,connect_args={} if not details['url'].startswith('postgresql') else {'connect_timeout':10})
        try:
            insp=inspect(engine)
            names=insp.get_table_names() + insp.get_view_names()
            return [{'table':table,'columns':[x['name'] for x in insp.get_columns(table)]} for table in names[:100]]
        finally:engine.dispose()
    if kind=='mongodb':
        from pymongo import MongoClient
        with MongoClient(details['url'],serverSelectionTimeoutMS=8000) as client:
            return [{'table':v,'columns':sorted([k for k in (client[details['database']][v].find_one() or {}).keys() if k!='_id'])} for v in client[details['database']].list_collection_names()[:100]]
    if kind=='api':
        safe_api(details['url'])
        return [{'table':'Canonical HTTPS API','columns':list(SCHEMAS)}]
    raise ConnectorError('Unknown source kind.')

def fetch(kind,details,mapping,app_url):
    if kind=='sql':return fetch_sql(details['url'],mapping,app_url)
    if kind=='mongodb':return fetch_mongo(details['url'],details['database'],mapping)
    if kind=='api':
        safe_api(details['url'])
        # Canonical payload is expected. Redirects disabled in the adapter.
        return fetch_api(details['url'],details.get('token',''))
    raise ConnectorError('Unknown source kind.')
