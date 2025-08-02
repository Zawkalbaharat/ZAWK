import gspread
from google.oauth2.service_account import Credentials
import pandas as pd

def get_client():
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_file("zawk-approvals-2cd13c2e6d93.json", scopes=scope)
    client = gspread.authorize(creds)
    return client

def read_sheet(sheet_name):
    client = get_client()
    sheet = client.open(sheet_name).sheet1
    data = sheet.get_all_records()
    return pd.DataFrame(data, dtype=str)

def write_sheet(sheet_name, df):
    client = get_client()
    sheet = client.open(sheet_name).sheet1
    sheet.clear()
    sheet.update([df.columns.values.tolist()] + df.values.tolist())
