import json
import re
import requests

from utils import get_random_ua


class Custom_EDHRec:
    def __init__(self, cookies: str = None):
        self.cookies = cookies
        self.session = requests.Session()
        if self.cookies:
            self.session.cookies = self.get_cookie_jar(cookies)
        self.session.headers = {
            "Accept": "application/json",
            "User-Agent": get_random_ua()
        }
        self.base_url = "https://edhrec.com"
        self.default_build_id = "mI7k8IZ23x74LocK_h-qe"
        self.current_build_id = None

    @staticmethod
    def get_cookie_jar(cookie_str: str):
        if cookie_str.startswith("userState="):
            cookie_str = cookie_str.split("userState=")[1]

        d = {
            "userState": cookie_str
        }
        cookie_jar = requests.cookies.cookiejar_from_dict(d)
        return cookie_jar
    
    def get(self, uri: str, query_params: dict =None, return_type: str = "json") -> tuple[dict, int]:
        return self._get(uri, query_params=query_params, return_type=return_type)
    def _get(self, uri: str, query_params: dict =None, return_type: str = "json") -> tuple[dict, int]:
        res = self.session.get(uri, params=query_params)
        
        if res.status_code != 200:
            print(f"Error fetching data from {uri}: {res.status_code}")
            return None, res.status_code
        
        if return_type == "json":
            res_json = res.json()
            return res_json, res.status_code
        else:
            return res.content, res.status_code

    def get_next_data(self, uri: str) -> tuple[dict, int] | None:
        home_page, status_code = self._get(uri, return_type="raw")
        home_page_content = home_page.decode("utf-8")
        script_block_regex = r"<script id=\"__NEXT_DATA__\" type=\"application/json\">(.*)</script>"
        if script_match := re.findall(script_block_regex, home_page_content):
            props_str = script_match[0]
        else:
            return None
        try:
            props_data = json.loads(props_str)
            return props_data, status_code
        except json.JSONDecodeError:
            return None

    def get_build_id(self) -> str | None:
        props_data, status_code = self.get_next_data(uri=self.base_url)
        
        if props_data:
            return props_data.get("buildId")
        else:
            return None

    def check_build_id(self):
        if not self.current_build_id:
            self.current_build_id = self.get_build_id()
            # If we couldn't get the current buildId we'll try to fall back to a known static string
            if not self.current_build_id:
                self.current_build_id = self.default_build_id
        # We have a build ID set
        return True

    def _build_nextjs_uri(self, 
                          endpoint: str, 
                          page_number: int = None,
                          tag: str = None):
        self.check_build_id()
        query_params = {}
        uri = f"{self.base_url}/_next/data/{self.current_build_id}/{endpoint}"
        
        if tag:
            uri += f"/tag/{tag}"
            query_params["tag"] = tag

        if page_number:
            if tag:    
                uri += f"/{page_number}.json"                 
            else:
                uri += f"/page/{page_number}.json"
                
            query_params["page"] = page_number
        
        return uri, query_params

    @staticmethod
    def _get_nextjs_data(response: dict, data_name: str) -> dict:
        if "pageProps" in response:
            return response.get("pageProps", {}).get(data_name)

    def get_articles(self, page_number: int, tag: str = None) -> tuple[dict, int]:
        article_uri, params = self._build_nextjs_uri("articles", page_number=page_number, tag=tag)
        res, status_code = self._get(article_uri, query_params=params)
        data = self._get_nextjs_data(res, "posts")
        return data, status_code
    
    def get_guides(self, page_number: int) -> tuple[dict, int]:
        article_uri, params = self._build_nextjs_uri("guides", page_number=page_number)
        res, status_code = self._get(article_uri, query_params=params)
        data = self._get_nextjs_data(res, "posts")
        return data, status_code
        