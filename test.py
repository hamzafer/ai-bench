import asyncio
import io
import httpx
import pandas as pd
from tqdm.asyncio import tqdm

# --- CONFIGURATION ---
API_URL = "https://hero.deepinsight.internal/api/comment-analysis/analyze"
COOKIE_STRING = "client_name=mock; access_token=eyJraWQiOiJtb2NrLWlzc3VlciIsInR5cCI6IkpXVCIsImFsZyI6IlJTMjU2In0.eyJzdWIiOiI3YzU1ZGIyZS04NmI5LTQ2NGEtOTVmZC05YTA3MmVkNWY1NGIiLCJuYmYiOjE3NTczNDU3NzQsImlzcyI6Imh0dHBzOi8vb2F1dGgyLmhlcm8uZGVlcGluc2lnaHQuaW50ZXJuYWwvbW9jay1pc3N1ZXIiLCJuYW1lIjoiTW9jayB1c2VyIiwicHJlZmVycmVkX3VzZXJuYW1lIjoibW9jayIsImV4cCI6MTc1NzM0OTM3NCwiaWF0IjoxNzU3MzQ1Nzc0LCJub25jZSI6ImVhSGRNaENRaUkyRWVMTnY4cXdxIiwianRpIjoiYWNjMTNhYjAtNjNlZC00Zjk4LWFkYzctMjM0MjQ0NDJlMmM2IiwiZW1haWwiOiJtb2NrQGV4YW1wbGUuY29tIn0.ZDaKsWREZBC_Z6WLRXQgOlzbcczp1JUDAAatRfg-WN6pHkkb-hrGXg430fxCl4MbOYARuLCUqB7DSLWsnfcj9tHm5OGa39eT3wsMoF1q5Tad8xbKOYhEwiMsdAcF8lPHBjlGPV5rO2C4F2CbYx_dd1YrAgfdrKlPh-u0RrgSnnww3-ejE85N6RcDig6L7F_TLSJM-K7q0O6LcSMoIJGbyBmaYELZXD9rwwTTzVxX0M9ur8UmzHEezuj5YS_s3X8u4vaZcY8J8_v3XSxzjlv0nd-Gg-9bfY754kosR_1S47DQ78KLa0SwKkFBX5BLvUsSpgop7iz4jM_pRgpSwYhqSw; id_token=eyJraWQiOiJtb2NrLWlzc3VlciIsInR5cCI6IkpXVCIsImFsZyI6IlJTMjU2In0.eyJzdWIiOiI3YzU1ZGIyZS04NmI5LTQ2NGEtOTVmZC05YTA3MmVkNWY1NGIiLCJhdWQiOiJpbXBsaWNpdC1tb2NrLWNsaWVudCIsIm5iZiI6MTc1NzM0NTc3NCwiaXNzIjoiaHR0cHM6Ly9vYXV0aDIuaGVyby5kZWVwaW5zaWdodC5pbnRlcm5hbC9tb2NrLWlzc3VlciIsIm5hbWUiOiJNb2NrIHVzZXIiLCJwcmVmZXJyZWRfdXNlcm5hbWUiOiJtb2NrIiwiZXhwIjoxNzU3MzQ5Mzc0LCJpYXQiOjE3NTczNDU3NzQsIm5vbmNlIjoiZWFIZE1oQ1FpTDJFZUxOdjhxd3EiLCJqdGkiOiI2MWY3NmVjZC1kMGNmLTQ2ZjItOWZkZi1hNTFkYzBhYmM2YTkiLCJlbWFpbCI6Im1vY2tAZXhhbXBsZS5jb20ifQ.NvlfVcvdrNtIKCXsPx3EIkEBfAUa6bkfEDsqvHrV4VxylRge8QfmDko79iYP6nj1uOBjiivH9xedH8j0TC9JObH9OYnvkCABB8t94Ll_K8V6ytlYnSz9GxC-qTiRRNrkUgqoCSOf6UcFnzWiaGP2nJX8lLNQkDGEaFoCGjq8rNEPDcASf3NINshrknRq0Lmh46i2kzCrXnR_QcrZCROAh0Ng35xTcljHvmC12yHVAg73hn3C2mVYEyznYnph-RGEh7CH423jhhuJvoC0M-PAxFqD6MWoeqmH7yN3sWRptyosBQ72jkAklxZGNRZM4oQZkHiAwMFUSOlB7NYwrMbGjw"

# --- DO NOT EDIT BELOW THIS LINE ---

HEADERS = {
    "Content-Type": "application/json",
    "Cookie": COOKIE_STRING
}

RAW_TEST_DATA = """
comment_text|klarert|ikke_klarert|kort_varsel|ikke_kort_varsel
Ikke kort varsel. Stue 11|0|0|0|1
Stent ok, kan settes opp til operasjon|1|0|0|0
Stue 11. Klar fra etter påske.|1|0|0|0
PRIO, august|0|0|0|0
CT 10.03 Avvent med å sette opp til op.|0|1|0|0
Tolk: Ukrainsk. Ønsker kort varse|0|0|1|0
Ønsker ikke kort varsel.|0|0|0|1
Avvent, pasient tar kontakt|0|1|0|0
PRIO juni eller august|0|0|0|0
Ønsker å satt på time i august. Studerer i utlandet.|0|0|0|0
PRIO, før sommeren. Kort varsel.|0|0|1|0
Avvent opr. Hjerteutredning.|0|1|0|0
Varsel i god tid|0|0|0|1
Avvent, pas gir tilbakemelding.|0|1|0|0
Stent ok, kan settes til opr.Prio. Ikke stue 11. Høy BMI. CT ok. Etterlyser time.|1|0|0|0
Ring pas jan-26. Stue 11. RT ok. Beh for annen sykdom nå, bruker MEtex.|0|1|0|0
Stue 11. Ny CT|0|1|0|0
"""

def prepare_ground_truth(raw_data: str) -> list[dict]:
    df = pd.read_csv(io.StringIO(raw_data), sep='|')
    test_cases = []
    for _, row in df.iterrows():
        if row['klarert'] == 1:
            status = "cleared"
        elif row['ikke_klarert'] == 1:
            status = "not_cleared"
        else:
            status = "unspecified"
        if row['kort_varsel'] == 1:
            notice = "short_notice_ok"
        elif row['ikke_kort_varsel'] == 1:
            notice = "requires_advance_notice"
        else:
            notice = "unspecified"
        is_priority = "prio" in row['comment_text'].lower()
        test_cases.append({
            "comment_text": row['comment_text'],
            "expected": {
                "status": status,
                "notice_preference": notice,
                "is_priority": is_priority,
            }
        })
    return test_cases

async def run_single_test(client: httpx.AsyncClient, test_case: dict) -> dict:
    """
    Calls the API and compares the new schema against the expected logic.
    """
    comment = test_case["comment_text"]
    expected = test_case["expected"]
    
    try:
        response = await client.post(API_URL, json={"comment_text": comment}, timeout=30.0)
        response.raise_for_status()
        
        # --- FIX: The API is returning a nested 'en' object again. We need to extract it. ---
        raw_response = response.json()
        actual = raw_response.get("en", {}) # Get the English dictionary

        # Map new API response schema to the expected test logic
        expected_status = expected["status"]
        actual_ready = actual.get("patient_ready")
        if expected_status == "cleared":
            status_ok = actual_ready is True
        elif expected_status == "not_cleared":
            status_ok = actual_ready is False
        else:  # unspecified
            status_ok = actual_ready is None

        expected_notice = expected["notice_preference"]
        actual_short_notice = actual.get("patient_short_notice")
        if expected_notice == "short_notice_ok":
            notice_ok = actual_short_notice is True
        elif expected_notice == "requires_advance_notice":
            notice_ok = actual_short_notice is False
        else:  # unspecified
            notice_ok = actual_short_notice is None

        priority_ok = actual.get("patient_prioritized") == expected["is_priority"]
        
        return {
            "comment_text": comment,
            "expected": expected,
            "actual": actual,
            "results": {
                "status": status_ok,
                "notice": notice_ok,
                "priority": priority_ok,
                "overall": all([status_ok, notice_ok, priority_ok])
            },
            "error": None
        }

    except httpx.RequestError as e:
        return {"comment_text": comment, "expected": expected, "actual": None, "results": None, "error": f"Request failed: {e}"}
    except Exception as e:
        return {"comment_text": comment, "expected": expected, "actual": None, "results": None, "error": f"An unexpected error occurred: {e}"}

def print_report(results: list[dict]):
    total_tests = len(results)
    successes = {
        "status": sum(1 for r in results if r["results"] and r["results"]["status"]),
        "notice": sum(1 for r in results if r["results"] and r["results"]["notice"]),
        "priority": sum(1 for r in results if r["results"] and r["results"]["priority"]),
        "overall": sum(1 for r in results if r["results"] and r["results"]["overall"]),
    }
    failures = [r for r in results if not (r["results"] and r["results"]["overall"])]
    errors = [r for r in results if r["error"]]

    print("\n--- Endpoint Benchmark Report ---")
    print(f"API Endpoint: {API_URL}")
    print(f"Total Test Cases: {total_tests}\n")

    print("--- Accuracy ---")
    if total_tests > 0:
        print(f"Overall Accuracy: {successes['overall'] / total_tests:.2%} ({successes['overall']}/{total_tests})")
        print(f"  - Status Label:   {successes['status'] / total_tests:.2%} ({successes['status']}/{total_tests})")
        print(f"  - Notice Label:   {successes['notice'] / total_tests:.2%} ({successes['notice']}/{total_tests})")
        print(f"  - Priority Label: {successes['priority'] / total_tests:.2%} ({successes['priority']}/{total_tests})")
    
    if failures:
        print("\n--- Detailed Failures ---")
        for i, failure in enumerate(failures):
            print(f"\n[{i+1}] Comment: \"{failure['comment_text']}\"")
            print(f"  - Expected: {failure['expected']}")
            print(f"  - Actual:   {failure.get('actual', 'N/A')}")
            if failure.get("actual") and "reasoning" in failure["actual"]:
                 print(f"  - Model Reasoning: \"{failure['actual']['reasoning']}\"")

    if errors:
        print("\n--- API Errors ---")
        for i, error in enumerate(errors):
            print(f"\n[{i+1}] Comment: \"{error['comment_text']}\"")
            print(f"  - Error: {error['error']}")

    print("\n--- Report Complete ---")

async def main():
    print("Preparing test data...")
    test_cases = prepare_ground_truth(RAW_TEST_DATA)
    print(f"Starting benchmark with {len(test_cases)} test cases...")
    async with httpx.AsyncClient(headers=HEADERS, verify=False) as client:
        tasks = [run_single_test(client, case) for case in test_cases]
        results = await tqdm.gather(*tasks, desc="Running tests")
    print_report(results)

if __name__ == "__main__":
    asyncio.run(main())

