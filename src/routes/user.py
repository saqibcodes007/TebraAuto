# Flask and standard library imports
import os
import traceback
from flask import Blueprint, request, jsonify, current_app, send_file, session
import io # For handling file stream

# Imports from your Colab script (PART 1, 4, 5)
import pandas as pd
import zeep
import zeep.helpers
from zeep.exceptions import Fault as SoapFault
import datetime # Keep main datetime import
import time
import re
from collections import defaultdict
import pytz # For timezone handling if needed by Tebra functions

user_bp = Blueprint('user_bp', __name__)

UPLOAD_FOLDER = 'temp_files'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Helper: Display Message (from Colab PART 3) ---
def display_message(level, message): # [cite: 11]
    """Prints a formatted message to the server console."""
    print(f"[{level.upper()}] {message}")

# --- Tebra WSDL URL (from Colab PART 2) ---
TEBRA_WSDL_URL = "https://webservice.kareo.com/services/soap/2.1/KareoServices.svc?singleWsdl" # [cite: 8]

# --- 🔐 PART 2 Adaptations (Credentials & API Client) ---
def escape_xml_special_chars(password): # [cite: 3]
    """Escapes special XML characters in the password."""
    password = password.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&apos;') # [cite: 3]
    return password

def create_api_client_adapted(wsdl_url): # [cite: 4]
    """Creates and returns a Zeep client for the Tebra SOAP API."""
    display_message("info", "Attempting to connect to Tebra SOAP API...")
    try:
        from requests import Session # [cite: 4]
        from zeep.transports import Transport # [cite: 4]

        session_req = Session() # [cite: 4]
        session_req.timeout = 60  # Set a timeout for the session (seconds) # [cite: 4]
        transport = Transport(session=session_req, timeout=60) # Set a timeout for the transport # [cite: 4]

        client = zeep.Client(wsdl=wsdl_url, transport=transport) # [cite: 4]
        display_message("info", "✅ Connected to Tebra API.") # [cite: 4]
        return client
    except Exception as e: # [cite: 5]
        display_message("error", f"❌ Failed to connect to Tebra API.") # [cite: 5]
        display_message("error", f"Details: {e}") # [cite: 5]
        return None

def build_request_header_adapted(credentials, client): # [cite: 6, 7]
    """Builds the request header for Tebra API calls."""
    if not client:
        display_message("error", "Cannot build request header: API client is not available.")
        return None
    try:
        header_type = client.get_type('ns0:RequestHeader') # [cite: 7]
        request_header = header_type(
            CustomerKey=credentials['CustomerKey'],
            User=credentials['User'],
            Password=credentials['Password']
        ) # [cite: 7]
        return request_header
    except Exception as e: # [cite: 8]
        display_message("error", f"❌ Error building request header: {e}") # [cite: 8]
        display_message("error", "Ensure the WSDL loaded correctly and 'ns0:RequestHeader' is the correct type.") # [cite: 8]
        return None

# --- 📄 PART 3 Adaptations (File Upload, Validation) ---
EXPECTED_COLUMNS_CONFIG = { # [cite: 13]
    "Patient ID": {"normalized": "patient id", "is_critical_input": True, "purpose": "Input for Phase 1 & 2 & 3 (Patient Identifier)"}, # [cite: 13]
    "Practice": {"normalized": "practice", "is_critical_input": True, "purpose": "Input for Phase 1, 2 & 3 (Practice/Service Location Name & Tebra Practice Context)"}, # [cite: 13]
    "DOS": {"normalized": "dos", "is_critical_input": True, "purpose": "Input for Phase 1 (Insurance Check) & Phase 3 (Encounter DOS)"}, # [cite: 13]
    "Patient Name": {"normalized": "patient name", "is_critical_input": False, "purpose": "Output for Phase 1 (Fetched Patient Name)"}, # [cite: 14]
    "DOB": {"normalized": "dob", "is_critical_input": False, "purpose": "Output for Phase 1 (Fetched Patient DOB)"}, # [cite: 14]
    "Insurance": {"normalized": "insurance", "is_critical_input": False, "purpose": "Output for Phase 1 (Fetched Insurance Name)"}, # [cite: 14]
    "Insurance ID": {"normalized": "insurance id", "is_critical_input": False, "purpose": "Output for Phase 1 (Fetched Insurance Policy #)"}, # [cite: 14]
    "Insurance Status": {"normalized": "insurance status", "is_critical_input": False, "purpose": "Output for Phase 1 (Fetched Insurance Status)"}, # [cite: 14]
    "PP Batch #": {"normalized": "pp batch #", "is_critical_input": True, "purpose": "Input for Phase 2 (Payment Batch)"}, # [cite: 15]
    "Patient Payment": {"normalized": "patient payment", "is_critical_input": True, "purpose": "Input for Phase 2 (Payment Amount)"}, # [cite: 15]
    "Patient Payment Source": {"normalized": "patient payment source", "is_critical_input": True, "purpose": "Input for Phase 2 (Payment Source)"}, # [cite: 15]
    "Reference Number": {"normalized": "reference number", "is_critical_input": False, "purpose": "Input for Phase 2 (Payment Reference, optional)"}, # [cite: 15]
    "CE Batch #": {"normalized": "ce batch #", "is_critical_input": False, "purpose": "Input for Phase 3 (Encounter Batch Number, optional)"}, # [cite: 16]
    "Rendering Provider": {"normalized": "rendering provider", "is_critical_input": False, "purpose": "Input for Phase 3 (Rendering Provider Name)"}, # [cite: 16]
    "Scheduling Provider": {"normalized": "scheduling provider", "is_critical_input": False, "purpose": "Input for Phase 3 (Scheduling Provider Name, optional)"}, # [cite: 16]
    "Encounter Mode": {"normalized": "encounter mode", "is_critical_input": False, "purpose": "Input for Phase 3 (e.g., Tele Health, In Office - used with POS)"}, # [cite: 16]
    "POS": {"normalized": "pos", "is_critical_input": False, "purpose": "Input for Phase 3 (Place of Service Code, e.g., 10, 11)"}, # [cite: 16]
    "Procedures": {"normalized": "procedures", "is_critical_input": False, "purpose": "Input for Phase 3 (Procedure Code)"}, # [cite: 17]
    "Mod 1": {"normalized": "mod 1", "is_critical_input": False, "purpose": "Input for Phase 3 (Modifier 1, optional)"}, # [cite: 17]
    "Mod 2": {"normalized": "mod 2", "is_critical_input": False, "purpose": "Input for Phase 3 (Modifier 2, optional)"}, # [cite: 17]
    "Mod 3": {"normalized": "mod 3", "is_critical_input": False, "purpose": "Input for Phase 3 (Modifier 3, optional)"}, # [cite: 17]
    "Mod 4": {"normalized": "mod 4", "is_critical_input": False, "purpose": "Input for Phase 3 (Modifier 4, optional)"}, # [cite: 17]
    "Units": {"normalized": "units", "is_critical_input": False, "purpose": "Input for Phase 3 (Procedure Units)"}, # [cite: 18]
    "Diag 1": {"normalized": "diag 1", "is_critical_input": False, "purpose": "Input for Phase 3 (Diagnosis Code 1)"}, # [cite: 18]
    "Diag 2": {"normalized": "diag 2", "is_critical_input": False, "purpose": "Input for Phase 3 (Diagnosis Code 2, optional)"}, # [cite: 18]
    "Diag 3": {"normalized": "diag 3", "is_critical_input": False, "purpose": "Input for Phase 3 (Diagnosis Code 3, optional)"}, # [cite: 18]
    "Diag 4": {"normalized": "diag 4", "is_critical_input": False, "purpose": "Input for Phase 3 (Diagnosis Code 4, optional)"}, # [cite: 18]
    "Charge Amount": {"normalized": "charge amount", "is_critical_input": False, "purpose": "Output for Phase 3 (Fetched Encounter Charge Amount)"}, # [cite: 19]
    "Charge Status": {"normalized": "charge status", "is_critical_input": False, "purpose": "Output for Phase 3 (Fetched Encounter Status)"}, # [cite: 19]
    "Encounter ID": {"normalized": "encounter id", "is_critical_input": False, "purpose": "Output for Phase 3 (Created Encounter ID)"}, # [cite: 19]
}

def normalize_header_name_adapted(header_name): # [cite: 19]
    """Converts header to lowercase, trims, and replaces multiple spaces with a single space."""
    if pd.isna(header_name) or not isinstance(header_name, str): # [cite: 19]
        return ""
    return ' '.join(str(header_name).lower().strip().split()) # [cite: 19]

def validate_spreadsheet_adapted(file_stream, filename_str): # [cite: 20]
    df_temp = None
    actual_column_headers_map = {} # [cite: 11]
    error_messages = []

    # Reset for re-runs if EXPECTED_COLUMNS_CONFIG is modified (it's not in this flow per request)
    for config_item in EXPECTED_COLUMNS_CONFIG.values(): # [cite: 21]
        config_item["actual_header_found"] = None

    display_message("info", f"Processing uploaded file stream for: '{filename_str}'")

    try:
        if filename_str.lower().endswith('.csv'): # [cite: 22]
            display_message("info", "Reading as CSV file...") # [cite: 22]
            df_temp = pd.read_csv(file_stream, dtype=str, keep_default_na=True) # [cite: 22]
        elif filename_str.lower().endswith(('.xlsx', '.xls')): # [cite: 23]
            display_message("info", "Reading as Excel file...") # [cite: 23]
            df_temp = pd.read_excel(file_stream, dtype=str, keep_default_na=True) # [cite: 23]
        else:
            error_messages.append(f"Unsupported file type: '{filename_str}'. Please upload a CSV or XLSX file.") # [cite: 24]
            return None, {}, error_messages

        display_message("info", f"Successfully read '{filename_str}'. Initial columns: {df_temp.columns.tolist()}") # [cite: 24]

        if not df_temp.empty: # [cite: 24]
            first_cell_first_data_row = str(df_temp.iloc[0, 0]).lower() # [cite: 25]
            if "script will read this from excel" in first_cell_first_data_row or \
               ("practice" == first_cell_first_data_row and len(df_temp.columns) > 1 and "patient id" == str(df_temp.iloc[0,1]).lower()): # [cite: 25]
                display_message("info", "Detected and skipping the descriptive first data row.") # [cite: 25]
                df_temp = df_temp.iloc[1:].reset_index(drop=True) # [cite: 25]

        display_message("info", f"DataFrame ready for validation. Found {len(df_temp.columns)} columns and {len(df_temp)} actual data rows.") # [cite: 26]
        if df_temp.empty and len(df_temp.columns) > 0 : # [cite: 26]
             display_message("warning", "The file contains headers (and possibly a descriptor row) but no actual data rows.") # [cite: 26]
        elif df_temp.empty: # [cite: 27]
            error_messages.append("The file appears to be empty or has an unexpected structure after header processing.") # [cite: 27]
            return None, {}, error_messages
    except Exception as e: # [cite: 27]
        error_messages.append(f"Error reading or initially processing file '{filename_str}': {e}") # [cite: 27]
        return None, {}, error_messages

    actual_headers_from_file = df_temp.columns.tolist() # [cite: 27]
    normalized_headers_map_from_file = {normalize_header_name_adapted(h): h for h in actual_headers_from_file} # [cite: 27]

    missing_critical_inputs = [] # [cite: 28]
    found_all_critical = True # [cite: 28]

    for logical_name, config in EXPECTED_COLUMNS_CONFIG.items(): # [cite: 29]
        normalized_expected = config["normalized"] # [cite: 29]
        actual_header_found_in_file = normalized_headers_map_from_file.get(normalized_expected) # [cite: 29]

        if actual_header_found_in_file: # [cite: 29]
            actual_column_headers_map[logical_name] = actual_header_found_in_file # [cite: 29]
            config["actual_header_found"] = actual_header_found_in_file # [cite: 29]
        elif config["is_critical_input"]: # [cite: 29]
            missing_critical_inputs.append(logical_name) # [cite: 29]
            found_all_critical = False # [cite: 29]
        else: # Not critical and not found by normalized name, will use logical name # [cite: 30]
            actual_column_headers_map[logical_name] = logical_name # [cite: 30]


    if not found_all_critical: # [cite: 30]
        error_messages.append("CRITICAL INPUT COLUMNS ARE MISSING OR MISMATCHED based on normalized names:") # [cite: 30]
        for col_name in missing_critical_inputs: # [cite: 30]
            error_messages.append(f"  - Logical Name: '{col_name}' (Script expects normalized: '{EXPECTED_COLUMNS_CONFIG[col_name]['normalized']}') - Not found in file's normalized headers.") # [cite: 30]
        return None, actual_column_headers_map, error_messages

    display_message("info", "All critical input columns found and mapped successfully.") # [cite: 31]

    output_columns_to_ensure = { # [cite: 34]
        "Patient Name": actual_column_headers_map.get("Patient Name", "Patient Name"), # [cite: 34]
        "DOB": actual_column_headers_map.get("DOB", "DOB"), # [cite: 34]
        "Insurance": actual_column_headers_map.get("Insurance", "Insurance"), # [cite: 34]
        "Insurance ID": actual_column_headers_map.get("Insurance ID", "Insurance ID"), # [cite: 34]
        "Insurance Status": actual_column_headers_map.get("Insurance Status", "Insurance Status"), # [cite: 34]
        "Charge Amount": actual_column_headers_map.get("Charge Amount", "Charge Amount"), # [cite: 34]
        "Charge Status": actual_column_headers_map.get("Charge Status", "Charge Status"), # [cite: 34]
        "Encounter ID": actual_column_headers_map.get("Encounter ID", "Encounter ID"), # [cite: 35]
        "Error": "Error" # [cite: 35]
    }

    for logical_output_name, actual_col_name_to_use in output_columns_to_ensure.items(): # [cite: 35]
        if actual_col_name_to_use not in df_temp.columns: # [cite: 35]
            df_temp[actual_col_name_to_use] = "" # [cite: 35]
            display_message("info", f"Column '{actual_col_name_to_use}' (for {logical_output_name}) added to DataFrame.") # [cite: 35]
        elif logical_output_name == "Error": # Ensure "Error" column is initialized (cleared) # [cite: 36]
             df_temp[actual_col_name_to_use] = "" # [cite: 36]
    return df_temp, actual_column_headers_map, error_messages


# --- 🛠️ PART 4: Core Utility Functions (Adapted from Colab) ---

def is_date_value_present(date_str): # [cite: 38]
    """Checks if a date string is not None, not empty, and not the literal string 'None'."""
    if pd.isna(date_str) or date_str is None: # [cite: 38]
        return False
    s = str(date_str).strip() # [cite: 38]
    if not s: # [cite: 39]
        return False
    if s.lower() == 'none': # [cite: 39]
        return False
    return True # [cite: 39]

PAYMENT_SOURCE_TO_CODE = { # [cite: 39]
    "CHECK": "1", # [cite: 39]
    "CREDIT CARD": "3", # [cite: 39]
    "CC": "3", # [cite: 40]
    "ELECTRONIC FUNDS TRANSFER": "4", # [cite: 40]
    "EFT": "4", # [cite: 40]
    "CASH": "5" # [cite: 40]
}

def get_payment_source_code(source_str): # [cite: 40]
    """Normalizes payment source string and returns Tebra code."""
    if pd.isna(source_str) or not source_str: # [cite: 40]
        return None
    normalized_source = str(source_str).strip().upper() # [cite: 40]
    return PAYMENT_SOURCE_TO_CODE.get(normalized_source) # [cite: 40]

def get_practice_id_by_name(client_obj, header_obj, practice_name_to_find, cache_dict): # [cite: 41]
    """
    Fetches PracticeID from Tebra based on PracticeName.
    Uses a cache to avoid repeated API calls for the same practice name.
    """
    if pd.isna(practice_name_to_find) or not str(practice_name_to_find).strip(): # [cite: 42]
        display_message("warning", "[GetPracticeID] Practice name is missing or empty. Cannot fetch ID.") # [cite: 42]
        return None

    normalized_practice_name = str(practice_name_to_find).strip().lower() # [cite: 42]
    if normalized_practice_name in cache_dict: # [cite: 42]
        display_message("debug", f"[GetPracticeID] Found '{practice_name_to_find}' (Practice Context) in cache. ID: {cache_dict[normalized_practice_name]}") # [cite: 42]
        return cache_dict[normalized_practice_name] # [cite: 42]

    display_message("info", f"[GetPracticeID] Practice '{practice_name_to_find}' (Practice Context) not in cache. Querying Tebra API...") # [cite: 42]
    try:
        GetPracticesReqType = client_obj.get_type('ns0:GetPracticesReq') # [cite: 43]
        PracticeFilterType = client_obj.get_type('ns0:PracticeFilter') # [cite: 43]
        PracticeFieldsToReturnType = client_obj.get_type('ns0:PracticeFieldsToReturn') # [cite: 43]

        practice_filter = PracticeFilterType(PracticeName=str(practice_name_to_find).strip()) # [cite: 43]
        fields_to_return = PracticeFieldsToReturnType(ID=True, PracticeName=True, Active=True) # [cite: 43]

        request_payload = GetPracticesReqType( # [cite: 43]
            RequestHeader=header_obj,
            Filter=practice_filter,
            Fields=fields_to_return
        )
        api_response = client_obj.service.GetPractices(request=request_payload) # [cite: 44]

        if hasattr(api_response, 'ErrorResponse') and api_response.ErrorResponse and api_response.ErrorResponse.IsError: # [cite: 44]
            display_message("error", f"[GetPracticeID] API Error fetching practice '{practice_name_to_find}': {api_response.ErrorResponse.ErrorMessage}") # [cite: 44]
            return None
        if hasattr(api_response, 'SecurityResponse') and api_response.SecurityResponse and not api_response.SecurityResponse.Authorized: # [cite: 44]
            display_message("error", f"[GetPracticeID] API Authorization Error fetching practice '{practice_name_to_find}': {api_response.SecurityResponse.SecurityResult}") # [cite: 44]
            return None # [cite: 45]

        if hasattr(api_response, 'Practices') and api_response.Practices and \
           hasattr(api_response.Practices, 'PracticeData') and api_response.Practices.PracticeData: # [cite: 45]

            all_practices_data = api_response.Practices.PracticeData # [cite: 45]
            if not isinstance(all_practices_data, list): # [cite: 45]
                all_practices_data = [all_practices_data] # [cite: 45]

            found_practice_id_val = None # [cite: 45]
            for p_data in all_practices_data: # [cite: 46]
                api_practice_name = getattr(p_data, 'PracticeName', '') # [cite: 46]
                is_active_str = getattr(p_data, 'Active', 'false') # [cite: 46]

                if str(api_practice_name).strip().lower() == normalized_practice_name: # [cite: 46]
                    if str(is_active_str).strip().lower() == 'true': # [cite: 46]
                        found_practice_id_val = getattr(p_data, 'ID', None) # [cite: 47]
                        display_message("info", f"[GetPracticeID] Exact match found for ACTIVE practice '{practice_name_to_find}'. ID: {found_practice_id_val}") # [cite: 47]
                        break # [cite: 48]
                    else: # [cite: 48]
                        display_message("warning", f"[GetPracticeID] Practice '{practice_name_to_find}' found but is INACTIVE (ID: {getattr(p_data, 'ID', 'N/A')}). Will prioritize active match if available.") # [cite: 48]
                        if not found_practice_id_val: # This line appears to be a bug in original if an inactive is found first, then an active one. # [cite: 49]
                             found_practice_id_val = getattr(p_data, 'ID', 'N/A') # This line means an inactive ID could be stored if it's found before an active one for the same name.

            if found_practice_id_val and str(found_practice_id_val) != 'N/A': # Check if it's not the placeholder 'N/A'
                final_id_to_cache = str(found_practice_id_val) # [cite: 49]
                cache_dict[normalized_practice_name] = final_id_to_cache # [cite: 49]
                return final_id_to_cache # [cite: 50]
            else: # [cite: 50]
                display_message("warning", f"[GetPracticeID] No exact match found for ACTIVE practice named '{practice_name_to_find}' in Tebra.") # [cite: 50]
                return None
        else: # [cite: 50]
            display_message("warning", f"[GetPracticeID] No 'Practices' data returned by API for filter name '{practice_name_to_find}'.") # [cite: 50]
            return None # [cite: 51]

    except zeep.exceptions.Fault as soap_fault: # [cite: 51]
        display_message("error", f"[GetPracticeID] SOAP FAULT fetching practice '{practice_name_to_find}': {soap_fault.message}") # [cite: 51]
    except Exception as e: # [cite: 51]
        display_message("error", f"[GetPracticeID] Unexpected error fetching practice '{practice_name_to_find}': {type(e).__name__} - {e}") # [cite: 51]
    return None

def phase1_fetch_patient_and_insurance(client_obj, header_obj, patient_id_str, practice_name_context, dos_str): # [cite: 51]
    results = { # [cite: 51]
        'FetchedPatientName': None, 'FetchedPatientDOB': None, # [cite: 51]
        'FetchedInsuranceName': None, 'FetchedInsuranceID': None, # [cite: 52]
        'FetchedInsuranceStatus': "Error during fetch", # [cite: 52]
        'SimpleError': None # [cite: 52]
    }
    if pd.isna(patient_id_str) or not str(patient_id_str).strip(): # [cite: 52]
        results['SimpleError'] = "Patient ID is missing." # [cite: 52]
        results['FetchedInsuranceStatus'] = "Patient ID Missing" # [cite: 52]
        return results # [cite: 52]
    patient_id_int = None # [cite: 52]
    try:
        patient_id_int = int(float(str(patient_id_str).strip())) # [cite: 52]
    except ValueError: # [cite: 52]
        results['SimpleError'] = f"Invalid Patient ID format: '{patient_id_str}'." # [cite: 53]
        results['FetchedInsuranceStatus'] = "Invalid Patient ID" # [cite: 53]
        return results # [cite: 53]
    dos_date_obj = None # [cite: 53]
    dos_available_for_check = False # [cite: 53]
    if is_date_value_present(dos_str): # [cite: 53]
        try:
            dos_date_obj = pd.to_datetime(dos_str).date() # [cite: 53]
            dos_available_for_check = True # [cite: 53]
        except Exception as e: # [cite: 53]
            existing_error = results['SimpleError'] + "; " if results['SimpleError'] else "" # [cite: 54, 55]
            results['SimpleError'] = existing_error + f"Invalid DOS format '{dos_str}': {e}" # [cite: 55]
            results['FetchedInsuranceStatus'] = "Invalid DOS for Check" # [cite: 55]
    else: # [cite: 55]
        results['FetchedInsuranceStatus'] = "DOS Missing for Check" # [cite: 55]
    display_message("info", f"[Phase1] Fetching Patient/Ins for ID: {patient_id_int}, Practice (context): {practice_name_context}, Effective DOS for check: {dos_date_obj if dos_available_for_check else 'N/A'}") # [cite: 55]
    try:
        GetPatientReqType = client_obj.get_type('ns0:GetPatientReq') # [cite: 55]
        SinglePatientFilterType = client_obj.get_type('ns0:SinglePatientFilter') # [cite: 56]
        patient_filter = SinglePatientFilterType(PatientID=patient_id_int) # [cite: 56]
        request_payload = GetPatientReqType(RequestHeader=header_obj, Filter=patient_filter) # [cite: 56]
        api_response = client_obj.service.GetPatient(request=request_payload) # [cite: 56]
        if hasattr(api_response, 'ErrorResponse') and api_response.ErrorResponse and api_response.ErrorResponse.IsError: # [cite: 56]
            results['SimpleError'] = f"API Error (GetPatient): {api_response.ErrorResponse.ErrorMessage}" # [cite: 56]
            results['FetchedInsuranceStatus'] = "API Error (Patient)" # [cite: 56]
            return results # [cite: 56]
        if hasattr(api_response, 'SecurityResponse') and api_response.SecurityResponse and not api_response.SecurityResponse.Authorized: # [cite: 57]
            results['SimpleError'] = f"API Auth Error (GetPatient): {api_response.SecurityResponse.SecurityResult}" # [cite: 57]
            results['FetchedInsuranceStatus'] = "API Auth Error (Patient)" # [cite: 57]
            return results # [cite: 57]
        if hasattr(api_response, 'Patient') and api_response.Patient: # [cite: 57]
            patient_data = api_response.Patient # [cite: 57]
            first_name = getattr(patient_data, 'FirstName', '') # [cite: 57]
            last_name = getattr(patient_data, 'LastName', '') # [cite: 58]
            results['FetchedPatientName'] = f"{first_name} {last_name}".strip() # [cite: 58]
            dob_api_val = getattr(patient_data, 'DOB', None) # [cite: 58]
            if is_date_value_present(dob_api_val): # [cite: 58]
                try:
                    results['FetchedPatientDOB'] = pd.to_datetime(dob_api_val).strftime('%Y-%m-%d') # [cite: 58]
                except Exception: # [cite: 59]
                    results['FetchedPatientDOB'] = str(dob_api_val) # [cite: 59]
            if not dos_available_for_check: # [cite: 59]
                 pass # [cite: 59]
            elif hasattr(patient_data, 'Cases') and patient_data.Cases and \
              hasattr(patient_data.Cases, 'PatientCaseData') and patient_data.Cases.PatientCaseData: # [cite: 59, 60]
                all_cases_data = patient_data.Cases.PatientCaseData # [cite: 60]
                all_cases = all_cases_data if isinstance(all_cases_data, list) else [all_cases_data] # [cite: 60]
                active_policies_found = [] # [cite: 60]
                for case_item in all_cases: # [cite: 60]
                   if hasattr(case_item, 'InsurancePolicies') and case_item.InsurancePolicies and \
                       hasattr(case_item.InsurancePolicies, 'PatientInsurancePolicyData') and \
                       case_item.InsurancePolicies.PatientInsurancePolicyData: # [cite: 61]
                        policies_on_case_raw = case_item.InsurancePolicies.PatientInsurancePolicyData # [cite: 61]
                        policies_on_case = policies_on_case_raw if isinstance(policies_on_case_raw, list) else [policies_on_case_raw] # [cite: 62]
                        for policy_obj in policies_on_case: # [cite: 62]
                            policy_name = getattr(policy_obj, 'PlanName', getattr(policy_obj, 'CompanyName', 'N/A')) # [cite: 62]
                            policy_num = getattr(policy_obj, 'Number', 'N/A') # [cite: 63]
                            eff_start_str = getattr(policy_obj, 'EffectiveStartDate', None) # [cite: 63]
                            eff_end_str = getattr(policy_obj, 'EffectiveEndDate', None) # [cite: 63]
                            is_active_on_dos = False # [cite: 63]
                            has_valid_start = is_date_value_present(eff_start_str) # [cite: 64]
                            has_valid_end = is_date_value_present(eff_end_str) # [cite: 64]
                            if has_valid_start: # [cite: 64]
                                try: # [cite: 65]
                                    eff_start_date = pd.to_datetime(eff_start_str).date() # [cite: 65]
                                    if eff_start_date <= dos_date_obj: # [cite: 65]
                                        if not has_valid_end: # [cite: 66]
                                            is_active_on_dos = True # [cite: 66]
                                        else: # [cite: 67]
                                            eff_end_date = pd.to_datetime(eff_end_str).date() # [cite: 67]
                                            if eff_end_date >= dos_date_obj: # [cite: 68]
                                                is_active_on_dos = True # [cite: 68]
                                except Exception: pass # [cite: 69]
                            elif not has_valid_start and not has_valid_end: # [cite: 69] # This implies always active if no dates
                                is_active_on_dos = True # [cite: 69]
                            if is_active_on_dos: # [cite: 69, 70]
                                active_policies_found.append({'name': policy_name, 'id': policy_num}) # [cite: 70]
                if not active_policies_found: # [cite: 70]
                    results['FetchedInsuranceStatus'] = "No Active Insurance Found" # [cite: 70]
                elif len(active_policies_found) == 1: # [cite: 70]
                    results['FetchedInsuranceName'] = active_policies_found[0]['name'] # [cite: 71]
                    results['FetchedInsuranceID'] = active_policies_found[0]['id'] # [cite: 71]
                    results['FetchedInsuranceStatus'] = "Active" # [cite: 71]
                else: # Multiple active policies # [cite: 71]
                    results['FetchedInsuranceName'] = "; ".join(p['name'] for p in active_policies_found) # [cite: 72]
                    results['FetchedInsuranceID'] = "; ".join(p['id'] for p in active_policies_found) # [cite: 73]
                    results['FetchedInsuranceStatus'] = "Multiple Active Found" # [cite: 73]
            else: # No cases or case data # [cite: 73]
                results['FetchedInsuranceStatus'] = "No Insurance Policies Found" # [cite: 73]
        else: # No patient data # [cite: 73]
            results['SimpleError'] = "Patient data not found in Tebra API response." # [cite: 73]
            results['FetchedInsuranceStatus'] = "Patient Not Found" # [cite: 74]
    except zeep.exceptions.Fault as soap_fault: # [cite: 74]
        results['SimpleError'] = f"SOAP FAULT (GetPatient): {soap_fault.message}" # [cite: 74]
        results['FetchedInsuranceStatus'] = "SOAP Error (Patient)" # [cite: 74]
    except Exception as e: # [cite: 74]
        results['SimpleError'] = f"Unexpected error in Phase 1 (GetPatient): {type(e).__name__} - {str(e)}" # [cite: 74]
        results['FetchedInsuranceStatus'] = "System Error (Patient)" # [cite: 74]
    if results['SimpleError']: # [cite: 74]
        display_message("warning", f"[Phase1] Patient {patient_id_int if patient_id_int else patient_id_str}: {results['SimpleError']}") # [cite: 74]
    return results # [cite: 74]

def phase2_post_tebra_payment(client_obj, header_obj, patient_id_str, resolved_practice_id_str, # [cite: 75]
                              practice_name_context, pp_batch_str, payment_amount_input_str,
                              payment_source_input_str, payment_ref_num_str):
    """
    Posts a patient payment to Tebra.
    Assumes PostDate is omitted for Tebra default. [cite: 76]
    """
    results = {'Success': False, 'Message': "Processing not initiated.", # [cite: 76]
               'SimpleMessage': "Payment not processed.", 'PaymentID': None} # [cite: 76]

    critical_payment_fields = { # [cite: 76]
        "Patient ID": patient_id_str, # [cite: 76]
        "Practice ID": resolved_practice_id_str, # [cite: 76]
        "PP Batch #": pp_batch_str, # [cite: 77]
        "Patient Payment": payment_amount_input_str, # [cite: 77]
        "Patient Payment Source": payment_source_input_str # [cite: 77]
    }
    missing_or_invalid_fields = [] # [cite: 77]
    for field_name, field_value in critical_payment_fields.items(): # [cite: 77]
        if pd.isna(field_value) or not str(field_value).strip() or str(field_value).strip().lower() == 'nan': # [cite: 77]
            missing_or_invalid_fields.append(field_name) # [cite: 77]

    if missing_or_invalid_fields: # [cite: 77]
        results['SimpleMessage'] = f"P2 Skipped: Missing/invalid core payment data: {', '.join(missing_or_invalid_fields)}." # [cite: 78]
        return results # [cite: 78]

    try:
        cleaned_amount_str = str(payment_amount_input_str).replace('$', '').replace(',', '').strip() # [cite: 78]
        amount_float = float(cleaned_amount_str) # [cite: 78]
        if amount_float <= 0: # Typically payments should be positive # [cite: 79]
            results['SimpleMessage'] = f"P2 Invalid: Payment amount ${amount_float:.2f} must be > 0." # [cite: 79]
            display_message("warning", f"[Phase2] Pt {patient_id_str}: {results['SimpleMessage']}") # [cite: 79]
            return results # [cite: 79]
        amount_to_post_str = f"{amount_float:.2f}" # [cite: 79]
    except ValueError: # [cite: 79]
        results['SimpleMessage'] = f"P2 Invalid: Payment amount format '{payment_amount_input_str}'." # [cite: 79]
        display_message("warning", f"[Phase2] Pt {patient_id_str}: {results['SimpleMessage']}") # [cite: 80]
        return results # [cite: 80]

    payment_method_code = get_payment_source_code(payment_source_input_str) # [cite: 80]
    if not payment_method_code: # [cite: 80]
        results['SimpleMessage'] = f"P2 Invalid: Unmapped payment source '{payment_source_input_str}'." # [cite: 80]
        display_message("warning", f"[Phase2] Pt {patient_id_str}: {results['SimpleMessage']}") # [cite: 80]
        return results # [cite: 80]

    display_message("info", f"[Phase2] Attempting to post payment for Pt ID: {patient_id_str}, Practice ID: {resolved_practice_id_str}, Amount: ${amount_to_post_str}, Batch: {pp_batch_str}") # [cite: 80]
    try: # [cite: 81]
        CreatePaymentRequestType = client_obj.get_type('ns0:CreatePaymentRequest') # [cite: 81]
        PaymentCreateType = client_obj.get_type('ns0:PaymentCreate') # [cite: 81]
        PaymentPatientCreateType = client_obj.get_type('ns0:PaymentPatientCreate') # [cite: 81]
        PaymentPaymentCreateType = client_obj.get_type('ns0:PaymentPaymentCreate') # [cite: 81]
        PaymentPracticeCreateType = client_obj.get_type('ns0:PaymentPracticeCreate') # [cite: 81]

        patient_data = PaymentPatientCreateType(PatientID=str(patient_id_str).strip()) # [cite: 81]
        payment_data_obj = PaymentPaymentCreateType( # [cite: 82]
            AmountPaid=amount_to_post_str, # [cite: 82]
            PaymentMethod=payment_method_code, # [cite: 82]
            ReferenceNumber=str(payment_ref_num_str if pd.notna(payment_ref_num_str) else '').strip() # [cite: 82]
        )
        practice_data_obj = PaymentPracticeCreateType( # [cite: 82]
            PracticeID=str(resolved_practice_id_str).strip(), # [cite: 82]
            PracticeName=str(practice_name_context).strip() # [cite: 82]
        )
        payment_to_create_obj = PaymentCreateType( # [cite: 83]
            BatchNumber=str(pp_batch_str).strip(), # [cite: 83]
            Patient=patient_data, # [cite: 83]
            PayerType="Patient", # [cite: 83]
            Payment=payment_data_obj, # [cite: 83]
            Practice=practice_data_obj # [cite: 83]
        )
        request_payload = CreatePaymentRequestType(RequestHeader=header_obj, Payment=payment_to_create_obj) # [cite: 83]
        api_response = client_obj.service.CreatePayment(request=request_payload) # [cite: 83]

        if hasattr(api_response, 'ErrorResponse') and api_response.ErrorResponse and api_response.ErrorResponse.IsError: # [cite: 84]
            err_msg = api_response.ErrorResponse.ErrorMessage # [cite: 84]
            results['Message'] = f"API Error (CreatePayment): {err_msg}" # [cite: 84]
            results['SimpleMessage'] = f"P2 API Error ({err_msg[:70]}...)" # [cite: 84]
        elif hasattr(api_response, 'SecurityResponse') and api_response.SecurityResponse and not api_response.SecurityResponse.Authorized: # [cite: 84]
            sec_msg = api_response.SecurityResponse.SecurityResult # [cite: 84]
            results['Message'] = f"API Auth Error (CreatePayment): {sec_msg}" # [cite: 84, 85]
            results['SimpleMessage'] = "P2 API Auth Error." # [cite: 85]
        elif hasattr(api_response, 'PaymentID') and api_response.PaymentID is not None: # [cite: 85]
            results['Success'] = True # [cite: 85]
            results['PaymentID'] = str(api_response.PaymentID) # [cite: 85]
            results['Message'] = f"Payment successfully posted. Tebra Payment ID: {results['PaymentID']}" # [cite: 85, 86]
            results['SimpleMessage'] = f"Payment #{results['PaymentID']} Posted." # [cite: 86]
        else: # [cite: 86]
            results['Message'] = "Payment response from Tebra was unclear (no PaymentID returned and no explicit API error)." # [cite: 86]
            results['SimpleMessage'] = "P2 Status Unknown (unexpected Tebra response)." # [cite: 86]
            display_message("warning", f"[Phase2] Unclear payment response for Pt {patient_id_str}. Response: {zeep.helpers.serialize_object(api_response) if client_obj and api_response else 'Response not available'}") # [cite: 86, 87]
    except zeep.exceptions.Fault as soap_fault: # [cite: 87]
        results['Message'] = f"SOAP FAULT (CreatePayment): {soap_fault.message}" # [cite: 87]
        results['SimpleMessage'] = "P2 Failed (SOAP Error)." # [cite: 87]
    except Exception as e: # [cite: 87]
        results['Message'] = f"Unexpected error during payment creation: {type(e).__name__} - {str(e)}" # [cite: 87]
        results['SimpleMessage'] = f"P2 Failed (System Error: {type(e).__name__})." # [cite: 87]

    log_level = "error" if not results['Success'] else "info" # [cite: 87]
    if results['SimpleMessage'] and "Skipped" not in results['SimpleMessage']: # [cite: 88]
        display_message(log_level, f"[Phase2] Pt {patient_id_str}: {results['SimpleMessage']}") # [cite: 88]
    elif "Skipped" in results['SimpleMessage']: # [cite: 88]
        display_message("debug", f"[Phase2] Pt {patient_id_str}: {results['SimpleMessage']}") # [cite: 88]
    return results # [cite: 88]

# --- HELPER FUNCTIONS FOR PHASE 3: ENCOUNTER CREATION ---
POS_CODE_MAP_PHASE3 = { # [cite: 89]
    "OFFICE": {"code": "11", "name": "Office"}, # [cite: 89]
    "IN OFFICE": {"code": "11", "name": "Office"}, # [cite: 89]
    "INOFFICE": {"code": "11", "name": "Office"}, # [cite: 89]
    "TELEHEALTH": {"code": "10", "name": "Telehealth Provided in Patient’s Home"}, # [cite: 89]
    "TELEHEALTH OFFICE": {"code": "02", "name": "Telehealth Provided Other than in Patient’s Home"}, # [cite: 89]
}

ENCOUNTER_STATUS_CODE_MAP_PHASE3 = { # [cite: 89]
    "0": "Undefined", # [cite: 89]
    "1": "Draft", # [cite: 89]
    "2": "Review", # [cite: 89]
    "3": "Approved", # [cite: 90]
    "4": "Rejected", # [cite: 90]
    "5": "Billed", # [cite: 90]
    "6": "Unpayable",# [cite: 90]
    "7": "Pending", # [cite: 90]
}

def map_encounter_status_code(status_code_str): # [cite: 90]
    """Maps an encounter status code string to a descriptive string."""
    if pd.isna(status_code_str) or not str(status_code_str).strip(): # [cite: 90]
        return "Status N/A" # [cite: 90]
    return ENCOUNTER_STATUS_CODE_MAP_PHASE3.get(str(status_code_str).strip(), f"Unknown Code ({status_code_str})") # [cite: 90]

def format_datetime_for_api_phase3(date_value): # [cite: 90]
    if pd.isna(date_value) or date_value is None: return None # [cite: 90]
    try:
        return pd.to_datetime(date_value).strftime('%Y-%m-%dT%H:%M:%S') # [cite: 90]
    except Exception as e: # [cite: 91]
        display_message("warning", f"[FormatDT_P3] Date parse warning for '{date_value}'. Error: {e}. Using None.") # [cite: 91, 92]
        return None # [cite: 92]

def get_service_location_id_by_name(client_obj, header_obj, service_location_name_to_find, current_practice_id_context, cache_dict): # [cite: 92]
    if pd.isna(service_location_name_to_find) or not str(service_location_name_to_find).strip(): # [cite: 92]
        display_message("warning", "[GetServiceLocID_P3] Service Location name is missing. Cannot fetch ID.") # [cite: 92]
        return None
    if pd.isna(current_practice_id_context): # [cite: 92]
        display_message("error", "[GetServiceLocID_P3] Practice ID context is missing for Service Location lookup.") # [cite: 92]
        return None
    normalized_sl_name = str(service_location_name_to_find).strip().lower() # [cite: 92]
    cache_key = f"sl_{current_practice_id_context}_{normalized_sl_name}" # [cite: 92]
    if cache_key in cache_dict: # [cite: 93]
        display_message("debug", f"[GetServiceLocID_P3] Found SL '{service_location_name_to_find}' in cache. ID: {cache_dict[cache_key]}") # [cite: 93]
        return cache_dict[cache_key] # [cite: 93]
    display_message("info", f"[GetServiceLocID_P3] SL '{service_location_name_to_find}' (PracticeID {current_practice_id_context}) not in cache. Querying API...") # [cite: 93, 94]
    try:
        GetServiceLocationsReqType = client_obj.get_type('ns6:GetServiceLocationsReq') # [cite: 94]
        ServiceLocationFilterType = client_obj.get_type('ns6:ServiceLocationFilter') # [cite: 94]
        ServiceLocationFieldsToReturnType = client_obj.get_type('ns6:ServiceLocationFieldsToReturn') # [cite: 94]
        sl_filter = ServiceLocationFilterType(PracticeID=str(current_practice_id_context)) # [cite: 94]
        fields = ServiceLocationFieldsToReturnType(ID=True, Name=True, PracticeID=True) # [cite: 94]
        request_payload = GetServiceLocationsReqType(RequestHeader=header_obj, Filter=sl_filter, Fields=fields) # [cite: 94]
        api_response = client_obj.service.GetServiceLocations(request=request_payload) # [cite: 94]
        if hasattr(api_response, 'ErrorResponse') and api_response.ErrorResponse and api_response.ErrorResponse.IsError: # [cite: 94]
            display_message("error", f"[GetServiceLocID_P3] API Error for SL '{service_location_name_to_find}': {api_response.ErrorResponse.ErrorMessage}") # [cite: 95]
            return None
        if hasattr(api_response, 'SecurityResponse') and api_response.SecurityResponse and not api_response.SecurityResponse.Authorized: # [cite: 95]
            display_message("error", f"[GetServiceLocID_P3] API Auth Error for SL '{service_location_name_to_find}': {api_response.SecurityResponse.SecurityResult}") # [cite: 95]
            return None
        if hasattr(api_response, 'ServiceLocations') and api_response.ServiceLocations and \
           hasattr(api_response.ServiceLocations, 'ServiceLocationData') and api_response.ServiceLocations.ServiceLocationData: # [cite: 95, 96]
            all_sl_data = api_response.ServiceLocations.ServiceLocationData # [cite: 96]
            if not isinstance(all_sl_data, list): all_sl_data = [all_sl_data] # [cite: 96]
            for sl_data in all_sl_data: # [cite: 96]
                api_sl_name = getattr(sl_data, 'Name', '') # [cite: 96]
                if str(api_sl_name).strip().lower() == normalized_sl_name: # [cite: 96]
                    found_sl_id = getattr(sl_data, 'ID', None) # [cite: 97]
                    if found_sl_id: # [cite: 97]
                        display_message("info", f"[GetServiceLocID_P3] Exact match for SL '{service_location_name_to_find}'. ID: {found_sl_id}") # [cite: 97, 98]
                        cache_dict[cache_key] = str(found_sl_id) # [cite: 98]
                        return str(found_sl_id) # [cite: 98]
            display_message("warning", f"[GetServiceLocID_P3] No exact match found for SL '{service_location_name_to_find}' under PracticeID {current_practice_id_context}.") # [cite: 98]
            return None
        else: # [cite: 98]
            display_message("warning", f"[GetServiceLocID_P3] No 'ServiceLocations' data for PracticeID {current_practice_id_context}.") # [cite: 99]
            return None
    except zeep.exceptions.Fault as soap_fault: display_message("error", f"[GetServiceLocID_P3] SOAP FAULT for SL '{service_location_name_to_find}': {soap_fault.message}") # [cite: 99]
    except Exception as e: display_message("error", f"[GetServiceLocID_P3] Unexpected error for SL '{service_location_name_to_find}': {type(e).__name__} - {e}") # [cite: 99]
    return None

def get_provider_id_by_name_phase3(client_obj, header_obj, provider_name_excel, current_practice_id_context, cache_dict): # [cite: 99]
    if pd.isna(provider_name_excel) or not str(provider_name_excel).strip(): # [cite: 99]
        display_message("warning", "[GetProvID_P3] Provider name is missing.") # [cite: 99]
        return None # [cite: 100]
    if pd.isna(current_practice_id_context): # [cite: 100]
        display_message("error", "[GetProvID_P3] Practice ID context is missing for Provider lookup.") # [cite: 100]
        return None
    provider_search_name = str(provider_name_excel).strip() # [cite: 100]
    normalized_search_name_key = provider_search_name.lower() # [cite: 100]
    cache_key = f"prov_{current_practice_id_context}_{normalized_search_name_key}" # [cite: 100]
    if cache_key in cache_dict: # [cite: 100]
        display_message("debug", f"[GetProvID_P3] Found Provider '{provider_search_name}' in cache. ID: {cache_dict[cache_key]}") # [cite: 100, 101]
        return cache_dict[cache_key] # [cite: 101]
    display_message("info", f"[GetProvID_P3] Provider '{provider_search_name}' (PracticeID {current_practice_id_context}) not in cache. Querying API...") # [cite: 101]
    try:
        GetProvidersReqType = client_obj.get_type('ns0:GetProvidersReq') # [cite: 101]
        ProviderFilterType = client_obj.get_type('ns0:ProviderFilter') # [cite: 101]
        ProviderFieldsToReturnType = client_obj.get_type('ns0:ProviderFieldsToReturn') # [cite: 101]
        fields = ProviderFieldsToReturnType(ID=True, FullName=True, FirstName=True, LastName=True, Active=True, PracticeID=True, Type=True) # [cite: 101]
        exact_filter = ProviderFilterType(FullName=provider_search_name, PracticeID=str(current_practice_id_context)) # [cite: 101]
        resp_exact = client_obj.service.GetProviders(request=GetProvidersReqType(RequestHeader=header_obj, Filter=exact_filter, Fields=fields)) # [cite: 101]
        provider_id_found = None # [cite: 102]
        if not (hasattr(resp_exact, 'ErrorResponse') and resp_exact.ErrorResponse and resp_exact.ErrorResponse.IsError) and \
           not (hasattr(resp_exact, 'SecurityResponse') and resp_exact.SecurityResponse and not resp_exact.SecurityResponse.Authorized) and \
           hasattr(resp_exact, 'Providers') and resp_exact.Providers and hasattr(resp_exact.Providers, 'ProviderData') and resp_exact.Providers.ProviderData: # [cite: 102]
            exact_providers_data = resp_exact.Providers.ProviderData # [cite: 102]
            if not isinstance(exact_providers_data, list): exact_providers_data = [exact_providers_data] # [cite: 102]
            for p_data in exact_providers_data: # [cite: 103]
                is_active = (getattr(p_data, 'Active') is not None and str(getattr(p_data, 'Active')).lower() == 'true') # [cite: 103]
                api_full_name = getattr(p_data, 'FullName', '') # [cite: 103]
                if is_active and str(api_full_name).strip().lower() == normalized_search_name_key: # [cite: 103]
                    provider_id_found = getattr(p_data, 'ID', None) # [cite: 104]
                    if provider_id_found: # [cite: 104]
                        display_message("info", f"[GetProvID_P3] Exact match for ACTIVE Provider '{provider_search_name}'. ID: {provider_id_found}") # [cite: 104, 105]
                        cache_dict[cache_key] = str(provider_id_found) # [cite: 105]
                        return str(provider_id_found) # [cite: 105]
        if not provider_id_found: # [cite: 105]
            display_message("info", f"[GetProvID_P3] No exact active match for '{provider_search_name}'. Trying broader...") # [cite: 105]
            broad_filter = ProviderFilterType(PracticeID=str(current_practice_id_context)) # [cite: 105]
            resp_all = client_obj.service.GetProviders(request=GetProvidersReqType(RequestHeader=header_obj, Filter=broad_filter, Fields=fields)) # [cite: 106]
            if not (hasattr(resp_all, 'ErrorResponse') and resp_all.ErrorResponse and resp_all.ErrorResponse.IsError) and \
               not (hasattr(resp_all, 'SecurityResponse') and resp_all.SecurityResponse and not resp_all.SecurityResponse.Authorized) and \
               hasattr(resp_all, 'Providers') and resp_all.Providers and hasattr(resp_all.Providers, 'ProviderData') and resp_all.Providers.ProviderData: # [cite: 106]
                all_providers_data_broad = resp_all.Providers.ProviderData # [cite: 106]
                if not isinstance(all_providers_data_broad, list): all_providers_data_broad = [all_providers_data_broad] # [cite: 107]
                found_providers_flex = [] # [cite: 107]
                terms = [t.lower() for t in provider_search_name.replace(',', '').replace('.', '').split() if t.lower() not in ['md', 'do', 'pa', 'np'] and t] # [cite: 107]
                if not terms: terms = [normalized_search_name_key] # [cite: 107]
                for p_item in all_providers_data_broad: # [cite: 108]
                    is_active = (getattr(p_item, 'Active') is not None and str(getattr(p_item, 'Active')).lower() == 'true') # [cite: 108]
                    if not is_active: continue # [cite: 108]
                    name_api = str(getattr(p_item, 'FullName', '')).strip().lower() # [cite: 108]
                    if not name_api: continue # [cite: 109]
                    score = 0 # [cite: 109]
                    if name_api == normalized_search_name_key: score = 100 # [cite: 109]
                    elif terms: score = (sum(1 for t_term in terms if t_term in name_api) / len(terms)) * 90 # [cite: 109]
                    if score > 70 and getattr(p_item, 'ID', None) is not None: # [cite: 110]
                        found_providers_flex.append({"ID": str(getattr(p_item, 'ID')), "FullName": str(getattr(p_item, 'FullName','')), "score": score}) # [cite: 110]
                if found_providers_flex: # [cite: 110]
                    best_match = sorted(found_providers_flex, key=lambda x: x['score'], reverse=True)[0] # [cite: 110, 111]
                    provider_id_found = best_match['ID'] # [cite: 111]
                    display_message("info", f"[GetProvID_P3] Flexible match for ACTIVE Provider '{provider_search_name}' is '{best_match['FullName']}'. ID: {provider_id_found} (Score: {best_match['score']})") # [cite: 111, 112]
                    cache_dict[cache_key] = provider_id_found # [cite: 112]
                    return provider_id_found # [cite: 112]
        if not provider_id_found: display_message("warning", f"[GetProvID_P3] Could not find ACTIVE provider '{provider_search_name}' (PracID {current_practice_id_context}).") # [cite: 112]
        return None
    except zeep.exceptions.Fault as soap_fault: display_message("error", f"[GetProvID_P3] SOAP FAULT for Prov '{provider_search_name}': {soap_fault.message}") # [cite: 112]
    except Exception as e: display_message("error", f"[GetProvID_P3] Unexpected error for Prov '{provider_search_name}': {type(e).__name__} - {e}") # [cite: 113]
    return None

def get_case_id_for_patient_phase3(client_obj, header_obj, patient_id_int, cache_dict): # [cite: 113]
    if pd.isna(patient_id_int): # [cite: 113]
        display_message("warning", "[GetCaseID_P3] Patient ID missing for Case ID fetch.") # [cite: 113]
        return None
    cache_key = f"case_{patient_id_int}" # [cite: 113]
    if cache_key in cache_dict: # [cite: 113]
        display_message("debug", f"[GetCaseID_P3] Found CaseID for Pt {patient_id_int} in cache. ID: {cache_dict[cache_key]}") # [cite: 113, 114]
        return cache_dict[cache_key] # [cite: 114]
    display_message("info", f"[GetCaseID_P3] CaseID for Pt {patient_id_int} not in cache. Querying API...") # [cite: 114]
    case_id_found = None # [cite: 114]
    try:
        GetPatientReqType = client_obj.get_type('ns0:GetPatientReq') # [cite: 114]
        SinglePatientFilterType = client_obj.get_type('ns0:SinglePatientFilter') # [cite: 114]
        patient_filter = SinglePatientFilterType(PatientID=int(patient_id_int)) # [cite: 114]
        request_payload = GetPatientReqType(RequestHeader=header_obj, Filter=patient_filter) # [cite: 114]
        api_response = client_obj.service.GetPatient(request=request_payload) # [cite: 114]
        if hasattr(api_response, 'ErrorResponse') and api_response.ErrorResponse and api_response.ErrorResponse.IsError: # [cite: 114, 115]
            display_message("error", f"[GetCaseID_P3] API Error for CaseID (Pt {patient_id_int}): {api_response.ErrorResponse.ErrorMessage}") # [cite: 115]
            return None
        if hasattr(api_response, 'SecurityResponse') and api_response.SecurityResponse and not api_response.SecurityResponse.Authorized: # [cite: 115]
            display_message("error", f"[GetCaseID_P3] API Auth Error for CaseID (Pt {patient_id_int}): {api_response.SecurityResponse.SecurityResult}") # [cite: 115]
            return None
        if hasattr(api_response, 'Patient') and api_response.Patient and \
           hasattr(api_response.Patient, 'Cases') and api_response.Patient.Cases and \
           hasattr(api_response.Patient.Cases, 'PatientCaseData') and api_response.Patient.Cases.PatientCaseData: # [cite: 115, 116]
            cases_data = api_response.Patient.Cases.PatientCaseData # [cite: 116]
            if not isinstance(cases_data, list): cases_data = [cases_data] # [cite: 116]
            primary_case = next((c for c in cases_data if getattr(c, 'IsPrimaryCase', False) and str(getattr(c, 'IsPrimaryCase')).lower() == 'true' and getattr(c, 'PatientCaseID', None)), None) # [cite: 116]
            if primary_case and getattr(primary_case, 'PatientCaseID', None): # [cite: 117]
                case_id_found = str(getattr(primary_case, 'PatientCaseID')) # [cite: 117]
                display_message("info", f"[GetCaseID_P3] Primary case for Pt {patient_id_int}. CaseID: {case_id_found}") # [cite: 117, 118]
            elif cases_data and getattr(cases_data[0], 'PatientCaseID', None): # [cite: 118]
                case_id_found = str(getattr(cases_data[0], 'PatientCaseID')) # [cite: 118]
                display_message("info", f"[GetCaseID_P3] No primary, using first case for Pt {patient_id_int}. CaseID: {case_id_found}") # [cite: 118]
        if not case_id_found: display_message("warning", f"[GetCaseID_P3] No usable case for Pt ID {patient_id_int}.") # [cite: 118]
        cache_dict[cache_key] = case_id_found # [cite: 118]
        return case_id_found # [cite: 119]
    except zeep.exceptions.Fault as soap_fault: display_message("error", f"[GetCaseID_P3] SOAP FAULT for CaseID (Pt {patient_id_int}): {soap_fault.message}") # [cite: 119]
    except Exception as e: display_message("error", f"[GetCaseID_P3] Unexpected error for CaseID (Pt {patient_id_int}): {type(e).__name__} - {e}") # [cite: 119]
    return None

def create_place_of_service_payload_phase3(client_obj, excel_pos_code, excel_encounter_mode, row_identifier_log): # [cite: 119]
    if not client_obj: return None # [cite: 119]
    EncounterPlaceOfServiceType = client_obj.get_type('ns0:EncounterPlaceOfService') # [cite: 119]
    pos_code_input = str(excel_pos_code).strip() if pd.notna(excel_pos_code) else "" # [cite: 119]
    encounter_mode_input = str(excel_encounter_mode).strip().lower() if pd.notna(excel_encounter_mode) else "" # [cite: 119]
    is_telehealth_mode = encounter_mode_input in ["tele health", "telehealth"] # [cite: 119]
    is_in_office_mode = encounter_mode_input in ["in office", "office", "inoffice"] # [cite: 119, 120]
    final_pos_code, final_pos_name = None, None # [cite: 120]
    if pos_code_input == "10" and is_telehealth_mode: # [cite: 120]
        final_pos_code = "10" # [cite: 120]
        final_pos_name = POS_CODE_MAP_PHASE3.get("TELEHEALTH", {}).get("name", "Telehealth Provided in Patient’s Home") # [cite: 120]
    elif pos_code_input == "11" and is_in_office_mode: # [cite: 120]
        final_pos_code = "11" # [cite: 120]
        final_pos_name = POS_CODE_MAP_PHASE3.get("OFFICE", {}).get("name", "Office") # [cite: 120]
    else: # Fallback logic # [cite: 120]
        if pos_code_input in ["02", "10", "11"]: # Known valid POS codes # [cite: 120, 121]
            final_pos_code = pos_code_input # [cite: 121]
            for key, value_dict in POS_CODE_MAP_PHASE3.items(): # [cite: 121]
                if value_dict["code"] == final_pos_code: final_pos_name = value_dict["name"]; break # [cite: 121, 122]
            if not final_pos_name: final_pos_name = f"POS Code {final_pos_code}" # [cite: 122]
        elif is_telehealth_mode: # [cite: 122]
            final_pos_code = POS_CODE_MAP_PHASE3.get("TELEHEALTH", {}).get("code", "10") # [cite: 122]
            final_pos_name = POS_CODE_MAP_PHASE3.get("TELEHEALTH", {}).get("name", "Telehealth Provided in Patient’s Home") # [cite: 122]
        elif is_in_office_mode: # [cite: 122]
            final_pos_code = POS_CODE_MAP_PHASE3.get("OFFICE", {}).get("code", "11") # [cite: 122]
            final_pos_name = POS_CODE_MAP_PHASE3.get("OFFICE", {}).get("name", "Office") # [cite: 123]
    if not final_pos_code or not final_pos_name: # [cite: 123]
        display_message("warning", f"[POS_P3] {row_identifier_log}: Cannot determine POS from Code '{pos_code_input}' & Mode '{encounter_mode_input}'.") # [cite: 123]
        return None
    display_message("debug", f"[POS_P3] {row_identifier_log}: Using POS Code: {final_pos_code}, Name: {final_pos_name}") # [cite: 123]
    try: return EncounterPlaceOfServiceType(PlaceOfServiceCode=str(final_pos_code), PlaceOfServiceName=str(final_pos_name)) # [cite: 123]
    except Exception as e: display_message("error", f"[POS_P3] {row_identifier_log}: Error creating POS payload: {e}"); return None # [cite: 123, 124]

def create_service_line_payload_phase3(client_obj, service_line_data_dict, encounter_start_dt_api_str, encounter_end_dt_api_str, row_identifier_log, actual_headers_map_param): # [cite: 124]
    if not client_obj: return None # [cite: 124]
    ServiceLineReqType = client_obj.get_type('ns0:ServiceLineReq') # [cite: 124]
    proc_code = str(service_line_data_dict.get(actual_headers_map_param.get("Procedures", "Procedures"), "")).strip() # [cite: 124]
    units_val = service_line_data_dict.get(actual_headers_map_param.get("Units", "Units")) # [cite: 124]
    diag1_val = service_line_data_dict.get(actual_headers_map_param.get("Diag 1", "Diag 1")) # [cite: 124]
    if not proc_code: display_message("warning", f"[SvcLine_P3] {row_identifier_log}: Proc code missing."); return None # [cite: 124, 125]
    if units_val is None or pd.isna(units_val) or str(units_val).strip() == "": display_message("warning", f"[SvcLine_P3] {row_identifier_log} (Proc {proc_code}): Units missing."); return None # [cite: 125, 126]
    if diag1_val is None or pd.isna(diag1_val) or not str(diag1_val).strip(): display_message("warning", f"[SvcLine_P3] {row_identifier_log} (Proc {proc_code}): Diag 1 missing."); return None # [cite: 126, 127]
    try:
        units_float = float(str(units_val).strip()) # [cite: 127]
        if units_float <= 0: display_message("warning", f"[SvcLine_P3] {row_identifier_log} (Proc {proc_code}): Units <= 0 ({units_float})."); return None # [cite: 127, 128]
    except ValueError: display_message("warning", f"[SvcLine_P3] {row_identifier_log} (Proc {proc_code}): Units '{units_val}' not valid number."); return None # [cite: 128, 129]
    def clean_value_p3(val, is_modifier=False): # [cite: 129]
        s_val = str(val if pd.notna(val) else "").strip() # [cite: 129]
        if is_modifier: # [cite: 129]
            if s_val.endswith(".0"): s_val = s_val[:-2] # [cite: 129]
            if s_val and len(s_val) > 2 : s_val = s_val[:2] # [cite: 129]
        return s_val if s_val and s_val.lower() != 'nan' else None # [cite: 129]
    diag1_cleaned = clean_value_p3(diag1_val) # [cite: 129]
    if not diag1_cleaned: display_message("warning", f"[SvcLine_P3] {row_identifier_log} (Proc {proc_code}): Diag1 invalid after cleaning."); return None # [cite: 129, 130]
    sl_args = {'ProcedureCode': proc_code, 'Units': units_float, 'ServiceStartDate': encounter_start_dt_api_str, 'ServiceEndDate': encounter_end_dt_api_str, 'DiagnosisCode1': diag1_cleaned} # [cite: 130]
    for i, mod_key in enumerate(["Mod 1", "Mod 2", "Mod 3", "Mod 4"]): # [cite: 130]
        mod_val = clean_value_p3(service_line_data_dict.get(actual_headers_map_param.get(mod_key, mod_key)), is_modifier=True) # [cite: 130]
        if mod_val: sl_args[f'ProcedureModifier{i+1}'] = mod_val # [cite: 130]
    for i, diag_key in enumerate(["Diag 2", "Diag 3", "Diag 4"]): # [cite: 130]
        diag_val = clean_value_p3(service_line_data_dict.get(actual_headers_map_param.get(diag_key, diag_key))) # [cite: 130]
        if diag_val: sl_args[f'DiagnosisCode{i+2}'] = diag_val # [cite: 130]
    try: return ServiceLineReqType(**sl_args) # [cite: 131]
    except Exception as e: display_message("error", f"[SvcLine_P3] {row_identifier_log} (Proc {proc_code}): Payload Error: {e}. Args: {sl_args}"); return None # [cite: 131, 132]

def parse_tebra_xml_error_phase3(xml_string, patient_id_context="N/A", dos_context="N/A", row_identifier_log=""): # [cite: 132]
    if not xml_string or not isinstance(xml_string, str): return str(xml_string) if xml_string else "Unknown error." # [cite: 132]
    if not ("<Encounter" in xml_string or "<err " in xml_string or "<Error>" in xml_string): # [cite: 133]
        return xml_string.strip() if xml_string.strip() else "Encounter error (non-XML)." # [cite: 133]
    simplified_errors = [] # [cite: 134]
    try:
        if xml_string.startswith("API Error: "): xml_string = xml_string[len("API Error: "):].strip() # [cite: 134]
        service_line_pattern = r"<ServiceLine>(.*?)</ServiceLine>" # [cite: 134]
        diag_error_pattern = r"<DiagnosisCode(?P<diag_num>\d)>(?P<diag_code_val>[^<]+?)<err id=\"\d+\">(?P<err_msg>[^<]+)</err>" # [cite: 134]
        mod_error_pattern = r"<ProcedureModifier(?P<mod_num>\d)>(?P<mod_code_val>[^<]+?)<err id=\"\d+\">(?P<err_msg>[^<]+)</err>" # [cite: 134]
        proc_code_pattern = r"<ProcedureCode>(?P<proc_code_val>[^<]+)</ProcedureCode>" # [cite: 134]
        general_err_pattern = r"<err id=\"\d+\">(?P<err_msg>[^<]+)</err>" # [cite: 134]
        service_lines_xml_content = re.findall(service_line_pattern, xml_string, re.DOTALL) # [cite: 134]
        sl_counter = 0 # [cite: 134]
        for sl_xml_item in service_lines_xml_content: # [cite: 135]
            sl_counter += 1; proc_code_val = "N/A" # [cite: 135, 136]
            proc_match = re.search(proc_code_pattern, sl_xml_item) # [cite: 136]
            if proc_match: proc_code_val = proc_match.group("proc_code_val") # [cite: 136]
            for match_item in re.finditer(diag_error_pattern, sl_xml_item): simplified_errors.append(f"L{sl_counter}(Proc {proc_code_val}): Diag{match_item.group('diag_num')} ('{match_item.group('diag_code_val')}') - {match_item.group('err_msg').split(',')[0].strip()}.") # [cite: 136]
            for match_item in re.finditer(mod_error_pattern, sl_xml_item): simplified_errors.append(f"L{sl_counter}(Proc {proc_code_val}): Mod{match_item.group('mod_num')} ('{match_item.group('mod_code_val')}') - {match_item.group('err_msg').split(',')[0].strip()}{' (No .0)' if '.0' in match_item.group('mod_code_val') else ''}.") # [cite: 136]
            if not re.search(diag_error_pattern, sl_xml_item) and not re.search(mod_error_pattern, sl_xml_item): # [cite: 136, 137]
                 for generic_match in re.finditer(general_err_pattern, sl_xml_item): simplified_errors.append(f"L{sl_counter}(Proc {proc_code_val}): {generic_match.group('err_msg').strip()}.") # [cite: 137]
        overall_err_match = re.search(r'<Encounter[^>]*>.*<err id="\d+">(.*?)</err>.*</Encounter>', xml_string, re.DOTALL) # [cite: 137]
        if overall_err_match and not simplified_errors: simplified_errors.append(f"Encounter Error: {overall_err_match.group(1).strip()}.") # [cite: 137]
        elif not overall_err_match and not simplified_errors: # [cite: 137]
             top_err = re.search(general_err_pattern, xml_string) # [cite: 137]
             if top_err: simplified_errors.append(f"Encounter Error: {top_err.group('err_msg').strip()}.") # [cite: 138]
        if not simplified_errors and "<Encounter" in xml_string : simplified_errors.append("Enc creation failed (no specific errors parsed).") # [cite: 138]
        elif not simplified_errors: return xml_string.strip() if xml_string.strip() else "Enc error (unspecified)." # [cite: 138]
        unique_errors = []; [unique_errors.append(e) for e in simplified_errors if e not in unique_errors] # [cite: 139]
        return "; ".join(unique_errors) # [cite: 139]
    except Exception: return "Error simplifying API message. Original (first 300): " + xml_string[:300].strip() + "..." # [cite: 139]

def get_encounter_details_phase3(client_obj, header_obj, encounter_id_str, tebra_practice_id_for_filter_str, row_identifier_log): # [cite: 139]
    results = {'RawEncounterStatusCode': None, 'SimpleError': None} # [cite: 139]
    if not encounter_id_str or pd.isna(encounter_id_str) or not tebra_practice_id_for_filter_str or pd.isna(tebra_practice_id_for_filter_str): # [cite: 140]
        results['SimpleError'] = "EncID or PracticeID missing for GetEncDetails." # [cite: 140]
        return results # [cite: 141]
    display_message("info", f"[GetEncStatus_P3] {row_identifier_log}: Fetching status for EncID {encounter_id_str}, TebraPracticeID {tebra_practice_id_for_filter_str}...") # [cite: 141]
    try:
        GetEncounterDetailsReqType = client_obj.get_type('ns0:GetEncounterDetailsReq') # [cite: 141]
        EncounterDetailsFilterType = client_obj.get_type('ns0:EncounterDetailsFilter') # [cite: 141]
        EncounterDetailsPracticeType = client_obj.get_type('ns0:EncounterDetailsPractice') # [cite: 141]
        EncounterDetailsFieldsToReturnType = client_obj.get_type('ns0:EncounterDetailsFieldsToReturn') # [cite: 141]
        fields_to_return = EncounterDetailsFieldsToReturnType(EncounterID=True, EncounterStatus=True, PracticeID=True) # [cite: 141]
        practice_filter_details = EncounterDetailsPracticeType(PracticeID=str(tebra_practice_id_for_filter_str)) # [cite: 141]
        encounter_filter = EncounterDetailsFilterType(EncounterID=str(encounter_id_str), Practice=practice_filter_details) # [cite: 141]
        request_payload = GetEncounterDetailsReqType(RequestHeader=header_obj, Fields=fields_to_return, Filter=encounter_filter) # [cite: 142]
        api_response = client_obj.service.GetEncounterDetails(request=request_payload) # [cite: 142]

        if hasattr(api_response, 'ErrorResponse') and api_response.ErrorResponse and api_response.ErrorResponse.IsError: # [cite: 142]
            results['SimpleError'] = f"API Error (GetEncStatus): {api_response.ErrorResponse.ErrorMessage}" # [cite: 142]
        elif hasattr(api_response, 'SecurityResponse') and api_response.SecurityResponse and not api_response.SecurityResponse.Authorized: # [cite: 142]
            results['SimpleError'] = f"API Auth Error (GetEncStatus): {api_response.SecurityResponse.SecurityResult}" # [cite: 142]
        elif hasattr(api_response, 'EncounterDetails') and api_response.EncounterDetails and \
             hasattr(api_response.EncounterDetails, 'EncounterDetailsData') and api_response.EncounterDetails.EncounterDetailsData: # [cite: 142, 143]
            details_data_list = api_response.EncounterDetails.EncounterDetailsData # [cite: 143]
            if not isinstance(details_data_list, list): details_data_list = [details_data_list] # [cite: 143]
            if details_data_list: # [cite: 143]
                enc_data = details_data_list[0] # [cite: 143]
                results['RawEncounterStatusCode'] = getattr(enc_data, 'EncounterStatus', None) # [cite: 143]
            else: results['SimpleError'] = "No EncounterDetailsData for EncID." # [cite: 144]
        else: results['SimpleError'] = "Unknown response structure (GetEncStatus)." # [cite: 144]
    except zeep.exceptions.Fault as soap_fault: results['SimpleError'] = f"SOAP FAULT (GetEncStatus): {soap_fault.message}" # [cite: 145]
    except Exception as e: results['SimpleError'] = f"Unexpected error in GetEncStatus: {type(e).__name__} - {str(e)}" # [cite: 145]
    if results['SimpleError']: display_message("error", f"[GetEncStatus_P3] {row_identifier_log}: Error for EncID {encounter_id_str}: {results['SimpleError']}") # [cite: 145]
    return results # [cite: 145]

def get_total_charge_amount_for_encounter_phase3(client_obj, header_obj, target_encounter_id_str, # [cite: 146]
                                                 practice_name_filter_str, patient_name_filter_str, dos_filter_str,
                                                 row_identifier_log): # [cite: 147]
    results = {'TotalChargeAmount': None, 'SimpleError': None} # [cite: 147]
    if not all([target_encounter_id_str, practice_name_filter_str, patient_name_filter_str, dos_filter_str]): # [cite: 147]
        results['SimpleError'] = "Missing required params for GetCharges (EncID, PracName, PtName, DOS)." # [cite: 147]
        return results # [cite: 148]

    display_message("info", f"[GetCharges_P3] {row_identifier_log}: Fetching charges for EncID {target_encounter_id_str} (Filters: Prac='{practice_name_filter_str}', Pt='{patient_name_filter_str}', DOS='{dos_filter_str}', IncludeUnapproved='true')...") # [cite: 148]

    try:
        service_date_api_format = format_datetime_for_api_phase3(dos_filter_str) # [cite: 148]
        if not service_date_api_format: # [cite: 148]
            results['SimpleError'] = f"Invalid DOS '{dos_filter_str}' for GetCharges filter." # [cite: 148]
            return results # [cite: 149]

        GetChargesReqType = client_obj.get_type('ns0:GetChargesReq') # [cite: 149]
        ChargeFilterType = client_obj.get_type('ns0:ChargeFilter') # [cite: 149]
        ChargeFieldsToReturnType = client_obj.get_type('ns0:ChargeFieldsToReturn') # [cite: 149]

        charge_fields = ChargeFieldsToReturnType(EncounterID=True, TotalCharges=True, ID=True, ProcedureCode=True) # [cite: 149]

        charge_filter = ChargeFilterType( # [cite: 149]
            PracticeName=str(practice_name_filter_str), # [cite: 149]
            PatientName=str(patient_name_filter_str), # [cite: 149]
            FromServiceDate=service_date_api_format, # [cite: 149]
            ToServiceDate=service_date_api_format, # [cite: 150]
            IncludeUnapprovedCharges="true"  # MODIFICATION HERE # [cite: 150]
        )
        request_payload_charges = GetChargesReqType(RequestHeader=header_obj, Fields=charge_fields, Filter=charge_filter) # [cite: 150]
        api_response_charges = client_obj.service.GetCharges(request=request_payload_charges) # [cite: 150]

        if hasattr(api_response_charges, 'ErrorResponse') and api_response_charges.ErrorResponse and api_response_charges.ErrorResponse.IsError: # [cite: 150]
            results['SimpleError'] = f"API Error (GetCharges): {api_response_charges.ErrorResponse.ErrorMessage}" # [cite: 150]
        elif hasattr(api_response_charges, 'SecurityResponse') and api_response_charges.SecurityResponse and not api_response_charges.SecurityResponse.Authorized: # [cite: 150]
             results['SimpleError'] = f"API Auth Error (GetCharges): {api_response_charges.SecurityResponse.SecurityResult}" # [cite: 151]
        elif hasattr(api_response_charges, 'Charges') and api_response_charges.Charges and \
             hasattr(api_response_charges.Charges, 'ChargeData') and api_response_charges.Charges.ChargeData: # [cite: 151]

            all_charge_data_list = api_response_charges.Charges.ChargeData # [cite: 151]
            if not isinstance(all_charge_data_list, list): all_charge_data_list = [all_charge_data_list] # [cite: 151]

            current_encounter_total_charges = 0.0 # [cite: 151]
            charges_found_for_encounter = False # [cite: 152]
            for charge_item in all_charge_data_list: # [cite: 152]
                if str(getattr(charge_item, 'EncounterID', '')) == str(target_encounter_id_str): # [cite: 152]
                    tc_str = getattr(charge_item, 'TotalCharges', None) # [cite: 152]
                    if tc_str is not None and str(tc_str).strip(): # [cite: 152]
                        try: # [cite: 153]
                            current_encounter_total_charges += float(str(tc_str).strip()) # [cite: 153]
                            charges_found_for_encounter = True # [cite: 153]
                        except ValueError: # [cite: 153]
                            display_message("warning", f"[GetCharges_P3] {row_identifier_log}: Could not parse TotalCharges '{tc_str}' for ChargeID {getattr(charge_item, 'ID','N/A')} on EncID {target_encounter_id_str}.") # [cite: 154]
            if charges_found_for_encounter: # [cite: 154]
                results['TotalChargeAmount'] = f"{current_encounter_total_charges:.2f}" # [cite: 154]
            else: # [cite: 154]
                display_message("warning", f"[GetCharges_P3] {row_identifier_log}: No specific charges found for EncounterID {target_encounter_id_str} in GetCharges response (IncludeUnapprovedCharges='true'). Defaulting amount to 0.00.") # [cite: 155, 156]
                results['TotalChargeAmount'] = "0.00" # [cite: 156]
        else: # [cite: 156]
            display_message("warning", f"[GetCharges_P3] {row_identifier_log}: No 'Charges.ChargeData' in API response for EncID {target_encounter_id_str}. Defaulting amount to 0.00.") # [cite: 156]
            results['TotalChargeAmount'] = "0.00" # [cite: 156]
    except zeep.exceptions.Fault as soap_fault: # [cite: 157]
        results['SimpleError'] = f"SOAP FAULT (GetCharges): {soap_fault.message}" # [cite: 157]
    except Exception as e: # [cite: 157]
        results['SimpleError'] = f"Unexpected error in GetCharges: {type(e).__name__} - {str(e)}" # [cite: 157]

    if results['SimpleError'] and results.get('TotalChargeAmount') is None : # [cite: 157]
         display_message("error", f"[GetCharges_P3] {row_identifier_log}: Error fetching charges for EncID {target_encounter_id_str}: {results['SimpleError']}") # [cite: 157]
         results['TotalChargeAmount'] = "Error" # [cite: 158]
    elif results.get('TotalChargeAmount') is None: # [cite: 158]
        results['TotalChargeAmount'] = "0.00" # [cite: 158]
    return results # [cite: 158]

# --- ⚙️ PART 5: Main Processing Loop (Adapted from Colab) ---

def _create_encounter_for_group_and_get_details( # [cite: 159]
    client_obj, header_obj, group_key, group_df_rows,
    practice_id_for_encounter_payload_str, # Tebra PracticeID for encounter # [cite: 160]
    patient_full_name_for_charges_filter, # Patient Full Name for GetCharges # [cite: 160]
    log_prefix, # Renamed from log_identifier for clarity [cite: 161]
    # Parameters added for adaptation:
    actual_headers_map_param,
    service_location_id_cache_param,
    patient_case_id_cache_param,
    provider_id_cache_param
):
    patient_id_str, dos_str, practice_name_excel_str = group_key # [cite: 161]
    row_identifier_log = f"{log_prefix} Grp (Pt:{patient_id_str}, DOS:{dos_str}, PracFromExcel:{practice_name_excel_str})" # [cite: 161]

    results = { # [cite: 162]
        'EncounterID': None, # [cite: 162]
        'ChargeAmount': "Error", # [cite: 162]
        'ChargeStatus': "Error", # [cite: 162]
        'SimpleMessage': "Encounter processing not initiated.", # [cite: 162]
        'ErrorDetail': None # [cite: 162]
    }

    if group_df_rows.empty: # [cite: 162]
        results['SimpleMessage'] = "Encounter Error: No rows in group." # [cite: 162]
        display_message("error", f"{row_identifier_log}: {results['SimpleMessage']}") # [cite: 163]
        return results # [cite: 163]

    first_row_data = group_df_rows.iloc[0] # [cite: 163]

    try:
        if not practice_id_for_encounter_payload_str: # [cite: 163]
            results['SimpleMessage'] = "Encounter Error: Missing Tebra Practice ID for encounter payload." # [cite: 163]
            return results # [cite: 163]

        # Use passed caches and actual_headers_map_param
        service_location_id_str = get_service_location_id_by_name(client_obj, header_obj, practice_name_excel_str, practice_id_for_encounter_payload_str, service_location_id_cache_param) # [cite: 163]
        if not service_location_id_str: # [cite: 163]
            results['SimpleMessage'] = f"Encounter Error: Service Location '{practice_name_excel_str}' not found for Tebra Practice ID {practice_id_for_encounter_payload_str}." # [cite: 164]
            return results # [cite: 164]

        case_id_str = get_case_id_for_patient_phase3(client_obj, header_obj, int(float(patient_id_str)), patient_case_id_cache_param) # [cite: 164]
        if not case_id_str: # [cite: 164]
            results['SimpleMessage'] = f"Encounter Error: Case ID not found for Patient {patient_id_str}." # [cite: 164]
            return results # [cite: 164]

        rp_name_col = actual_headers_map_param.get("Rendering Provider", "Rendering Provider") # [cite: 164, 165]
        rp_name = str(first_row_data.get(rp_name_col, "")).strip() # [cite: 165]
        if not rp_name: # [cite: 165]
            results['SimpleMessage'] = "Encounter Error: Rendering Provider name missing." # [cite: 165]
            return results # [cite: 165]
        rp_id_str = get_provider_id_by_name_phase3(client_obj, header_obj, rp_name, practice_id_for_encounter_payload_str, provider_id_cache_param) # [cite: 165]
        if not rp_id_str: # [cite: 165]
            results['SimpleMessage'] = f"Encounter Error: Rendering Provider ID for '{rp_name}' not found." # [cite: 165, 166]
            return results # [cite: 166]

        sp_name_col = actual_headers_map_param.get("Scheduling Provider", "Scheduling Provider") # [cite: 166]
        sp_name = str(first_row_data.get(sp_name_col, "")).strip() # [cite: 166]
        sp_id_str = None # [cite: 166]
        if sp_name: # [cite: 166]
            sp_id_str = get_provider_id_by_name_phase3(client_obj, header_obj, sp_name, practice_id_for_encounter_payload_str, provider_id_cache_param) # [cite: 166]
            if not sp_id_str: display_message("warning", f"{row_identifier_log}: Sched Prov '{sp_name}' ID not found.") # [cite: 166]

        encounter_dos_api_str = format_datetime_for_api_phase3(dos_str) # [cite: 167]
        if not encounter_dos_api_str: # [cite: 167]
            results['SimpleMessage'] = f"Encounter Error: Invalid DOS '{dos_str}' for API." # [cite: 167]
            return results # [cite: 167]

        pos_col = actual_headers_map_param.get("POS", "POS") # [cite: 167]
        enc_mode_col = actual_headers_map_param.get("Encounter Mode", "Encounter Mode") # [cite: 167]
        excel_pos_code = first_row_data.get(pos_col) # [cite: 167]
        excel_enc_mode = first_row_data.get(enc_mode_col) # [cite: 167]
        pos_payload = create_place_of_service_payload_phase3(client_obj, excel_pos_code, excel_enc_mode, row_identifier_log) # [cite: 168]
        if not pos_payload: # [cite: 168]
            results['SimpleMessage'] = f"Encounter Error: Failed POS payload (POS: {excel_pos_code}, Mode: {excel_enc_mode})." # [cite: 168]
            return results # [cite: 168]

        service_lines_payload_list = [] # [cite: 168]
        for sl_idx, sl_row_data in group_df_rows.iterrows(): # [cite: 168]
            original_row_num_for_log = sl_row_data.get('original_excel_row_num', f"DF_Idx_{sl_idx}") # [cite: 168]
            sl_log_id = f"{row_identifier_log} (ExcelRow {original_row_num_for_log})" # [cite: 169]
            # Pass actual_headers_map_param to create_service_line_payload_phase3
            sl_payload = create_service_line_payload_phase3(client_obj, sl_row_data, encounter_dos_api_str, encounter_dos_api_str, sl_log_id, actual_headers_map_param) # [cite: 169]
            if sl_payload: # [cite: 169]
                service_lines_payload_list.append(sl_payload) # [cite: 169]
            else: # [cite: 169]
                results['SimpleMessage'] = f"Encounter Error: Failed to create service line from Excel row {original_row_num_for_log}." # [cite: 169]
                return results # [cite: 170]
        if not service_lines_payload_list: # [cite: 170]
            results['SimpleMessage'] = "Encounter Error: No valid service lines created." # [cite: 170]
            return results # [cite: 170]

        ce_batch_col = actual_headers_map_param.get("CE Batch #", "CE Batch #") # [cite: 170]
        ce_batch_num_str = str(first_row_data.get(ce_batch_col, "")).strip() # [cite: 170]

        EncounterCreateType = client_obj.get_type('ns0:EncounterCreate') # [cite: 170]
        PatientIdentifierReqType = client_obj.get_type('ns0:PatientIdentifierReq') # [cite: 170]
        PracticeIdentifierReqType = client_obj.get_type('ns0:PracticeIdentifierReq') # [cite: 171]
        EncounterServiceLocationType = client_obj.get_type('ns0:EncounterServiceLocation') # [cite: 171]
        PatientCaseIdentifierReqType = client_obj.get_type('ns0:PatientCaseIdentifierReq') # [cite: 171]
        ProviderIdentifierDetailedReqType = client_obj.get_type('ns0:ProviderIdentifierDetailedReq') # [cite: 171]
        ArrayOfServiceLineReqType = client_obj.get_type('ns0:ArrayOfServiceLineReq') # [cite: 171]
        encounter_args = { # [cite: 171]
            "Patient": PatientIdentifierReqType(PatientID=int(float(patient_id_str))), # [cite: 171]
            "Practice": PracticeIdentifierReqType(PracticeID=int(practice_id_for_encounter_payload_str)), # [cite: 171]
            "ServiceLocation": EncounterServiceLocationType(LocationID=int(service_location_id_str)), # [cite: 171]
            "Case": PatientCaseIdentifierReqType(CaseID=int(case_id_str)), # [cite: 172]
            "RenderingProvider": ProviderIdentifierDetailedReqType(ProviderID=int(rp_id_str)), # [cite: 172]
            "ServiceStartDate": encounter_dos_api_str, "ServiceEndDate": encounter_dos_api_str, # [cite: 172]
            "PlaceOfService": pos_payload, # [cite: 172]
            "ServiceLines": ArrayOfServiceLineReqType(ServiceLineReq=service_lines_payload_list), # [cite: 172]
            "EncounterStatus": "Draft" # [cite: 172]
        }
        if sp_id_str: encounter_args["SchedulingProvider"] = ProviderIdentifierDetailedReqType(ProviderID=int(sp_id_str)) # [cite: 172]
        if ce_batch_num_str: encounter_args["BatchNumber"] = ce_batch_num_str # [cite: 173]

        encounter_payload = EncounterCreateType(**encounter_args) # [cite: 173]
        CreateEncounterReqType = client_obj.get_type('ns0:CreateEncounterReq') # [cite: 173]
        final_request = CreateEncounterReqType(RequestHeader=header_obj, Encounter=encounter_payload) # [cite: 173]

        display_message("info", f"{row_identifier_log}: Sending CreateEncounter request...") # [cite: 173]
        api_response_create = client_obj.service.CreateEncounter(request=final_request) # [cite: 173]

        if hasattr(api_response_create, 'ErrorResponse') and api_response_create.ErrorResponse and api_response_create.ErrorResponse.IsError: # [cite: 173]
            raw_error = api_response_create.ErrorResponse.ErrorMessage # [cite: 173]
            results['ErrorDetail'] = raw_error # [cite: 174]
            results['SimpleMessage'] = f"Encounter API Error: {parse_tebra_xml_error_phase3(raw_error, patient_id_str, dos_str, row_identifier_log)}" # [cite: 174]
        elif hasattr(api_response_create, 'SecurityResponse') and api_response_create.SecurityResponse and not api_response_create.SecurityResponse.Authorized: # [cite: 174]
            results['SimpleMessage'] = f"Encounter API Auth Error: {api_response_create.SecurityResponse.SecurityResult}" # [cite: 174]
        elif hasattr(api_response_create, 'EncounterID') and api_response_create.EncounterID is not None: # [cite: 174]
            created_encounter_id = str(api_response_create.EncounterID) # [cite: 174]
            results['EncounterID'] = created_encounter_id # [cite: 174, 175]

            status_fetch_result = get_encounter_details_phase3(client_obj, header_obj, created_encounter_id, practice_id_for_encounter_payload_str, row_identifier_log) # [cite: 175]
            current_charge_status = "Status Fetch Error" # [cite: 175]
            status_warning = "" # [cite: 175]
            if status_fetch_result.get('RawEncounterStatusCode') is not None: # [cite: 175]
                current_charge_status = map_encounter_status_code(status_fetch_result['RawEncounterStatusCode']) # [cite: 175]
            elif status_fetch_result.get('SimpleError'): # [cite: 175]
                status_warning = f" (Status Warn: {status_fetch_result['SimpleError']})" # [cite: 176]
            results['ChargeStatus'] = current_charge_status # [cite: 176]

            current_charge_amount = "Amount Fetch Error" # [cite: 176]
            charge_warning = "" # [cite: 176]
            if patient_full_name_for_charges_filter and dos_str: # [cite: 176]
                charge_fetch_result = get_total_charge_amount_for_encounter_phase3( # [cite: 177]
                    client_obj, header_obj, created_encounter_id,
                    practice_name_excel_str, # This is correct, it's for the filter [cite: 177]
                    patient_full_name_for_charges_filter, # [cite: 177]
                    dos_str, # [cite: 177]
                    row_identifier_log # [cite: 178]
                )
                if charge_fetch_result.get('TotalChargeAmount') not in [None, "Error"]: # [cite: 178]
                    current_charge_amount = charge_fetch_result['TotalChargeAmount'] # [cite: 178]
                elif charge_fetch_result.get('SimpleError'): # [cite: 178]
                    charge_warning = f" (Charge Warn: {charge_fetch_result.get('SimpleError')})" # [cite: 179]
            else: # [cite: 179]
                current_charge_amount = "Amount Fetch Skipped" # [cite: 179]
                charge_warning = " (Charge Warn: Missing info for filter)" # [cite: 179]
            results['ChargeAmount'] = current_charge_amount # [cite: 179]

            results['SimpleMessage'] = f"Encounter #{created_encounter_id} Created." # [cite: 180]
            if status_warning: results['SimpleMessage'] += status_warning # [cite: 180]
            if charge_warning: results['SimpleMessage'] += charge_warning # [cite: 180]
            if current_charge_status == "Status Fetch Error" and "(Status Warn:" not in results['SimpleMessage']: # [cite: 180]
                results['SimpleMessage'] += " (Status could not be confirmed)." # [cite: 181]
            if current_charge_amount in ["Amount Fetch Error", "Amount Fetch Skipped", "Error"] and "(Charge Warn:" not in results['SimpleMessage']: # [cite: 181]
                 results['SimpleMessage'] += " (Charge amount could not be confirmed)." # [cite: 181]
        else: # [cite: 181]
            results['SimpleMessage'] = "Encounter creation response unclear." # [cite: 181]
            results['ErrorDetail'] = zeep.helpers.serialize_object(api_response_create) if api_response_create else "No API response." # [cite: 181, 182]
    except zeep.exceptions.Fault as soap_fault: # [cite: 182]
        results['SimpleMessage'] = f"Encounter SOAP Fault: {str(soap_fault.message)[:100]}..." # [cite: 182]
        results['ErrorDetail'] = str(soap_fault) # [cite: 182]
    except Exception as e: # [cite: 182]
        results['SimpleMessage'] = f"Encounter System Error: {type(e).__name__}." # [cite: 182]
        results['ErrorDetail'] = str(e) # [cite: 182]
        # import traceback # Already imported at top level of file
        display_message("error", f"{row_identifier_log} Exception: {traceback.format_exc()}") # [cite: 182]
    log_level = "error" if results['ErrorDetail'] or "Error" in results['SimpleMessage'] or "Warn" in results['SimpleMessage'] else "info" # [cite: 182, 183]
    if not results['SimpleMessage'].startswith(f"Encounter API Error:"): # [cite: 183]
        display_message(log_level, f"{row_identifier_log}: Final status for group: {results['SimpleMessage']}") # [cite: 183]

    if results['ErrorDetail'] and log_level == "error" and "Encounter API Error:" not in results['SimpleMessage']: # [cite: 183]
         display_message("debug", f"{row_identifier_log} Raw Error Detail for group: {results['ErrorDetail']}") # [cite: 183]
    return results # [cite: 183]

def run_all_phases_processing_adapted(df_param, actual_headers_map_param, tebra_client_param, tebra_header_param): # [cite: 183]
    """
    Adapted main processing loop from Colab Part 5.
    """
    # Initialize caches locally for this processing run
    g_practice_id_cache = {} # [cite: 184]
    g_service_location_id_cache = {} # [cite: 184]
    g_provider_id_cache = {} # [cite: 184]
    g_patient_case_id_cache = {} # [cite: 184]

    # Use df_param, actual_headers_map_param, tebra_client_param, tebra_header_param
    # instead of g_df, g_actual_column_headers_map, client, header

    if 'original_excel_row_num' not in df_param.columns: # [cite: 185, 186]
         df_param['original_excel_row_num'] = df_param.index + 2 # Assuming row 2 is the first data row in Excel # [cite: 186]

    # Initialize Phase 3 output columns if they don't exist (using actual_headers_map_param)
    for col_key in ["Encounter ID", "Charge Amount", "Charge Status"]: # [cite: 186]
        actual_col_name = actual_headers_map_param.get(col_key, col_key) # [cite: 186]
        if actual_col_name not in df_param.columns: # [cite: 186]
            df_param[actual_col_name] = None # Or pd.NA # [cite: 186]

    display_message("info", "--- Starting Phases 1 (Patient/Insurance) & 2 (Payment Posting) ---") # [cite: 186]
    for index, row_data in df_param.iterrows(): # [cite: 187]
        current_row_messages = [] # [cite: 187]
        payment_id_for_row = None # [cite: 187]
        log_prefix_row = f"DF_Row {index} (OrigExcelRow {row_data.get('original_excel_row_num', index+2)})" # [cite: 187]

        try:
            patient_id_col = actual_headers_map_param.get("Patient ID") # [cite: 187]
            practice_col = actual_headers_map_param.get("Practice") # [cite: 187]
            dos_col = actual_headers_map_param.get("DOS") # [cite: 187]

            patient_id_str = str(row_data.get(patient_id_col, "")).strip() # [cite: 188]
            practice_name_str = str(row_data.get(practice_col, "")).strip() # [cite: 188]
            dos_for_insurance_str = str(row_data.get(dos_col, "")).strip() # [cite: 188]

            if not patient_id_str or not practice_name_str: # [cite: 188]
                msg = "Skipped (Ph1/2): Patient ID or Practice Name (from Excel) missing." # [cite: 188, 189]
                current_row_messages.append(msg) # [cite: 189]
                df_param.loc[index, actual_headers_map_param.get("Error", "Error")] = "; ".join(filter(None, current_row_messages)) # [cite: 189, 190]
                continue # [cite: 190]

            p1_status_msg = "" # [cite: 190]
            try:
                insurance_results = phase1_fetch_patient_and_insurance(tebra_client_param, tebra_header_param, patient_id_str, practice_name_str, dos_for_insurance_str) # [cite: 190]
                df_param.loc[index, actual_headers_map_param.get("Patient Name", "Patient Name")] = insurance_results.get('FetchedPatientName') # [cite: 190]
                df_param.loc[index, actual_headers_map_param.get("DOB", "DOB")] = insurance_results.get('FetchedPatientDOB') # [cite: 191]
                df_param.loc[index, actual_headers_map_param.get("Insurance", "Insurance")] = insurance_results.get('FetchedInsuranceName') # [cite: 191]
                df_param.loc[index, actual_headers_map_param.get("Insurance ID", "Insurance ID")] = insurance_results.get('FetchedInsuranceID') # [cite: 191]
                df_param.loc[index, actual_headers_map_param.get("Insurance Status", "Insurance Status")] = insurance_results.get('FetchedInsuranceStatus') # [cite: 191]
                if insurance_results.get('SimpleError'): p1_status_msg = f"P1 Error: {insurance_results['SimpleError']}" # [cite: 191]
                elif insurance_results.get('FetchedInsuranceStatus') not in ["Active", "Multiple Active Found"]: # [cite: 192]
                    p1_status_msg = f"P1: {insurance_results.get('FetchedInsuranceStatus', 'Ins status unknown')}" # [cite: 192]
                if p1_status_msg: current_row_messages.append(p1_status_msg) # [cite: 192]
            except Exception as e1: # [cite: 192]
                p1_status_msg = f"P1 System Error: {e1.__class__.__name__}" # [cite: 192]
                display_message("error", f"{log_prefix_row}: {p1_status_msg} - {e1}") # [cite: 193]
                current_row_messages.append(p1_status_msg) # [cite: 193]

            p2_status_msg = "" # [cite: 193]
            try:
                pp_batch_str = str(row_data.get(actual_headers_map_param.get("PP Batch #"), "")).strip() # [cite: 193]
                payment_amount_val_str = str(row_data.get(actual_headers_map_param.get("Patient Payment"), "")).strip() # [cite: 193, 194]
                payment_source_val_str = str(row_data.get(actual_headers_map_param.get("Patient Payment Source"), "")).strip() # [cite: 194]

                attempt_payment = True # [cite: 194]
                payment_inputs_for_check = { # [cite: 194]
                    "PP Batch #": pp_batch_str, "Patient Payment": payment_amount_val_str, "Patient Payment Source": payment_source_val_str # [cite: 194]
                }
                if not all(val and val.lower() != 'nan' for val in payment_inputs_for_check.values()): # [cite: 195]
                    attempt_payment = False # [cite: 195]

                if attempt_payment: # [cite: 196]
                    tebra_practice_id_for_payment = get_practice_id_by_name(tebra_client_param, tebra_header_param, practice_name_str, g_practice_id_cache) # Pass local cache # [cite: 196]
                    if tebra_practice_id_for_payment: # [cite: 196]
                        payment_result = phase2_post_tebra_payment(tebra_client_param, tebra_header_param, patient_id_str, tebra_practice_id_for_payment, # [cite: 196]
                                                       practice_name_str, pp_batch_str, payment_amount_val_str, # [cite: 197]
                                                       payment_source_val_str, str(row_data.get(actual_headers_map_param.get("Reference Number"), "")).strip()) # [cite: 198]
                        p2_status_msg = payment_result.get('SimpleMessage', 'P2: Pay status unclear.') # [cite: 198]
                        if payment_result.get('Success'): payment_id_for_row = payment_result.get('PaymentID') # [cite: 198]
                        if not p2_status_msg.startswith("P2 Skipped:"): # [cite: 199]
                             current_row_messages.append(p2_status_msg) # [cite: 199]
                    else: # [cite: 199]
                        p2_status_msg = f"P2 Error: Tebra Practice ID for '{practice_name_str}' (payment) not found." # [cite: 200]
                        current_row_messages.append(p2_status_msg) # [cite: 200]
            except Exception as e2: # [cite: 201]
                p2_status_msg = f"P2 System Error: {e2.__class__.__name__}" # [cite: 201]
                display_message("error", f"{log_prefix_row}: {p2_status_msg} - {e2}") # [cite: 201]
                current_row_messages.append(p2_status_msg) # [cite: 201]

            df_param.loc[index, '_PaymentID_Temp'] = payment_id_for_row # [cite: 201]
            df_param.loc[index, actual_headers_map_param.get("Error", "Error")] = "; ".join(filter(None, current_row_messages)) # [cite: 201, 202]
        except Exception as e_row_ph12: # [cite: 202]
            df_param.loc[index, actual_headers_map_param.get("Error", "Error")] = f"Error preparing row {index} for Ph1/2: {e_row_ph12.__class__.__name__}" # [cite: 202]

    display_message("info", "--- Phases 1 & 2 processing complete. ---") # [cite: 202]
    display_message("info", "--- Starting Phase 3 (Encounter Creation - Grouped) ---") # [cite: 202]

    patient_id_col = actual_headers_map_param.get("Patient ID") # [cite: 202]
    dos_col = actual_headers_map_param.get("DOS") # [cite: 202]
    practice_excel_col = actual_headers_map_param.get("Practice") # [cite: 203]
    patient_name_col = actual_headers_map_param.get("Patient Name") # [cite: 203]

    if not all([patient_id_col, dos_col, practice_excel_col, patient_name_col]): # [cite: 203]
        error_msg_critical = "CRITICAL: Key column names for grouping (Patient ID, DOS, Practice, Patient Name) not mapped. Cannot proceed with Phase 3." # [cite: 203]
        display_message("error", error_msg_critical) # [cite: 203]
        # Update all rows in df_param with this critical error if it occurs.
        error_col_name = actual_headers_map_param.get("Error", "Error")
        df_param[error_col_name] = df_param[error_col_name].apply(lambda x: f"{x}; {error_msg_critical}".strip('; ') if pd.notna(x) and x else error_msg_critical)

        # Prepare summary for this critical failure
        summary_for_critical_failure = {
            "total_rows": len(df_param),
            "encounters_created": 0,
            "payments_posted": 0,
            "failed_rows": len(df_param), # All rows effectively failed for P3
            "results": [{
                "row_number": row.get('original_excel_row_num', idx + 2),
                "practice_name": row.get(actual_headers_map_param.get("Practice", ""), ""),
                "patient_id": row.get(actual_headers_map_param.get("Patient ID", ""), ""),
                "results": row.get(error_col_name, error_msg_critical)
            } for idx, row in df_param.iterrows()]
        }
        return df_param, summary_for_critical_failure # [cite: 204]

    groupable_df = df_param[ # [cite: 204]
        df_param[patient_id_col].notna() & (df_param[patient_id_col].astype(str).str.strip() != "") & # [cite: 204]
        df_param[dos_col].notna() & (df_param[dos_col].astype(str).str.strip() != "") & # [cite: 204]
        df_param[practice_excel_col].notna() & (df_param[practice_excel_col].astype(str).str.strip() != "") & # [cite: 204]
        df_param[patient_name_col].notna() & (df_param[patient_name_col].astype(str).str.strip() != "") # [cite: 204]
    ].copy()

    if groupable_df.empty: # [cite: 204]
        display_message("warning", "No rows with valid Patient ID, DOS, Practice (from Excel), and Patient Name found to group for Phase 3.") # [cite: 205]
    else:
        groupable_df[dos_col] = groupable_df[dos_col].astype(str) # [cite: 205]
        grouped_for_encounter = groupable_df.groupby([patient_id_col, dos_col, practice_excel_col]) # [cite: 205]
        display_message("info", f"Found {len(grouped_for_encounter)} groups for encounter creation.") # [cite: 205]
        group_counter = 0 # [cite: 205]
        for group_keys, group_indices in grouped_for_encounter.groups.items(): # [cite: 205]
            group_counter += 1 # [cite: 206]
            patient_id_grp, dos_grp, practice_name_excel_grp = group_keys # [cite: 206]
            current_group_df_slice = df_param.loc[group_indices] # [cite: 206]
            first_row_of_group = current_group_df_slice.iloc[0] # [cite: 206]
            patient_full_name_grp = str(first_row_of_group.get(patient_name_col, "")).strip() # [cite: 206]
            log_prefix_grp = f"EncGrp {group_counter}/{len(grouped_for_encounter)}" # [cite: 206]
            display_message("info", f"Processing {log_prefix_grp} - PtID: {patient_id_grp}, DOS: {dos_grp}, PracticeFromExcel: {practice_name_excel_grp} ({len(group_indices)} Excel row(s))") # [cite: 206, 207]

            if not patient_full_name_grp: # [cite: 207]
                error_msg = "P3 Error: Patient Full Name missing for group (required for GetCharges filter)." # [cite: 207]
                for idx_in_group in group_indices: # [cite: 207]
                    existing_err = str(df_param.loc[idx_in_group, actual_headers_map_param.get("Error", "Error")]).strip() # [cite: 207]
                    df_param.loc[idx_in_group, actual_headers_map_param.get("Error", "Error")] = f"{existing_err}; {error_msg}".strip('; ') # [cite: 208, 209]
                continue # [cite: 209]

            tebra_practice_id_for_enc_payload = get_practice_id_by_name(tebra_client_param, tebra_header_param, practice_name_excel_grp, g_practice_id_cache) # Pass local cache # [cite: 209]
            if not tebra_practice_id_for_enc_payload: # [cite: 209]
                error_msg = f"P3 Error: Tebra Practice ID for '{practice_name_excel_grp}' not found for encounter creation." # [cite: 209]
                for idx_in_group in group_indices: # [cite: 209]
                    existing_err = str(df_param.loc[idx_in_group, actual_headers_map_param.get("Error", "Error")]).strip() # [cite: 210]
                    df_param.loc[idx_in_group, actual_headers_map_param.get("Error", "Error")] = f"{existing_err}; {error_msg}".strip('; ') # [cite: 210, 211]
                continue # [cite: 211]

            p3_results = _create_encounter_for_group_and_get_details( # [cite: 211]
                tebra_client_param, tebra_header_param, group_keys, current_group_df_slice,
                tebra_practice_id_for_enc_payload, # [cite: 211]
                patient_full_name_grp, # [cite: 211]
                log_prefix_grp,
                actual_headers_map_param, # Pass adapted map
                g_service_location_id_cache, # Pass local cache
                g_patient_case_id_cache, # Pass local cache
                g_provider_id_cache # Pass local cache # [cite: 212]
            )

            for idx_in_group in group_indices: # [cite: 212]
                df_param.loc[idx_in_group, actual_headers_map_param.get("Encounter ID", "Encounter ID")] = p3_results.get('EncounterID') # [cite: 212]
                df_param.loc[idx_in_group, actual_headers_map_param.get("Charge Amount", "Charge Amount")] = p3_results.get('ChargeAmount') # [cite: 212]
                df_param.loc[idx_in_group, actual_headers_map_param.get("Charge Status", "Charge Status")] = p3_results.get('ChargeStatus') # [cite: 212]

                phase1_2_messages_for_row_str = str(df_param.loc[idx_in_group, actual_headers_map_param.get("Error", "Error")]).strip() # [cite: 213]
                final_messages_list = [] # [cite: 215]
                if phase1_2_messages_for_row_str: # [cite: 215]
                    final_messages_list.extend(msg.strip() for msg in phase1_2_messages_for_row_str.split(';') if msg.strip()) # [cite: 215]

                payment_id_this_row = df_param.loc[idx_in_group, '_PaymentID_Temp'] # [cite: 215]

                if p3_results.get('EncounterID'): # [cite: 215]
                    encounter_success_msg = f"Encounter #{p3_results['EncounterID']} Created." # [cite: 216]
                    if payment_id_this_row and str(payment_id_this_row).strip(): # [cite: 218]
                        found_p2_success = False # [cite: 219]
                        for i, msg in enumerate(final_messages_list): # [cite: 219]
                            if str(payment_id_this_row) in msg and "Posted" in msg: # [cite: 219]
                                final_messages_list[i] = f"Payment #{payment_id_this_row} Posted. {encounter_success_msg}" # [cite: 220]
                                found_p2_success = True # [cite: 220]
                                break # [cite: 220]
                        if not found_p2_success: # [cite: 221]
                             final_messages_list.append(encounter_success_msg) # [cite: 221]
                    else: # No payment for this row, or payment failed. # [cite: 221]
                        final_messages_list.append(encounter_success_msg) # [cite: 222]

                    p3_simple_msg_for_warnings = p3_results.get('SimpleMessage', '') # [cite: 222]
                    temp_p3_warnings = [] # [cite: 224]
                    if "(Status Warn:" in p3_simple_msg_for_warnings: # [cite: 224]
                         temp_p3_warnings.append(p3_simple_msg_for_warnings[p3_simple_msg_for_warnings.find("(Status Warn:"):]) # [cite: 224]
                    elif p3_results.get('ChargeStatus') == "Status Fetch Error": # [cite: 225]
                         temp_p3_warnings.append("(Warn: Encounter status could not be confirmed)") # [cite: 225]

                    if "(Charge Warn:" in p3_simple_msg_for_warnings: # [cite: 225]
                         temp_p3_warnings.append(p3_simple_msg_for_warnings[p3_simple_msg_for_warnings.find("(Charge Warn:"):]) # [cite: 226]
                    elif p3_results.get('ChargeAmount') in ["Amount Fetch Error", "Amount Fetch Skipped", "Error"]: # [cite: 226]
                         temp_p3_warnings.append("(Warn: Charge amount could not be confirmed)") # [cite: 226]

                    for warn_msg in temp_p3_warnings: # [cite: 226, 227]
                         clean_warn = warn_msg.strip('; ') # [cite: 227, 228]
                         if clean_warn and clean_warn not in final_messages_list: final_messages_list.append(clean_warn) # [cite: 228]
                else: # P3 failed # [cite: 228]
                    final_messages_list.append(p3_results.get('SimpleMessage', "P3: Encounter processing issue.")) # [cite: 229]
                df_param.loc[idx_in_group, actual_headers_map_param.get("Error", "Error")] = "; ".join(filter(None, final_messages_list)).strip('; ') # [cite: 229]

    if '_PaymentID_Temp' in df_param.columns: # [cite: 229]
        df_param.drop(columns=['_PaymentID_Temp'], inplace=True) # [cite: 229]

    display_message("info", "🏁 All phases processing completed.") # [cite: 229]

    # Prepare summary for JSON response
    total_rows = len(df_param) # [cite: 229]
    enc_id_col_actual = actual_headers_map_param.get("Encounter ID", "Encounter ID") # [cite: 229]
    encounters_created = df_param[enc_id_col_actual].notna().sum() if enc_id_col_actual in df_param.columns else 0 # [cite: 229]

    # Counting successful payments requires checking the 'Error' column for payment success messages
    # or ideally a dedicated temporary column that tracks P2 success status.
    # For simplicity, we search for "Payment #" and "Posted" in the Error column.
    # This is a proxy and might not be perfectly robust if error messages also contain these strings.
    error_col_actual = actual_headers_map_param.get("Error", "Error") # [cite: 229]
    payments_posted_series = df_param[error_col_actual].astype(str).str.contains(r"Payment #\w+ Posted", na=False) # [cite: 229]
    payments_posted = payments_posted_series.sum() # [cite: 229]

    failed_rows = df_param[error_col_actual].astype(str).str.contains("Error|Failed|Skipped", case=False, na=False).sum() # [cite: 229]
    # Adjust failed_rows: if a row has a payment AND an encounter, it might not be a "failed" row in overall sense
    # This simple 'failed_rows' count might be an overestimation if success messages are also present.
    # A more nuanced definition of "failed_rows" might be needed based on business logic.
    # For instance, a row is truly failed if it has an error and NO successful encounter/payment.

    results_for_json = [] # [cite: 229]
    # Columns for JSON: original_excel_row_num, practice_name, patient_id, results string
    practice_name_col_actual = actual_headers_map_param.get("Practice", "Practice") # [cite: 229]
    patient_id_col_actual = actual_headers_map_param.get("Patient ID", "Patient ID") # [cite: 229]

    # ... inside run_all_phases_processing_adapted

    def clean_for_json(value, default=""):
        if pd.isna(value) or value is None: # Handles np.nan, pd.NA, None
            return None # Will be converted to null in JSON, or use default if you prefer ""
        return value

    for index, row in df_param.iterrows():
        results_for_json.append({
            "row_number": clean_for_json(row.get('original_excel_row_num'), index + 2), # row_number should ideally not be NaN
            "practice_name": clean_for_json(row.get(practice_name_col_actual, ""), ""),
            "patient_id": clean_for_json(row.get(patient_id_col_actual, ""), ""),
            "results": clean_for_json(row.get(error_col_actual, "No status"), "No status")
        })

    # Also ensure summary count values are valid integers
    summary = {
        "total_rows": int(total_rows) if pd.notna(total_rows) else 0,
        "encounters_created": int(encounters_created) if pd.notna(encounters_created) else 0,
        "payments_posted": int(payments_posted) if pd.notna(payments_posted) else 0,
        "failed_rows": int(failed_rows) if pd.notna(failed_rows) else 0,
        "results": results_for_json
    }
    
    
    return df_param, summary # [cite: 229]


# --- Flask Route Handlers ---
@user_bp.route('/api/process', methods=['POST'])
def process_file_route():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    customer_key = request.form.get('customer_key')
    username = request.form.get('username')
    password = request.form.get('password')

    if not all([customer_key, username, password]):
        return jsonify({"error": "Missing Tebra credentials"}), 400

    escaped_password = escape_xml_special_chars(password) # [cite: 3]
    
    credentials = { # [cite: 2]
        "CustomerKey": customer_key,
        "User": username,
        "Password": escaped_password
    }

    tebra_client = create_api_client_adapted(TEBRA_WSDL_URL) # [cite: 9]
    if not tebra_client:
        return jsonify({"error": "Failed to connect to Tebra API. Check server logs."}), 500

    tebra_header = build_request_header_adapted(credentials, tebra_client) # [cite: 9]
    if not tebra_header:
        return jsonify({"error": "Failed to build Tebra API request header. Check credentials and server logs."}), 500
    
    display_message("info", "✅ Tebra API client and header ready.")

    try:
        file_stream = io.BytesIO(file.read())
        # Use filename_str for validate_spreadsheet_adapted
        df, actual_column_headers_map, validation_errors = validate_spreadsheet_adapted(file_stream, file.filename) # [cite: 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36]
        file.close() 

        if df is None or validation_errors:
            error_message = "File validation failed: " + "; ".join(validation_errors)
            display_message("error", error_message)
            return jsonify({
                "error": error_message, # This key can be used by main.js if it checks for a general error
                "total_rows": 0, "encounters_created": 0, "payments_posted": 0, "failed_rows": 0,
                "results": [{"row_number": "N/A", "practice_name": "N/A", "patient_id": "N/A", "results": error_message}]
            }), 400
        
        display_message("info", "✅ File validated successfully. DataFrame is ready.") # [cite: 37]

        # --- MOCKING run_all_phases_processing_adapted FOR NOW ---
        # Comment out the actual call and use mock data until all helpers are fully adapted and tested.
        # display_message("warning", "USING MOCKED PROCESSING RESULTS until all Colab functions are adapted.")
        # processed_df = df.copy()
        # error_col_for_mock = actual_column_headers_map.get("Error", "Error")
        # if error_col_for_mock not in processed_df.columns: processed_df[error_col_for_mock] = "Mock processing - Tebra functions not yet called."
        # else: processed_df[error_col_for_mock] = processed_df[error_col_for_mock].fillna("Mock processing - Tebra functions not yet called.")
        # if 'original_excel_row_num' not in processed_df.columns: processed_df['original_excel_row_num'] = processed_df.index + 2


        # mock_results_for_json = []
        # practice_name_col_mock = actual_column_headers_map.get("Practice", "Practice")
        # patient_id_col_mock = actual_column_headers_map.get("Patient ID", "Patient ID")

        # for index_mock, row_mock in processed_df.iterrows():
        #     mock_results_for_json.append({
        #         "row_number": row_mock.get('original_excel_row_num', index_mock + 2),
        #         "practice_name": row_mock.get(practice_name_col_mock, "Mock Practice"),
        #         "patient_id": row_mock.get(patient_id_col_mock, "Mock PID"),
        #         "results": row_mock.get(error_col_for_mock, "Mock status")
        #     })
        # summary_stats = {
        #     "total_rows": len(processed_df),
        #     "encounters_created": 0, 
        #     "payments_posted": 0,    
        #     "failed_rows": processed_df[error_col_for_mock].str.contains("Error|Failed|Mock|Skipped", case=False, na=False).sum(),
        #     "results": mock_results_for_json
        # }
        # --- END MOCK ---

        # UNCOMMENT THIS LINE WHEN READY TO TEST FULL PROCESSING:
        processed_df, summary_stats = run_all_phases_processing_adapted(df, actual_column_headers_map, tebra_client, tebra_header)


        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") # [cite: 232]
        # Use a consistent base name for the processed file for easier identification by main.js if needed,
        # though main.js currently generates its own download filename.
        # The session filename should match what's saved.
        base_output_filename = "Processed_Tebra_Data"
        processed_filename_for_server = f"{base_output_filename}_{timestamp}.xlsx" # [cite: 234]
        processed_filepath = os.path.join(UPLOAD_FOLDER, processed_filename_for_server)

        if 'original_excel_row_num' in processed_df.columns: # [cite: 234]
            processed_df.drop(columns=['original_excel_row_num'], inplace=True, errors='ignore') # [cite: 235]
        
        processed_df.to_excel(processed_filepath, index=False) # [cite: 235]
        display_message("info", f"✅ Processed data saved to '{processed_filepath}'") # [cite: 235]

        session['processed_file_path'] = processed_filepath
        # Store a user-friendly download name, main.js will use its own generated name.
        session['processed_file_download_name'] = f"{base_output_filename}_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx"

        return jsonify(summary_stats), 200

    except zeep.exceptions.Fault as soap_fault: # [cite: 51, 74, 87, 99, 112, 119, 145, 157, 182]
        display_message("error", f"SOAP FAULT during processing: {soap_fault.message}")
        if soap_fault.detail is not None:
             display_message("error", f"SOAP Detail: {zeep.helpers.serialize_object(soap_fault.detail)}")
        return jsonify({"error": f"Tebra API SOAP Fault: {soap_fault.message}. Check server logs."}), 500
    except Exception as e:
        display_message("error", f"An error occurred during processing: {e}") # [cite: 5, 8, 27, 51, 74, 87, 91, 99, 113, 119, 123, 131, 139, 145, 157, 182, 237, 248]
        display_message("error", f"Stack trace: {traceback.format_exc()}") # [cite: 182, 237, 248]
        return jsonify({"error": f"An unexpected error occurred: {str(e)}. Check server logs."}), 500

@user_bp.route('/api/download', methods=['GET'])
def download_file_route():
    processed_filepath = session.get('processed_file_path')
    # Use the name stored in session for 'download_name' for consistency if frontend doesn't override
    processed_filename_for_download = session.get('processed_file_download_name', 'Processed_Tebra_Data.xlsx') # [cite: 236]

    if not processed_filepath or not os.path.exists(processed_filepath):
        return jsonify({"error": "Processed file not found or path not in session. Please process a file first."}), 404

    try:
        return send_file(processed_filepath, as_attachment=True, download_name=processed_filename_for_download) # [cite: 236]
    except Exception as e: # [cite: 236]
        display_message("error", f"Error during file download: {e}")
        return jsonify({"error": str(e)}), 500
    # finally:
        # Optional: Clean up the file from the server after download if desired
        # Consider if multiple downloads of the same file are needed or if it's one-time
        # if processed_filepath and os.path.exists(processed_filepath):
        #     try:
        #         os.remove(processed_filepath)
        #         display_message("info", f"Cleaned up temporary file: {processed_filepath}")
        #     except Exception as e_remove:
        #         display_message("error", f"Error cleaning up temp file {processed_filepath}: {e_remove}")
        # session.pop('processed_file_path', None)
        # session.pop('processed_file_download_name', None)