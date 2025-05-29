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

@user_bp.route('/health', methods=['GET'])
def health_check():
    return "OK", 200

# Use /tmp for Azure's ephemeral storage, otherwise use a local folder
UPLOAD_FOLDER = '/tmp' if os.path.exists('/tmp') else 'temp_files'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# --- Helper: Display Message (from Colab PART 3) ---
def display_message(level, message): #
    """Prints a formatted message to the server console."""
    print(f"[{level.upper()}] {message}")

# --- Tebra WSDL URL (from Colab PART 2) ---
TEBRA_WSDL_URL = "https://webservice.kareo.com/services/soap/2.1/KareoServices.svc?singleWsdl" #

# --- 🔐 PART 2 Adaptations (Credentials & API Client) ---
def escape_xml_special_chars(password): #
    """Escapes special XML characters in the password."""
    password = password.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&apos;') #
    return password

def create_api_client_adapted(wsdl_url): #
    """Creates and returns a Zeep client for the Tebra SOAP API."""
    display_message("info", "Attempting to connect to Tebra SOAP API...")
    try:
        from requests import Session as RequestsSession # Renamed to avoid conflict with flask.session
        from zeep.transports import Transport #

        session_req = RequestsSession() #
        session_req.timeout = 60  # Set a timeout for the session (seconds) #
        transport = Transport(session=session_req, timeout=60) # Set a timeout for the transport #

        client = zeep.Client(wsdl=wsdl_url, transport=transport) #
        display_message("info", "✅ Connected to Tebra API.") #
        return client
    except Exception as e: #
        display_message("error", f"❌ Failed to connect to Tebra API.") #
        display_message("error", f"Details: {e}") #
        return None

def build_request_header_adapted(credentials, client): #
    """Builds the request header for Tebra API calls."""
    if not client:
        display_message("error", "Cannot build request header: API client is not available.")
        return None
    try:
        header_type = client.get_type('ns0:RequestHeader') #
        request_header = header_type(
            CustomerKey=credentials['CustomerKey'],
            User=credentials['User'],
            Password=credentials['Password']
        ) #
        return request_header
    except Exception as e: #
        display_message("error", f"❌ Error building request header: {e}") #
        display_message("error", "Ensure the WSDL loaded correctly and 'ns0:RequestHeader' is the correct type.") #
        return None

# --- 📄 PART 3 Adaptations (File Upload, Validation) ---
# MODIFIED EXPECTED_COLUMNS_CONFIG from tebra_automation_tool_v2.py
EXPECTED_COLUMNS_CONFIG = {
    # Phase 1 Inputs (Read from Excel/CSV)
    "Patient ID": {"normalized": "patient id", "is_critical_input": True, "purpose": "Input for Phase 1 & 2 & 3 (Patient Identifier)"},
    "Practice": {"normalized": "practice", "is_critical_input": True, "purpose": "Input for Phase 1, 2 & 3 (Practice/Service Location Name & Tebra Practice Context)"},
    "DOS": {"normalized": "dos", "is_critical_input": True, "purpose": "Input for Phase 1 (Insurance Check) & Phase 3 (Encounter DOS)"},

    # Phase 1 Outputs (Script writes to these columns)
    "Patient Name": {"normalized": "patient name", "is_critical_input": False, "purpose": "Output for Phase 1 (Fetched Patient Name)"},
    "DOB": {"normalized": "dob", "is_critical_input": False, "purpose": "Output for Phase 1 (Fetched Patient DOB)"},
    "Insurance": {"normalized": "insurance", "is_critical_input": False, "purpose": "Output for Phase 1 (Fetched Insurance Name)"},
    "Insurance ID": {"normalized": "insurance id", "is_critical_input": False, "purpose": "Output for Phase 1 (Fetched Insurance Policy #)"},
    "Insurance Status": {"normalized": "insurance status", "is_critical_input": False, "purpose": "Output for Phase 1 (Fetched Insurance Status)"},

    # Phase 2 Inputs (Read from Excel/CSV) - Criticality changed to False
    "PP Batch #": {"normalized": "pp batch #", "is_critical_input": False, "purpose": "Input for Phase 2 (Payment Batch, optional)"},
    "Patient Payment": {"normalized": "patient payment", "is_critical_input": False, "purpose": "Input for Phase 2 (Payment Amount, optional)"},
    "Patient Payment Source": {"normalized": "patient payment source", "is_critical_input": False, "purpose": "Input for Phase 2 (Payment Source, optional)"},
    "Reference Number": {"normalized": "reference number", "is_critical_input": False, "purpose": "Input for Phase 2 (Payment Reference, optional)"},

    # Phase 3 Inputs (Read from Excel/CSV for Encounter Creation)
    "CE Batch #": {"normalized": "ce batch #", "is_critical_input": False, "purpose": "Input for Phase 3 (Encounter Batch Number, optional)"},
    "Rendering Provider": {"normalized": "rendering provider", "is_critical_input": True, "purpose": "Input for Phase 3 (Rendering Provider Name - CRITICAL)"},
    "Scheduling Provider": {"normalized": "scheduling provider", "is_critical_input": False, "purpose": "Input for Phase 3 (Scheduling Provider Name, optional)"},
    "Referring Provider": {"normalized": "referring provider", "is_critical_input": False, "purpose": "Input for Phase 3 (Referring Provider, optional)"}, # NEW
    "Encounter Mode": {"normalized": "encounter mode", "is_critical_input": True, "purpose": "Input for Phase 3 (e.g., Tele Health, In Office - CRITICAL)"},
    "POS": {"normalized": "pos", "is_critical_input": True, "purpose": "Input for Phase 3 (Place of Service Code - CRITICAL)"},
    "Admit Date": {"normalized": "admit date", "is_critical_input": False, "purpose": "Input for Phase 3 (Hospitalization Admit Date, optional)"}, # NEW
    "Discharge Date": {"normalized": "discharge date", "is_critical_input": False, "purpose": "Input for Phase 3 (Hospitalization Discharge Date, optional)"}, # NEW
    "Procedures": {"normalized": "procedures", "is_critical_input": True, "purpose": "Input for Phase 3 (Procedure Code - CRITICAL)"},
    "Mod 1": {"normalized": "mod 1", "is_critical_input": False, "purpose": "Input for Phase 3 (Modifier 1, optional)"},
    "Mod 2": {"normalized": "mod 2", "is_critical_input": False, "purpose": "Input for Phase 3 (Modifier 2, optional)"},
    "Mod 3": {"normalized": "mod 3", "is_critical_input": False, "purpose": "Input for Phase 3 (Modifier 3, optional)"},
    "Mod 4": {"normalized": "mod 4", "is_critical_input": False, "purpose": "Input for Phase 3 (Modifier 4, optional)"},
    "Units": {"normalized": "units", "is_critical_input": True, "purpose": "Input for Phase 3 (Procedure Units - CRITICAL)"},
    "Diag 1": {"normalized": "diag 1", "is_critical_input": True, "purpose": "Input for Phase 3 (Diagnosis Code 1 - CRITICAL)"},
    "Diag 2": {"normalized": "diag 2", "is_critical_input": False, "purpose": "Input for Phase 3 (Diagnosis Code 2, optional)"},
    "Diag 3": {"normalized": "diag 3", "is_critical_input": False, "purpose": "Input for Phase 3 (Diagnosis Code 3, optional)"},
    "Diag 4": {"normalized": "diag 4", "is_critical_input": False, "purpose": "Input for Phase 3 (Diagnosis Code 4, optional)"},

    # Phase 3 Outputs (Script writes to these columns)
    "Charge Amount": {"normalized": "charge amount", "is_critical_input": False, "purpose": "Output for Phase 3 (Fetched Encounter Charge Amount)"},
    "Charge Status": {"normalized": "charge status", "is_critical_input": False, "purpose": "Output for Phase 3 (Fetched Encounter Status)"},
    "Encounter ID": {"normalized": "encounter id", "is_critical_input": False, "purpose": "Output for Phase 3 (Created Encounter ID)"},
}

def normalize_header_name_adapted(header_name): #
    """Converts header to lowercase, trims, and replaces multiple spaces with a single space."""
    if pd.isna(header_name) or not isinstance(header_name, str): #
        return ""
    return ' '.join(str(header_name).lower().strip().split()) #

def validate_spreadsheet_adapted(file_stream, filename_str): #
    df_temp = None
    actual_column_headers_map = {} #
    error_messages = []
    target_sheet_name = "Charges" # Process only this sheet as per tebra_automation_tool_v2.py

    for config_item in EXPECTED_COLUMNS_CONFIG.values(): #
        config_item["actual_header_found"] = None

    display_message("info", f"Processing uploaded file stream for: '{filename_str}'")

    try:
        if filename_str.lower().endswith(('.xlsx', '.xls')): #
            display_message("info", f"Attempting to read '{target_sheet_name}' tab from Excel file (first row should be headers)...")
            xls = pd.ExcelFile(file_stream)
            if target_sheet_name not in xls.sheet_names:
                error_messages.append(f"CRITICAL: Target sheet '{target_sheet_name}' not found in '{filename_str}'. Available sheets: {xls.sheet_names}. Please ensure your Excel file contains a sheet named 'Charges'.")
                return None, {}, error_messages
            # Read all data as strings to preserve formatting like leading zeros
            df_temp = pd.read_excel(xls, sheet_name=target_sheet_name, dtype=str, keep_default_na=True) #
        else:
            error_messages.append(f"Unsupported file type: '{filename_str}'. Please upload an XLSX or XLS file.") #
            return None, {}, error_messages

        display_message("info", f"Successfully read '{target_sheet_name}' tab from '{filename_str}'. Initial columns found: {df_temp.columns.tolist()}")

        if not df_temp.empty: #
            first_cell_first_data_row = str(df_temp.iloc[0, 0]).lower() #
            if "script will read this from excel" in first_cell_first_data_row or \
               ("practice" == first_cell_first_data_row and len(df_temp.columns) > 1 and "patient id" == str(df_temp.iloc[0,1]).lower()): #
                display_message("info", "Detected and skipping a descriptive first data row (assuming actual headers are used by pandas).") #
                df_temp = df_temp.iloc[1:].reset_index(drop=True) #

        display_message("info", f"DataFrame ready for validation. Found {len(df_temp.columns)} columns and {len(df_temp)} data rows from '{target_sheet_name}' tab.") #
        if df_temp.empty and len(df_temp.columns) == 0 : #
             error_messages.append(f"The '{target_sheet_name}' tab appears to be empty or has no columns after initial read.")
             return None, {}, error_messages
        elif df_temp.empty: # Has columns but no data rows
             display_message("warning", f"The '{target_sheet_name}' tab contains headers but no actual data rows. Column validation will proceed.")
    except Exception as e: #
        error_messages.append(f"Error reading or initially processing file '{filename_str}': {e}") #
        return None, {}, error_messages

    actual_headers_from_file = df_temp.columns.tolist() #
    normalized_headers_map_from_file = {normalize_header_name_adapted(h): h for h in actual_headers_from_file} #

    missing_critical_inputs = [] #
    found_all_critical = True #

    for logical_name, config in EXPECTED_COLUMNS_CONFIG.items(): #
        normalized_expected = config["normalized"] #
        actual_header_found_in_file = normalized_headers_map_from_file.get(normalized_expected) #

        if actual_header_found_in_file: #
            actual_column_headers_map[logical_name] = actual_header_found_in_file #
            config["actual_header_found"] = actual_header_found_in_file #
        elif config["is_critical_input"]: #
            missing_critical_inputs.append(f"'{logical_name}' (expected normalized: '{normalized_expected}')") #
            found_all_critical = False #
        else: # Not critical and not found, will map logical name to itself for potential creation #
            actual_column_headers_map[logical_name] = logical_name #


    if not found_all_critical: #
        error_messages.append(f"CRITICAL INPUT COLUMNS ARE MISSING OR MISMATCHED in the '{target_sheet_name}' tab:") #
        for col_detail in missing_critical_inputs: #
            error_messages.append(f"  - {col_detail} - Not found in file's normalized headers.") #
        return None, actual_column_headers_map, error_messages

    display_message("info", f"All critical input columns found and mapped successfully from '{target_sheet_name}' tab.") #

    output_columns_to_ensure = { #
        "Patient Name": "Patient Name", "DOB": "DOB", "Insurance": "Insurance", #
        "Insurance ID": "Insurance ID", "Insurance Status": "Insurance Status", #
        "Charge Amount": "Charge Amount", "Charge Status": "Charge Status", #
        "Encounter ID": "Encounter ID", "Error": "Error" #
    }

    for logical_output_name, default_col_name in output_columns_to_ensure.items(): #
        actual_col_name_to_use = actual_column_headers_map.get(logical_output_name, default_col_name) #
        if actual_col_name_to_use not in df_temp.columns: #
            df_temp[actual_col_name_to_use] = "" # Initialize empty for strings #
            display_message("info", f"Output column '{actual_col_name_to_use}' (for {logical_output_name}) added to DataFrame.") #
        elif logical_output_name == "Error": # Ensure "Error" column is cleared for new run #
             df_temp[actual_col_name_to_use] = "" #
    return df_temp, actual_column_headers_map, error_messages


# --- 🛠️ PART 4: Core Utility Functions (Adapted from Colab) ---

def is_date_value_present(date_str): #
    """Checks if a date string is not None, not empty, and not the literal string 'None'."""
    if pd.isna(date_str) or date_str is None: #
        return False
    s = str(date_str).strip() #
    return bool(s and s.lower() != 'none') # Simplified from v2

PAYMENT_SOURCE_TO_CODE = { #
    "CHECK": "1", #
    "CREDIT CARD": "3", #
    "CC": "3", #
    "ELECTRONIC FUNDS TRANSFER": "4", #
    "EFT": "4", #
    "CASH": "5" #
}

def get_payment_source_code(source_str): #
    """Normalizes payment source string and returns Tebra code."""
    if pd.isna(source_str) or not source_str: #
        return None
    normalized_source = str(source_str).strip().upper() #
    return PAYMENT_SOURCE_TO_CODE.get(normalized_source) #

def get_practice_id_by_name(client_obj, header_obj, practice_name_to_find, cache_dict): #
    # Using robust version from tebra_automation_tool_v2.py (Part 4A)
    if pd.isna(practice_name_to_find) or not str(practice_name_to_find).strip(): #
        display_message("warning", "[GetPracticeID] Practice name is missing. Cannot fetch ID.") #
        return None
    normalized_practice_name = str(practice_name_to_find).strip().lower() #
    if normalized_practice_name in cache_dict: #
        cached_id = cache_dict[normalized_practice_name]
        display_message("debug", f"[GetPracticeID] Found '{practice_name_to_find}' in cache. ID: {cached_id}") #
        return cached_id #
    display_message("info", f"[GetPracticeID] Practice '{practice_name_to_find}' not in cache. Querying API...") #
    try:
        GetPracticesReqType = client_obj.get_type('ns0:GetPracticesReq') #
        PracticeFilterType = client_obj.get_type('ns0:PracticeFilter') #
        PracticeFieldsToReturnType = client_obj.get_type('ns0:PracticeFieldsToReturn') #
        practice_filter = PracticeFilterType(PracticeName=str(practice_name_to_find).strip()) #
        fields_to_return = PracticeFieldsToReturnType(ID=True, PracticeName=True, Active=True) #
        request_payload = GetPracticesReqType(RequestHeader=header_obj, Filter=practice_filter, Fields=fields_to_return)
        api_response = client_obj.service.GetPractices(request=request_payload) #
        if hasattr(api_response, 'ErrorResponse') and api_response.ErrorResponse and api_response.ErrorResponse.IsError: #
            display_message("error", f"[GetPracticeID] API Error for '{practice_name_to_find}': {api_response.ErrorResponse.ErrorMessage}") #
            return None
        if hasattr(api_response, 'SecurityResponse') and api_response.SecurityResponse and not api_response.SecurityResponse.Authorized: #
            display_message("error", f"[GetPracticeID] API Auth Error for '{practice_name_to_find}': {api_response.SecurityResponse.SecurityResult}") #
            return None #
        if hasattr(api_response, 'Practices') and api_response.Practices and hasattr(api_response.Practices, 'PracticeData') and api_response.Practices.PracticeData: #
            all_practices_data = api_response.Practices.PracticeData #
            if not isinstance(all_practices_data, list): all_practices_data = [all_practices_data] if all_practices_data else [] #
            found_active_id, found_inactive_id = None, None
            for p_data in all_practices_data: #
                api_practice_name = str(getattr(p_data, 'PracticeName', '')).strip()
                current_id_str = str(getattr(p_data, 'ID', '')).strip()
                is_active = (str(getattr(p_data, 'Active', 'false')).lower() == 'true')
                if api_practice_name.lower() == normalized_practice_name:
                    if is_active and current_id_str: found_active_id = current_id_str; break
                    elif not found_active_id and current_id_str: found_inactive_id = current_id_str #
            final_id_to_use = found_active_id if found_active_id else found_inactive_id
            if final_id_to_use:
                display_message("info" if found_active_id else "warning", f"[GetPracticeID] Match for '{practice_name_to_find}': ID {final_id_to_use}{'' if found_active_id else ' (INACTIVE)'}.") #
                cache_dict[normalized_practice_name] = final_id_to_use; return final_id_to_use #
            else: display_message("warning", f"[GetPracticeID] No exact name match for '{practice_name_to_find}'."); cache_dict[normalized_practice_name] = None; return None #
        else: display_message("warning", f"[GetPracticeID] No 'Practices.PracticeData' for '{practice_name_to_find}'."); cache_dict[normalized_practice_name] = None; return None #
    except zeep.exceptions.Fault as sf: display_message("error", f"[GetPracticeID] SOAP FAULT for '{practice_name_to_find}': {sf.message}") #
    except Exception as e: display_message("error", f"[GetPracticeID] Error for '{practice_name_to_find}': {type(e).__name__} - {e}") #
    return None

# MODIFIED phase1_fetch_patient_and_insurance from tebra_automation_tool_v2.py (Part 4A)
def phase1_fetch_patient_and_insurance(client_obj, header_obj, patient_id_str, practice_name_context, dos_str):
    results = { #
        'FetchedPatientName': None, 'FetchedPatientDOB': None, #
        'FetchedInsuranceName': None, 'FetchedInsuranceID': None, #
        'FetchedInsuranceStatus': "Error during fetch", 'SimpleError': None #
    }
    if pd.isna(patient_id_str) or not str(patient_id_str).strip(): #
        results['SimpleError'] = "Patient ID is missing."; results['FetchedInsuranceStatus'] = "Patient ID Missing"; return results #
    try: patient_id_int = int(float(str(patient_id_str).strip())) #
    except ValueError: results['SimpleError'] = f"Invalid Patient ID format: '{patient_id_str}'."; results['FetchedInsuranceStatus'] = "Invalid Patient ID"; return results #

    dos_date_obj, dos_available = None, False #
    if is_date_value_present(dos_str): #
        try: dos_date_obj = pd.to_datetime(dos_str).date(); dos_available = True #
        except Exception as e: results['SimpleError'] = f"Invalid DOS '{dos_str}': {e}"; results['FetchedInsuranceStatus'] = "Invalid DOS for Check" #
    else: results['FetchedInsuranceStatus'] = "DOS Missing for Ins Check" #

    display_message("info", f"[Phase1] Fetching Pt/Ins for ID: {patient_id_int}, PracCtx: {practice_name_context}, Eff. DOS: {dos_date_obj if dos_available else 'N/A'}") #
    try:
        GetPatientReqType = client_obj.get_type('ns0:GetPatientReq') #
        SinglePatientFilterType = client_obj.get_type('ns0:SinglePatientFilter') #
        request_payload = GetPatientReqType(RequestHeader=header_obj, Filter=SinglePatientFilterType(PatientID=patient_id_int)) #
        api_response = client_obj.service.GetPatient(request=request_payload) #

        if hasattr(api_response, 'ErrorResponse') and api_response.ErrorResponse and api_response.ErrorResponse.IsError: #
            results['SimpleError'] = f"API Err(GetPt): {api_response.ErrorResponse.ErrorMessage}"; results['FetchedInsuranceStatus'] = "API Error (Patient)"; return results #
        if hasattr(api_response, 'SecurityResponse') and api_response.SecurityResponse and not api_response.SecurityResponse.Authorized: #
            results['SimpleError'] = f"API Auth Err(GetPt): {api_response.SecurityResponse.SecurityResult}"; results['FetchedInsuranceStatus'] = "API Auth Error (Patient)"; return results #

        if hasattr(api_response, 'Patient') and api_response.Patient: #
            pt_data = api_response.Patient #
            results['FetchedPatientName'] = f"{getattr(pt_data, 'FirstName', '')} {getattr(pt_data, 'LastName', '')}".strip() or None #
            dob_val = getattr(pt_data, 'DOB', None) #
            if is_date_value_present(dob_val): #
                 try: results['FetchedPatientDOB'] = pd.to_datetime(dob_val).strftime('%Y-%m-%d') #
                 except: results['FetchedPatientDOB'] = str(dob_val) #


            if not dos_available: results['FetchedInsuranceStatus'] = "Ins. Check Skipped (No Valid DOS)" #
            elif hasattr(pt_data, 'Cases') and pt_data.Cases and hasattr(pt_data.Cases, 'PatientCaseData') and pt_data.Cases.PatientCaseData: #
                all_cases_data = pt_data.Cases.PatientCaseData #
                all_cases = all_cases_data if isinstance(all_cases_data, list) else [all_cases_data] if all_cases_data else [] #
                
                primary_case_obj = next((c for c in all_cases if str(getattr(c, 'IsPrimaryCase', 'false')).lower() == 'true'), all_cases[0] if all_cases else None)

                if primary_case_obj and hasattr(primary_case_obj, 'InsurancePolicies') and primary_case_obj.InsurancePolicies and \
                   hasattr(primary_case_obj.InsurancePolicies, 'PatientInsurancePolicyData') and primary_case_obj.InsurancePolicies.PatientInsurancePolicyData: #
                    policies_on_case_raw = primary_case_obj.InsurancePolicies.PatientInsurancePolicyData #
                    policies = policies_on_case_raw if isinstance(policies_on_case_raw, list) else [policies_on_case_raw] if policies_on_case_raw else [] #
                    
                    found_primary_active_policy = False
                    for policy_obj in policies: # Assuming API returns policies in precedence order (Primary first) #
                        eff_start_str = getattr(policy_obj, 'EffectiveStartDate', None) #
                        eff_end_str = getattr(policy_obj, 'EffectiveEndDate', None) #
                        is_active_on_dos = False #
                        has_valid_start = is_date_value_present(eff_start_str) #
                        has_valid_end = is_date_value_present(eff_end_str) #

                        if has_valid_start: #
                            try: #
                                eff_start_date = pd.to_datetime(eff_start_str).date() #
                                if eff_start_date <= dos_date_obj: #
                                    if not has_valid_end: #
                                        is_active_on_dos = True #
                                    else: #
                                        eff_end_date = pd.to_datetime(eff_end_str).date() #
                                        if eff_end_date >= dos_date_obj: #
                                            is_active_on_dos = True #
                            except Exception: pass #
                        elif not has_valid_start and not has_valid_end: # No dates, assume active #
                            is_active_on_dos = True #
                        
                        if is_active_on_dos: #
                            results['FetchedInsuranceName'] = str(getattr(policy_obj, 'PlanName', getattr(policy_obj, 'CompanyName', 'N/A'))).strip() #
                            results['FetchedInsuranceID'] = str(getattr(policy_obj, 'Number', 'N/A')).strip() #
                            results['FetchedInsuranceStatus'] = "Active" #
                            found_primary_active_policy = True
                            display_message("debug", f"[Phase1] Pt {patient_id_int}: Found Primary Active Policy - Name: '{results['FetchedInsuranceName']}', ID: '{results['FetchedInsuranceID']}'")
                            break # Stop after finding the first active policy (assumed primary)
                    if not found_primary_active_policy: results['FetchedInsuranceStatus'] = "No Primary Active Ins. Found" #
                else: results['FetchedInsuranceStatus'] = "No Ins. Policies on Primary Case" #
            else: results['FetchedInsuranceStatus'] = "No Case Data for Ins. Check" if dos_available else results['FetchedInsuranceStatus'] #
        else: results['SimpleError'] = "Patient data not in API resp."; results['FetchedInsuranceStatus'] = "Patient Not Found" #
    except zeep.exceptions.Fault as sf: results['SimpleError'] = f"SOAP Fault(GetPt): {sf.message}"; results['FetchedInsuranceStatus'] = "SOAP Error (Patient)" #
    except Exception as e: results['SimpleError'] = f"Error in Ph1(GetPt): {type(e).__name__} - {e}"; results['FetchedInsuranceStatus'] = "Sys Err(Pt)" #
    if results['SimpleError']: display_message("warning", f"[Phase1] Patient {patient_id_int if 'patient_id_int' in locals() else patient_id_str}: {results['SimpleError']}") #
    return results #


def phase2_post_tebra_payment(client_obj, header_obj, patient_id_str, resolved_practice_id_str, #
                              practice_name_context, pp_batch_str, payment_amount_input_str,
                              payment_source_input_str, payment_ref_num_str):
    results = {'Success': False, 'Message': "Processing not initiated.", #
               'SimpleMessage': "Payment not processed.", 'PaymentID': None} #

    critical_payment_fields = { #
        "Patient ID": patient_id_str, #
        "Practice ID": resolved_practice_id_str, #
        "PP Batch #": pp_batch_str, #
        "Patient Payment": payment_amount_input_str, #
        "Patient Payment Source": payment_source_input_str #
    }
    # Check if any of the core payment fields (batch, amount, source) are missing, if so, skip.
    # This check makes payment posting optional as per tebra_automation_tool_v2.py
    payment_core_inputs = [pp_batch_str, payment_amount_input_str, payment_source_input_str]
    if not all(val and str(val).strip() and str(val).strip().lower() != 'nan' for val in payment_core_inputs):
        results['SimpleMessage'] = f"P2 Skipped: Missing one or more core payment inputs (Batch, Amount, Source)."
        return results


    missing_or_invalid_fields = [] #
    for field_name, field_value in critical_payment_fields.items(): #
        if pd.isna(field_value) or not str(field_value).strip() or str(field_value).strip().lower() == 'nan': #
            missing_or_invalid_fields.append(field_name) #

    if missing_or_invalid_fields: #
        # This specific check might be redundant if the above core input check handles it.
        # However, keeping it for robustness as per original structure.
        results['SimpleMessage'] = f"P2 Skipped: Missing/invalid data for: {', '.join(missing_or_invalid_fields)}." #
        return results #

    try:
        cleaned_amount_str = str(payment_amount_input_str).replace('$', '').replace(',', '').strip() #
        amount_float = float(cleaned_amount_str) #
        if amount_float <= 0: # Typically payments should be positive #
            results['SimpleMessage'] = f"P2 Invalid: Payment amount ${amount_float:.2f} must be > 0." #
            display_message("warning", f"[Phase2] Pt {patient_id_str}: {results['SimpleMessage']}") #
            return results #
        amount_to_post_str = f"{amount_float:.2f}" #
    except ValueError: #
        results['SimpleMessage'] = f"P2 Invalid: Payment amount format '{payment_amount_input_str}'." #
        display_message("warning", f"[Phase2] Pt {patient_id_str}: {results['SimpleMessage']}") #
        return results #

    payment_method_code = get_payment_source_code(payment_source_input_str) #
    if not payment_method_code: #
        results['SimpleMessage'] = f"P2 Invalid: Unmapped payment source '{payment_source_input_str}'." #
        display_message("warning", f"[Phase2] Pt {patient_id_str}: {results['SimpleMessage']}") #
        return results #

    display_message("info", f"[Phase2] Attempting to post payment for Pt ID: {patient_id_str}, Practice ID: {resolved_practice_id_str}, Amount: ${amount_to_post_str}, Batch: {pp_batch_str}") #
    try: #
        CreatePaymentRequestType = client_obj.get_type('ns0:CreatePaymentRequest') #
        PaymentCreateType = client_obj.get_type('ns0:PaymentCreate') #
        PaymentPatientCreateType = client_obj.get_type('ns0:PaymentPatientCreate') #
        PaymentPaymentCreateType = client_obj.get_type('ns0:PaymentPaymentCreate') #
        PaymentPracticeCreateType = client_obj.get_type('ns0:PaymentPracticeCreate') #

        patient_data = PaymentPatientCreateType(PatientID=str(patient_id_str).strip()) #
        payment_data_obj = PaymentPaymentCreateType( #
            AmountPaid=amount_to_post_str, #
            PaymentMethod=payment_method_code, #
            ReferenceNumber=str(payment_ref_num_str if pd.notna(payment_ref_num_str) else '').strip() #
        )
        practice_data_obj = PaymentPracticeCreateType( #
            PracticeID=str(resolved_practice_id_str).strip(), #
            PracticeName=str(practice_name_context).strip() #
        )
        payment_to_create_obj = PaymentCreateType( #
            BatchNumber=str(pp_batch_str).strip(), #
            Patient=patient_data, #
            PayerType="Patient", #
            Payment=payment_data_obj, #
            Practice=practice_data_obj #
        )
        request_payload = CreatePaymentRequestType(RequestHeader=header_obj, Payment=payment_to_create_obj) #
        api_response = client_obj.service.CreatePayment(request=request_payload) #

        if hasattr(api_response, 'ErrorResponse') and api_response.ErrorResponse and api_response.ErrorResponse.IsError: #
            err_msg = api_response.ErrorResponse.ErrorMessage #
            results['Message'] = f"API Error (CreatePayment): {err_msg}" #
            results['SimpleMessage'] = f"P2 API Error ({err_msg[:70].strip()}...)" #
        elif hasattr(api_response, 'SecurityResponse') and api_response.SecurityResponse and not api_response.SecurityResponse.Authorized: #
            sec_msg = api_response.SecurityResponse.SecurityResult #
            results['Message'] = f"API Auth Error (CreatePayment): {sec_msg}" #
            results['SimpleMessage'] = "P2 API Auth Error." #
        elif hasattr(api_response, 'PaymentID') and api_response.PaymentID is not None and int(api_response.PaymentID) > 0: #
            results['Success'] = True #
            results['PaymentID'] = str(api_response.PaymentID) #
            results['Message'] = f"Payment successfully posted. Tebra Payment ID: {results['PaymentID']}" #
            results['SimpleMessage'] = f"Payment #{results['PaymentID']} Posted." #
        else: #
            results['Message'] = "Payment response from Tebra unclear (no PaymentID or error)." #
            results['SimpleMessage'] = "P2 Status Unknown (Tebra resp unclear)." #
            if client_obj and api_response: display_message("warning", f"[Phase2] Unclear payment for Pt {patient_id_str}. Resp: {zeep.helpers.serialize_object(api_response, dict)}") #
    except zeep.exceptions.Fault as soap_fault: #
        results['Message'] = f"SOAP FAULT (CreatePayment): {soap_fault.message}"; results['SimpleMessage'] = "P2 Failed (SOAP Error)." #
    except Exception as e: #
        results['Message'] = f"Error during payment: {type(e).__name__} - {str(e)}"; results['SimpleMessage'] = f"P2 Failed (System Error: {type(e).__name__})." #
    
    log_level = "error" if not results['Success'] and "Skipped" not in results['SimpleMessage'] else "info" #
    if results['SimpleMessage'] and "Skipped" not in results['SimpleMessage']: display_message(log_level, f"[Phase2] Pt {patient_id_str}: {results['SimpleMessage']}") #
    elif "Skipped" in results['SimpleMessage']: display_message("debug", f"[Phase2] Pt {patient_id_str}: {results['SimpleMessage']}") #
    return results #

# --- HELPER FUNCTIONS FOR PHASE 3: ENCOUNTER CREATION ---
# MODIFIED POS_CODE_MAP_PHASE3 from tebra_automation_tool_v2.py (Part 4C)
POS_CODE_MAP_PHASE3 = { #
    "OFFICE": {"code": "11", "name": "Office"}, #
    "IN OFFICE": {"code": "11", "name": "Office"}, #
    "INOFFICE": {"code": "11", "name": "Office"}, #
    "TELEHEALTH": {"code": "10", "name": "Telehealth Provided in Patient’s Home"}, #
    "TELEHEALTH OFFICE": {"code": "02", "name": "Telehealth Provided Other than in Patient’s Home"}, #
    "HOME": {"code": "12", "name": "Home"},
    "IH": {"code": "21", "name": "Inpatient Hospital"},
    "INPATIENT HOSPITAL": {"code": "21", "name": "Inpatient Hospital"},
    "OH": {"code": "22", "name": "Outpatient Hospital"},
    "OUTPATIENT HOSPITAL": {"code": "22", "name": "Outpatient Hospital"},
    "ER": {"code": "23", "name": "Emergency Room - Hospital"},
    "EMERGENCY ROOM": {"code": "23", "name": "Emergency Room - Hospital"},
    "ASC": {"code": "24", "name": "Ambulatory Surgical Center"},
    "AMBULATORY SURGICAL CENTER": {"code": "24", "name": "Ambulatory Surgical Center"},
    "DEFAULT_IN_OFFICE": {"code": "11", "name": "Office"},
    "DEFAULT_TELEHEALTH": {"code": "10", "name": "Telehealth Provided in Patient’s Home"}
}

ENCOUNTER_STATUS_CODE_MAP_PHASE3 = { #
    "0": "Undefined", "1": "Draft", "2": "Review", #
    "3": "Approved",  "4": "Rejected", "5": "Billed", #
    "6": "Unpayable", "7": "Pending", #
}

def map_encounter_status_code(status_code_str): #
    """Maps an encounter status code string to a descriptive string."""
    if pd.isna(status_code_str) or not str(status_code_str).strip(): #
        return "Status N/A" #
    return ENCOUNTER_STATUS_CODE_MAP_PHASE3.get(str(status_code_str).strip(), f"Unknown Code ({status_code_str})") #

def format_datetime_for_api_phase3(date_value): #
    if pd.isna(date_value) or date_value is None: return None #
    try:
        dt_obj = pd.to_datetime(date_value) #
        return dt_obj.strftime('%Y-%m-%dT%H:%M:%S') #
    except Exception as e: #
        display_message("warning", f"[FormatDT_P3] Date parse warning for '{date_value}'. Error: {e}. Using None.") #
        return None #

def get_service_location_id_by_name(client_obj, header_obj, service_location_name_to_find, current_practice_id_context, cache_dict): #
    # Using robust version from tebra_automation_tool_v2.py (Part 4C)
    if pd.isna(service_location_name_to_find) or not str(service_location_name_to_find).strip(): #
        display_message("warning", "[GetServiceLocID_P3] Service Location name is missing. Cannot fetch ID.") #
        return None
    if pd.isna(current_practice_id_context): #
        display_message("error", "[GetServiceLocID_P3] Practice ID context (Tebra Practice ID) is missing for Service Location lookup.") #
        return None
    normalized_sl_name = str(service_location_name_to_find).strip().lower() #
    cache_key = f"sl_{str(current_practice_id_context)}_{normalized_sl_name}" #
    if cache_key in cache_dict: #
        cached_id = cache_dict[cache_key]
        display_message("debug", f"[GetServiceLocID_P3] Found SL '{service_location_name_to_find}' in cache for Practice ID {current_practice_id_context}. ID: {cached_id}") #
        return cached_id #
    display_message("info", f"[GetServiceLocID_P3] SL '{service_location_name_to_find}' (PracticeID {current_practice_id_context}) not in cache. Querying API...") #
    try:
        GetServiceLocationsReqType = client_obj.get_type('ns6:GetServiceLocationsReq') #
        ServiceLocationFilterType = client_obj.get_type('ns6:ServiceLocationFilter') #
        ServiceLocationFieldsToReturnType = client_obj.get_type('ns6:ServiceLocationFieldsToReturn') #
        sl_filter = ServiceLocationFilterType(PracticeID=str(current_practice_id_context)) #
        fields = ServiceLocationFieldsToReturnType(ID=True, Name=True, PracticeID=True) #
        request_payload = GetServiceLocationsReqType(RequestHeader=header_obj, Filter=sl_filter, Fields=fields) #
        api_response = client_obj.service.GetServiceLocations(request=request_payload) #
        if hasattr(api_response, 'ErrorResponse') and api_response.ErrorResponse and api_response.ErrorResponse.IsError: #
            display_message("error", f"[GetServiceLocID_P3] API Error fetching SL '{service_location_name_to_find}' for Practice {current_practice_id_context}: {api_response.ErrorResponse.ErrorMessage}") #
            return None
        if hasattr(api_response, 'SecurityResponse') and api_response.SecurityResponse and not api_response.SecurityResponse.Authorized: #
            display_message("error", f"[GetServiceLocID_P3] API Auth Error fetching SL '{service_location_name_to_find}': {api_response.SecurityResponse.SecurityResult}") #
            return None
        if hasattr(api_response, 'ServiceLocations') and api_response.ServiceLocations and \
           hasattr(api_response.ServiceLocations, 'ServiceLocationData') and api_response.ServiceLocations.ServiceLocationData: #
            all_sl_data = api_response.ServiceLocations.ServiceLocationData #
            if not isinstance(all_sl_data, list): all_sl_data = [all_sl_data] if all_sl_data else [] #
            found_sl_id_str = None
            for sl_data_item in all_sl_data: #
                api_sl_name = str(getattr(sl_data_item, 'Name', '')).strip()
                api_sl_practice_id = str(getattr(sl_data_item, 'PracticeID', '')).strip()
                if api_sl_practice_id == str(current_practice_id_context):
                    if api_sl_name.lower() == normalized_sl_name: #
                        temp_id = str(getattr(sl_data_item, 'ID', '')).strip() #
                        if temp_id: found_sl_id_str = temp_id; #
                        display_message("info", f"[GetServiceLocID_P3] Exact match for SL '{service_location_name_to_find}' (PracticeID {current_practice_id_context}). ID: {found_sl_id_str}"); break #
            cache_dict[cache_key] = found_sl_id_str # Cache result (ID string or None) #
            if not found_sl_id_str: display_message("warning", f"[GetServiceLocID_P3] No exact name match for SL '{service_location_name_to_find}' for PracticeID {current_practice_id_context}.") #
            return found_sl_id_str #
        else: #
            display_message("warning", f"[GetServiceLocID_P3] No 'ServiceLocations.ServiceLocationData' for PracticeID {current_practice_id_context} to find '{service_location_name_to_find}'.") #
            cache_dict[cache_key] = None; return None
    except zeep.exceptions.Fault as soap_fault: display_message("error", f"[GetServiceLocID_P3] SOAP FAULT for SL '{service_location_name_to_find}': {soap_fault.message}") #
    except Exception as e: display_message("error", f"[GetServiceLocID_P3] Unexpected error for SL '{service_location_name_to_find}': {type(e).__name__} - {e}") #
    return None

# MODIFIED get_provider_id_by_name_phase3 from tebra_automation_tool_v2.py (Part 4B)
def get_provider_id_by_name_phase3(client_obj, header_obj, provider_name_excel, current_tebra_practice_id, cache_dict): #
    if pd.isna(provider_name_excel) or not str(provider_name_excel).strip(): #
        display_message("warning", "[GetProvID_P3] Provider name missing for Rendering/Scheduling lookup.") #
        return None #
    if pd.isna(current_tebra_practice_id): #
        display_message("error", "[GetProvID_P3] Tebra Practice ID context missing for Provider lookup.") #
        return None
    search_name = str(provider_name_excel).strip() #
    normalized_search_name_key = search_name.lower() #
    cache_key = f"rs_prov_{current_tebra_practice_id}_{normalized_search_name_key}" #
    if cache_key in cache_dict: #
        cached_val = cache_dict[cache_key]
        display_message("debug", f"[GetProvID_P3] Found RS Provider '{search_name}' in cache for PracID {current_tebra_practice_id}. ID: {cached_val}") #
        return cached_val #
    display_message("info", f"[GetProvID_P3] RS Provider '{search_name}' (PracID {current_tebra_practice_id}) not in cache. Querying API...") #
    ACCEPTABLE_RS_TYPES = ["normal provider", "physician", "group practice"]
    try:
        GetProvidersReqType = client_obj.get_type('ns0:GetProvidersReq') #
        ProviderFilterType = client_obj.get_type('ns0:ProviderFilter') #
        ProviderFieldsToReturnType = client_obj.get_type('ns0:ProviderFieldsToReturn') #
        fields = ProviderFieldsToReturnType(ID=True, FullName=True, FirstName=True, LastName=True, Type=True, Active=True, NationalProviderIdentifier=True) #
        api_filter = ProviderFilterType(PracticeID=str(current_tebra_practice_id))
        api_response = client_obj.service.GetProviders(request=GetProvidersReqType(RequestHeader=header_obj, Filter=api_filter, Fields=fields)) #
        provider_id_found = None #
        if hasattr(api_response, 'ErrorResponse') and api_response.ErrorResponse and api_response.ErrorResponse.IsError: #
            display_message("error", f"[GetProvID_P3] API Error for RS Prov '{search_name}': {api_response.ErrorResponse.ErrorMessage}")
        elif hasattr(api_response, 'SecurityResponse') and api_response.SecurityResponse and not api_response.SecurityResponse.Authorized: #
            display_message("error", f"[GetProvID_P3] API Auth Error for RS Prov '{search_name}': {api_response.SecurityResponse.SecurityResult}")
        elif hasattr(api_response, 'Providers') and api_response.Providers and hasattr(api_response.Providers, 'ProviderData') and api_response.Providers.ProviderData: #
            all_providers_data = api_response.Providers.ProviderData #
            if not isinstance(all_providers_data, list): all_providers_data = [all_providers_data] if all_providers_data else [] #
            exact_match_acceptable_type_provider_id = None
            flexible_matches_acceptable_type = []
            search_terms = [t.lower() for t in re.split(r'[\s,.]+', search_name) if t.lower() not in ['md', 'do', 'pa', 'np', 'lcsw', 'msw', 'inc', 'llc', 'pc', 'group', 'associates', 'services', 'medical'] and t] #
            if not search_terms: search_terms = [normalized_search_name_key] #
            for p_data in all_providers_data: #
                is_active = (str(getattr(p_data, 'Active', 'false')).lower() == 'true') #
                if not is_active: continue #
                api_full_name = str(getattr(p_data, 'FullName', '')).strip() #
                api_provider_type_norm = str(getattr(p_data, 'Type', '')).strip().lower()
                api_provider_id_str = str(getattr(p_data, 'ID', '')).strip()
                if not api_full_name or not api_provider_id_str: continue #
                if api_full_name.lower() == normalized_search_name_key: #
                    if api_provider_type_norm in ACCEPTABLE_RS_TYPES:
                        exact_match_acceptable_type_provider_id = api_provider_id_str #
                        display_message("info", f"[GetProvID_P3] Exact name match for ACTIVE RS Provider '{search_name}' with optimal Type '{api_provider_type_norm}'. ID: {exact_match_acceptable_type_provider_id}") #
                        break
            if exact_match_acceptable_type_provider_id: #
                provider_id_found = exact_match_acceptable_type_provider_id
            else: #
                display_message("info", f"[GetProvID_P3] No exact active match for '{search_name}' with an acceptable RS type. Trying flexible search...") #
                for p_data in all_providers_data:
                    is_active = (str(getattr(p_data, 'Active', 'false')).lower() == 'true')
                    if not is_active: continue
                    api_full_name = str(getattr(p_data, 'FullName', '')).strip()
                    api_provider_type_norm = str(getattr(p_data, 'Type', '')).strip().lower()
                    api_provider_id_str = str(getattr(p_data, 'ID', '')).strip()
                    if not api_full_name or not api_provider_id_str: continue
                    if api_provider_type_norm in ACCEPTABLE_RS_TYPES:
                        name_api_lower_terms = [t.lower() for t in re.split(r'[\s,.]+', api_full_name) if t.lower() not in ['md', 'do', 'pa', 'np', 'lcsw', 'msw', 'inc', 'llc', 'pc', 'group', 'associates', 'services', 'medical'] and t]
                        if not name_api_lower_terms: name_api_lower_terms = [api_full_name.lower()]
                        match_count = sum(1 for term_excel in search_terms if term_excel in name_api_lower_terms)
                        score = ((match_count / len(search_terms)) * 100) if search_terms and match_count == len(search_terms) else 0 #
                        if score >= 80: #
                            flexible_matches_acceptable_type.append({"ID": api_provider_id_str, "FullName": api_full_name, "Type": api_provider_type_norm, "score": score}) #
                if flexible_matches_acceptable_type: #
                    best_flex_match = sorted(flexible_matches_acceptable_type, key=lambda x: x['score'], reverse=True)[0] #
                    provider_id_found = best_flex_match['ID'] #
                    display_message("info", f"[GetProvID_P3] Flexible match for ACTIVE RS Provider '{search_name}' is '{best_flex_match['FullName']}' (Type: '{best_flex_match['Type']}'). ID: {provider_id_found} (Score: {best_flex_match['score']:.0f})") #
        else: display_message("warning", f"[GetProvID_P3] No provider data from API for Practice {current_tebra_practice_id} for RS Provider '{search_name}'.") #
        cache_dict[cache_key] = provider_id_found #
        if not provider_id_found: display_message("warning", f"[GetProvID_P3] Could not find suitable ACTIVE RS provider for '{search_name}' (PracID {current_tebra_practice_id}) with types {ACCEPTABLE_RS_TYPES}.") #
        return provider_id_found
    except zeep.exceptions.Fault as soap_fault: display_message("error", f"[GetProvID_P3] SOAP FAULT for RS Prov '{search_name}': {soap_fault.message}") #
    except Exception as e: display_message("error", f"[GetProvID_P3] Unexpected error for RS Prov '{search_name}': {type(e).__name__} - {e}") #
    cache_dict[cache_key] = None
    return None

# NEW function get_referring_provider_details_for_encounter from tebra_automation_tool_v2.py (Part 4B)
def get_referring_provider_details_for_encounter(client_obj, header_obj, ref_provider_name_excel, current_tebra_practice_id, cache_dict):
    if pd.isna(ref_provider_name_excel) or not str(ref_provider_name_excel).strip():
        display_message("debug", "[GetRefProv_P3] Referring Provider name is blank in Excel. Skipping Tebra lookup.")
        return None
    if pd.isna(current_tebra_practice_id):
        display_message("error", "[GetRefProv_P3] Tebra Practice ID context missing for Referring Provider lookup.")
        return None
    search_name = str(ref_provider_name_excel).strip()
    normalized_search_name_key = search_name.lower()
    cache_key = f"refprov_{current_tebra_practice_id}_{normalized_search_name_key}"
    if cache_key in cache_dict:
        cached_data = cache_dict[cache_key]
        display_message("debug", f"[GetRefProv_P3] Found Ref Prov '{search_name}' in cache for Practice {current_tebra_practice_id}. Details: {cached_data}")
        return cached_data
    display_message("info", f"[GetRefProv_P3] Ref Prov '{search_name}' (Normalized: '{normalized_search_name_key}', PracID {current_tebra_practice_id}) not in cache. Querying API...")
    try:
        GetProvidersReqType = client_obj.get_type('ns0:GetProvidersReq')
        ProviderFilterType = client_obj.get_type('ns0:ProviderFilter')
        ProviderFieldsToReturnType = client_obj.get_type('ns0:ProviderFieldsToReturn')
        fields = ProviderFieldsToReturnType(ID=True, FullName=True, FirstName=True, LastName=True, MiddleName=True, NationalProviderIdentifier=True, Type=True, Active=True)
        provider_filter = ProviderFilterType(PracticeID=str(current_tebra_practice_id))
        request_payload = GetProvidersReqType(RequestHeader=header_obj, Filter=provider_filter, Fields=fields)
        display_message("debug", f"[GetRefProv_P3] Calling GetProviders API for Practice ID {current_tebra_practice_id} to find Referring Provider '{search_name}'.")
        api_response = client_obj.service.GetProviders(request=request_payload)
        if hasattr(api_response, 'ErrorResponse') and api_response.ErrorResponse and api_response.ErrorResponse.IsError:
            display_message("error", f"[GetRefProv_P3] API Error for Ref Prov '{search_name}': {api_response.ErrorResponse.ErrorMessage}")
            return None
        if hasattr(api_response, 'SecurityResponse') and api_response.SecurityResponse and not api_response.SecurityResponse.Authorized:
            display_message("error", f"[GetRefProv_P3] API Auth Error for Ref Prov '{search_name}': {api_response.SecurityResponse.SecurityResult}")
            return None
        if hasattr(api_response, 'Providers') and api_response.Providers and hasattr(api_response.Providers, 'ProviderData') and api_response.Providers.ProviderData:
            all_providers_data = api_response.Providers.ProviderData
            if not isinstance(all_providers_data, list): all_providers_data = [all_providers_data] if all_providers_data else []
            display_message("debug", f"[GetRefProv_P3] Received {len(all_providers_data)} provider records from API for Practice {current_tebra_practice_id} for '{search_name}'.")
            best_match_referring_type_details = None
            for p_data_idx, p_data in enumerate(all_providers_data):
                is_active = (str(getattr(p_data, 'Active', 'false')).lower() == 'true')
                if not is_active: continue
                api_full_name = str(getattr(p_data, 'FullName', '')).strip()
                api_provider_type_original = str(getattr(p_data, 'Type', '')).strip()
                api_provider_type_norm = api_provider_type_original.lower()
                api_provider_id_str = str(getattr(p_data, 'ID', '')).strip()
                api_npi_str = str(getattr(p_data, 'NationalProviderIdentifier', '')).strip()
                current_api_first_name = str(getattr(p_data, 'FirstName', '')).strip()
                current_api_last_name = str(getattr(p_data, 'LastName', '')).strip()
                display_message("debug", f"[GetRefProv_P3] Checking API Prov #{p_data_idx+1}: Name='{api_full_name}', NormName='{api_full_name.lower()}', Type='{api_provider_type_original}', NormType='{api_provider_type_norm}', ID='{api_provider_id_str}', NPI='{api_npi_str if api_npi_str else 'N/A'}'")
                if api_full_name.lower() == normalized_search_name_key:
                    display_message("debug", f"[GetRefProv_P3] Name '{api_full_name}' matches Excel input '{search_name}'. API Type is '{api_provider_type_norm}'. Required Type is 'referring provider'.")
                    if api_provider_type_norm == "referring provider":
                        if (not current_api_first_name or not current_api_last_name) and api_full_name:
                            name_parts = api_full_name.split()
                            if not current_api_first_name and name_parts: current_api_first_name = name_parts[0]
                            if not current_api_last_name and len(name_parts) > 1: current_api_last_name = " ".join(name_parts[1:])
                            elif not current_api_last_name and not current_api_first_name and len(name_parts) == 1 : current_api_last_name = name_parts[0]
                        best_match_referring_type_details = {'ProviderID': api_provider_id_str if api_provider_id_str else None, 'FirstName': current_api_first_name if current_api_first_name else None, 'LastName': current_api_last_name if current_api_last_name else None, 'NPI': api_npi_str if api_npi_str else None, 'Type': api_provider_type_original, 'FullName': api_full_name}
                        display_message("info", f"[GetRefProv_P3] EXACT MATCH for ACTIVE Ref Prov '{search_name}' (Type: '{api_provider_type_original}'). Details: {best_match_referring_type_details}")
                        break
            if best_match_referring_type_details:
                cache_dict[cache_key] = best_match_referring_type_details
                display_message("debug", f"[GetRefProv_P3] Returning found details for '{search_name}': {best_match_referring_type_details}")
                return best_match_referring_type_details
            display_message("warning", f"[GetRefProv_P3] No specific 'Referring Provider' type record found by exact name match for '{search_name}' in Practice {current_tebra_practice_id}.")
            cache_dict[cache_key] = None; return None
        else:
            display_message("warning", f"[GetRefProv_P3] No provider data from API for Practice {current_tebra_practice_id} for Ref Prov '{search_name}'.")
            return None
    except zeep.exceptions.Fault as soap_fault: display_message("error", f"[GetRefProv_P3] SOAP FAULT for Ref Prov '{search_name}': {soap_fault.message}")
    except Exception as e: display_message("error", f"[GetRefProv_P3] Unexpected error for Ref Prov '{search_name}': {type(e).__name__} - {e}\n{traceback.format_exc()}")
    return None


def get_case_id_for_patient_phase3(client_obj, header_obj, patient_id_int_input, cache_dict): #
    # Using robust version from tebra_automation_tool_v2.py (Part 4B)
    if pd.isna(patient_id_int_input): #
        display_message("warning", "[GetCaseID_P3] Patient ID missing for Case ID fetch.") #
        return None
    try: patient_id_val = int(float(str(patient_id_int_input).strip()))
    except ValueError: display_message("error", f"[GetCaseID_P3] Invalid Patient ID format '{patient_id_int_input}' for Case ID fetch."); return None #
    cache_key = f"case_{patient_id_val}" #
    if cache_key in cache_dict: #
        cached_val = cache_dict[cache_key]
        display_message("debug", f"[GetCaseID_P3] Found CaseID for Pt {patient_id_val} in cache. ID: {cached_val}") #
        return cached_val #
    display_message("info", f"[GetCaseID_P3] CaseID for Pt {patient_id_val} not in cache. Querying API...") #
    case_id_found_str = None #
    try:
        GetPatientReqType = client_obj.get_type('ns0:GetPatientReq') #
        SinglePatientFilterType = client_obj.get_type('ns0:SinglePatientFilter') #
        patient_filter = SinglePatientFilterType(PatientID=patient_id_val) #
        request_payload = GetPatientReqType(RequestHeader=header_obj, Filter=patient_filter) #
        api_response = client_obj.service.GetPatient(request=request_payload) #
        if hasattr(api_response, 'ErrorResponse') and api_response.ErrorResponse and api_response.ErrorResponse.IsError: #
            display_message("error", f"[GetCaseID_P3] API Error getting patient for CaseID (Pt {patient_id_val}): {api_response.ErrorResponse.ErrorMessage}") #
        elif hasattr(api_response, 'SecurityResponse') and api_response.SecurityResponse and not api_response.SecurityResponse.Authorized: #
            display_message("error", f"[GetCaseID_P3] API Auth Error for CaseID (Pt {patient_id_val}): {api_response.SecurityResponse.SecurityResult}") #
        elif hasattr(api_response, 'Patient') and api_response.Patient and hasattr(api_response.Patient, 'Cases') and api_response.Patient.Cases and hasattr(api_response.Patient.Cases, 'PatientCaseData') and api_response.Patient.Cases.PatientCaseData: #
            cases_data_raw = api_response.Patient.Cases.PatientCaseData #
            cases_data_list = cases_data_raw if isinstance(cases_data_raw, list) else [cases_data_raw] if cases_data_raw else [] #
            primary_case_obj = None
            for case_obj_item in cases_data_list:
                is_primary_attr = getattr(case_obj_item, 'IsPrimaryCase', False)
                is_primary = (str(is_primary_attr).lower() == 'true') if is_primary_attr is not None else False
                if is_primary and getattr(case_obj_item, 'PatientCaseID', None): primary_case_obj = case_obj_item; break #
            if primary_case_obj: #
                case_id_found_str = str(getattr(primary_case_obj, 'PatientCaseID')).strip() #
                display_message("info", f"[GetCaseID_P3] Using primary case for Pt {patient_id_val}. CaseID: {case_id_found_str}") #
            elif cases_data_list and getattr(cases_data_list[0], 'PatientCaseID', None): #
                case_id_found_str = str(getattr(cases_data_list[0], 'PatientCaseID')).strip() #
                display_message("info", f"[GetCaseID_P3] No primary case, using first available for Pt {patient_id_val}. CaseID: {case_id_found_str}") #
            else: display_message("warning", f"[GetCaseID_P3] No cases with ID found for Pt {patient_id_val}.") #
        else: display_message("warning", f"[GetCaseID_P3] No 'Cases.PatientCaseData' in API response for Pt {patient_id_val}.") #
        if not case_id_found_str or not case_id_found_str.strip(): case_id_found_str = None #
        cache_dict[cache_key] = case_id_found_str; return case_id_found_str #
    except zeep.exceptions.Fault as soap_fault: display_message("error", f"[GetCaseID_P3] SOAP FAULT for CaseID (Pt {patient_id_val}): {soap_fault.message}") #
    except Exception as e: display_message("error", f"[GetCaseID_P3] Unexpected error for CaseID (Pt {patient_id_val}): {type(e).__name__} - {e}") #
    cache_dict[cache_key] = None
    return None

# MODIFIED create_place_of_service_payload_phase3 from tebra_automation_tool_v2.py (Part 4C)
def create_place_of_service_payload_phase3(client_obj, excel_pos_code, excel_encounter_mode, row_identifier_log): #
    if not client_obj: return None #
    EncounterPlaceOfServiceType = client_obj.get_type('ns0:EncounterPlaceOfService') #
    pos_code_input_str = str(excel_pos_code).strip() if pd.notna(excel_pos_code) else "" #
    encounter_mode_input_norm = str(excel_encounter_mode).strip().lower() if pd.notna(excel_encounter_mode) else "" #
    final_pos_code, final_pos_name = None, None #
    known_pos_codes_with_names = { "02": "Telehealth Provided Other than in Patient’s Home", "10": "Telehealth Provided in Patient’s Home", "11": "Office", "12": "Home", "21": "Inpatient Hospital", "22": "Outpatient Hospital", "23": "Emergency Room - Hospital", "24": "Ambulatory Surgical Center" }
    if pos_code_input_str in known_pos_codes_with_names:
        final_pos_code = pos_code_input_str #
        final_pos_name = known_pos_codes_with_names[pos_code_input_str] #
        display_message("debug", f"[POS_P3] {row_identifier_log}: Direct POS code '{final_pos_code}' from Excel used.")
    else:
        is_telehealth_mode = "telehealth" in encounter_mode_input_norm or "tele health" in encounter_mode_input_norm #
        is_in_office_mode = "in office" in encounter_mode_input_norm or "office" in encounter_mode_input_norm or "inoffice" in encounter_mode_input_norm #
        if is_telehealth_mode: #
            if pos_code_input_str == "02": final_pos_code = "02"; final_pos_name = POS_CODE_MAP_PHASE3.get("TELEHEALTH OFFICE", {}).get("name") #
            else: final_pos_code = POS_CODE_MAP_PHASE3.get("DEFAULT_TELEHEALTH", {}).get("code", "10"); final_pos_name = POS_CODE_MAP_PHASE3.get("DEFAULT_TELEHEALTH", {}).get("name") #
            display_message("debug", f"[POS_P3] {row_identifier_log}: Inferred POS from Telehealth mode. Excel POS: '{pos_code_input_str}', Using: {final_pos_code}.")
        elif is_in_office_mode: #
            final_pos_code = POS_CODE_MAP_PHASE3.get("DEFAULT_IN_OFFICE", {}).get("code", "11"); final_pos_name = POS_CODE_MAP_PHASE3.get("DEFAULT_IN_OFFICE", {}).get("name") #
            display_message("debug", f"[POS_P3] {row_identifier_log}: Inferred POS from In Office mode. Using: {final_pos_code}.")
    if not final_pos_code: #
        display_message("warning", f"[POS_P3] {row_identifier_log}: Cannot determine POS from Excel Code '{excel_pos_code}' & Mode '{excel_encounter_mode}'. Defaulting to Office (11).") #
        final_pos_code = "11"; final_pos_name = POS_CODE_MAP_PHASE3.get("OFFICE", {}).get("name", "Office")
    display_message("debug", f"[POS_P3] {row_identifier_log}: Final POS Code To Use: {final_pos_code}, Name: {final_pos_name}") #
    try: return EncounterPlaceOfServiceType(PlaceOfServiceCode=str(final_pos_code), PlaceOfServiceName=str(final_pos_name)) #
    except Exception as e: display_message("error", f"[POS_P3] {row_identifier_log}: Error creating POS payload object: {e}"); return None #

def create_service_line_payload_phase3(client_obj, service_line_data_dict, encounter_start_dt_api_str, encounter_end_dt_api_str, row_identifier_log, actual_headers_map_param): #
    # Using version from existing Flask app (user.py lines 1004-1048), which is similar to Colab's v1 and handles Diag 1-4, Mod 1-4
    if not client_obj: return None #
    ServiceLineReqType = client_obj.get_type('ns0:ServiceLineReq') #
    proc_col = actual_headers_map_param.get("Procedures", "Procedures") #
    units_col = actual_headers_map_param.get("Units", "Units") #
    diag1_col = actual_headers_map_param.get("Diag 1", "Diag 1") #
    proc_code = str(service_line_data_dict.get(proc_col, "")).strip() #
    units_val = service_line_data_dict.get(units_col) #
    diag1_val = service_line_data_dict.get(diag1_col) #
    if not proc_code: display_message("warning", f"[SvcLine_P3] {row_identifier_log}: Proc code missing."); return None #
    if units_val is None or pd.isna(units_val) or str(units_val).strip() == "" or str(units_val).strip().lower() == 'nan': display_message("warning", f"[SvcLine_P3] {row_identifier_log} (Proc {proc_code}): Units missing."); return None #
    if diag1_val is None or pd.isna(diag1_val) or not str(diag1_val).strip() or str(diag1_val).strip().lower() == 'nan': display_message("warning", f"[SvcLine_P3] {row_identifier_log} (Proc {proc_code}): Diag 1 missing."); return None #
    try:
        units_float = float(str(units_val).strip()) #
        if units_float <= 0: display_message("warning", f"[SvcLine_P3] {row_identifier_log} (Proc {proc_code}): Units <= 0 ({units_float})."); return None #
    except ValueError: display_message("warning", f"[SvcLine_P3] {row_identifier_log} (Proc {proc_code}): Units '{units_val}' not valid number."); return None #
    def clean_value_p3(val, is_modifier=False, is_diag=False): # is_diag added for consistency with Colab v2, though not strictly used differently here yet #
        s_val = str(val if pd.notna(val) else "").strip() #
        if is_modifier: #
            if s_val.endswith(".0"): s_val = s_val[:-2] #
            if s_val and len(s_val) > 2 : s_val = s_val[:2] #
        return s_val if s_val and s_val.lower() != 'nan' else None #
    diag1_cleaned = clean_value_p3(diag1_val, is_diag=True) #
    if not diag1_cleaned: display_message("warning", f"[SvcLine_P3] {row_identifier_log} (Proc {proc_code}): Diag1 invalid after cleaning."); return None #
    sl_args = {'ProcedureCode': proc_code, 'Units': units_float, 'ServiceStartDate': encounter_start_dt_api_str, 'ServiceEndDate': encounter_end_dt_api_str, 'DiagnosisCode1': diag1_cleaned} #
    for i in range(1, 5): # Loop for Mod 1-4 #
        mod_key_logical = f"Mod {i}"
        actual_mod_col_name = actual_headers_map_param.get(mod_key_logical, mod_key_logical) #
        mod_val = clean_value_p3(service_line_data_dict.get(actual_mod_col_name), is_modifier=True) #
        if mod_val: sl_args[f'ProcedureModifier{i}'] = mod_val #
    for i in range(2, 5): # Loop for Diag 2-4 #
        diag_key_logical = f"Diag {i}"
        actual_diag_col_name = actual_headers_map_param.get(diag_key_logical, diag_key_logical) #
        diag_val = clean_value_p3(service_line_data_dict.get(actual_diag_col_name), is_diag=True) #
        if diag_val: sl_args[f'DiagnosisCode{i}'] = diag_val #
    try: return ServiceLineReqType(**sl_args) #
    except Exception as e: display_message("error", f"[SvcLine_P3] {row_identifier_log} (Proc {proc_code}): ServiceLineReq Payload Creation Error: {e}. Args considered: {sl_args}"); return None #

# MODIFIED parse_tebra_xml_error_phase3 from tebra_automation_tool_v2.py (Part 4C)
def parse_tebra_xml_error_phase3(xml_string, patient_id_context="N/A", dos_context="N/A", row_identifier_log=""): #
    if not xml_string or not isinstance(xml_string, str): return str(xml_string) if xml_string else "Unknown error." #
    if not ("<Encounter" in xml_string or "<err " in xml_string or "<Error>" in xml_string): #
        return xml_string.strip() if xml_string.strip() else "Encounter error (non-XML)." #
    simplified_errors = [] #
    try:
        if xml_string.startswith("API Error: "): xml_string = xml_string[len("API Error: "):].strip() #
        service_line_pattern = r"<ServiceLine>(.*?)</ServiceLine>" #
        diag_error_pattern = r"<DiagnosisCode(?P<diag_num>\d)>(?P<diag_code_val>[^<]+?)<err id=\"\d+\">(?P<err_msg>[^<]+)</err>" #
        mod_error_pattern = r"<ProcedureModifier(?P<mod_num>\d)>(?P<mod_code_val>[^<]+?)<err id=\"\d+\">(?P<err_msg>[^<]+)</err>" #
        proc_code_pattern = r"<ProcedureCode>(?P<proc_code_val>[^<]+)</ProcedureCode>" #
        general_err_pattern = r"<err id=\"(\d+)\">(.*?)</err>" #

        ref_prov_error = re.search(r"<ReferringProvider>.*?<err id=\"(\d+)\">(.*?)</err>.*?</ReferringProvider>", xml_string, re.DOTALL)
        if ref_prov_error: simplified_errors.append(f"ReferringProvider Err(ID:{ref_prov_error.group(1)}): {ref_prov_error.group(2).strip()}")
        rend_prov_error = re.search(r"<RenderingProvider>.*?<err id=\"(\d+)\">(.*?)</err>.*?</RenderingProvider>", xml_string, re.DOTALL)
        if rend_prov_error: simplified_errors.append(f"RenderingProvider Err(ID:{rend_prov_error.group(1)}): {rend_prov_error.group(2).strip()}")
        sloc_error = re.search(r"<ServiceLocation>.*?<err id=\"(\d+)\">(.*?)</err>.*?</ServiceLocation>", xml_string, re.DOTALL)
        if sloc_error: simplified_errors.append(f"ServiceLocation Err(ID:{sloc_error.group(1)}): {sloc_error.group(2).strip()}")

        service_lines_xml_content = re.findall(service_line_pattern, xml_string, re.DOTALL) #
        sl_counter = 0 #
        for sl_xml_item in service_lines_xml_content: #
            sl_counter += 1; proc_code_val = "N/A" #
            proc_match = re.search(proc_code_pattern, sl_xml_item) #
            if proc_match: proc_code_val = proc_match.group("proc_code_val") #
            for match_item in re.finditer(diag_error_pattern, sl_xml_item): simplified_errors.append(f"L{sl_counter}(Proc {proc_code_val}): Diag{match_item.group('diag_num')} ('{match_item.group('diag_code_val')}') - {match_item.group('err_msg').split(',')[0].strip()}.") #
            for match_item in re.finditer(mod_error_pattern, sl_xml_item): simplified_errors.append(f"L{sl_counter}(Proc {proc_code_val}): Mod{match_item.group('mod_num')} ('{match_item.group('mod_code_val')}') - {match_item.group('err_msg').split(',')[0].strip()}{' (No .0)' if '.0' in match_item.group('mod_code_val') else ''}.") #
            if not re.search(diag_error_pattern, sl_xml_item) and not re.search(mod_error_pattern, sl_xml_item): #
                 for generic_match in re.finditer(general_err_pattern, sl_xml_item): simplified_errors.append(f"L{sl_counter}(Proc {proc_code_val}): {generic_match.group(2).strip()}.") #
        
        overall_sl_err_match = re.search(r"<ServiceLines>.*?<err id=\"(\d+)\">(.*?)</err>(?!.*</ServiceLine>)", xml_string, re.DOTALL)
        if overall_sl_err_match: simplified_errors.append(f"ServiceLines Overall Err(ID:{overall_sl_err_match.group(1)}): {overall_sl_err_match.group(2).strip()}.")
        
        if not simplified_errors: #
            top_level_encounter_err = re.search(r"<Encounter[^>]*>.*?<err id=\"(\d+)\">(.*?)</err>", xml_string, re.DOTALL) #
            if top_level_encounter_err: simplified_errors.append(f"Encounter Level Err(ID:{top_level_encounter_err.group(1)}): {top_level_encounter_err.group(2).strip()}.") #
            elif "<Encounter" in xml_string : simplified_errors.append("Enc creation failed (unparsed XML error).") #
        
        if not simplified_errors : return xml_string.strip()[:250] + "..." if len(xml_string) > 250 else xml_string.strip() #
        unique_errors = []; [unique_errors.append(e) for e in simplified_errors if e not in unique_errors] #
        return "; ".join(unique_errors) #
    except Exception: return "Error simplifying API error message. Original (first 300): " + xml_string[:300].strip() + "..." #

def get_encounter_details_phase3(client_obj, header_obj, encounter_id_str, tebra_practice_id_for_filter_str, row_identifier_log): #
    # Using robust version from tebra_automation_tool_v2.py (Part 4C)
    results = {'RawEncounterStatusCode': None, 'SimpleError': None} #
    if not all([encounter_id_str, str(encounter_id_str).strip() != "-1" if encounter_id_str else False, tebra_practice_id_for_filter_str, str(tebra_practice_id_for_filter_str).strip()]): #
        results['SimpleError'] = "EncID or TebraPracticeID missing/invalid for GetEncounterDetails." #
        return results #
    display_message("info", f"[GetEncStatus_P3] {row_identifier_log}: Fetching status for EncID {encounter_id_str}, TebraPracticeID {tebra_practice_id_for_filter_str}...") #
    try:
        GetEncounterDetailsReqType = client_obj.get_type('ns0:GetEncounterDetailsReq') #
        EncounterDetailsFilterType = client_obj.get_type('ns0:EncounterDetailsFilter') #
        EncounterDetailsPracticeType = client_obj.get_type('ns0:EncounterDetailsPractice') #
        EncounterDetailsFieldsToReturnType = client_obj.get_type('ns0:EncounterDetailsFieldsToReturn') #
        fields_to_return = EncounterDetailsFieldsToReturnType(EncounterID=True, EncounterStatus=True, PracticeID=True) #
        practice_filter_details = EncounterDetailsPracticeType(PracticeID=str(tebra_practice_id_for_filter_str)) #
        encounter_filter = EncounterDetailsFilterType(EncounterID=str(encounter_id_str), Practice=practice_filter_details) #
        request_payload = GetEncounterDetailsReqType(RequestHeader=header_obj, Fields=fields_to_return, Filter=encounter_filter) #
        api_response = client_obj.service.GetEncounterDetails(request=request_payload) #
        if hasattr(api_response, 'ErrorResponse') and api_response.ErrorResponse and api_response.ErrorResponse.IsError: #
            results['SimpleError'] = f"API Error (GetEncStatus): {api_response.ErrorResponse.ErrorMessage}" #
        elif hasattr(api_response, 'SecurityResponse') and api_response.SecurityResponse and not api_response.SecurityResponse.Authorized: #
            results['SimpleError'] = f"API Auth Error (GetEncStatus): {api_response.SecurityResponse.SecurityResult}" #
        elif hasattr(api_response, 'EncounterDetails') and api_response.EncounterDetails and hasattr(api_response.EncounterDetails, 'EncounterDetailsData') and api_response.EncounterDetails.EncounterDetailsData: #
            details_data_list = api_response.EncounterDetails.EncounterDetailsData #
            if not isinstance(details_data_list, list): details_data_list = [details_data_list] if details_data_list else [] #
            if details_data_list: #
                enc_data = details_data_list[0] #
                results['RawEncounterStatusCode'] = getattr(enc_data, 'EncounterStatus', None) #
            else: results['SimpleError'] = "No EncounterDetailsData returned for the specified EncID." #
        else: results['SimpleError'] = "Unknown response structure from GetEncounterDetails." #
    except zeep.exceptions.Fault as soap_fault: results['SimpleError'] = f"SOAP FAULT (GetEncStatus): {soap_fault.message}" #
    except Exception as e: results['SimpleError'] = f"Unexpected error in GetEncounterStatus: {type(e).__name__} - {str(e)}" #
    if results['SimpleError']: display_message("error", f"[GetEncStatus_P3] {row_identifier_log}: Error fetching status for EncID {encounter_id_str}: {results['SimpleError']}") #
    return results #

# THIS FUNCTION REPLACES the existing get_total_charge_amount_for_encounter_phase3
# in your src/routes/user.py file

def get_total_charge_amount_for_encounter_phase3(client_obj, header_obj, target_encounter_id_str,
                                                 target_patient_id_str,
                                                 practice_name_filter_str,
                                                 dos_filter_str,
                                                 list_of_procedure_codes_on_encounter, # Still needed to get one proc for filter
                                                 row_identifier_log):
    """
    Fetches charges using GetCharges. Uses the FIRST procedure code from the list
    for the API filter, assuming this will return all charge lines for the encounter.
    Then filters by PatientID and EncounterID in Python and sums TotalCharges.
    """
    results = {'TotalChargeAmount': "0.00", 'SimpleError': None}

    if not all([target_encounter_id_str, str(target_encounter_id_str).strip() != "-1" if target_encounter_id_str else False,
                target_patient_id_str,
                practice_name_filter_str,
                dos_filter_str,
                list_of_procedure_codes_on_encounter and len(list_of_procedure_codes_on_encounter) > 0]):
        results['SimpleError'] = "Missing required params for GetCharges (EncID, PatientID, PracName, DOS, at least one ProcCode)."
        if results['SimpleError']: results['TotalChargeAmount'] = "Error"
        display_message("error", f"[GetCharges_P3] {row_identifier_log}: {results['SimpleError']}") #
        return results

    # Use only the first procedure code for the API filter
    representative_proc_code = list_of_procedure_codes_on_encounter[0]
    display_message("info", f"[GetCharges_P3] {row_identifier_log}: Fetching charges for EncID {target_encounter_id_str}, PatientID {target_patient_id_str} using representative ProcCode {representative_proc_code} (Filters: Prac='{practice_name_filter_str}', DOS='{dos_filter_str}', IncludeUnapproved='true')...") #

    cumulative_encounter_total_charges = 0.0
    any_charges_found_for_this_specific_encounter = False

    try:
        service_date_api_format = format_datetime_for_api_phase3(dos_filter_str) #
        if not service_date_api_format:
            results['SimpleError'] = f"Invalid DOS '{dos_filter_str}' for GetCharges filter."
            results['TotalChargeAmount'] = "Error"
            return results

        GetChargesReqType = client_obj.get_type('ns0:GetChargesReq') #
        ChargeFilterType = client_obj.get_type('ns0:ChargeFilter') #
        ChargeFieldsToReturnType = client_obj.get_type('ns0:ChargeFieldsToReturn') #

        charge_fields = ChargeFieldsToReturnType(
            EncounterID=True, TotalCharges=True, ID=True, ProcedureCode=True,
            PatientID=True, UnitCharge=True, Units=True
        )

        # API call is made ONCE using the representative procedure code
        charge_filter = ChargeFilterType(
            PracticeName=str(practice_name_filter_str),
            FromServiceDate=service_date_api_format,
            ToServiceDate=service_date_api_format,
            ProcedureCode=str(representative_proc_code),
            IncludeUnapprovedCharges="true"
        )
        request_payload_charges = GetChargesReqType(RequestHeader=header_obj, Fields=charge_fields, Filter=charge_filter) #
        api_response_charges = client_obj.service.GetCharges(request=request_payload_charges) #

        if hasattr(api_response_charges, 'ErrorResponse') and api_response_charges.ErrorResponse and api_response_charges.ErrorResponse.IsError: #
            err_msg = f"API Error (GetCharges for Proc {representative_proc_code}): {api_response_charges.ErrorResponse.ErrorMessage}" #
            display_message("error", f"[GetCharges_P3] {row_identifier_log}: {err_msg}") #
            results['SimpleError'] = err_msg
        elif hasattr(api_response_charges, 'SecurityResponse') and api_response_charges.SecurityResponse and not api_response_charges.SecurityResponse.Authorized: #
            err_msg = f"API Auth Error (GetCharges for Proc {representative_proc_code}): {api_response_charges.SecurityResponse.SecurityResult}" #
            display_message("error", f"[GetCharges_P3] {row_identifier_log}: {err_msg}") #
            results['SimpleError'] = err_msg
        elif hasattr(api_response_charges, 'Charges') and api_response_charges.Charges and \
             hasattr(api_response_charges.Charges, 'ChargeData') and api_response_charges.Charges.ChargeData: #
            all_charge_data_list = api_response_charges.Charges.ChargeData #
            if not isinstance(all_charge_data_list, list):
                all_charge_data_list = [all_charge_data_list] if all_charge_data_list else []

            display_message("debug", f"[GetCharges_P3] {row_identifier_log}: API returned {len(all_charge_data_list)} charge items using representative Proc {representative_proc_code}.") #

            for charge_item in all_charge_data_list:
                if charge_item is None: continue

                api_item_patient_id = str(getattr(charge_item, 'PatientID', '')).strip()
                api_item_encounter_id = str(getattr(charge_item, 'EncounterID', '')).strip()

                if api_item_patient_id == str(target_patient_id_str).strip() and \
                   api_item_encounter_id == str(target_encounter_id_str).strip():

                    tc_str = getattr(charge_item, 'TotalCharges', None)
                    proc_on_line = getattr(charge_item, 'ProcedureCode', 'N/A')
                    display_message("debug", f"[GetCharges_P3] {row_identifier_log}: Matched EncID {api_item_encounter_id}, PtID {api_item_patient_id}, ProcOnLine {proc_on_line}. Raw TotalCharges: '{tc_str}'") #
                    if tc_str is not None and str(tc_str).strip() and str(tc_str).lower() != 'none':
                        try:
                            charge_value = float(str(tc_str).strip())
                            cumulative_encounter_total_charges += charge_value
                            any_charges_found_for_this_specific_encounter = True
                            display_message("debug", f"[GetCharges_P3] {row_identifier_log}: Added {charge_value} from line with proc {proc_on_line}. New sum: {cumulative_encounter_total_charges}") #
                        except ValueError:
                            display_message("warning", f"[GetCharges_P3] {row_identifier_log}: Could not parse TotalCharges '{tc_str}' for ChargeID {getattr(charge_item, 'ID','N/A')} on EncID {target_encounter_id_str}, ProcOnLine {proc_on_line}.") #
                    else:
                        display_message("debug", f"[GetCharges_P3] {row_identifier_log}: TotalCharges is None or empty for matching line (ChargeID {getattr(charge_item, 'ID','N/A')}, ProcOnLine {proc_on_line}).") #
        else:
            display_message("debug",f"[GetCharges_P3] {row_identifier_log}: No 'Charges.ChargeData' structure in API response for representative Proc {representative_proc_code}.") #

        if any_charges_found_for_this_specific_encounter:
            results['TotalChargeAmount'] = f"{cumulative_encounter_total_charges:.2f}"
        elif not results['SimpleError']:
            display_message("warning", f"[GetCharges_P3] {row_identifier_log}: No specific charges with value ultimately found for EncounterID {target_encounter_id_str} and PatientID {target_patient_id_str} after API call. Defaulting amount to 0.00.") #
            results['TotalChargeAmount'] = "0.00"

    except zeep.exceptions.Fault as soap_fault: #
        results['SimpleError'] = f"SOAP FAULT (GetCharges): {soap_fault.message}"
    except Exception as e:
        results['SimpleError'] = f"Unexpected error in GetCharges: {type(e).__name__} - {str(e)}"
        display_message("error", f"[GetCharges_P3] {row_identifier_log}: Exception: {traceback.format_exc()}") #

    if results['SimpleError'] and results['TotalChargeAmount'] == "0.00" :
         display_message("error", f"[GetCharges_P3] {row_identifier_log}: Error occurred and no charges summed for EncID {target_encounter_id_str}: {results['SimpleError']}") #
         results['TotalChargeAmount'] = "Error"
    elif results.get('TotalChargeAmount') is None:
        results['TotalChargeAmount'] = "Error" if results['SimpleError'] else "0.00"

    display_message("info", f"[GetCharges_P3] {row_identifier_log}: Final result for EncID {target_encounter_id_str}: Amount='{results['TotalChargeAmount']}', Error='{results['SimpleError']}'") #
    return results

# --- ⚙️ PART 5: Main Processing Loop (Adapted from Colab) ---
# MODIFIED _create_encounter_for_group_and_get_details from tebra_automation_tool_v2.py (Part 5)
# THIS FUNCTION REPLACES the existing _create_encounter_for_group_and_get_details
# in your src/routes/user.py file (or wherever it's defined in your Flask app)

def _create_encounter_for_group_and_get_details(
    client_obj, header_obj, group_key, group_df_rows,
    practice_id_for_encounter_payload_str, 
    # patient_full_name_for_charges_filter is NO LONGER directly used by get_total_charge_amount...
    # but might be used elsewhere or for logging. Let's assume it's still passed for now.
    patient_full_name_for_charges_filter, 
    log_prefix,
    actual_headers_map_param, # Passed from run_all_phases_processing_adapted
    # Caches passed from run_all_phases_processing_adapted
    service_location_id_cache_param, 
    patient_case_id_cache_param,
    provider_id_cache_param,
    referring_provider_cache_param 
):
    patient_id_str, dos_str, practice_name_excel_str = group_key
    row_identifier_log = f"{log_prefix} Grp (Pt:{patient_id_str}, DOS:{dos_str}, PracFromExcel:{practice_name_excel_str})"

    results = {
        'EncounterID': None, 'ChargeAmount': "Error", 'ChargeStatus': "Error",
        'SimpleMessage': "Encounter processing not initiated.", 'ErrorDetail': None
    }

    if group_df_rows.empty:
        results['SimpleMessage'] = "Enc Error: No rows in group."; display_message("error", f"{row_identifier_log}: {results['SimpleMessage']}"); return results
    
    first_row_data = group_df_rows.iloc[0]

    try:
        # --- Essential IDs and Common Data Validation (from your original script) ---
        if not practice_id_for_encounter_payload_str: results['SimpleMessage'] = "Enc Error: Missing Tebra Practice ID."; return results
        
        # Use caches passed as parameters
        service_location_id_str = get_service_location_id_by_name(client_obj, header_obj, practice_name_excel_str, practice_id_for_encounter_payload_str, service_location_id_cache_param)
        if not service_location_id_str: results['SimpleMessage'] = f"Enc Error: SL '{practice_name_excel_str}' not found for TebraPracID {practice_id_for_encounter_payload_str}."; return results
        
        case_id_str = get_case_id_for_patient_phase3(client_obj, header_obj, int(float(patient_id_str)), patient_case_id_cache_param)
        if not case_id_str: results['SimpleMessage'] = f"Enc Error: Case ID not found for Pt {patient_id_str}."; return results
        
        rp_name_col = actual_headers_map_param.get("Rendering Provider")
        rp_name = str(first_row_data.get(rp_name_col, "")).strip()
        if not rp_name: results['SimpleMessage'] = "Enc Error: Rendering Provider name missing."; return results
        rp_id_str = get_provider_id_by_name_phase3(client_obj, header_obj, rp_name, practice_id_for_encounter_payload_str, provider_id_cache_param)
        if not rp_id_str: results['SimpleMessage'] = f"Enc Error: Rendering Provider ID for '{rp_name}' not found."; return results

        encounter_dos_api_str = format_datetime_for_api_phase3(dos_str)
        if not encounter_dos_api_str: results['SimpleMessage'] = f"Enc Error: Invalid DOS '{dos_str}'."; return results
        
        pos_col = actual_headers_map_param.get("POS"); enc_mode_col = actual_headers_map_param.get("Encounter Mode")
        pos_payload = create_place_of_service_payload_phase3(client_obj, first_row_data.get(pos_col), first_row_data.get(enc_mode_col), row_identifier_log)
        if not pos_payload: results['SimpleMessage'] = f"Enc Error: Failed POS payload."; return results

        # --- Referring Provider Logic ---
        referring_provider_payload_obj = None
        ref_prov_excel_logical_key = "Referring Provider" # Ensure this matches EXPECTED_COLUMNS_CONFIG Part 3
        ref_prov_name_col_actual = actual_headers_map_param.get(ref_prov_excel_logical_key)
        if ref_prov_name_col_actual:
            referring_provider_name_from_excel = str(first_row_data.get(ref_prov_name_col_actual, "")).strip()
            display_message("debug", f"{row_identifier_log}: Value for '{ref_prov_name_col_actual}' (logical '{ref_prov_excel_logical_key}'): '{referring_provider_name_from_excel}'")
            if referring_provider_name_from_excel and referring_provider_name_from_excel.lower() != 'nan':
                display_message("info", f"{row_identifier_log}: Finding Referring Provider: '{referring_provider_name_from_excel}'")
                ref_prov_details = get_referring_provider_details_for_encounter(client_obj, header_obj, referring_provider_name_from_excel, practice_id_for_encounter_payload_str, referring_provider_cache_param) # Pass ref prov cache
                display_message("debug", f"{row_identifier_log}: Lookup result for Ref Prov: {ref_prov_details}")
                if ref_prov_details and ref_prov_details.get('NPI'):
                    ProviderIdentifierDetailedReqType = client_obj.get_type('ns0:ProviderIdentifierDetailedReq')
                    ref_prov_args = {'NPI': ref_prov_details['NPI']}
                    if ref_prov_details.get('FirstName'): ref_prov_args['FirstName'] = ref_prov_details['FirstName']
                    if ref_prov_details.get('LastName'): ref_prov_args['LastName'] = ref_prov_details['LastName']
                    ref_prov_args_cleaned = {k:v for k,v in ref_prov_args.items() if v is not None and str(v).strip()!=""}
                    if ref_prov_args_cleaned.get('NPI'):
                        referring_provider_payload_obj = ProviderIdentifierDetailedReqType(**ref_prov_args_cleaned)
                        display_message("info", f"{row_identifier_log}: Added Referring Provider (NPI: {ref_prov_details['NPI']})")
                elif ref_prov_details and ref_prov_details.get('ProviderID'): # Fallback to ProviderID
                    ProviderIdentifierDetailedReqType = client_obj.get_type('ns0:ProviderIdentifierDetailedReq')
                    ref_prov_args = {'ProviderID': int(ref_prov_details['ProviderID'])}
                    if ref_prov_details.get('FirstName'): ref_prov_args['FirstName'] = ref_prov_details['FirstName']
                    if ref_prov_details.get('LastName'): ref_prov_args['LastName'] = ref_prov_details['LastName']
                    referring_provider_payload_obj = ProviderIdentifierDetailedReqType(**ref_prov_args)
                    display_message("info", f"{row_identifier_log}: Added Referring Provider (Tebra ID: {ref_prov_details['ProviderID']})")
                elif referring_provider_name_from_excel: display_message("warning", f"{row_identifier_log}: Ref Prov '{referring_provider_name_from_excel}' not found with NPI/ID.")
        else: display_message("debug", f"{row_identifier_log}: 'Referring Provider' col not mapped. Skipping.")
        
        # --- Hospitalization Dates Logic ---
        hospitalization_payload_obj = None
        admit_date_col = actual_headers_map_param.get("Admit Date", "Admit Date")
        discharge_date_col = actual_headers_map_param.get("Discharge Date", "Discharge Date")
        admit_date_str = str(first_row_data.get(admit_date_col, "")).strip()
        discharge_date_str = str(first_row_data.get(discharge_date_col, "")).strip()
        if admit_date_str and discharge_date_str and admit_date_str.lower()!='nan' and discharge_date_str.lower()!='nan':
            fmt_admit = format_datetime_for_api_phase3(admit_date_str)
            fmt_discharge = format_datetime_for_api_phase3(discharge_date_str)
            if fmt_admit and fmt_discharge:
                try:
                    EncounterHospitalizationType = client_obj.get_type('ns0:EncounterHospitalization')
                    hospitalization_payload_obj = EncounterHospitalizationType(StartDate=fmt_admit, EndDate=fmt_discharge)
                    display_message("info", f"{row_identifier_log}: Added Hospitalization: {admit_date_str} to {discharge_date_str}")
                except Exception as e_h: display_message("warning", f"{row_identifier_log}: Error Hospitalization: {e_h}")
            else: display_message("warning", f"{row_identifier_log}: Invalid Admit/Discharge Date format. Hosp. not sent.")
        elif (admit_date_str and admit_date_str.lower()!='nan') or \
             (discharge_date_str and discharge_date_str.lower()!='nan'):
            display_message("warning", f"{row_identifier_log}: Both Admit & Discharge Dates needed. Hosp. not sent.")

        # --- Service Lines ---
        service_lines_payload_list = []
        procedure_codes_for_this_encounter = [] # Collect for GetCharges call
        proc_col_name_for_collect = actual_headers_map_param.get("Procedures", "Procedures")

        for sl_idx, sl_row_data in group_df_rows.iterrows():
            original_row_num = sl_row_data.get('original_excel_row_num', f"DF_Idx_{sl_idx}")
            sl_log_id = f"{row_identifier_log} (ExcelRow {original_row_num})"
            # Pass actual_headers_map_param to create_service_line_payload_phase3
            sl_payload = create_service_line_payload_phase3(client_obj, sl_row_data, encounter_dos_api_str, encounter_dos_api_str, sl_log_id, actual_headers_map_param)
            if sl_payload:
                service_lines_payload_list.append(sl_payload)
                # Collect procedure code
                proc_code_on_line = str(sl_row_data.get(proc_col_name_for_collect, "")).strip()
                if proc_code_on_line and proc_code_on_line not in procedure_codes_for_this_encounter:
                    procedure_codes_for_this_encounter.append(proc_code_on_line)
            else: results['SimpleMessage'] = f"Enc Error: Failed service line from Excel row {original_row_num}."; return results
        if not service_lines_payload_list: results['SimpleMessage'] = "Enc Error: No valid service lines."; return results
        
        # --- Construct Encounter Payload ---
        EncounterCreateType = client_obj.get_type('ns0:EncounterCreate')
        PatientIdentifierReqType = client_obj.get_type('ns0:PatientIdentifierReq')
        PracticeIdentifierReqType = client_obj.get_type('ns0:PracticeIdentifierReq')
        EncounterServiceLocationType = client_obj.get_type('ns0:EncounterServiceLocation')
        PatientCaseIdentifierReqType = client_obj.get_type('ns0:PatientCaseIdentifierReq')
        ProviderIdentifierDetailedReqType = client_obj.get_type('ns0:ProviderIdentifierDetailedReq')
        ArrayOfServiceLineReqType = client_obj.get_type('ns0:ArrayOfServiceLineReq')
        
        encounter_args = {
            "Patient": PatientIdentifierReqType(PatientID=int(float(patient_id_str))),
            "Practice": PracticeIdentifierReqType(PracticeID=int(practice_id_for_encounter_payload_str)),
            "ServiceLocation": EncounterServiceLocationType(LocationID=int(service_location_id_str)),
            "Case": PatientCaseIdentifierReqType(CaseID=int(case_id_str)),
            "RenderingProvider": ProviderIdentifierDetailedReqType(ProviderID=int(rp_id_str)),
            "ServiceStartDate": encounter_dos_api_str, "ServiceEndDate": encounter_dos_api_str,
            "PostDate": encounter_dos_api_str, 
            "PlaceOfService": pos_payload,
            "ServiceLines": ArrayOfServiceLineReqType(ServiceLineReq=service_lines_payload_list),
            "EncounterStatus": "Draft" # EncounterStatus is 'ns2:EncounterStatusCode'
        }
        if referring_provider_payload_obj: encounter_args["ReferringProvider"] = referring_provider_payload_obj
        if hospitalization_payload_obj: encounter_args["Hospitalization"] = hospitalization_payload_obj
            
        sp_name_col_actual = actual_headers_map_param.get("Scheduling Provider", "Scheduling Provider")
        sp_name = str(first_row_data.get(sp_name_col_actual, "")).strip()
        if sp_name:
            sp_id_str = get_provider_id_by_name_phase3(client_obj, header_obj, sp_name, practice_id_for_encounter_payload_str, provider_id_cache_param)
            if sp_id_str: encounter_args["SchedulingProvider"] = ProviderIdentifierDetailedReqType(ProviderID=int(sp_id_str))
            else: display_message("warning", f"{row_identifier_log}: Sched Prov '{sp_name}' ID not found. Not adding.")
        
        ce_batch_col_actual = actual_headers_map_param.get("CE Batch #", "CE Batch #")
        ce_batch_num_str = str(first_row_data.get(ce_batch_col_actual, "")).strip()
        if ce_batch_num_str: encounter_args["BatchNumber"] = ce_batch_num_str
        
        encounter_payload = EncounterCreateType(**encounter_args)
        CreateEncounterReqType = client_obj.get_type('ns0:CreateEncounterReq')
        final_request = CreateEncounterReqType(RequestHeader=header_obj, Encounter=encounter_payload)

        display_message("info", f"{row_identifier_log}: Sending CreateEncounter request to Tebra API...")
        api_response_create = client_obj.service.CreateEncounter(request=final_request)

        # --- Process API Response for CreateEncounter ---
        if hasattr(api_response_create, 'ErrorResponse') and api_response_create.ErrorResponse and api_response_create.ErrorResponse.IsError:
            raw_error = api_response_create.ErrorResponse.ErrorMessage
            results['ErrorDetail'] = raw_error; results['SimpleMessage'] = f"Enc API Err: {parse_tebra_xml_error_phase3(raw_error, patient_id_str, dos_str, row_identifier_log)}"
        elif hasattr(api_response_create, 'SecurityResponse') and api_response_create.SecurityResponse and not api_response_create.SecurityResponse.Authorized:
            results['SimpleMessage'] = f"Enc API Auth Err: {api_response_create.SecurityResponse.SecurityResult}"
        elif hasattr(api_response_create, 'EncounterID') and api_response_create.EncounterID is not None and int(api_response_create.EncounterID) > 0:
            created_encounter_id = str(api_response_create.EncounterID); results['EncounterID'] = created_encounter_id
            results['SimpleMessage'] = f"Encounter #{created_encounter_id} Created."
            
            # Optional: Add a small delay before fetching charges, if helpful for data propagation
            # display_message("info", f"{row_identifier_log}: Waiting 5 seconds before fetching details for new Encounter #{created_encounter_id}...")
            # time.sleep(5)

            status_fetch_result = get_encounter_details_phase3(client_obj, header_obj, created_encounter_id, practice_id_for_encounter_payload_str, row_identifier_log)
            status_warning = ""; 
            if status_fetch_result.get('RawEncounterStatusCode') is not None: results['ChargeStatus'] = map_encounter_status_code(status_fetch_result['RawEncounterStatusCode'])
            else: results['ChargeStatus'] = "Status Fetch Error"; status_warning = f" (Status Warn: {status_fetch_result.get('SimpleError', 'Unknown')})"
            if status_warning : results['SimpleMessage'] += status_warning
            
            charge_warning = "";
            # Pass patient_id_str (Tebra PatientID) and collected procedure_codes_for_this_encounter
            charge_fetch_result = get_total_charge_amount_for_encounter_phase3(
                client_obj, header_obj, created_encounter_id,
                patient_id_str, # target_patient_id_str
                practice_name_excel_str, # practice_name_filter_str
                dos_str, # dos_filter_str
                procedure_codes_for_this_encounter, # list_of_procedure_codes_on_encounter
                row_identifier_log
            )
            if charge_fetch_result.get('TotalChargeAmount') not in [None, "Error"]: results['ChargeAmount'] = charge_fetch_result['TotalChargeAmount']
            else: results['ChargeAmount'] = "Charge Fetch Error"; charge_warning = f" (Charge Warn: {charge_fetch_result.get('SimpleError', 'Unknown')})"
            if charge_fetch_result.get('TotalChargeAmount') is None and not charge_fetch_result.get('SimpleError'): results['ChargeAmount'] = "0.00" # Default
            if charge_warning: results['SimpleMessage'] += charge_warning
        else: 
            results['SimpleMessage'] = "Enc creation unclear (EncID -1 or missing)."; 
            results['ErrorDetail'] = zeep.helpers.serialize_object(api_response_create, dict) if client_obj and api_response_create else "No API response."
    except zeep.exceptions.Fault as soap_fault:
        results['SimpleMessage'] = f"Enc SOAP Fault: {str(soap_fault.message)[:100]}..."; results['ErrorDetail'] = str(soap_fault)
    except Exception as e:
        results['SimpleMessage'] = f"Enc System Error: {type(e).__name__}."; results['ErrorDetail'] = str(e)
        display_message("error", f"{row_identifier_log} Exception in _create_encounter_for_group_and_get_details: {traceback.format_exc()}")
    
    log_level_final = "error" if results['ErrorDetail'] or "Error" in results['SimpleMessage'] or "Warn" in results['SimpleMessage'] else "info"
    if not (results['SimpleMessage'].startswith("Enc API Err:") and results['ErrorDetail']): display_message(log_level_final, f"{row_identifier_log}: Group Result: {results['SimpleMessage']}")
    if results['ErrorDetail'] and log_level_final == "error" and not results['SimpleMessage'].startswith("Enc API Err:"): display_message("debug", f"{row_identifier_log} Group Raw Error Detail: {results['ErrorDetail']}")
    return results


def run_all_phases_processing_adapted(df_param, actual_headers_map_param, tebra_client_param, tebra_header_param):
    # (This function is taken directly from your Flask app's user.py, with the P1/P2 loop restored
    #  and ensuring it passes the new referring_provider_cache_param to _create_encounter_for_group_and_get_details)

    # Initialize caches locally for this processing run for thread safety / request isolation
    # This is from your Flask user.py and is a good approach.
    g_practice_id_cache_local = {} 
    g_service_location_id_cache_local = {} 
    g_provider_id_cache_local = {} # For Rendering/Scheduling providers
    g_referring_provider_cache_local = {} # For Referring providers
    g_patient_case_id_cache_local = {} 

    display_message("info", "Local caches initialized for this processing request.")

    if 'original_excel_row_num' not in df_param.columns:
        df_param['original_excel_row_num'] = df_param.index + 2

    output_cols_to_init = {
        "Patient Name": pd.NA, "DOB": pd.NA, "Insurance": pd.NA, "Insurance ID": pd.NA, "Insurance Status": pd.NA,
        "Encounter ID": pd.NA, "Charge Amount": pd.NA, "Charge Status": pd.NA, "Error": "" 
    }
    for logical_col_name, default_val in output_cols_to_init.items():
        actual_col_name = actual_headers_map_param.get(logical_col_name, logical_col_name)
        if actual_col_name not in df_param.columns: df_param[actual_col_name] = default_val
        else: df_param[actual_col_name] = default_val
            
    if '_PaymentID_Temp' not in df_param.columns: df_param['_PaymentID_Temp'] = pd.NA
    else: df_param['_PaymentID_Temp'] = pd.NA

    display_message("info", "--- Running Phases 1 (Patient/Insurance) & 2 (Payment Posting) per row (Adapted for Flask) ---")
    # (Full P1/P2 loop structure from your user.py, ensuring it uses tebra_client_param, tebra_header_param, and local caches)
    for index, row_data in df_param.iterrows():
        current_row_messages = [] 
        payment_id_for_row = pd.NA
        log_prefix_row = f"DF_Row {index} (OrigExcelRow {row_data.get('original_excel_row_num', index+2)})"
        try:
            patient_id_col = actual_headers_map_param.get("Patient ID"); practice_col = actual_headers_map_param.get("Practice"); dos_col = actual_headers_map_param.get("DOS")
            patient_id_str = str(row_data.get(patient_id_col, "")).strip(); practice_name_excel_str = str(row_data.get(practice_col, "")).strip(); dos_for_insurance_str = str(row_data.get(dos_col, "")).strip()
            if not patient_id_str or not practice_name_excel_str:
                msg = "Skipped (Ph1/2): Patient ID or Practice Name missing."; current_row_messages.append(msg)
                df_param.loc[index, actual_headers_map_param.get("Error", "Error")] = "; ".join(filter(None, current_row_messages)).strip('; '); continue
            p1_status_msg = ""; patient_name_output_col = actual_headers_map_param.get("Patient Name", "Patient Name")
            try:
                insurance_results = phase1_fetch_patient_and_insurance(tebra_client_param, tebra_header_param, patient_id_str, practice_name_excel_str, dos_for_insurance_str) # Uses adapted client/header
                
                # Update all relevant DataFrame columns with Phase 1 results
                df_param.loc[index, patient_name_output_col] = insurance_results.get('FetchedPatientName')
                df_param.loc[index, actual_headers_map_param.get("DOB", "DOB")] = insurance_results.get('FetchedPatientDOB')
                df_param.loc[index, actual_headers_map_param.get("Insurance", "Insurance")] = insurance_results.get('FetchedInsuranceName')
                df_param.loc[index, actual_headers_map_param.get("Insurance ID", "Insurance ID")] = insurance_results.get('FetchedInsuranceID')
                df_param.loc[index, actual_headers_map_param.get("Insurance Status", "Insurance Status")] = insurance_results.get('FetchedInsuranceStatus')
                
                if insurance_results.get('SimpleError'): p1_status_msg = f"P1 Error: {insurance_results['SimpleError']}"
                elif insurance_results.get('FetchedInsuranceStatus') not in ["Active", "Active (Primary)", "Multiple Active Found", None, "", "Ins. Check Skipped (No Valid DOS)"]: p1_status_msg = f"P1 Status: {insurance_results.get('FetchedInsuranceStatus', 'Ins status unknown')}"
                if p1_status_msg: current_row_messages.append(p1_status_msg)
            except Exception as e1_proc: p1_status_msg = f"P1 System Error: {e1_proc.__class__.__name__}"; current_row_messages.append(p1_status_msg); display_message("error", f"{log_prefix_row}: {p1_status_msg} - {e1_proc}")
            p2_status_msg = ""
            try:
                pp_batch_col = actual_headers_map_param.get("PP Batch #"); patient_payment_col = actual_headers_map_param.get("Patient Payment"); patient_payment_source_col = actual_headers_map_param.get("Patient Payment Source"); reference_number_col = actual_headers_map_param.get("Reference Number")
                pp_batch_str = str(row_data.get(pp_batch_col, "")).strip(); payment_amount_val_str = str(row_data.get(patient_payment_col, "")).strip(); payment_source_val_str = str(row_data.get(patient_payment_source_col, "")).strip(); payment_ref_num_val_str = str(row_data.get(reference_number_col, "")).strip()
                attempt_payment = False
                if all(val and val.lower() != 'nan' for val in [pp_batch_str, payment_amount_val_str, payment_source_val_str]):
                    try:
                        if float(str(payment_amount_val_str).replace('$', '').replace(',', '').strip()) > 0: attempt_payment = True
                    except ValueError: pass
                if attempt_payment:
                    tebra_practice_id_for_payment = get_practice_id_by_name(tebra_client_param, tebra_header_param, practice_name_excel_str, g_practice_id_cache_local) # Use local cache
                    if tebra_practice_id_for_payment:
                        payment_result = phase2_post_tebra_payment(tebra_client_param, tebra_header_param, patient_id_str, tebra_practice_id_for_payment, practice_name_excel_str, pp_batch_str, payment_amount_val_str, payment_source_val_str, payment_ref_num_val_str)
                        p2_status_msg = payment_result.get('SimpleMessage', 'P2: Pay status unclear.')
                        if payment_result.get('Success'): payment_id_for_row = payment_result.get('PaymentID')
                        if p2_status_msg and not p2_status_msg.startswith("P2 Skipped:"): current_row_messages.append(p2_status_msg)
                    else: p2_status_msg = f"P2 Error: Tebra Practice ID for '{practice_name_excel_str}' (payment) not found."; current_row_messages.append(p2_status_msg)
            except Exception as e2_proc: p2_status_msg = f"P2 System Error: {e2_proc.__class__.__name__}"; current_row_messages.append(p2_status_msg); display_message("error", f"{log_prefix_row}: {p2_status_msg} - {e2_proc}")
            df_param.loc[index, '_PaymentID_Temp'] = payment_id_for_row
            error_col_name = actual_headers_map_param.get('Error', 'Error'); df_param.loc[index, error_col_name] = "; ".join(filter(None, current_row_messages)).strip('; ')
        except Exception as e_outer_row:
            error_col_name = actual_headers_map_param.get('Error', 'Error')
            display_message("critical", f"CRITICAL ERROR processing DF_Row {index} in P1/P2 loop: {e_outer_row}")
            if error_col_name in df_param.columns : df_param.loc[index, error_col_name] = f"Outer Row Proc Err: {e_outer_row.__class__.__name__}"
            else: df_param.loc[index, 'Error'] = f"Outer Row Proc Err: {e_outer_row.__class__.__name__}"

    display_message("info", "--- Phases 1 & 2 row-by-row processing complete. ---")
    display_message("info", "--- Starting Phase 3 (Encounter Creation - Grouped) ---")
    
    # Phase 3 Grouping Logic (from your user.py, ensure it uses adapted client, header and local caches)
    # ... (This is the existing Phase 3 grouping loop structure from your user.py script)
    # The key is that inside this loop, when _create_encounter_for_group_and_get_details is called,
    # it passes tebra_client_param, tebra_header_param, and the local caches.
    patient_id_col = actual_headers_map_param.get("Patient ID"); dos_col = actual_headers_map_param.get("DOS"); practice_excel_col = actual_headers_map_param.get("Practice"); patient_name_col = actual_headers_map_param.get("Patient Name") 
    if not all([patient_id_col, dos_col, practice_excel_col, patient_name_col]): # ... (critical check as before)
        error_msg_critical = "CRITICAL: Key column names for grouping not mapped. Cannot proceed with Phase 3."
        # ... (error handling and return as in your user.py)
        summary_for_critical_failure = {"total_rows": len(df_param), "encounters_created": 0, "payments_posted": 0, "failed_rows": len(df_param), "results": [{"row_number": idx + 2, "practice_name": "", "patient_id": "", "results": error_msg_critical} for idx, row in df_param.iterrows()]}
        return df_param, summary_for_critical_failure

    groupable_df = df_param[df_param[patient_id_col].notna() & (df_param[patient_id_col].astype(str).str.strip()!="") & df_param[dos_col].notna() & (df_param[dos_col].astype(str).str.strip()!="") & df_param[practice_excel_col].notna() & (df_param[practice_excel_col].astype(str).str.strip()!="") & df_param[patient_name_col].notna() & (df_param[patient_name_col].astype(str).str.strip()!="")].copy()
    if groupable_df.empty: display_message("warning", "No rows with valid data for Phase 3 grouping.")
    else:
        groupable_df[dos_col] = groupable_df[dos_col].astype(str)
        grouped_for_encounter = groupable_df.groupby([patient_id_col, dos_col, practice_excel_col], dropna=False)
        display_message("info", f"Found {len(grouped_for_encounter)} groups for encounter creation.")
        group_counter = 0
        for group_keys, group_indices in grouped_for_encounter.groups.items():
            group_counter += 1; patient_id_grp, dos_grp, practice_name_excel_grp = group_keys
            current_group_df_slice = df_param.loc[group_indices]; first_row_of_group = current_group_df_slice.iloc[0]
            patient_full_name_grp = str(first_row_of_group.get(patient_name_col, "")).strip()
            log_prefix_grp = f"EncGrp {group_counter}/{len(grouped_for_encounter)}"
            display_message("info", f"Processing {log_prefix_grp} - PtID: {patient_id_grp}, DOS: {dos_grp}, PracFromExcel: {practice_name_excel_grp} ({len(group_indices)} rows)")
            if not patient_full_name_grp :
                error_msg = "P3 Error: Patient Full Name missing for group."; 
                for idx_in_group in group_indices: df_param.loc[idx_in_group, actual_headers_map_param.get("Error", "Error")] = f"{str(df_param.loc[idx_in_group, actual_headers_map_param.get('Error', 'Error')]).strip('; ')}; {error_msg}".strip('; ')
                continue
            tebra_practice_id_for_enc_payload = get_practice_id_by_name(tebra_client_param, tebra_header_param, practice_name_excel_grp, g_practice_id_cache_local) # Use local cache
            if not tebra_practice_id_for_enc_payload:
                error_msg = f"P3 Error: Tebra Practice ID for '{practice_name_excel_grp}' (enc) not found."; 
                for idx_in_group in group_indices: df_param.loc[idx_in_group, actual_headers_map_param.get("Error", "Error")] = f"{str(df_param.loc[idx_in_group, actual_headers_map_param.get('Error', 'Error')]).strip('; ')}; {error_msg}".strip('; ')
                continue
            
            # CALLING THE MODIFIED FUNCTION
            p3_results = _create_encounter_for_group_and_get_details(
                tebra_client_param, tebra_header_param, group_keys, current_group_df_slice, 
                tebra_practice_id_for_enc_payload, patient_full_name_grp, log_prefix_grp,
                actual_headers_map_param, # Pass the map
                g_service_location_id_cache_local, # Pass local caches
                g_patient_case_id_cache_local,
                g_provider_id_cache_local,
                g_referring_provider_cache_local # Pass new cache
            )
            for idx_in_group in group_indices: # Update group rows...
                df_param.loc[idx_in_group, actual_headers_map_param.get("Encounter ID", "Encounter ID")] = p3_results.get('EncounterID')
                df_param.loc[idx_in_group, actual_headers_map_param.get("Charge Amount", "Charge Amount")] = p3_results.get('ChargeAmount')
                df_param.loc[idx_in_group, actual_headers_map_param.get("Charge Status", "Charge Status")] = p3_results.get('ChargeStatus')
                existing_errors_str = str(df_param.loc[idx_in_group, actual_headers_map_param.get('Error', 'Error')]).strip()
                all_msgs = [m.strip() for m in existing_errors_str.split(';') if m.strip()] if existing_errors_str else []
                p3_simple = p3_results.get('SimpleMessage', "P3 status unknown.")
                if p3_simple:
                    is_created = p3_results.get('EncounterID') and f"Encounter #{p3_results.get('EncounterID')}" in p3_simple
                    has_created = any(f"Encounter #{p3_results.get('EncounterID')}" in m for m in all_msgs if p3_results.get('EncounterID'))
                    if not (is_created and has_created): all_msgs.append(p3_simple.strip())
                df_param.loc[idx_in_group, actual_headers_map_param.get("Error", "Error")] = "; ".join(filter(None, all_msgs)).strip('; ')

    if '_PaymentID_Temp' in df_param.columns: df_param.drop(columns=['_PaymentID_Temp'], inplace=True, errors='ignore')
    display_message("info", "🏁 All phases processing completed.")
    
    # --- Summary Stats (from your user.py) ---
    total_rows = len(df_param)
    enc_id_col_actual = actual_headers_map_param.get("Encounter ID", "Encounter ID")
    encounters_created = df_param[enc_id_col_actual].notna().sum() if enc_id_col_actual in df_param.columns else 0
    error_col_actual = actual_headers_map_param.get("Error", "Error")
    payments_posted_series = df_param[error_col_actual].astype(str).str.contains(r"Payment #\w+ Posted", na=False, regex=True)
    payments_posted = payments_posted_series.sum()
    failed_conditions = (df_param[error_col_actual].astype(str).str.contains("Error|Failed|Skipped", case=False, na=False, regex=True) & \
                        ~df_param[error_col_actual].astype(str).str.contains(r"Encounter #\w+ Created", na=False, regex=True) & \
                        ~payments_posted_series)
    failed_rows = failed_conditions.sum()
    results_for_json = []
    practice_name_col = actual_headers_map_param.get("Practice", "Practice")
    patient_id_col = actual_headers_map_param.get("Patient ID", "Patient ID")
    def clean_for_json(value, default_val=""): # Renamed 'default' to 'default_val'
        if pd.isna(value) or value is None: return None
        return str(value)
    for index_json, row_json in df_param.iterrows():
        results_for_json.append({
            "row_number": clean_for_json(row_json.get('original_excel_row_num'), index_json + 2),
            "practice_name": clean_for_json(row_json.get(practice_name_col, ""), ""),
            "patient_id": clean_for_json(row_json.get(patient_id_col, ""), ""),
            "results": clean_for_json(row_json.get(error_col_actual, "No status"), "No status")
        })
    summary = {
        "total_rows": int(total_rows) if pd.notna(total_rows) else 0,
        "encounters_created": int(encounters_created) if pd.notna(encounters_created) else 0,
        "payments_posted": int(payments_posted) if pd.notna(payments_posted) else 0,
        "failed_rows": int(failed_rows) if pd.notna(failed_rows) else 0,
        "results": results_for_json
    }
    return df_param, summary

# --- Flask Route Handlers (main /api/process and /api/download) ---
# These will use the adapted functions above.
# (The actual @user_bp.route decorators and Flask request/response handling
#  are part of your user.py and should remain, calling these adapted functions.)


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

    escaped_password = escape_xml_special_chars(password) #
    
    credentials = { #
        "CustomerKey": customer_key,
        "User": username,
        "Password": escaped_password
    }

    tebra_client = create_api_client_adapted(TEBRA_WSDL_URL) #
    if not tebra_client:
        return jsonify({"error": "Failed to connect to Tebra API. Check server logs."}), 500

    tebra_header = build_request_header_adapted(credentials, tebra_client) #
    if not tebra_header:
        return jsonify({"error": "Failed to build Tebra API request header. Check credentials and server logs."}), 500
    
    display_message("info", "✅ Tebra API client and header ready.")

    try:
        file_stream = io.BytesIO(file.read())
        df, actual_column_headers_map, validation_errors = validate_spreadsheet_adapted(file_stream, file.filename) #
        file_stream.close() # Close the stream after reading

        if df is None or validation_errors:
            error_message = "File validation failed: " + "; ".join(validation_errors)
            display_message("error", error_message)
            return jsonify({
                "error": error_message, 
                "total_rows": 0, "encounters_created": 0, "payments_posted": 0, "failed_rows": 0,
                "results": [{"row_number": "N/A", "practice_name": "N/A", "patient_id": "N/A", "results": error_message}]
            }), 400
        
        display_message("info", "✅ File validated successfully. DataFrame is ready.") #
        processed_df, summary_stats = run_all_phases_processing_adapted(df, actual_column_headers_map, tebra_client, tebra_header)

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S") #
        base_output_filename = "Processed_Tebra_Data"
        processed_filename_for_server = f"{base_output_filename}_{timestamp}.xlsx" #
        processed_filepath = os.path.join(UPLOAD_FOLDER, processed_filename_for_server)

        if 'original_excel_row_num' in processed_df.columns: #
            # Drop the column before saving as per Colab v2 Part 6
            processed_df_to_save = processed_df.drop(columns=['original_excel_row_num'], errors='ignore') #
        else:
            processed_df_to_save = processed_df
        
        processed_df_to_save.to_excel(processed_filepath, index=False) #
        display_message("info", f"✅ Processed data saved to '{processed_filepath}'") #

        session['processed_file_path'] = processed_filepath
        session['processed_file_download_name'] = f"{base_output_filename}_{datetime.datetime.now().strftime('%Y%m%d')}.xlsx"

        return jsonify(summary_stats), 200

    except zeep.exceptions.Fault as soap_fault: #
        display_message("error", f"SOAP FAULT during processing: {soap_fault.message}")
        if soap_fault.detail is not None:
             display_message("error", f"SOAP Detail: {zeep.helpers.serialize_object(soap_fault.detail)}")
        return jsonify({"error": f"Tebra API SOAP Fault: {soap_fault.message}. Check server logs."}), 500
    except Exception as e:
        display_message("error", f"An error occurred during processing: {e}") #
        display_message("error", f"Stack trace: {traceback.format_exc()}") #
        return jsonify({"error": f"An unexpected error occurred: {str(e)}. Check server logs."}), 500

@user_bp.route('/api/download', methods=['GET'])
def download_file_route():
    processed_filepath = session.get('processed_file_path')
    processed_filename_for_download = session.get('processed_file_download_name', 'Processed_Tebra_Data.xlsx') #

    if not processed_filepath or not os.path.exists(processed_filepath):
        return jsonify({"error": "Processed file not found or path not in session. Please process a file first."}), 404

    try:
        return send_file(processed_filepath, as_attachment=True, download_name=processed_filename_for_download) #
    except Exception as e: #
        display_message("error", f"Error during file download: {e}")
        return jsonify({"error": str(e)}), 500
    # Optional cleanup can be added here if desired, as in the original commented-out block.
