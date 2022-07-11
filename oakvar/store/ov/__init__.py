from typing import Optional


def module_code_url(module_name: str, version=None) -> Optional[str]:
    from requests import Session
    from .account import get_current_id_token
    from ...exceptions import AuthorizationError
    from ...exceptions import StoreServerError

    id_token = get_current_id_token(args={"quiet": True})
    s = Session()
    s.headers["User-Agent"] = "oakvar"
    url = get_store_url() + f"/moduleurls/{module_name}/{version}/code"
    params = {"idToken": id_token}
    res = s.post(url, data=params)
    if res.status_code == 200:
        code_url = res.text
        return code_url
    elif res.status_code == 401:
        raise AuthorizationError()
    elif res.status_code == 500:
        raise StoreServerError()
    else:
        return None


def module_data_url(module_name: str, version=None) -> Optional[str]:
    from requests import Session
    from .account import get_current_id_token
    from ...exceptions import AuthorizationError
    from ...exceptions import StoreServerError

    id_token = get_current_id_token(args={"quiet": True})
    s = Session()
    s.headers["User-Agent"] = "oakvar"
    url = get_store_url() + f"/moduleurls/{module_name}/{version}/data"
    params = {"idToken": id_token}
    res = s.post(url, data=params)
    if res.status_code == 200:
        data_url = res.text
        return data_url
    elif res.status_code == 401:
        raise AuthorizationError()
    elif res.status_code == 500:
        raise StoreServerError()
    else:
        return None


def setup_ov_store_cache(conf=None, args=None):
    from ..db import drop_ov_store_cache
    from ..db import create_ov_store_cache
    from ..db import fetch_ov_store_cache

    drop_ov_store_cache(conf=conf, args=args)
    create_ov_store_cache(conf=conf, args=args)
    fetch_ov_store_cache(args=args)


def url_is_valid(url: str) -> bool:
    from requests import head

    res = head(url)
    if res.status_code == 200:
        return True
    else:
        return False


def get_register_args_of_module(module_name: str, args={}) -> Optional[dict]:
    from ...module.local import get_remote_manifest_from_local
    from ...exceptions import ArgumentError
    from re import fullmatch

    rmi = get_remote_manifest_from_local(module_name)
    if not rmi or not args:
        return None
    rmi["code_url"] = args.get("code_url")
    rmi["data_url"] = args.get("data_url")
    rmi["logo_url"] = args.get("logo_url")
    rmi["module_name"] = module_name
    for v in ["code", "data", "logo"]:
        k = f"{v}_url"
        if v == "logo" and rmi[k] == "":
            continue
        if not fullmatch(
            r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)",
            rmi[k],
        ) or not url_is_valid(rmi[k]):
            raise ArgumentError(f"invalid {k}")
    return rmi


def make_remote_module_info_from_local(module_name: str) -> Optional[dict]:
    from ...module.local import get_local_module_info
    from time import time

    mi = get_local_module_info(module_name)
    if not mi:
        return None
    versions = {}
    latest_version = ""
    ty = mi.type
    title = mi.title
    description = mi.description
    size = mi.size
    code_size = 0
    data_size = 0
    datasource = mi.data_source
    hidden = mi.conf.get("hidden", False)
    developer = mi.developer
    data_versions = {}
    data_sources = {}
    tags = mi.tags
    publish_time = str(time())
    rmi = {
        "versions": versions,
        "latest_version": latest_version,
        "type": ty,
        "title": title,
        "description": description,
        "size": size,
        "code_size": code_size,
        "data_size": data_size,
        "datasource": datasource,
        "hidden": hidden,
        "developer": developer,
        "data_versions": data_versions,
        "data_sources": data_sources,
        "tags": tags,
        "publish_time": publish_time,
    }
    return rmi


def get_server_last_updated(args={}):
    from requests import Session
    from .account import get_current_id_token

    id_token = get_current_id_token(args=args)
    s = Session()
    s.headers["User-Agent"] = "oakvar"
    url = get_store_url() + "/last_updated"
    params = {"idToken": id_token}
    res = s.post(url, data=params)
    if res.status_code != 200:
        return 0, res.status_code
    server_last_updated = float(res.json())
    return server_last_updated, res.status_code


def make_module_info_from_table_row(row: dict) -> dict:
    d = {
        "name": row["name"],
        "type": row["type"],
        "code_version": row["code_version"],
        "data_version": row["data_version"],
        "tags": row["tags"],
        "code_size": row["code_size"],
        "data_size": row["data_size"],
        "logo_url": row["logo_url"],
        "description": row["description"],
        "readme": row["readme"],
        "logo": row["logo"],
        "conf": row["conf"],
        "store": row["store"],
    }
    return d


def get_store_url() -> str:
    from ...system import get_system_conf

    sys_conf = get_system_conf()
    store_url = sys_conf["store_url"]
    return store_url


# @db_func
# def fetch_ov_store_cache(
#    email: Optional[str] = None,
#    pw: Optional[str] = None,
#    conn=None,
#    cursor=None,
#    args={},
# ):
#    from ..consts import ov_store_email_key
#    from ..consts import ov_store_pw_key
#    from ..consts import ov_store_last_updated_col
#    from ...system import get_sys_conf_value
#    from ...system import get_user_conf
#    from requests import Session
#    from ...util.util import quiet_print
#    from ...exceptions import StoreServerError
#    from ...exceptions import AuthorizationError
#
#    if not conn or not cursor:
#        return False
#    if not email and args:
#        email = args.get("email")
#        pw = args.get("pw")
#    if not email:
#        user_conf = get_user_conf()
#        email = user_conf.get(ov_store_email_key)
#        pw = user_conf.get(ov_store_pw_key)
#    if not email or not pw:
#        return False
#    params = {"email": email, "pw": pw}
#    s = Session()
#    s.headers["User-Agent"] = "oakvar"
#    store_url = get_sys_conf_value("store_url")
#    if not store_url:
#        return False
#    server_last_updated, status_code = get_server_last_updated(email, pw)
#    local_last_updated = get_local_last_updated()
#    clean = args.get("clean")
#    if not server_last_updated:
#        if status_code == 401:
#            raise AuthorizationError()
#        elif status_code == 500:
#            raise StoreServerError()
#        return False
#    if not clean and local_last_updated and local_last_updated >= server_last_updated:
#        quiet_print("No store update to fetch", args=args)
#        return True
#    url = f"{store_url}/fetch"
#    res = s.get(url, params=params)
#    if res.status_code != 200:
#        if res.status_code == 401:
#            raise AuthorizationError()
#        elif res.status_code == 500:
#            raise StoreServerError()
#        return False
#    q = f"delete from modules"
#    cursor.execute(q)
#    conn.commit()
#    res = res.json()
#    cols = res["cols"]
#    for row in res["data"]:
#        q = f"insert into modules ( {', '.join(cols)} ) values ( {', '.join(['?'] * len(cols))} )"
#        cursor.execute(q, row)
#    q = f"insert or replace into info ( key, value ) values ( ?, ? )"
#    cursor.execute(q, (ov_store_last_updated_col, str(server_last_updated)))
#    conn.commit()
#    quiet_print("OakVar store cache has been fetched.", args=args)
