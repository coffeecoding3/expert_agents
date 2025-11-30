"""
Web Search Component

웹 서치 컴포넌트
"""

## settings
# pip uninstall -y openai httpx
# pip install --upgrade openai httpx

import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict

import fitz  # PyMuPDF
import requests
import trafilatura
from dotenv import load_dotenv
from openai import AzureOpenAI, BadRequestError

# sys.path.append('/project/work/expert_agents')
from src.prompts.prompt_manager import prompt_manager

load_dotenv()

logger = logging.getLogger("agents.components.web_search")


class WebSearch:
    """웹 서치 컴포넌트"""

    name = "web_search"
    description = "웹 검색을 수행합니다"

    def __init__(self):
        """
        초기화
        - 참고: LLM API 및 google Engine ID 밖에서 불러와야 함
        """
        self.query = ""

        self.api_key = os.getenv("GOOGLE_API_KEY")
        self.cx = os.getenv("GOOGLE_CX")

        self.azure_openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.azure_openai_key = os.getenv("AZURE_OPENAI_KEY")
        self.azure_openai_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        self.azure_openai_api_version = os.getenv("AZURE_OPENAI_API_VERSION")

        self.client = AzureOpenAI(
            api_key=self.azure_openai_key,
            api_version=self.azure_openai_api_version,
            azure_endpoint=self.azure_openai_endpoint,
        )

    # def _translate_to_english(self) -> str:
    #     """한국어를 영어로 번역"""
    #     prompt = prompt_manager.render_template(
    #             "search_agent/translate_to_english.j2",
    #             {"query": self.query},
    #         )
    #     try:
    #         resp = self.client.chat.completions.create(
    #             model=self.azure_openai_deployment,
    #             messages=[{"role": "user", "content": prompt}],
    #             temperature=0,
    #         )
    #         answer = resp.choices[0].message.content.strip()
    #         return answer
    #     except BadRequestError as e:
    #         return f"Unexpected Error: {str(e)}"

    def _google_search(self, num_urls: int) -> list:
        """자연어 질의와 관련된 url 검색"""
        if num_urls <= 100:  # 100개까지만 가능
            url = "https://www.googleapis.com/customsearch/v1"

            exclude_filetypes = [
                "doc",
                "docx",
                "ppt",
                "pptx",
                "xls",
                "xlsx",
                "csv",
                "txt",
            ]  # "pdf" 제외
            exclude_query = " ".join([f"-filetype:{ft}" for ft in exclude_filetypes])

            quotient = num_urls // 10
            remainder = num_urls % 10

            total_params = []
            for i in range(quotient):
                tmp_params = {
                    "key": self.api_key,
                    "cx": self.cx,
                    "q": f"{self.query} {exclude_query}",
                    "num": 10,
                    "start": 10 * i + 1,
                }
                total_params.append(tmp_params)

            if remainder:
                tmp_params = {
                    "key": self.api_key,
                    "cx": self.cx,
                    "q": f"{self.query} {exclude_query}",
                    "num": remainder,
                    "start": 10 * quotient + 1,
                }
                total_params.append(tmp_params)

            total_urls = []
            for param in total_params:
                try:
                    response = requests.get(url, params=param)
                    response.raise_for_status()
                    results = response.json()

                    if "items" in results:
                        for item in results["items"]:
                            total_urls.append(item["link"])
                except Exception as e:
                    pass

            return total_urls
        else:  # 100개 초과
            # return ValueError(f"{num_urls}는 100보다 클 수 없습니다.")
            return []

    def _replace_newlines(self, text: str) -> str:
        # 3개 이상의 연속된 개행을 2개로 치환
        if text:
            return re.sub(r"\n{3,}", "\n\n", text)
        else:
            return text

    def _safe_fetch_url(self, url: str, timeout: int = 30) -> str:
        try:
            response = requests.get(
                url, timeout=(5, timeout)
            )  # 연결 5초, 읽기 timeout초
            response.raise_for_status()
            return response.text
        except requests.exceptions.Timeout:
            return "None"
        except Exception as e:
            return "None"

    def _pdf_crawling(self, url: str, timeout: int = 30) -> str:
        """PDF 크롤링"""
        try:
            response = requests.get(url, timeout=(5, timeout))
            response.raise_for_status()
            doc = fitz.open(stream=response.content, filetype="pdf")

            text_total = ""
            for page_num in range(len(doc)):
                page = doc[page_num]
                text_total += page.get_text()

            return text_total
        except:
            return ""

    def _crawling(self, urls: list) -> list:
        """본문 크롤링

        활용 라이브러리: trafilatura
        """
        full_text = []
        # keywords: keywords의 값이 url에 속해있으면 크롤링 pass
        keywords = ["download", "report/", "filedown", "downfile", "viewer"]
        for i in range(len(urls)):

            try:
                if any(keyword in urls[i].lower() for keyword in keywords):
                    full_text.append(None)
                else:
                    if "pdf" in urls[i].lower():  # pdf 파일
                        content = self._pdf_crawling(urls[i])
                    else:  # 웹 페이지
                        downloaded = self._safe_fetch_url(urls[i])
                        if downloaded:
                            try:
                                content = trafilatura.extract(downloaded)
                                if content:
                                    content = self._replace_newlines(content)
                                else:
                                    content = None
                            except Exception as traf_error:
                                logger.debug(
                                    f"[WEB_SEARCH] trafilatura 추출 실패: {urls[i]}, 오류: {traf_error}"
                                )
                                content = None
                        else:
                            content = None

                    if content:
                        tmp = re.split(r"[.\n]", content)
                        length = len(tmp)
                        if length > 40:
                            tmp1 = " ".join(tmp[: int(length // 10)])
                            content = tmp1

                    content = f"""{content}""" if content else None
                    full_text.append(content)

            except Exception as e:
                logger.debug(
                    f"[WEB_SEARCH] URL 크롤링 실패: {urls[i] if i < len(urls) else 'unknown'}, 오류: {e}"
                )
                full_text.append(None)

        ## 크롤링 가능한 url index 확인
        not_None_indexes = [i for i, v in enumerate(full_text) if v is not None]
        filtered_full_text = [full_text[i] for i in not_None_indexes]

        logger.info(
            f"[WEB_SEARCH] 크롤링 결과: 전체 {len(full_text)}개 중 {len(filtered_full_text)}개 성공"
        )

        # 원본 URL 인덱스 정보와 함께 반환
        return {"contents": filtered_full_text, "indices": not_None_indexes}

    def _summerized_text(self, text: list) -> list:
        """본문 요약"""
        results = []

        for txt in text:
            prompt = prompt_manager.render_template(
                "search_agent/web_search_summerized_text.j2",
                {"query": self.query, "content": txt},
            )
            try:
                resp = self.client.chat.completions.create(
                    model=self.azure_openai_deployment,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                )
                answer = resp.choices[0].message.content.strip()
                results.append(answer)
            except Exception as e:
                pass
            except BadRequestError as e:
                pass

        summerized_text = []
        for i in range(len(results)):
            if "None" not in results[i]:
                summerized_text.append(results[i])
            else:  # None
                summerized_text.append(results[i])
        return summerized_text

    def _summary(self, text: list) -> str:
        """LLM 최종 Output"""
        prompt = prompt_manager.render_template(
            "search_agent/web_search_final_summary.j2",
            {"query": self.query, "text": str(text)},
        )
        try:
            resp = self.client.chat.completions.create(
                model=self.azure_openai_deployment,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
            )
            answer = resp.choices[0].message.content.strip()
            return answer
        except BadRequestError as e:
            return f"Unexpected Error: {str(e)}"

    def web_search(self, query: str, num_urls: int = 10) -> Dict[str, Any]:
        """웹 서치
        Args:
            query: 사용자 쿼리

        Returns:
            분석 결과
        """
        self.query = query
        logger.info(f"[WEB_SEARCH] 웹 검색 시작: query='{query}', num_urls={num_urls}")

        final_results = []

        try:
            # 1단계: 자연어 질의와 관련된 url 검색
            logger.info("[WEB_SEARCH] 1단계: URL 검색 시작")
            urls = self._google_search(num_urls=num_urls)
            logger.info(f"[WEB_SEARCH] URL 검색 완료: {len(urls)}개 URL 발견")
            if urls:
                logger.info(
                    f"[WEB_SEARCH] 발견된 URL 예시: {urls[0][:100] if urls[0] else 'None'}..."
                )

            if not urls:
                logger.warning("[WEB_SEARCH] 검색된 URL이 없습니다")
                return []

            # 2단계: url 본문 크롤링
            logger.info("[WEB_SEARCH] 2단계: 본문 크롤링 시작")
            crawled_data = self._crawling(urls=urls)
            crawled_urls = crawled_data["contents"]
            crawled_indices = crawled_data["indices"]
            logger.info(
                f"[WEB_SEARCH] 크롤링 완료: {len(crawled_urls)}개 성공 (원본 {len(urls)}개 중)"
            )

            if not crawled_urls:
                logger.warning("[WEB_SEARCH] 크롤링된 내용이 없습니다")
                # URL만이라도 반환
                return [{"url": url, "content": None, "summary": None} for url in urls]

            # 3단계: 본문 요약
            logger.info("[WEB_SEARCH] 3단계: 본문 요약 시작")
            summerized_texts = self._summerized_text(text=crawled_urls)
            logger.info(f"[WEB_SEARCH] 요약 완료: {len(summerized_texts)}개")

            # 결과 조합 (크롤링된 URL과 요약 매칭)
            min_len = min(len(crawled_urls), len(summerized_texts))
            for i in range(min_len):
                tmp = {}
                # crawled_indices를 사용하여 원본 URL 인덱스 찾기
                url_index = crawled_indices[i] if i < len(crawled_indices) else i
                if url_index < len(urls):
                    tmp["url"] = urls[url_index]
                else:
                    tmp["url"] = None
                tmp["content"] = crawled_urls[i] if crawled_urls[i] else None
                tmp["summary"] = (
                    summerized_texts[i] if i < len(summerized_texts) else None
                )
                final_results.append(tmp)

            logger.info(f"[WEB_SEARCH] 웹 검색 완료: {len(final_results)}개 결과 반환")
            if final_results:
                first_result = final_results[0]
                logger.info(
                    f"[WEB_SEARCH] 첫 번째 결과 샘플 - URL: {first_result.get('url', 'None')[:80] if first_result.get('url') else 'None'}..., "
                    f"content 길이: {len(str(first_result.get('content', ''))) if first_result.get('content') else 0}자, "
                    f"summary 길이: {len(str(first_result.get('summary', ''))) if first_result.get('summary') else 0}자"
                )
            return final_results

        except Exception as e:
            logger.error(f"[WEB_SEARCH] 웹 검색 중 예외 발생: {e}", exc_info=True)
            # 부분 결과라도 있으면 반환
            if final_results:
                logger.warning(f"[WEB_SEARCH] 부분 결과 {len(final_results)}개 반환")
                return final_results
            # 에러 정보를 포함한 결과 반환
            return [
                {
                    "url": None,
                    "content": f"웹 검색 중 오류 발생: {str(e)}",
                    "summary": None,
                }
            ]

    async def run(self, query: str, num_urls: int = 10):
        """도구 인터페이스를 위한 run 메서드"""
        return await self.web_search(query=query, num_urls=num_urls)


if __name__ == "__main__":
    start = time.time()
    # query = "지식 그래프를 활용한 generative ai 연구 동향"
    query = "2025년 9월 17일 서울 여의도 날씨를 알려줘."
    num_urls = 15

    web_search = WebSearch()
    output = web_search.web_search(query=query, num_urls=num_urls)
    end = time.time()

    print(output)
    print(f"\n총 실행 시간: {end-start:.5f} sec")
